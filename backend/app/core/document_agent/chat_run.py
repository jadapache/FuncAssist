"""One chat run of the document agent: intent, runner configuration, the final answer and what is stored."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.ai.artifacts import artifacts_to_dict, build_fallback_artifact, extract_artifacts
from app.ai.errors import AIError
from app.ai.intent_classifier import classifier_enabled, classify_intent_with_model
from app.ai.logging import log_ai_call
from app.ai.providers.factory import resolve_provider
from app.ai.runner import (
    TRUNCATION_NOTICE,
    AgenticChatConfig,
    error_log_fields,
    run_agentic_chat_stream,
)
from app.db.repositories.history_repository import ChatRepository

from .intent import (
    ARTIFACT_INTENTS,
    classify_prompt_intent_by_rules,
    infer_active_artifact_intent,
    is_artifact_follow_up,
    needs_model_classification,
)
from .payloads import AgenticPromptRequest

logger = logging.getLogger(__name__)


def start_run(cfg: AgenticChatConfig):
    """The one place that starts the model run, shared by the plain and the streamed endpoints."""
    return run_agentic_chat_stream(cfg)


_DEFAULT_TEMPLATE_MODULES = ("mejora", "funcional", "requerimiento")


def _content_and_extension(detail: Optional[Dict[str, Any]]) -> Optional[tuple[str, str]]:
    """Content and file extension of a template that has text, None for one without."""
    if not detail or not detail.get("content", "").strip():
        return None
    filename = detail.get("filename", "")
    ext = filename.rpartition(".")[2].lower() if "." in filename else "docx"
    return detail["content"].strip(), ext


async def load_active_template_info(template_id: str | None = None) -> tuple[str, str]:
    """Load the active template content and file extension (e.g. ('...content...', 'docx'/'xlsx'))."""
    try:
        from app.core.template_storage import list_templates, get_template_detail

        if template_id:
            found = _content_and_extension(await get_template_detail(template_id))
            if found:
                return found

        templates = await list_templates()
        candidates = [
            t for t in templates
            if any(kw in (t.get("module") or "").lower() for kw in _DEFAULT_TEMPLATE_MODULES)
        ] or templates

        for tmpl in candidates:
            found = _content_and_extension(await get_template_detail(tmpl["id"]))
            if found:
                return found
    except Exception:
        pass
    return "", "docx"


async def load_active_template_content(template_id: str | None = None) -> str:
    content, _ = await load_active_template_info(template_id)
    return content



HISTORY_DB_LIMIT = 60


async def resolve_chat_history(
    req: "AgenticPromptRequest",
    chat_repo: ChatRepository,
    user_id: str | None,
) -> list[dict[str, Any]] | list[str] | None:
    """Pick the most complete history source for the agentic chat.

    1. Persisted messages of the conversation (authoritative, scoped to the user).
    2. Structured `conversationHistory` sent by the client.
    3. Legacy `chat_context` lines (`"role: content"`), parsed downstream.
    """
    if req.conversation_id:
        try:
            stored = await chat_repo.get_session_messages(req.conversation_id, limit=0, user_id=user_id)
            turns = [
                {"role": m.get("role"), "content": m.get("content")}
                for m in stored[-HISTORY_DB_LIMIT:]
                if m.get("role") in ("user", "assistant") and m.get("content")
            ]
            if turns:
                return turns
        except Exception as exc:  # history is best-effort; never block the answer
            logger.warning("Could not load conversation history %s: %s", req.conversation_id, exc)
    if req.conversation_history:
        return req.conversation_history
    if req.chat_context:
        return req.chat_context if isinstance(req.chat_context, list) else [str(req.chat_context)]
    return None



async def resolve_active_artifact_intent(
    req: "AgenticPromptRequest", chat_repo: ChatRepository, user_id: str | None,
) -> Optional[str]:
    """Intent of the conversation's current document (from the stored session), if there is one."""
    artifacts: List[Dict[str, Any]] = []
    if req.conversation_id:
        try:
            artifacts = await chat_repo.get_session_artifacts(req.conversation_id, user_id=user_id)
        except Exception as exc:
            logger.warning("Could not load artifacts of conversation %s: %s", req.conversation_id, exc, exc_info=True)
    return infer_active_artifact_intent(
        artifacts, req.template_id, has_current_document=bool((req.current_document or "").strip()),
    )


@dataclass
class PreparedRun:
    cfg: AgenticChatConfig
    intent: str
    query_text: str
    sources: List[str]
    template_ext: str


@dataclass
class AnswerOutcome:
    artifacts: List[Dict[str, Any]]
    clean_answer: str
    assistant_message: str
    is_template: bool
    is_generative: bool


