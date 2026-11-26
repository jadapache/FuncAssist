"""Grounded AI runner — assemble context, apply template/rubric, refuse if empty."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.ai.agent import run_agent
from app.ai.artifacts import (
    artifacts_to_dict,
    extract_artifacts,
    has_unclosed_artifact,
    is_artifact_truncated,
)
from app.ai.budget import calculate_input_budget, chars_per_token, count_tokens
from app.ai.errors import AIError
from app.ai.events import AgentEvent
from app.ai.history import format_history_as_messages, prune_or_summarize_history
from app.ai.history_store import ChatSessionSummaryStore
from app.ai.logging import log_ai_call
from app.ai.multimodal import user_message_with_images
from app.ai.map_reduce import map_reduce_condense_context
from app.ai.policies import (
    resolve_feature_max_tokens,
    resolve_intent_max_tokens,
    resolve_max_continuations,
)
from app.ai.providers.base import AICompletion, AIMessage, AIProvider
from app.ai.providers.factory import resolve_provider
from app.ai.injection import begin_report, drain_report, prepare_untrusted, report_message
from app.ai.untrusted import UNTRUSTED_NOTICE
from app.ai.request_types import (
    DocumentFeatureRequest,
    GroundedFeatureRequest,
    SimpleFeatureRequest,
)
from app.ai.section_generator import (
    DocumentPlan,
    generate_sections_stream,
    is_section_generation_candidate,
    plan_document,
)
from app.ai.templates import get_prompt, get_rubric, rubric_to_text
from app.ai.tools.registry import ToolContext
from app.context.models import ContextChunk
from app.context.retrieval import chunks_from_documents
from app.context.service import assemble_context

logger = logging.getLogger(__name__)

GROUNDED_MAX_CONTINUATIONS = 3
CONTINUATION_TAIL_CHARS = 800
TRUNCATION_NOTICE = (
    "La respuesta se cortó por el límite de longitud del modelo. "
    "Escribe «continúa» para que siga desde ese punto."
)
# Usage keys that describe one LLM call and are summed across continuation/section calls.
_SUMMED_USAGE_KEYS = ("prompt_tokens", "completion_tokens", "cached_tokens", "cost_usd")


# ---------------------------------------------------------------------------
# Truncation and continuation (shared by every route)
# ---------------------------------------------------------------------------


def needs_continuation(text: str, finish_reason: str | None) -> bool:
    """The model stopped on its token limit, or the text looks cut (unclosed artifact, dangling heading)."""
    return finish_reason == "length" or is_artifact_truncated(text)


def _continuation_prompt(current_text: str) -> str:
    tail = current_text[-CONTINUATION_TAIL_CHARS:]
    return (
        "ATENCIÓN: Tu generación previa se interrumpió antes de completar todo el documento.\n"
        f"El último fragmento emitido fue exactamente:\n\"\"\"{tail}\"\"\"\n\n"
        "Continúa la redacción EXACTAMENTE en el punto donde se cortó, completando todas las secciones "
        "faltantes sin repetir lo ya emitido ni agregar saludos ni notas introductorias. "
        "Si estabas usando etiquetas <artifact>, ciérralas adecuadamente con </artifact> al terminar."
    )


def _continuation_messages(base_messages: list[AIMessage], current_text: str) -> list[AIMessage]:
    """Full original conversation (context, history, images) + the partial answer + the resume order."""
    return [
        *base_messages,
        AIMessage(role="assistant", content=current_text),
        AIMessage(role="user", content=_continuation_prompt(current_text)),
    ]


def _merge_usage(total: dict[str, Any], part: dict[str, Any]) -> None:
    for key in _SUMMED_USAGE_KEYS:
        value = part.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total[key] = (total.get(key) or 0) + value


async def continue_if_truncated(
    accumulated_text: list[str],
    provider: Any,
    base_messages: list[AIMessage],
    *,
    finish_reason: str | None = None,
    max_tokens: int | None = None,
    max_continuations: int = 2,
    usage_sink: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """Stream continuations while the answer looks truncated, appending them to `accumulated_text`.

    `finish_reason` is the one reported by the call that produced `accumulated_text`. When given,
    `usage_sink` receives the summed usage of the continuation calls plus `finish_reason` (of the
    last call) and `continuations` (how many were made).
    """
    continuations = 0
    current_text = "".join(accumulated_text)
    last_reason = finish_reason

    while needs_continuation(current_text, last_reason) and continuations < max_continuations:
        prev_len = len(current_text)
        continuations += 1
        logger.info(
            "Answer looks truncated (finish_reason=%s); continuation %d/%d", last_reason, continuations, max_continuations,
        )
        call_usage: dict[str, Any] = {}
        async for chunk in provider.complete_stream(
            _continuation_messages(base_messages, current_text), max_tokens=max_tokens, usage_sink=call_usage,
        ):
            accumulated_text.append(chunk)
            yield chunk
        last_reason = call_usage.get("finish_reason")
        if usage_sink is not None:
            _merge_usage(usage_sink, call_usage)
        current_text = "".join(accumulated_text)
        if len(current_text) <= prev_len:
            break

    if usage_sink is not None:
        usage_sink["finish_reason"] = last_reason
        usage_sink["continuations"] = continuations


def _add_completion_usage(total: AICompletion, part: AICompletion) -> None:
    """Add the tokens and cost of a continuation call to the completion being built."""
    for key in ("prompt_tokens", "completion_tokens", "cached_tokens"):
        value = getattr(part, key, None)
        if isinstance(value, int):
            setattr(total, key, (getattr(total, key) or 0) + value)
    if isinstance(part.cost_usd, (int, float)):
        total.cost_usd = (total.cost_usd or 0.0) + part.cost_usd


async def complete_with_continuation(
    provider: Any,
    messages: list[AIMessage],
    *,
    max_tokens: int | None,
    max_continuations: int = GROUNDED_MAX_CONTINUATIONS,
) -> AICompletion:
    """Non-streaming counterpart of `continue_if_truncated`: one completion, continued while truncated."""
    completion = await provider.complete(messages, max_tokens=max_tokens)
    text = completion.text or ""
    reason = completion.finish_reason
    continuations = 0
    while needs_continuation(text, reason) and continuations < max_continuations:
        continuations += 1
        nxt = await provider.complete(_continuation_messages(messages, text), max_tokens=max_tokens)
        _add_completion_usage(completion, nxt)
        if not nxt.text:
            break
        text += nxt.text
        reason = nxt.finish_reason
    completion.text = text
    completion.finish_reason = reason
    return completion


def truncation_tail(text: str) -> str:
    """Text appended when an answer is still truncated after the allowed continuations."""
    if "<artifact" in (text or "").lower():
        closing = "\n</artifact>" if has_unclosed_artifact(text) else ""
        return f"{closing}\n<chat>{TRUNCATION_NOTICE}</chat>"
    return f"\n\n_({TRUNCATION_NOTICE})_"


def error_log_fields(err: BaseException) -> dict[str, Any]:
    if isinstance(err, (asyncio.CancelledError, GeneratorExit)):
        return {"error_code": "cancelled", "error_message": "Cancelado o cliente desconectado"}
    if isinstance(err, AIError):
        detail = err.original_error or err
        return {
            "error_code": err.code,
            "error_message": err.user_message,
            "error_detail": str(detail)[:1000],
        }
    return {"error_code": type(err).__name__, "error_message": str(err)[:1000]}


# ---------------------------------------------------------------------------
# Grounded feature flows
# ---------------------------------------------------------------------------


async def _fit_bundle_to_budget(
    bundle: Any,
    *,
    provider: Any,
    max_output_tokens: int,
    fixed_texts: list[str],
) -> None:
    """Drop the least relevant chunks until the grounded prompt fits the input token budget.

    Chunks are dropped rather than summarized so citation indices `[n]` keep pointing at real
    sources. Uploaded documents sit at the front of the bundle, so they are kept longest.
    """
    model = getattr(provider, "default_model", "") or "gpt-4o"
    budget = await asyncio.to_thread(
        calculate_input_budget, getattr(provider, "id", ""), model, max_output_tokens
    )
    available = budget - sum(count_tokens(model, t) for t in fixed_texts if t)
    dropped = 0
    while len(bundle.chunks) > 1 and count_tokens(model, bundle.to_prompt_block()) > available:
        bundle.chunks.pop()
        dropped += 1
    if dropped:
        logger.info("Grounded context trimmed: dropped %d chunk(s) to fit %d input tokens", dropped, budget)


@dataclass
class _GroundedPrep:
    """Resultado de la fase de preparación del contexto grounded."""
    messages: list[AIMessage]
    bundle: Any          # ContextBundle
    prompt_meta: dict
    rubric_meta: dict
    allowed: list[str]


def _citation(index: int, chunk: ContextChunk) -> dict[str, Any]:
    return {
        "index": index,
        "id": chunk.id,
        "source_type": chunk.source_type.value,
        "source_label": chunk.source_label,
        "title": chunk.title,
    }


def _citations(chunks: list[ContextChunk]) -> list[dict[str, Any]]:
    """One numbered citation per chunk of the context, in the order the model saw them."""
    return [_citation(index, chunk) for index, chunk in enumerate(chunks, start=1)]


def _grounded_log(feature: str, **fields: Any) -> dict[str, Any]:
    """Log one grounded run; it is not a refusal unless the caller says so."""
    return log_ai_call({"feature": feature, "route": "grounded", "refused": False, **fields})


def _refusal(reason: str, bundle: Any = None) -> dict[str, Any]:
    """Answer for a request that is refused without calling the model."""
    refusal: dict[str, Any] = {"ok": False, "refused": True, "reason": reason, "answer": None, "citations": []}
    if bundle is not None:
        refusal["context"] = bundle.model_dump()
    return refusal


async def _load_document_chunks(document_ids: list[str] | None) -> list[ContextChunk]:
    if not document_ids:
        return []
    return await asyncio.to_thread(chunks_from_documents, document_ids)


def _merge_upload_chunks(bundle: Any, upload_chunks: list[ContextChunk]) -> None:
    """Put the uploaded documents' chunks at the front of the bundle, skipping ones already in it."""
    if not upload_chunks:
        return
    if "uploads" not in bundle.used_sources:
        bundle.used_sources.append("uploads")
    existing_ids = {chunk.id for chunk in bundle.chunks}
    for chunk in upload_chunks:
        if chunk.id not in existing_ids:
            bundle.chunks.insert(0, chunk)


