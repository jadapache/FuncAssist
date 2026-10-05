"""Grounded AI runner — assemble context, apply template/rubric, refuse if empty."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.artifacts import artifacts_to_dict, extract_artifacts
from app.ai.logging import log_ai_call
from app.ai.providers.base import AIMessage
from app.ai.providers.factory import resolve_provider
from app.ai.request_types import (
    DocumentFeatureRequest,
    GroundedFeatureRequest,
    SimpleFeatureRequest,
)
from app.ai.templates import get_prompt, get_rubric, rubric_to_text
from app.context.models import ContextChunk
from app.context.retrieval import chunks_from_documents
from app.context.service import assemble_context



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
) -> _GroundedPrep | dict:
    """Fase de preparación compartida entre run_grounded_feature y run_grounded_feature_stream.

    Retorna un _GroundedPrep listo para llamar al LLM,
    o un dict con refused=True si hay que rechazar sin llamar al LLM.
    """
    prompt = get_prompt(feature)
    rubric = get_rubric(feature)
    allowed = list(sources or prompt.get("allowed_sources") or [])

    if not allowed:
        return {
            "ok": False,
            "refused": True,
            "reason": "Esta funcionalidad no tiene fuentes de conocimiento configuradas.",
            "answer": None,
            "citations": [],
        }

    bundle = await assemble_context(query=query, sources=allowed)

    upload_chunks: list[ContextChunk] = []
    if document_ids:
        upload_chunks = chunks_from_documents(document_ids)
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
    format_kwargs = {
        "context": bundle.to_prompt_block(),
        "rubric": rubric_to_text(rubric),
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
        AIMessage(role="system", content=str(prompt.get("system") or "")),
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
) -> dict[str, Any]:
    prep = await _prepare_grounded_context(
        feature=feature,
        query=query,
        sources=sources,
        document_ids=document_ids,
        chat_context=chat_context,
        template_content=template_content,
    )
    if isinstance(prep, dict):  # refused
        return prep

    provider = resolve_provider()
    completion = await provider.complete(prep.messages, max_tokens=4096)

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
):
    """Versión streaming de run_grounded_feature. Yields text chunks via SSE."""
    prep = await _prepare_grounded_context(
        feature=feature,
        query=query,
        sources=sources,
        document_ids=document_ids,
        chat_context=chat_context,
        template_content=template_content,
    )
    if isinstance(prep, dict):  # refused
        reason = prep.get("reason", "Error desconocido al preparar contexto.")
        raise RuntimeError(reason)

    provider = resolve_provider()
    accumulated_text: list[str] = []

    async for chunk in provider.complete_stream(prep.messages, max_tokens=8192):
        accumulated_text.append(chunk)
        yield chunk

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
        "model": getattr(provider, "default_model", "unknown"),
        "output": full_output,
        "streamed": True,
    })


async def run_simple_feature(request: SimpleFeatureRequest) -> dict[str, Any]:
    """Run feature with only query (no external context sources)."""
    return await run_grounded_feature(
        feature=request.feature,
        query=request.query,
        sources=[],
        document_ids=None,
        chat_context=None,
    )


async def run_document_feature(request: DocumentFeatureRequest) -> dict[str, Any]:
    """Run feature with document analysis."""
    return await run_grounded_feature(
        feature=request.feature,
        query=request.query,
        sources=request.sources or ["knowledge"],
        document_ids=request.document_ids,
        chat_context=None,
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
    )