def _strip_command(prompt_str: str) -> str:
    if prompt_str.startswith("/plan"):
        return prompt_str[5:].strip() or "Generar plan de pruebas e implementación detallado"
    if prompt_str.startswith("/informe"):
        return prompt_str[8:].strip() or "Generar informe técnico y ejecutivo detallado"
    if prompt_str.startswith("/pregunta"):
        return prompt_str[9:].strip()
    if prompt_str.startswith("/plantilla"):
        return prompt_str[10:].strip()
    return prompt_str


async def _resolve_intent(
    req: "AgenticPromptRequest", user_id: str | None, active_intent: Optional[str],
) -> tuple[str, Dict[str, Any]]:
    """Rules first; the fast model only for undecided, document-related messages.

    Returns the intent and run info for the log: `intent_source` is "rules", "model" or
    "model_cache", plus `intent_rules` (what the rules said) when the model changed it.
    """
    prompt_str = req.prompt_text
    intent, decided = classify_prompt_intent_by_rules(
        prompt_str, req.mode, template_id=req.template_id, active_artifact_intent=active_intent,
    )
    info: Dict[str, Any] = {"intent_source": "rules"}
    if not classifier_enabled() or not needs_model_classification(prompt_str, decided, active_intent):
        return intent, info

    try:
        fast = await asyncio.to_thread(
            resolve_provider,
            provider_name=req.provider,
            user_id=user_id,
            tier="fast",
            main_model=req.model,
        )
    except ValueError as exc:
        logger.info("Intent classifier skipped, no fast provider: %s", exc)
        return intent, info

    has_template = bool((req.template_id or "").strip())
    t0 = time.perf_counter()
    decision = await classify_intent_with_model(
        prompt_str, provider=fast, active_intent=active_intent, has_template=has_template,
    )
    info["intent_classifier_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    if decision is None:
        return intent, info
    info["intent_source"] = "model_cache" if decision.cached else "model"
    if decision.intent != intent:
        info["intent_rules"] = intent
    return decision.intent, info


def _reject_unsupported_model(req: "AgenticPromptRequest") -> None:
    from app.ai.providers.registry import FORBIDDEN_BACKEND_PROVIDERS

    if req.provider and req.provider.lower() in FORBIDDEN_BACKEND_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail="Los modelos locales se ejecutan exclusivamente en el navegador mediante WebLLM.",
        )
    if req.model and req.model.lower().endswith(".gguf"):
        raise HTTPException(status_code=400, detail="Modelos GGUF no están admitidos en el backend.")


def _chat_context_text(chat_context: Any) -> Optional[str]:
    if not chat_context:
        return None
    return "\n".join(chat_context) if isinstance(chat_context, list) else str(chat_context)


async def prepare_chat_run(
    req: "AgenticPromptRequest",
    chat_repo: ChatRepository,
    user_id: str | None,
    active_intent: Optional[str],
) -> PreparedRun:
    """Validate the request and build the runner configuration (shared by both endpoints)."""
    _reject_unsupported_model(req)
    prompt_str = req.prompt_text
    chat_ctx_str = _chat_context_text(req.chat_context)
    chat_history = await resolve_chat_history(req, chat_repo, user_id)

    sources_to_use = req.sources or ["knowledge"]
    intent, intent_info = await _resolve_intent(req, user_id, active_intent)
    query_text = _strip_command(prompt_str)
    template_content, template_ext = await load_active_template_info(req.template_id)
    feature = req.feature or "mejoras_doc"
    document_ids = req.document_ids or []
    cfg = AgenticChatConfig(
        query=query_text,
        intent=intent,
        feature=feature,
        sources=sources_to_use,
        document_ids=document_ids,
        chat_context=chat_ctx_str,
        history=chat_history,
        conversation_id=req.conversation_id,
        template_content=template_content,
        template_extension=template_ext,
        images=req.images,
        attached_docs=req.attached_docs,
        user_id=user_id,
        provider=req.provider,
        model=req.model,
    )
    cfg.run_info.update(intent_info)
    if active_intent and intent == active_intent and is_artifact_follow_up(prompt_str):
        cfg.run_info["artifact_follow_up"] = True
    return PreparedRun(cfg=cfg, intent=intent, query_text=query_text, sources=sources_to_use, template_ext=template_ext)


_FALLBACK_TITLES = {"template_mutation": "Documento", "generic_plan": "Plan"}


def _assistant_message(
    full_content: str, clean_answer: str, has_artifacts: bool, is_template: bool, is_generative: bool,
) -> str:
    """What the chat shows: the text around the artifacts, or a note that the document is in the panel."""
    if has_artifacts:
        return clean_answer
    if is_template:
        return "He generado y estructurado el documento corporativo en el panel de artefactos."
    if is_generative:
        return "He elaborado el documento solicitado en el panel de artefactos."
    return full_content