def _bundle_refusal(
    feature: str, prompt: dict, rubric: dict, allowed: list[str], bundle: Any
) -> dict[str, Any] | None:
    """Refusal when the context is empty or every requested source is unavailable, else None."""
    if bundle.is_empty:
        missing = ", ".join(bundle.missing_sources) or "no matching context"
        reason = f"Not found in connected sources. Missing/unavailable: {missing}."
        log_ai_call({
            "feature": feature,
            "route": "grounded",
            "refused": True,
            "reason": reason,
            "prompt_version": prompt.get("version"),
            "rubric_version": rubric.get("version"),
            "sources_requested": allowed,
            "sources_used": bundle.used_sources,
            "chunk_ids": [],
        })
        return _refusal(reason, bundle)
    hard_missing = [item for item in bundle.missing_sources if "(" not in item]
    if set(allowed).issubset(set(hard_missing)):
        return _refusal(f"Required sources are not connected: {', '.join(hard_missing)}.", bundle)
    return None


def _prompt_texts(prompt: dict) -> tuple[str, str]:
    """(system text, user template) of a feature prompt; the template defaults to just the context."""
    return str(prompt.get("system") or ""), str(prompt.get("user_template") or "{context}")


def _fill_user_template(
    user_template: str, bundle: Any, rubric_text: str, query: str, chat_block: str, template_text: str
) -> str:
    return user_template.format(
        context=bundle.to_prompt_block(),
        rubric=rubric_text,
        query=query,
        chat_context=chat_block or "(none)",
        template=template_text,
    )


