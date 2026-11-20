"""Grounded AI runner — assemble context, apply template/rubric, refuse if empty."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
import os
from typing import Any

from app.ai.agent import run_agent
from app.ai.artifacts import artifacts_to_dict, extract_artifacts, is_artifact_truncated
from app.ai.budget import calculate_input_budget, chars_per_token, count_tokens
from app.ai.history import format_history_as_messages, prune_or_summarize_history
from app.ai.history_store import ChatSessionSummaryStore
from app.ai.logging import log_ai_call
from app.ai.map_reduce import map_reduce_condense_context
from app.ai.policies import resolve_intent_max_tokens
from app.ai.providers.base import AIMessage
from app.ai.providers.factory import resolve_provider
from app.ai.request_types import (
    DocumentFeatureRequest,
    GroundedFeatureRequest,
    SimpleFeatureRequest,
)
from app.ai.section_generator import (
    generate_sections_stream,
    is_section_generation_candidate,
    plan_document,
)
from app.ai.templates import get_prompt, get_rubric, rubric_to_text
from app.ai.tools.registry import ToolContext
from app.context.models import ContextChunk
from app.context.retrieval import chunks_from_documents
from app.context.service import assemble_context



GROUNDED_MAX_TOKENS = 8192


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

logger = logging.getLogger(__name__)


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
    max_output_tokens: int = GROUNDED_MAX_TOKENS,
) -> _GroundedPrep | dict:
    """Fase de preparación compartida entre run_grounded_feature y run_grounded_feature_stream.

    Retorna un _GroundedPrep listo para llamar al LLM,
    o un dict con refused=True si hay que rechazar sin llamar al LLM.
    """
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
    prep = await _prepare_grounded_context(
        feature=feature,
        query=query,
        sources=sources,
        document_ids=document_ids,
        chat_context=chat_context,
        template_content=template_content,
        user_id=user_id,
        provider=provider,
    )
    if isinstance(prep, dict):  # refused
        return prep

    completion = await provider.complete(prep.messages, max_tokens=8192)
    accumulated_output = completion.text

    # Detección de truncamiento y auto-resunción en llamadas síncronas
    max_continuations = 3
    continuations_done = 0
    while is_artifact_truncated(accumulated_output) and continuations_done < max_continuations:
        prev_len = len(accumulated_output)
        continuations_done += 1
        tail_context = accumulated_output[-800:] if len(accumulated_output) > 800 else accumulated_output
        continuation_prompt = (
            "ATENCIÓN: Tu generación previa se interrumpió antes de completar todo el documento.\n"
            f"El último fragmento emitido fue exactamente:\n\"\"\"{tail_context}\"\"\"\n\n"
            "Continúa la redacción EXACTAMENTE en el punto donde se cortó, completando todas las secciones "
            "faltantes sin repetir lo ya emitido ni agregar saludos ni notas introductorias. "
            "Si estabas usando etiquetas <artifact>, ciérralas adecuadamente con </artifact> al terminar."
        )
        continuation_messages = [
            *prep.messages,
            AIMessage(role="assistant", content=accumulated_output),
            AIMessage(role="user", content=continuation_prompt),
        ]
        next_part = await provider.complete(continuation_messages, max_tokens=8192)
        if not next_part.text:
            break
        accumulated_output += next_part.text
        if len(accumulated_output) <= prev_len:
            break

    completion.text = accumulated_output

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
    prep = await _prepare_grounded_context(
        feature=feature,
        query=query,
        sources=sources,
        document_ids=document_ids,
        chat_context=chat_context,
        template_content=template_content,
        user_id=user_id,
        provider=provider,
    )
    if isinstance(prep, dict):  # refused
        reason = prep.get("reason", "Error desconocido al preparar contexto.")
        raise RuntimeError(reason)

    accumulated_text: list[str] = []
    stream_usage: dict[str, Any] = {}

    async for chunk in provider.complete_stream(prep.messages, max_tokens=GROUNDED_MAX_TOKENS, usage_sink=stream_usage):
        accumulated_text.append(chunk)
        yield chunk

    # Detección de truncamiento y continuación automática (Auto-resume)
    max_continuations = 3
    continuations_done = 0
    current_text = "".join(accumulated_text)

    while is_artifact_truncated(current_text) and continuations_done < max_continuations:
        prev_len = len(current_text)
        continuations_done += 1
        tail_context = current_text[-800:] if len(current_text) > 800 else current_text
        continuation_prompt = (
            "ATENCIÓN: Tu generación previa se interrumpió antes de completar todo el documento.\n"
            f"El último fragmento emitido fue exactamente:\n\"\"\"{tail_context}\"\"\"\n\n"
            "Continúa la redacción EXACTAMENTE en el punto donde se cortó, completando todas las secciones "
            "faltantes sin repetir lo ya emitido ni agregar saludos ni notas introductorias. "
            "Si estabas usando etiquetas <artifact>, ciérralas adecuadamente con </artifact> al terminar."
        )
        continuation_messages = [
            *prep.messages,
            AIMessage(role="assistant", content=current_text),
            AIMessage(role="user", content=continuation_prompt),
        ]
        next_chunk_buffer = []
        async for chunk in provider.complete_stream(continuation_messages, max_tokens=8192):
            accumulated_text.append(chunk)
            next_chunk_buffer.append(chunk)
            yield chunk

        current_text = "".join(accumulated_text)
        if len(current_text) <= prev_len or not next_chunk_buffer:
            break

    full_output = "".join(accumulated_text)
    log_ai_call({
        "feature": feature,
        "refused": False,
        "prompt_version": prep.prompt_meta.get("version"),
        "rubric_version": prep.rubric_meta.get("version"),
        "sources_requested": prep.allowed,
        "sources_used": prep.bundle.used_sources,
        "chunk_ids": [chunk.id for chunk in prep.bundle.chunks],
        "provider": getattr(provider, "id", getattr(provider, "name", "unknown")),
        "output": full_output,
        "streamed": True,
        **stream_usage,
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


HISTORY_MIN_TOKENS = 1_000
HISTORY_MAX_TOKENS = 6_000
DOCS_MIN_TOKENS = 1_000
IMAGE_TOKEN_ESTIMATE = 1_200  # rough per-image cost on vision models

_ARTIFACT_INTENTS = frozenset({"generic_plan", "generic_report", "template_mutation"})


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


async def _build_chat_system_prompt(intent: str, feature: str | None = None, template_extension: str | None = "docx") -> str:
    target_feature = intent if intent and intent != "chat" else (feature or "chat")
    rule = _format_rule_for_intent(intent, template_extension or "docx")
    try:
        tmpl = await get_prompt(target_feature)
        if tmpl and tmpl.get("system"):
            return tmpl["system"] + rule
    except Exception:
        pass

    base = (
        "Eres un asistente experto en Aseguramiento de Calidad (QA), Gestión de Requerimientos y Arquitectura de Software. "
        "Responde con claridad, didáctica y precisión técnica utilizando formato Markdown enriquecido. "
        "Utiliza el contexto de los documentos cargados, historial de chat y las imágenes adjuntas cuando estén presentes."
    )
    return base + rule


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


async def continue_if_truncated(
    accumulated_text: list[str],
    provider: Any,
    sys_prompt: str,
    user_message: AIMessage,
    max_continuations: int = 2,
):
    """Safety net utility for legacy monolithic routes when generation is truncated."""
    continuations_done = 0
    current_text = "".join(accumulated_text)

    while is_artifact_truncated(current_text) and continuations_done < max_continuations:
        prev_len = len(current_text)
        continuations_done += 1
        tail_context = current_text[-800:] if len(current_text) > 800 else current_text
        continuation_prompt = (
            "ATENCIÓN: Tu generación previa se interrumpió antes de completar todo el documento.\n"
            f"El último fragmento emitido fue exactamente:\n\"\"\"{tail_context}\"\"\"\n\n"
            "Continúa la redacción EXACTAMENTE en el punto donde se cortó, completando todas las secciones "
            "faltantes sin repetir lo ya emitido ni agregar saludos ni notas introductorias. "
            "Si estabas usando etiquetas <artifact>, ciérralas adecuadamente con </artifact> al terminar."
        )
        continuation_messages = [
            AIMessage(role="system", content=sys_prompt),
            user_message,
            AIMessage(role="assistant", content=current_text),
            AIMessage(role="user", content=continuation_prompt),
        ]
        next_chunk_buffer = []
        async for chunk in provider.complete_stream(continuation_messages, max_tokens=8192):
            accumulated_text.append(chunk)
            next_chunk_buffer.append(chunk)
            yield chunk

        current_text = "".join(accumulated_text)
        if len(current_text) <= prev_len or not next_chunk_buffer:
            break


async def run_agentic_chat_stream(cfg: AgenticChatConfig):
    """Streaming runner for dynamic multimodal chat, generic artifacts, or direct Q&A."""
    allowed = list(cfg.sources or [])
    bundle_text = ""
    used_sources: list[str] = []

    async def _assemble_bundle():
        if allowed:
            b = await assemble_context(query=cfg.query, sources=allowed, user_id=cfg.user_id)
            return b
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

    bundle, upload_chunks, sys_prompt, provider = await asyncio.gather(
        _assemble_bundle(),
        _load_upload_chunks(),
        _build_chat_system_prompt(cfg.intent, cfg.feature, cfg.template_extension),
        _resolve_provider_async(),
    )

    if bundle and not bundle.is_empty:
        bundle_text = bundle.to_prompt_block()
        used_sources = list(bundle.used_sources)

    if upload_chunks:
        parts = [f"[{i+1}] (upload · {c.source_label}) {c.title}\n{c.text}" for i, c in enumerate(upload_chunks)]
        upload_block = "\n\n".join(parts)
        bundle_text = f"{bundle_text}\n\n{upload_block}".strip()
        if "uploads" not in used_sources:
            used_sources.append("uploads")

    if cfg.attached_docs:
        doc_parts = [
            f"[Documento adjunto en chat: {d.get('filename', 'documento')}]\n{d.get('content', '')}"
            for d in cfg.attached_docs
            if d.get("content")
        ]
        if doc_parts:
            attached_block = "\n\n".join(doc_parts)
            bundle_text = f"{bundle_text}\n\n{attached_block}".strip()
            if "chat_attachments" not in used_sources:
                used_sources.append("chat_attachments")

    user_prompt_sections = []
    if cfg.intent in _ARTIFACT_INTENTS:
        ext_label = (cfg.template_extension or "docx").upper()
        user_prompt_sections.append(
            f"[MODO DE TRABAJO: GENERACIÓN DE ARTEFACTO (Formato {ext_label})]\n"
            "Debes separar la respuesta: un mensaje breve en <chat>...</chat> y el documento completo en <artifact>...</artifact>."
        )

    context_docs_text = bundle_text or ""
    template_text = cfg.template_content or ""
    provider_id = getattr(provider, "id", "")
    main_model = getattr(provider, "default_model", "") or "gpt-4o"
    out_tokens = resolve_intent_max_tokens(cfg.intent, default_tokens=1500)

    # Token budget: what the model can take in this request once the answer is reserved.
    input_budget = await asyncio.to_thread(
        calculate_input_budget, provider_id, main_model, out_tokens
    )
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
            # map_reduce works in characters: translate with the measured chars/token ratio.
            ratio = chars_per_token(main_model, context_docs_text)
            target_chars = int(docs_budget_tokens * ratio)
            try:
                fast_prov = resolve_provider(provider_name=cfg.provider, user_id=cfg.user_id, tier="fast")
            except ValueError:
                fast_prov = provider
            context_docs_text = await map_reduce_condense_context(
                context_docs_text,
                target_budget=target_chars,
                provider=fast_prov,
                feature_goal=f"Contexto relevante para {cfg.intent}",
            )

    # Cache-friendly ordering: 1) System, 2) Documents & templates, 3) Chat History, 4) Current Query
    messages: list[AIMessage] = [AIMessage(role="system", content=sys_prompt)]

    # Add documentary context as separate message
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

    # Process history turns
    history_input = cfg.history if cfg.history else cfg.chat_context
    raw_history_msgs = format_history_as_messages(history_input)
    if raw_history_msgs:
        try:
            fast_prov = resolve_provider(provider_name=cfg.provider, user_id=cfg.user_id, tier="fast")
        except ValueError:
            fast_prov = None
        clean_history = await prune_or_summarize_history(
            raw_history_msgs,
            max_tokens_budget=history_budget,
            model=main_model,
            fast_provider=fast_prov,
            scope=cfg.conversation_id or cfg.user_id,
            store=ChatSessionSummaryStore(cfg.conversation_id, cfg.user_id) if cfg.conversation_id else None,
        )
        messages.extend(clean_history)

    # Current query as user turn
    user_message = _assemble_multimodal_message(cfg.query, cfg.images)
    messages.append(user_message)

    # Agent mode execution when tool calling is enabled and supported
    agent_mode_flag = os.getenv("AI_AGENT_MODE", "false").lower() in ("true", "1", "on")
    spec = getattr(provider, "spec", None)
    if agent_mode_flag and spec and getattr(spec, "supports_tools", False):
        max_iters = int(os.getenv("AI_AGENT_MAX_ITERS", "8"))
        tool_ctx = ToolContext(
            user_id=cfg.user_id,
            allowed_sources=allowed,
            allowed_document_ids=list(cfg.document_ids or []),
        )
        agent_output: list[str] = []
        usage: dict[str, Any] = {}
        async for ev in run_agent(
            messages=messages,
            provider=provider,
            ctx=tool_ctx,
            max_iters=max_iters,
            max_tokens=resolve_intent_max_tokens(cfg.intent, default_tokens=1500),
        ):
            if ev.type == "delta":
                text = ev.data.get("text", "")
                agent_output.append(text)
                yield text
            elif ev.type == "artifact_start":
                ext = ev.data.get("extension", "docx")
                text = f'\n<artifact title="{ev.data.get("title", "Documento")}" extension="{ext}">\n'
                agent_output.append(text)
                yield text
            elif ev.type == "artifact_delta":
                text = ev.data.get("text", "")
                agent_output.append(text)
                yield text
            elif ev.type == "artifact_end":
                agent_output.append("\n</artifact>\n")
                yield "\n</artifact>\n"
            elif ev.type == "done":
                break
            else:
                if ev.type == "usage":
                    usage = ev.data
                # status / tool_call / tool_result / usage: typed events for SSE v2 consumers.
                yield ev

        log_ai_call({
            "feature": cfg.feature,
            "refused": False,
            "intent": cfg.intent,
            "agent_mode": True,
            "sources_used": used_sources,
            "provider": getattr(provider, "id", "unknown"),
            "model": getattr(provider, "default_model", "unknown"),
            "output": "".join(agent_output),
            "streamed": True,
            **usage,
        })
        return

    # Section-by-section generation route if applicable
    section_flag = os.getenv("AI_SECTION_GENERATION", "true").lower() in ("true", "1", "on")
    if section_flag and is_section_generation_candidate(cfg.intent, cfg.query):
        fast_prov = resolve_provider(provider_name=cfg.provider, user_id=cfg.user_id, tier="fast")
        plan = await plan_document(
            query=cfg.query,
            context_summary=context_docs_text,
            template_extension=cfg.template_extension or "docx",
            provider=fast_prov,
        )
        if plan and plan.sections:
            accumulated_sections: list[str] = []
            async for chunk in generate_sections_stream(
                plan=plan,
                system_prompt=sys_prompt,
                context_block=context_docs_text,
                main_provider=provider,
            ):
                accumulated_sections.append(chunk)
                yield chunk

            full_section_output = "".join(accumulated_sections)
            log_ai_call({
                "feature": cfg.feature,
                "refused": False,
                "intent": cfg.intent,
                "sections": len(plan.sections),
                "sources_used": used_sources,
                "provider": getattr(provider, "id", "unknown"),
                "model": getattr(provider, "default_model", "unknown"),
                "output": full_section_output,
                "streamed": True,
            })
            return

    accumulated_text: list[str] = []
    stream_usage: dict[str, Any] = {}

    async for chunk in provider.complete_stream(messages, max_tokens=out_tokens, usage_sink=stream_usage):
        accumulated_text.append(chunk)
        yield chunk

    # Detección de truncamiento mediante utilidad única
    async for chunk in continue_if_truncated(accumulated_text, provider, sys_prompt, user_message):
        yield chunk

    full_output = "".join(accumulated_text)
    log_ai_call({
        "feature": cfg.feature,
        "refused": False,
        "intent": cfg.intent,
        "sources_used": used_sources,
        "provider": getattr(provider, "id", getattr(provider, "name", "unknown")),
        "output": full_output,
        "streamed": True,
        "input_budget_tokens": input_budget,
        **stream_usage,
        "model": stream_usage.get("model") or getattr(provider, "default_model", "unknown"),
    })