def finalize_answer(full_content: str, prepared: PreparedRun) -> AnswerOutcome:
    """Extract artifacts and the chat message from the raw answer."""
    intent = prepared.intent
    parsed_arts, clean_ans = extract_artifacts(full_content)
    art_dicts = artifacts_to_dict(parsed_arts)
    is_generative = intent in ARTIFACT_INTENTS

    if not art_dicts and is_generative and full_content.strip():
        fallback_title = _FALLBACK_TITLES.get(intent, "Informe")
        fallback_art = build_fallback_artifact(full_content, default_title=fallback_title, default_extension=prepared.template_ext)
        art_dicts = artifacts_to_dict([fallback_art])

    is_template = intent == "template_mutation"
    asst_msg = _assistant_message(full_content, clean_ans, bool(parsed_arts), is_template, is_generative)
    if prepared.cfg.run_info.get("truncated") and TRUNCATION_NOTICE not in asst_msg:
        asst_msg = f"{asst_msg}\n\n_({TRUNCATION_NOTICE})_".strip()
    for art in art_dicts:
        art["intent"] = intent  # lets a later "regenera" keep the same intent
    return AnswerOutcome(
        artifacts=art_dicts,
        clean_answer=clean_ans,
        assistant_message=asst_msg,
        is_template=is_template,
        is_generative=is_generative,
    )


def _merge_session_artifacts(existing: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add new artifacts to the stored ones; a new artifact with the same title replaces the old one."""
    merged = [dict(a) for a in existing]
    for art in new:
        key = str(art.get("title", "")).strip().lower()
        idx = next((i for i, a in enumerate(merged) if str(a.get("title", "")).strip().lower() == key), None)
        if idx is None:
            merged.append(dict(art))
        else:
            previous = merged[idx]
            updated = {**previous, **art}
            if previous.get("id"):
                updated["id"] = previous["id"]  # keep the client's identity for the artifact
            merged[idx] = updated
    return merged


async def persist_turn(
    chat_repo: ChatRepository,
    *,
    req: "AgenticPromptRequest",
    user_id: str | None,
    conv_id: str,
    user_text: str,
    prepared: PreparedRun,
    outcome: AnswerOutcome,
    full_content: str,
) -> None:
    """Store the turn. Client-generated ids make this idempotent with the client autosave."""
    try:
        await chat_repo.save_message(
            session_id=conv_id,
            role="user",
            content=user_text,
            user_id=user_id,
            id=req.user_message_id,
        )
        await chat_repo.save_message(
            session_id=conv_id,
            role="assistant",
            content=outcome.assistant_message,
            context_sources=[{"source": s} for s in prepared.sources],
            user_id=user_id,
            id=req.assistant_message_id,
        )
        session_data: Dict[str, Any] = {
            "id": conv_id,
            "user_id": user_id,
            "title": user_text[:35],
            "feature_slug": req.feature or "general",
        }
        # Only touch the stored document/artifacts when this turn produced them: a chat turn
        # must not wipe the conversation's document.
        if outcome.artifacts:
            existing = await chat_repo.get_session_artifacts(conv_id, user_id=user_id)
            session_data["artifacts"] = _merge_session_artifacts(existing, outcome.artifacts)
        if outcome.is_template:
            session_data["document_content"] = full_content
        await chat_repo.save_session(session_data)
    except Exception as exc:
        logger.warning("Could not persist chat turn of conversation %s: %s", conv_id, exc, exc_info=True)


def log_request_failure(cfg: AgenticChatConfig, err: BaseException, *, streamed: bool, stage: str | None = None) -> None:
    """Log a failed chat request unless the runner already logged it."""
    info = cfg.run_info
    if info.get("logged"):
        return
    stage = stage or info.get("stage") or "endpoint"
    provider = info.get("provider") or cfg.provider
    model = info.get("model") or cfg.model
    not_refused = {"refused": False}
    log_ai_call({
        **not_refused,
        "feature": cfg.feature,
        "intent": cfg.intent,
        "route": info.get("route"),
        "stage": stage,
        "conversation_id": cfg.conversation_id,
        "provider": provider,
        "model": model,
        "streamed": streamed,
        "protocol": info.get("protocol"),
        "intent_source": info.get("intent_source"),
        **error_log_fields(err),
    })
    info["logged"] = True


def error_code(err: BaseException) -> str:
    return err.code if isinstance(err, AIError) else "run_exception"




def format_stream_error(err: Exception) -> str:
    """User-facing message for a failed run.

    Provider errors arrive as typed `AIError`s (classified by exception type and HTTP status in the
    provider layer) and already carry a user message; nothing is inferred from message substrings.
    """
    if isinstance(err, AIError):
        return err.user_message
    if isinstance(err, ValueError):
        # Configuration problems (unknown provider, missing API key, invalid URL) carry readable text.
        return str(err)
    return f"Error inesperado al generar la respuesta: {err}"