async def _prepare_grounded_context(
    *,
    feature: str,
    query: str,
    sources: list[str] | None,
    document_ids: list[str] | None,
    chat_context: str | None,
    template_content: str | None,
    user_id: str | None = None,
    provider: Any = None,
    max_output_tokens: int | None = None,
) -> _GroundedPrep | dict:
    """Fase de preparación compartida entre run_grounded_feature y run_grounded_feature_stream.

    Retorna un _GroundedPrep listo para llamar al LLM,
    o un dict con refused=True si hay que rechazar sin llamar al LLM.
    """
    if max_output_tokens is None:
        max_output_tokens = resolve_feature_max_tokens(feature)
    # Fetch prompt and rubric concurrently
    prompt, rubric = await asyncio.gather(get_prompt(feature), get_rubric(feature))
    allowed = list(sources or prompt.get("allowed_sources") or [])
    if not allowed:
        return _refusal("Esta funcionalidad no tiene fuentes de conocimiento configuradas.")

    # Fetch context bundle and document chunks concurrently
    bundle, upload_chunks = await asyncio.gather(
        assemble_context(query=query, sources=allowed, user_id=user_id),
        _load_document_chunks(document_ids),
    )
    _merge_upload_chunks(bundle, upload_chunks)

    refusal = _bundle_refusal(feature, prompt, rubric, allowed, bundle)
    if refusal:
        return refusal

    chat_block = (chat_context or "").strip()
    template_text = template_content or ""
    system_text, user_template = _prompt_texts(prompt)
    rubric_text = rubric_to_text(rubric)
    if provider is not None:
        await _fit_bundle_to_budget(
            bundle,
            provider=provider,
            max_output_tokens=max_output_tokens,
            fixed_texts=[system_text, user_template, rubric_text, query, chat_block, template_text],
        )
    user_prompt = _fill_user_template(user_template, bundle, rubric_text, query, chat_block, template_text)

    return _GroundedPrep(
        messages=[AIMessage(role="system", content=system_text), AIMessage(role="user", content=user_prompt)],
        bundle=bundle,
        prompt_meta=prompt,
        rubric_meta=rubric,
        allowed=allowed,
    )


