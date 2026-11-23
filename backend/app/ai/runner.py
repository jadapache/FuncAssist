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
from app.ai.map_reduce import map_reduce_condense_context
from app.ai.policies import (
    resolve_feature_max_tokens,
    resolve_intent_max_tokens,
    resolve_max_continuations,
)
from app.ai.providers.base import AICompletion, AIMessage, AIProvider
from app.ai.providers.factory import resolve_provider
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
        produced = False
        async for chunk in provider.complete_stream(
            _continuation_messages(base_messages, current_text), max_tokens=max_tokens, usage_sink=call_usage,
        ):
            accumulated_text.append(chunk)
            produced = True
            yield chunk
        last_reason = call_usage.get("finish_reason")
        if usage_sink is not None:
            _merge_usage(usage_sink, call_usage)
        current_text = "".join(accumulated_text)
        if not produced or len(current_text) <= prev_len:
            break

    if usage_sink is not None:
        usage_sink["finish_reason"] = last_reason
        usage_sink["continuations"] = continuations


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
        prev_len = len(text)
        continuations += 1
        nxt = await provider.complete(_continuation_messages(messages, text), max_tokens=max_tokens)
        for key in ("prompt_tokens", "completion_tokens", "cached_tokens"):
            extra_value = getattr(nxt, key, None)
            if isinstance(extra_value, int):
                setattr(completion, key, (getattr(completion, key) or 0) + extra_value)
        if isinstance(nxt.cost_usd, (int, float)):
            completion.cost_usd = (completion.cost_usd or 0.0) + nxt.cost_usd
        if not nxt.text:
            break
        text += nxt.text
        reason = nxt.finish_reason
        if len(text) <= prev_len:
            break
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
    prompt, rubric = await asyncio.gather(
        get_prompt(feature),
        get_rubric(feature),
    )
    allowed = list(sources or prompt.get("allowed_sources") or [])

    if not allowed:
        return {
            "ok": False,
            "refused": True,
            "reason": "Esta funcionalidad no tiene fuentes de conocimiento configuradas.",
            "answer": None,
            "citations": [],
        }

    # Fetch context bundle and document chunks concurrently
    async def _fetch_chunks():
        if document_ids:
            return await asyncio.to_thread(chunks_from_documents, document_ids)
        return []

    bundle, upload_chunks = await asyncio.gather(
        assemble_context(query=query, sources=allowed, user_id=user_id),
        _fetch_chunks(),
    )

    if upload_chunks:
        if "uploads" not in bundle.used_sources:
            bundle.used_sources.append("uploads")
        existing_ids = {chunk.id for chunk in bundle.chunks}
        for chunk in upload_chunks:
            if chunk.id not in existing_ids:
                bundle.chunks.insert(0, chunk)

    chat_block = (chat_context or "").strip()

    if bundle.is_empty:
        reason = (
            "Not found in connected sources. "
            f"Missing/unavailable: {', '.join(bundle.missing_sources) or 'no matching context'}."
        )
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
        return {
            "ok": False,
            "refused": True,
            "reason": reason,
            "answer": None,
            "citations": [],
            "context": bundle.model_dump(),
        }

    hard_missing = [item for item in bundle.missing_sources if "(" not in item]
    if set(allowed).issubset(set(hard_missing)):
        reason = f"Required sources are not connected: {', '.join(hard_missing)}."
        return {
            "ok": False,
            "refused": True,
            "reason": reason,
            "answer": None,
            "citations": [],
            "context": bundle.model_dump(),
        }

    user_template = str(prompt.get("user_template") or "{context}")
    rubric_text = rubric_to_text(rubric)
    system_text = str(prompt.get("system") or "")
    if provider is not None:
        await _fit_bundle_to_budget(
            bundle,
            provider=provider,
            max_output_tokens=max_output_tokens,
            fixed_texts=[system_text, user_template, rubric_text, query, chat_block, template_content or ""],
        )
    format_kwargs = {
        "context": bundle.to_prompt_block(),
        "rubric": rubric_text,
        "query": query,
        "chat_context": chat_block or "(none)",
        "template": template_content or "",
    }
    if "{chat_context}" not in user_template:
        format_kwargs.pop("chat_context", None)
    if "{template}" not in user_template:
        format_kwargs.pop("template", None)

    user_prompt = user_template.format(**format_kwargs)
    messages = [
        AIMessage(role="system", content=system_text),
        AIMessage(role="user", content=user_prompt),
    ]

    return _GroundedPrep(
        messages=messages,
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
        log_ai_call({
            "feature": feature,
            "route": "grounded",
            "refused": False,
            "stage": "generate",
            "provider": getattr(provider, "id", "unknown"),
            "model": getattr(provider, "default_model", "unknown"),
            **error_log_fields(err),
        })
        raise

    citations = [
        {
            "index": index,
            "id": chunk.id,
            "source_type": chunk.source_type.value,
            "source_label": chunk.source_label,
            "title": chunk.title,
        }
        for index, chunk in enumerate(prep.bundle.chunks, start=1)
    ]

    log = log_ai_call({
        "feature": feature,
        "route": "grounded",
        "refused": False,
        "prompt_version": prep.prompt_meta.get("version"),
        "rubric_version": prep.rubric_meta.get("version"),
        "sources_requested": prep.allowed,
        "sources_used": prep.bundle.used_sources,
        "chunk_ids": [chunk.id for chunk in prep.bundle.chunks],
        "provider": completion.provider,
        "model": completion.model,
        "output": completion.text,
        "prompt_tokens": completion.prompt_tokens,
        "completion_tokens": completion.completion_tokens,
        "cached_tokens": completion.cached_tokens,
        "cost_usd": completion.cost_usd,
        "duration_ms": completion.duration_ms,
        "finish_reason": completion.finish_reason,
    })

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
        log_ai_call({
            "feature": feature,
            "route": "grounded",
            "refused": False,
            "streamed": True,
            "stage": "generate",
            "provider": getattr(provider, "id", "unknown"),
            "model": getattr(provider, "default_model", "unknown"),
            **error_log_fields(err),
        })
        raise

    usage = {k: v for k, v in stream_usage.items() if k != "tool_calls"}
    _merge_usage(usage, continuation_usage)
    log_ai_call({
        "feature": feature,
        "route": "grounded",
        "refused": False,
        "prompt_version": prep.prompt_meta.get("version"),
        "rubric_version": prep.rubric_meta.get("version"),
        "sources_requested": prep.allowed,
        "sources_used": prep.bundle.used_sources,
        "chunk_ids": [chunk.id for chunk in prep.bundle.chunks],
        "provider": getattr(provider, "id", getattr(provider, "name", "unknown")),
        "output": "".join(accumulated_text),
        "streamed": True,
        **usage,
        "finish_reason": continuation_usage.get("finish_reason", stream_usage.get("finish_reason")),
        "continuations": continuation_usage.get("continuations", 0),
        "model": stream_usage.get("model") or getattr(provider, "default_model", "unknown"),
    })


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


def _format_rule_for_intent(intent: str, extension: str = "docx") -> str:
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


async def _build_base_system_prompt(intent: str, feature: str | None = None) -> str:
    """System prompt without the output-format rule (sections add their own instructions)."""
    target_feature = intent if intent and intent != "chat" else (feature or "chat")
    try:
        tmpl = await get_prompt(target_feature)
        if tmpl and tmpl.get("system"):
            return tmpl["system"]
    except Exception as exc:
        logger.info("No prompt template for %s (%s); using the default system prompt", target_feature, exc)

    return (
        "Eres un asistente experto en Aseguramiento de Calidad (QA), Gestión de Requerimientos y Arquitectura de Software. "
        "Responde con claridad, didáctica y precisión técnica utilizando formato Markdown enriquecido. "
        "Utiliza el contexto de los documentos cargados, historial de chat y las imágenes adjuntas cuando estén presentes."
    )


async def _build_chat_system_prompt(intent: str, feature: str | None = None, template_extension: str | None = "docx") -> str:
    base = await _build_base_system_prompt(intent, feature)
    return base + _format_rule_for_intent(intent, template_extension or "docx")


def _assemble_multimodal_message(text_prompt: str, images: list[dict[str, str]] | None) -> AIMessage:
    if not images:
        return AIMessage(role="user", content=text_prompt)

    parts: list[dict[str, Any]] = [{"type": "text", "text": text_prompt}]
    for img in images:
        data_url = img.get("data") or img.get("dataUrl") or ""
        if not data_url.startswith("data:"):
            mime = img.get("mime_type") or img.get("type") or "image/png"
            data_url = f"data:{mime};base64,{data_url}"
        parts.append({"type": "image_url", "image_url": {"url": data_url}})

    return AIMessage(role="user", content=parts)


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


async def _prepare_chat(cfg: AgenticChatConfig) -> _ChatPrep:
    """Gather context, fit it to the token budget and assemble the conversation for any route."""
    allowed = list(cfg.sources or [])
    bundle_text = ""
    used_sources: list[str] = []

    async def _assemble_bundle():
        if allowed:
            return await assemble_context(query=cfg.query, sources=allowed, user_id=cfg.user_id)
        return None

    async def _load_upload_chunks():
        if cfg.document_ids:
            return await asyncio.to_thread(chunks_from_documents, cfg.document_ids)
        return []

    async def _resolve_provider_async():
        return await asyncio.to_thread(
            resolve_provider,
            provider_name=cfg.provider,
            model_name=cfg.model,
            user_id=cfg.user_id,
        )

    bundle, upload_chunks, base_prompt, provider = await asyncio.gather(
        _assemble_bundle(),
        _load_upload_chunks(),
        _build_base_system_prompt(cfg.intent, cfg.feature),
        _resolve_provider_async(),
    )
    sys_prompt = base_prompt + _format_rule_for_intent(cfg.intent, cfg.template_extension or "docx")
    cfg.run_info["provider"] = getattr(provider, "id", "unknown")
    cfg.run_info["model"] = getattr(provider, "default_model", "unknown")
    fast = _FastProviderResolver(cfg, provider)

    if bundle and not bundle.is_empty:
        bundle_text = bundle.to_prompt_block()
        used_sources = list(bundle.used_sources)

    if upload_chunks:
        parts = [f"[{i+1}] (upload · {c.source_label}) {c.title}\n{c.text}" for i, c in enumerate(upload_chunks)]
        bundle_text = f"{bundle_text}\n\n" + "\n\n".join(parts)
        bundle_text = bundle_text.strip()
        if "uploads" not in used_sources:
            used_sources.append("uploads")

    if cfg.attached_docs:
        doc_parts = [
            f"[Documento adjunto en chat: {d.get('filename', 'documento')}]\n{d.get('content', '')}"
            for d in cfg.attached_docs
            if d.get("content")
        ]
        if doc_parts:
            bundle_text = f"{bundle_text}\n\n" + "\n\n".join(doc_parts)
            bundle_text = bundle_text.strip()
            if "chat_attachments" not in used_sources:
                used_sources.append("chat_attachments")

    context_docs_text = bundle_text or ""
    template_text = cfg.template_content or ""
    provider_id = getattr(provider, "id", "")
    main_model = getattr(provider, "default_model", "") or "gpt-4o"
    out_tokens = resolve_intent_max_tokens(cfg.intent)

    # Token budget: what the model can take in this request once the answer is reserved.
    input_budget = await asyncio.to_thread(calculate_input_budget, provider_id, main_model, out_tokens)
    history_budget = min(HISTORY_MAX_TOKENS, max(HISTORY_MIN_TOKENS, input_budget // 4))
    fixed_tokens = (
        count_tokens(main_model, sys_prompt)
        + count_tokens(main_model, cfg.query)
        + (count_tokens(main_model, template_text) if cfg.intent == "template_mutation" else 0)
        + IMAGE_TOKEN_ESTIMATE * len(cfg.images or [])
    )
    # History is reserved up front so documents never starve the conversation.
    docs_budget_tokens = max(DOCS_MIN_TOKENS, input_budget - fixed_tokens - history_budget)

    if context_docs_text:
        docs_tokens = count_tokens(main_model, context_docs_text)
        if docs_tokens > docs_budget_tokens:
            cfg.run_info["stage"] = "condense"
            # map_reduce works in characters: translate with the measured chars/token ratio.
            ratio = chars_per_token(main_model, context_docs_text)
            target_chars = int(docs_budget_tokens * ratio)
            context_docs_text = await map_reduce_condense_context(
                context_docs_text,
                target_budget=target_chars,
                provider=await fast.get(),
                feature_goal=f"Contexto relevante para {cfg.intent}",
            )
            cfg.run_info["context_condensed"] = True

    # Cache-friendly ordering: 1) System, 2) Documents & templates, 3) Chat History, 4) Current Query
    messages: list[AIMessage] = [AIMessage(role="system", content=sys_prompt)]

    doc_sections = []
    if cfg.intent in _ARTIFACT_INTENTS:
        ext_label = (cfg.template_extension or "docx").upper()
        doc_sections.append(
            f"[MODO DE TRABAJO: GENERACIÓN DE ARTEFACTO (Formato {ext_label})]\n"
            "Debes separar la respuesta: un mensaje breve en <chat>...</chat> y el documento completo en <artifact>...</artifact>."
        )
    if context_docs_text:
        doc_sections.append(f"DOCUMENTOS Y CONTEXTO DISPONIBLE:\n{context_docs_text}")
    if template_text and cfg.intent == "template_mutation":
        doc_sections.append(f"PLANTILLA CORPORATIVA:\n{template_text}")
    if doc_sections:
        messages.append(AIMessage(role="system", content="\n\n".join(doc_sections)))

    clean_history: list[AIMessage] = []
    history_input = cfg.history if cfg.history else cfg.chat_context
    raw_history_msgs = format_history_as_messages(history_input)
    if raw_history_msgs:
        cfg.run_info["stage"] = "history"
        clean_history = await prune_or_summarize_history(
            raw_history_msgs,
            max_tokens_budget=history_budget,
            model=main_model,
            fast_provider=await fast.get(),
            scope=cfg.conversation_id or cfg.user_id,
            store=ChatSessionSummaryStore(cfg.conversation_id, cfg.user_id) if cfg.conversation_id else None,
        )
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
        input_budget=input_budget,
        out_tokens=out_tokens,
        allowed=allowed,
    )


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
    info = cfg.run_info
    if info.get("logged"):
        return
    clean_usage = {k: v for k, v in (usage or {}).items() if k != "tool_calls"}
    entry: dict[str, Any] = {
        "feature": cfg.feature,
        "refused": False,
        "intent": cfg.intent,
        "route": info.get("route"),
        "conversation_id": cfg.conversation_id,
        "sources_used": prep.used_sources if prep else [],
        "provider": info.get("provider", "unknown"),
        "output": output,
        "streamed": True,
        "input_budget_tokens": prep.input_budget if prep else None,
        "fast_model": info.get("fast_model"),
        # Set by the endpoint: SSE protocol (to know when v1 can be retired) and how the intent
        # was decided (rules / model / model_cache).
        "protocol": info.get("protocol"),
        "intent_source": info.get("intent_source"),
        **clean_usage,
        **extra,
        "model": clean_usage.get("model") or info.get("model", "unknown"),
    }
    if info.get("section_plan_failed"):
        entry["section_plan_failed"] = True
    for key in ("intent_rules", "intent_classifier_ms"):
        if key in info:
            entry[key] = info[key]
    if error is not None:
        entry["stage"] = info.get("stage")
        entry.update(error_log_fields(error))
    log_ai_call(entry)
    info["logged"] = True


def _usage_event(usage: dict[str, Any], route: str) -> AgentEvent:
    keys = (
        "prompt_tokens", "completion_tokens", "cached_tokens", "cost_usd", "ttft_ms", "duration_ms",
        "model", "fallback_used", "finish_reason", "continuations", "llm_calls", "iterations",
    )
    return AgentEvent(type="usage", data={"route": route, **{k: usage.get(k) for k in keys if k in usage}})


async def _agent_route(cfg: AgenticChatConfig, prep: _ChatPrep) -> AsyncIterator[str | AgentEvent]:
    cfg.run_info.update(route="agent", stage="agent")
    tool_ctx = ToolContext(
        user_id=cfg.user_id,
        allowed_sources=prep.allowed,
        allowed_document_ids=list(cfg.document_ids or []),
    )
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
    _log_chat(
        cfg, prep, output="".join(output), usage=usage,
        sections=len(plan.sections), failed_sections=usage.get("failed_sections") or [],
    )


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

    final_reason = continuation_usage.get("finish_reason", usage.get("finish_reason"))
    full_output = "".join(accumulated)
    truncated = final_reason == "length" or has_unclosed_artifact(full_output)
    if truncated:
        logger.warning(
            "Answer still truncated after %s continuation(s) (intent=%s, model=%s)",
            continuation_usage.get("continuations", 0), cfg.intent, usage.get("model"),
        )
        tail = truncation_tail(full_output)
        accumulated.append(tail)
        cfg.run_info["truncated"] = True
        yield tail

    merged = {k: v for k, v in usage.items() if k != "tool_calls"}
    _merge_usage(merged, continuation_usage)
    merged["finish_reason"] = final_reason
    merged["continuations"] = continuation_usage.get("continuations", 0)
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
        prep = await _prepare_chat(cfg)

        if _flag("AI_AGENT_MODE", "false"):
            if _supports_agent(prep.provider):
                async with aclosing(_agent_route(cfg, prep)) as route:
                    async for item in route:
                        yield item
                return
            info["agent_unsupported"] = True
            logger.info("Agent mode on but %s has no tool calling; using the normal route", info.get("model"))

        if _flag("AI_SECTION_GENERATION", "true") and is_section_generation_candidate(cfg.intent, cfg.query):
            info["stage"] = "plan"
            yield AgentEvent(type="status", data={"message": "Planificando el documento...", "stage": "plan"})
            plan_usage: dict[str, Any] = {}
            plan = await plan_document(
                query=cfg.query,
                context_summary=prep.context_docs_text,
                template_extension=cfg.template_extension or "docx",
                provider=await prep.fast.get(),
                history=prep.history,
                usage_sink=plan_usage,
            )
            if plan and plan.sections:
                async with aclosing(_sections_route(cfg, prep, plan, plan_usage)) as route:
                    async for item in route:
                        yield item
                return
            info["section_plan_failed"] = True
            logger.warning("No section plan for intent %s; falling back to the plain route", cfg.intent)

        async with aclosing(_plain_route(cfg, prep)) as route:
            async for item in route:
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