async def run_grounded_feature(
    *,
    feature: str,
    query: str,
    sources: list[str] | None = None,
    document_ids: list[str] | None = None,
    chat_context: str | None = None,
    template_content: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    provider = resolve_provider(user_id=user_id)
    max_tokens = resolve_feature_max_tokens(feature)
    prep = await _prepare_grounded_context(
        feature=feature,
        query=query,
        sources=sources,
        document_ids=document_ids,
        chat_context=chat_context,
        template_content=template_content,
        user_id=user_id,
        provider=provider,
        max_output_tokens=max_tokens,
    )
    if isinstance(prep, dict):  # refused
        return prep

    try:
        completion = await complete_with_continuation(provider, prep.messages, max_tokens=max_tokens)
    except Exception as err:
        _grounded_log(
            feature,
            stage="generate",
            provider=getattr(provider, "id", "unknown"),
            model=getattr(provider, "default_model", "unknown"),
            **error_log_fields(err),
        )
        raise

    citations = _citations(prep.bundle.chunks)

    log = _grounded_log(
        feature,
        prompt_version=prep.prompt_meta.get("version"),
        rubric_version=prep.rubric_meta.get("version"),
        sources_requested=prep.allowed,
        sources_used=prep.bundle.used_sources,
        chunk_ids=[chunk.id for chunk in prep.bundle.chunks],
        provider=completion.provider,
        model=completion.model,
        output=completion.text,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        cached_tokens=completion.cached_tokens,
        cost_usd=completion.cost_usd,
        duration_ms=completion.duration_ms,
        finish_reason=completion.finish_reason,
    )

    parsed_artifacts, clean_answer = extract_artifacts(completion.text)

    return {
        "ok": True,
        "refused": False,
        "reason": None,
        "answer": completion.text,
        "answer_clean": clean_answer,
        "artifacts": artifacts_to_dict(parsed_artifacts),
        "citations": citations,
        "context": prep.bundle.model_dump(),
        "meta": {
            "prompt_version": prep.prompt_meta.get("version"),
            "rubric_version": prep.rubric_meta.get("version"),
            "provider": completion.provider,
            "model": completion.model,
            "log_id": log["id"],
            "artifact_count": len(parsed_artifacts),
        },
    }


async def run_grounded_feature_stream(
    *,
    feature: str,
    query: str,
    sources: list[str] | None = None,
    document_ids: list[str] | None = None,
    chat_context: str | None = None,
    template_content: str | None = None,
    user_id: str | None = None,
):
    """Versión streaming de run_grounded_feature. Yields text chunks via SSE."""
    provider = resolve_provider(user_id=user_id)
    max_tokens = resolve_feature_max_tokens(feature)
    prep = await _prepare_grounded_context(
        feature=feature,
        query=query,
        sources=sources,
        document_ids=document_ids,
        chat_context=chat_context,
        template_content=template_content,
        user_id=user_id,
        provider=provider,
        max_output_tokens=max_tokens,
    )
    if isinstance(prep, dict):  # refused
        reason = prep.get("reason", "Error desconocido al preparar contexto.")
        raise RuntimeError(reason)

    accumulated_text: list[str] = []
    stream_usage: dict[str, Any] = {}
    continuation_usage: dict[str, Any] = {}
    try:
        async for chunk in provider.complete_stream(prep.messages, max_tokens=max_tokens, usage_sink=stream_usage):
            accumulated_text.append(chunk)
            yield chunk

        async with aclosing(continue_if_truncated(
            accumulated_text,
            provider,
            prep.messages,
            finish_reason=stream_usage.get("finish_reason"),
            max_tokens=max_tokens,
            max_continuations=GROUNDED_MAX_CONTINUATIONS,
            usage_sink=continuation_usage,
        )) as continuation:
            async for chunk in continuation:
                yield chunk
    except BaseException as err:
        _grounded_log(
            feature, streamed=True, stage="generate",
            provider=getattr(provider, "id", "unknown"),
            model=getattr(provider, "default_model", "unknown"),
            **error_log_fields(err),
        )
        raise

    usage = {k: v for k, v in stream_usage.items() if k != "tool_calls"}
    _merge_usage(usage, continuation_usage)
    finish_reason = continuation_usage["finish_reason"]
    continuations = continuation_usage["continuations"]
    model = stream_usage.get("model") or getattr(provider, "default_model", "unknown")
    _grounded_log(feature, streamed=True,
        prompt_version=prep.prompt_meta.get("version"),
        rubric_version=prep.rubric_meta.get("version"),
        sources_requested=prep.allowed,
        sources_used=prep.bundle.used_sources,
        chunk_ids=[chunk.id for chunk in prep.bundle.chunks],
        provider=getattr(provider, "id", getattr(provider, "name", "unknown")),
        output="".join(accumulated_text),
        **{**usage, "finish_reason": finish_reason, "continuations": continuations, "model": model},
    )


async def run_simple_feature(request: SimpleFeatureRequest) -> dict[str, Any]:
    """Run feature with only query (no external context sources)."""
    return await run_grounded_feature(
        feature=request.feature,
        query=request.query,
        sources=[],
        document_ids=None,
        chat_context=None,
        user_id=request.user_id,
    )


async def run_document_feature(request: DocumentFeatureRequest) -> dict[str, Any]:
    """Run feature with document analysis."""
    return await run_grounded_feature(
        feature=request.feature,
        query=request.query,
        sources=request.sources or ["knowledge"],
        document_ids=request.document_ids,
        chat_context=None,
        user_id=request.user_id,
    )


async def run_grounded_request(request: GroundedFeatureRequest) -> dict[str, Any]:
    """Run feature with full grounded request."""
    return await run_grounded_feature(
        feature=request.feature,
        query=request.query,
        sources=request.sources,
        document_ids=request.document_ids,
        chat_context=request.chat_context,
        template_content=request.template_content,
        user_id=request.user_id,
    )


# ---------------------------------------------------------------------------
# Agentic chat
# ---------------------------------------------------------------------------


@dataclass
class AgenticChatConfig:
    query: str
    intent: str = "chat"
    feature: str = "mejoras_doc"
    sources: list[str] | None = None
    document_ids: list[str] | None = None
    chat_context: str | None = None
    history: list[dict[str, Any]] | None = None
    conversation_id: str | None = None
    template_content: str | None = None
    template_extension: str | None = "docx"
    images: list[dict[str, str]] | None = None
    attached_docs: list[dict[str, Any]] | None = None
    user_id: str | None = None
    provider: str | None = None
    model: str | None = None
    # Filled by the runner while it works: route, stage, provider, model, truncated, logged...
    # The caller reads it to report failures and to tell the user about truncation.
    run_info: dict[str, Any] = field(default_factory=dict)


HISTORY_MIN_TOKENS = 1_000
HISTORY_MAX_TOKENS = 6_000
DOCS_MIN_TOKENS = 1_000
IMAGE_TOKEN_ESTIMATE = 1_200  # rough per-image cost on vision models

_ARTIFACT_INTENTS = frozenset({"generic_plan", "generic_report", "template_mutation"})


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("true", "1", "on", "yes")


def _format_rule_for_intent(intent: str, extension: str | None = "docx") -> str:
    ext = (extension or "docx").strip().lstrip(".").lower()
    if intent in _ARTIFACT_INTENTS:
        return (
            "\n\n## REGLA DE FORMATO OBLIGATORIA (GENERACIÓN DE ARTEFACTO)\n"
            "La solicitud exige generar un documento o artefacto formal. DEBES respetar estrictamente esta estructura:\n"
            "1. Mensaje ejecutivo breve para el chat dentro de etiquetas <chat>...</chat>.\n"
            f"2. El documento completo y estructurado dentro de etiquetas <artifact title=\"[Título del Documento]\" extension=\"{ext}\">...</artifact>.\n"
            "3. NUNCA coloques el contenido completo del documento fuera del bloque <artifact>.\n"
            "4. NO omitas el bloque <chat> inicial (debe ser una síntesis o presentación de 1 o 2 párrafos).\n"
            "Ejemplo de salida esperada:\n"
            "<chat>He elaborado el documento correspondiente con base en los lineamientos solicitados.</chat>\n"
            f"<artifact title=\"Plan de Pruebas\" extension=\"{ext}\">\n"
            "# 1. Objetivo\n...\n"
            "</artifact>"
        )
    return (
        "\n\n## REGLA DE FORMATO (RESPUESTA CONVERSACIONAL)\n"
        "La solicitud es de tipo consulta o conversacional. DEBES responder directamente en formato Markdown estándar en la burbuja de chat. "
        "NO utilices etiquetas <artifact> ni <chat> a menos que se haya solicitado explícitamente generar un documento descargable."
    )


# Every prompt that can receive external content tells the model how to treat it (see app.ai.untrusted).
_UNTRUSTED_SUFFIX = "\n\n" + UNTRUSTED_NOTICE


async def _build_base_system_prompt(intent: str, feature: str | None = None) -> str:
    """System prompt without the output-format rule (sections add their own instructions)."""
    target_feature = intent if intent and intent != "chat" else (feature or "chat")
    try:
        tmpl = await get_prompt(target_feature)
        if (tmpl or {}).get("system"):
            return tmpl["system"] + _UNTRUSTED_SUFFIX
    except Exception as exc:
        logger.info("No prompt template for %s (%s); using the default system prompt", target_feature, exc)

    return (
        "Eres un asistente experto en Aseguramiento de Calidad (QA), Gestión de Requerimientos y Arquitectura de Software. "
        "Responde con claridad, didáctica y precisión técnica utilizando formato Markdown enriquecido. "
        "Utiliza el contexto de los documentos cargados, historial de chat y las imágenes adjuntas cuando estén presentes."
        + _UNTRUSTED_SUFFIX
    )


async def _build_chat_system_prompt(intent: str, feature: str | None = None, template_extension: str | None = "docx") -> str:
    base = await _build_base_system_prompt(intent, feature)
    return base + _format_rule_for_intent(intent, template_extension)


def _assemble_multimodal_message(text_prompt: str, images: list[dict[str, str]] | None) -> AIMessage:
    return user_message_with_images(text_prompt, images)


class _FastProviderResolver:
    """Resolve the fast-tier provider at most once per request, falling back to the main provider."""

    def __init__(self, cfg: AgenticChatConfig, main_provider: AIProvider) -> None:
        self._cfg = cfg
        self._main = main_provider
        self._resolved: AIProvider | None = None

    async def get(self) -> AIProvider:
        if self._resolved is None:
            try:
                self._resolved = await asyncio.to_thread(
                    resolve_provider,
                    provider_name=self._cfg.provider,
                    user_id=self._cfg.user_id,
                    tier="fast",
                    main_model=getattr(self._main, "default_model", None),
                )
            except ValueError as exc:
                logger.warning("Fast model tier unavailable (%s); using the main model", exc)
                self._resolved = self._main
            self._cfg.run_info["fast_model"] = getattr(self._resolved, "default_model", None)
        return self._resolved


@dataclass
class _ChatPrep:
    provider: AIProvider
    fast: _FastProviderResolver
    base_prompt: str
    sys_prompt: str
    messages: list[AIMessage]
    history: list[AIMessage]
    context_docs_text: str
    used_sources: list[str]
    input_budget: int
    out_tokens: int
    allowed: list[str]


async def _assemble_bundle(cfg: AgenticChatConfig, allowed: list[str]) -> Any:
    if not allowed:
        return None
    return await assemble_context(query=cfg.query, sources=allowed, user_id=cfg.user_id)


async def _resolve_main_provider(cfg: AgenticChatConfig) -> AIProvider:
    return await asyncio.to_thread(
        resolve_provider, provider_name=cfg.provider, model_name=cfg.model, user_id=cfg.user_id,
    )


def _append_context_parts(text: str, used_sources: list[str], parts: list[str], source: str) -> str:
    """Append `parts` to the context text and record `source`; unchanged when there are no parts."""
    if not parts:
        return text
    if source not in used_sources:
        used_sources.append(source)
    return (f"{text}\n\n" + "\n\n".join(parts)).strip()


def _upload_part(index: int, chunk: ContextChunk) -> str:
    body = prepare_untrusted("upload", chunk.source_label, f"{chunk.title}\n{chunk.text}", max_chars=None)
    return f"[{index + 1}] " + body


def _attachment_part(doc: dict[str, Any]) -> str:
    return prepare_untrusted("adjunto", doc.get("filename", "documento"), doc.get("content", ""), max_chars=None)


def _collect_context(
    bundle: Any, upload_chunks: list[ContextChunk], attached_docs: list[dict[str, Any]] | None
) -> tuple[str, list[str]]:
    """Context text (retrieved sources, uploads, chat attachments) and the names of the sources used.

    Uploads and attachments are external content, so each part is delimited as untrusted data.
    """
    has_bundle = bool(bundle and not bundle.is_empty)
    text = bundle.to_prompt_block() if has_bundle else ""
    used_sources = list(bundle.used_sources) if has_bundle else []
    upload_parts = [_upload_part(i, chunk) for i, chunk in enumerate(upload_chunks)]
    text = _append_context_parts(text, used_sources, upload_parts, "uploads")
    attachments = [doc for doc in attached_docs or [] if doc.get("content")]
    attachment_parts = [_attachment_part(doc) for doc in attachments]
    return _append_context_parts(text, used_sources, attachment_parts, "chat_attachments"), used_sources


@dataclass
class _Budgets:
    """Token budgets of one chat request."""

    model: str
    input_tokens: int
    output_tokens: int
    history_tokens: int
    docs_tokens: int


async def _chat_budgets(cfg: AgenticChatConfig, provider: AIProvider, sys_prompt: str) -> _Budgets:
    """What the model can take in this request once the answer is reserved, split between parts."""
    model = getattr(provider, "default_model", "") or "gpt-4o"
    out_tokens = resolve_intent_max_tokens(cfg.intent)
    input_budget = await asyncio.to_thread(calculate_input_budget, getattr(provider, "id", ""), model, out_tokens)
    history_budget = min(HISTORY_MAX_TOKENS, max(HISTORY_MIN_TOKENS, input_budget // 4))
    template_tokens = count_tokens(model, cfg.template_content or "") if cfg.intent == "template_mutation" else 0
    prompt_tokens = count_tokens(model, sys_prompt) + count_tokens(model, cfg.query)
    image_tokens = IMAGE_TOKEN_ESTIMATE * len(cfg.images or [])
    fixed_tokens = prompt_tokens + template_tokens + image_tokens
    # History is reserved up front so documents never starve the conversation.
    docs_budget = max(DOCS_MIN_TOKENS, input_budget - fixed_tokens - history_budget)
    return _Budgets(model, input_budget, out_tokens, history_budget, docs_budget)


async def _condense_context(
    cfg: AgenticChatConfig, text: str, budgets: _Budgets, fast: _FastProviderResolver
) -> str:
    """Summarize the documents with the fast model when they do not fit their token budget."""
    if not text or count_tokens(budgets.model, text) <= budgets.docs_tokens:
        return text
    cfg.run_info["stage"] = "condense"
    # map_reduce works in characters: translate with the measured chars/token ratio.
    target_chars = int(budgets.docs_tokens * chars_per_token(budgets.model, text))
    condensed = await map_reduce_condense_context(
        text,
        target_budget=target_chars,
        provider=await fast.get(),
        feature_goal=f"Contexto relevante para {cfg.intent}",
    )
    cfg.run_info["context_condensed"] = True
    return condensed


def _documents_message(cfg: AgenticChatConfig, context_docs_text: str) -> str:
    """Second system message: work mode, documents and corporate template; empty when none applies."""
    sections = []
    if cfg.intent in _ARTIFACT_INTENTS:
        ext_label = (cfg.template_extension or "docx").upper()
        sections.append(
            f"[MODO DE TRABAJO: GENERACIÓN DE ARTEFACTO (Formato {ext_label})]\n"
            "Debes separar la respuesta: un mensaje breve en <chat>...</chat> y el documento completo en <artifact>...</artifact>."
        )
    if context_docs_text:
        sections.append(f"DOCUMENTOS Y CONTEXTO DISPONIBLE:\n{context_docs_text}")
    if cfg.template_content and cfg.intent == "template_mutation":
        sections.append(f"PLANTILLA CORPORATIVA:\n{cfg.template_content}")
    return "\n\n".join(sections)


async def _prepare_history(
    cfg: AgenticChatConfig, budgets: _Budgets, fast: _FastProviderResolver
) -> list[AIMessage]:
    """Previous turns kept verbatim within budget, older ones replaced by a rolling summary."""
    raw_history = format_history_as_messages(cfg.history if cfg.history else cfg.chat_context)
    if not raw_history:
        return []
    cfg.run_info["stage"] = "history"
    return await prune_or_summarize_history(
        raw_history,
        max_tokens_budget=budgets.history_tokens,
        model=budgets.model,
        fast_provider=await fast.get(),
        scope=cfg.conversation_id or cfg.user_id,
        store=ChatSessionSummaryStore(cfg.conversation_id, cfg.user_id) if cfg.conversation_id else None,
    )


async def _prepare_chat(cfg: AgenticChatConfig) -> _ChatPrep:
    """Gather context, fit it to the token budget and assemble the conversation for any route."""
    allowed = list(cfg.sources or [])
    bundle, upload_chunks, base_prompt, provider = await asyncio.gather(
        _assemble_bundle(cfg, allowed),
        _load_document_chunks(cfg.document_ids),
        _build_base_system_prompt(cfg.intent, cfg.feature),
        _resolve_main_provider(cfg),
    )
    sys_prompt = base_prompt + _format_rule_for_intent(cfg.intent, cfg.template_extension)
    cfg.run_info["provider"] = getattr(provider, "id", "unknown")
    cfg.run_info["model"] = getattr(provider, "default_model", "unknown")
    fast = _FastProviderResolver(cfg, provider)

    context_docs_text, used_sources = _collect_context(bundle, upload_chunks, cfg.attached_docs)
    budgets = await _chat_budgets(cfg, provider, sys_prompt)
    context_docs_text = await _condense_context(cfg, context_docs_text, budgets, fast)

    # Cache-friendly ordering: 1) System, 2) Documents & templates, 3) Chat History, 4) Current Query
    messages: list[AIMessage] = [AIMessage(role="system", content=sys_prompt)]
    documents_message = _documents_message(cfg, context_docs_text)
    if documents_message:
        messages.append(AIMessage(role="system", content=documents_message))
    clean_history = await _prepare_history(cfg, budgets, fast)
    messages.extend(clean_history)
    messages.append(_assemble_multimodal_message(cfg.query, cfg.images))

    return _ChatPrep(
        provider=provider,
        fast=fast,
        base_prompt=base_prompt,
        sys_prompt=sys_prompt,
        messages=messages,
        history=clean_history,
        context_docs_text=context_docs_text,
        used_sources=used_sources,
        input_budget=budgets.input_tokens,
        out_tokens=budgets.output_tokens,
        allowed=allowed,
    )


def _log_entry(
    cfg: AgenticChatConfig, prep: _ChatPrep | None, output: str, usage: dict[str, Any] | None, extra: dict[str, Any]
) -> dict[str, Any]:
    """The log entry of a chat request, from what the runner recorded in `cfg.run_info`."""
    info = cfg.run_info
    clean_usage = {k: v for k, v in (usage or {}).items() if k != "tool_calls"}
    always = {"refused": False, "streamed": True}
    model = clean_usage.get("model") or info.get("model", "unknown")
    entry: dict[str, Any] = {
        "feature": cfg.feature,
        **always,
        "intent": cfg.intent,
        "route": info.get("route"),
        "conversation_id": cfg.conversation_id,
        "sources_used": prep.used_sources if prep else [],
        "provider": info.get("provider", "unknown"),
        "output": output,
        "input_budget_tokens": prep.input_budget if prep else None,
        "fast_model": info.get("fast_model"),
        # Set by the endpoint: SSE protocol (to know when v1 can be retired) and how the intent
        # was decided (rules / model / model_cache).
        "protocol": info.get("protocol"),
        "intent_source": info.get("intent_source"),
        **clean_usage,
        **extra,
        "model": model,
    }
    if info.get("section_plan_failed"):
        entry["section_plan_failed"] = True
    entry.update({key: info[key] for key in ("intent_rules", "intent_classifier_ms") if key in info})
    return entry


def _log_chat(
    cfg: AgenticChatConfig,
    prep: _ChatPrep | None,
    *,
    output: str = "",
    usage: dict[str, Any] | None = None,
    error: BaseException | None = None,
    **extra: Any,
) -> None:
    """One log entry per chat request, whatever its route and outcome."""
    if cfg.run_info.get("logged"):
        return
    entry = _log_entry(cfg, prep, output, usage, extra)
    if error is not None:
        entry["stage"] = cfg.run_info.get("stage")
        entry.update(error_log_fields(error))
    log_ai_call(entry)
    cfg.run_info["logged"] = True


def _usage_event(usage: dict[str, Any], route: str) -> AgentEvent:
    keys = (
        "prompt_tokens", "completion_tokens", "cached_tokens", "cost_usd", "ttft_ms", "duration_ms",
        "model", "fallback_used", "finish_reason", "continuations", "llm_calls", "iterations",
    )
    return AgentEvent(type="usage", data={"route": route, **{k: usage.get(k) for k in keys if k in usage}})


async def _agent_route(cfg: AgenticChatConfig, prep: _ChatPrep) -> AsyncIterator[str | AgentEvent]:
    cfg.run_info.update(route="agent", stage="agent")
    document_ids = list(cfg.document_ids or [])
    tool_ctx = ToolContext(user_id=cfg.user_id, allowed_sources=prep.allowed, allowed_document_ids=document_ids)
    output: list[str] = []
    usage: dict[str, Any] = {}
    t0 = time.perf_counter()
    async with aclosing(run_agent(
        messages=prep.messages,
        provider=prep.provider,
        ctx=tool_ctx,
        max_iters=int(os.getenv("AI_AGENT_MAX_ITERS", "8")),
        max_tokens=prep.out_tokens,
    )) as events:
        async for ev in events:
            if ev.type == "delta":
                text = ev.data.get("text", "")
                output.append(text)
                yield text
            elif ev.type == "artifact_start":
                ext = ev.data.get("extension", "docx")
                text = f'\n<artifact title="{ev.data.get("title", "Documento")}" extension="{ext}">\n'
                output.append(text)
                yield text
            elif ev.type == "artifact_delta":
                text = ev.data.get("text", "")
                output.append(text)
                yield text
            elif ev.type == "artifact_end":
                output.append("\n</artifact>\n")
                yield "\n</artifact>\n"
            elif ev.type == "done":
                break
            else:
                if ev.type == "usage":
                    usage = dict(ev.data)
                    usage["duration_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
                    ev = _usage_event(usage, "agent")
                # status / tool_call / tool_result / usage: typed events for SSE consumers.
                yield ev

    _log_chat(cfg, prep, output="".join(output), usage=usage, agent_mode=True, artifacts_created=len(tool_ctx.artifacts))


async def _sections_route(
    cfg: AgenticChatConfig, prep: _ChatPrep, plan: DocumentPlan, plan_usage: dict[str, Any],
) -> AsyncIterator[str | AgentEvent]:
    cfg.run_info.update(route="sections", stage="sections", sections=len(plan.sections))
    yield AgentEvent(
        type="status",
        data={"message": f"Redactando {len(plan.sections)} secciones...", "stage": "sections"},
    )
    output: list[str] = []
    usage: dict[str, Any] = dict(plan_usage)
    t0 = time.perf_counter()
    async with aclosing(generate_sections_stream(
        plan=plan,
        system_prompt=prep.base_prompt,
        context_block=prep.context_docs_text,
        main_provider=prep.provider,
        history=prep.history,
        images=cfg.images,
        usage_sink=usage,
    )) as stream:
        async for item in stream:
            if isinstance(item, str):
                output.append(item)
            yield item

    usage["duration_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    yield _usage_event(usage, "sections")
    failed_sections = usage.get("failed_sections") or []
    _log_chat(cfg, prep, output="".join(output), usage=usage, sections=len(plan.sections), failed_sections=failed_sections)


async def _plain_route(cfg: AgenticChatConfig, prep: _ChatPrep) -> AsyncIterator[str | AgentEvent]:
    cfg.run_info.update(route="plain", stage="generate")
    yield AgentEvent(type="status", data={"message": "Generando respuesta...", "stage": "generate"})
    provider = prep.provider
    accumulated: list[str] = []
    usage: dict[str, Any] = {}

    async for chunk in provider.complete_stream(prep.messages, max_tokens=prep.out_tokens, usage_sink=usage):
        accumulated.append(chunk)
        yield chunk

    continuation_usage: dict[str, Any] = {}
    cfg.run_info["stage"] = "continue"
    async with aclosing(continue_if_truncated(
        accumulated,
        provider,
        prep.messages,
        finish_reason=usage.get("finish_reason"),
        max_tokens=prep.out_tokens,
        max_continuations=resolve_max_continuations(cfg.intent),
        usage_sink=continuation_usage,
    )) as continuation:
        async for chunk in continuation:
            yield chunk

    final_reason = continuation_usage["finish_reason"]
    continuations = continuation_usage["continuations"]
    full_output = "".join(accumulated)
    truncated = final_reason == "length" or has_unclosed_artifact(full_output)
    if truncated:
        logger.warning(
            "Answer still truncated after %s continuation(s) (intent=%s, model=%s)",
            continuations, cfg.intent, usage.get("model"),
        )
        tail = truncation_tail(full_output)
        accumulated.append(tail)
        cfg.run_info["truncated"] = True
        yield tail

    merged = dict(usage)
    _merge_usage(merged, continuation_usage)
    merged["finish_reason"] = final_reason
    merged["continuations"] = continuations
    yield _usage_event(merged, "plain")
    _log_chat(cfg, prep, output="".join(accumulated), usage=merged, truncated=truncated)


def _supports_agent(provider: AIProvider) -> bool:
    checker = getattr(provider, "supports_tools", None)
    if not callable(checker):
        return False
    try:
        return bool(checker())
    except Exception as exc:
        logger.warning("Could not determine tool support for %s: %s", getattr(provider, "default_model", "?"), exc)
        return False


def _agent_route_if_selected(cfg: AgenticChatConfig, prep: _ChatPrep) -> AsyncIterator[str | AgentEvent] | None:
    """The agent route when AI_AGENT_MODE is on and the model supports tool calling, else None."""
    if not _flag("AI_AGENT_MODE", "false"):
        return None
    if _supports_agent(prep.provider):
        return _agent_route(cfg, prep)
    cfg.run_info["agent_unsupported"] = True
    logger.info("Agent mode on but %s has no tool calling; using the normal route", cfg.run_info.get("model"))
    return None


def _wants_sections(cfg: AgenticChatConfig) -> bool:
    return _flag("AI_SECTION_GENERATION", "true") and is_section_generation_candidate(cfg.intent, cfg.query)


async def _sections_route_if_planned(
    cfg: AgenticChatConfig, prep: _ChatPrep
) -> AsyncIterator[str | AgentEvent] | None:
    """The sections route when the fast model produced a section plan, else None."""
    plan, plan_usage = await _plan_sections(cfg, prep)
    return _sections_route(cfg, prep, plan, plan_usage) if plan else None


async def _plan_sections(cfg: AgenticChatConfig, prep: _ChatPrep) -> tuple[DocumentPlan | None, dict[str, Any]]:
    """Section plan made with the fast model, and the usage it took; None when it has no sections."""
    plan_usage: dict[str, Any] = {}
    extension = cfg.template_extension or "docx"
    plan = await plan_document(
        query=cfg.query,
        context_summary=prep.context_docs_text,
        template_extension=extension,
        provider=await prep.fast.get(),
        history=prep.history,
        usage_sink=plan_usage,
    )
    if plan and plan.sections:
        return plan, plan_usage
    cfg.run_info["section_plan_failed"] = True
    logger.warning("No section plan for intent %s; falling back to the plain route", cfg.intent)
    return None, plan_usage


async def run_agentic_chat_stream(cfg: AgenticChatConfig) -> AsyncIterator[str | AgentEvent]:
    """Streaming runner for dynamic multimodal chat, generic artifacts, or direct Q&A.

    Yields text chunks (the raw answer, including `<chat>`/`<artifact>` markup) and typed
    `AgentEvent`s (status, plan, tool_call, tool_result, usage). Routes:
    - agent: AI_AGENT_MODE on and the model supports tool calling;
    - sections: document intents, when a section plan can be produced;
    - plain: a single streamed completion, continued if truncated.
    Every request leaves exactly one AI log entry, including failures and cancellations.
    """
    info = cfg.run_info
    info["stage"] = "context"
    prep: _ChatPrep | None = None
    try:
        yield AgentEvent(type="status", data={"message": "Preparando contexto...", "stage": "context"})
        begin_report()
        prep = await _prepare_chat(cfg)
        omitted = drain_report()
        if omitted:
            info["injection_detected"] = omitted
            yield AgentEvent(type="status", data={"message": report_message(omitted), "stage": "security"})

        route = _agent_route_if_selected(cfg, prep)
        if route is None and _wants_sections(cfg):
            info["stage"] = "plan"
            yield AgentEvent(type="status", data={"message": "Planificando el documento...", "stage": "plan"})
            route = await _sections_route_if_planned(cfg, prep)

        async with aclosing(route or _plain_route(cfg, prep)) as items:
            async for item in items:
                yield item
    except (asyncio.CancelledError, GeneratorExit) as err:
        _log_chat(cfg, prep, error=err)
        raise
    except Exception as err:
        logger.warning(
            "Chat run failed (route=%s, stage=%s): %s", info.get("route"), info.get("stage"), err, exc_info=True,
        )
        _log_chat(cfg, prep, error=err)
        raise
