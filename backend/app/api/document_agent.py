"""FastAPI router for DocumentAgent, Agentic RAG integration, and Native Document Exports."""

from __future__ import annotations

import asyncio
import io
import time
from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
import json
import logging
import uuid
from pydantic import BaseModel, Field

from app.api.deps import get_chat_repository, get_current_user, get_streaming_chat_repository
from app.context.knowledge import extract_text
from app.services.event_serializer import AgentRunEmitter, run_registry


from app.core.document_agent.schema import (
    CanonicalDocumentState,
    CamelModel,
    DocumentOperation,
    InsertImageOperation,
    InsertTextOperation,
    ReplaceContentOperation,
    UpdateTableOperation,
    OperationExecutionResult,
    TargetLocator,
    AssetLocator,
    VerificationReport,
)
from app.ai.artifacts import (
    ArtifactStreamSplitter,
    artifacts_to_dict,
    build_fallback_artifact,
    extract_artifacts,
)
from app.ai.errors import AIError
from app.ai.events import AgentEvent as AIAgentEvent, sse_event
from app.ai.logging import log_ai_call
from app.ai.runner import (
    TRUNCATION_NOTICE,
    AgenticChatConfig,
    error_log_fields,
    run_agentic_chat_stream,
    run_grounded_feature,
    run_grounded_feature_stream,
)
from app.ai.intent_classifier import classifier_enabled, classify_intent_with_model
from app.ai.providers.factory import resolve_provider
from app.ai.stream_control import StreamStopped, iterate_until_stopped
from app.db.repositories.history_repository import ChatRepository
from app.core.document_agent.validator import DocumentOperationValidator
from app.core.template_storage import list_templates, get_template_file_path
from app.features.mejoras.docx_builder import create_mejoras_docx
from app.features.levantamiento.docx_builder import create_levantamiento_docx
from app.features.inventario.xlsx_builder import create_inventario_xlsx
from app.features.mejoras.xlsx_builder import create_qa_matrix_xlsx
from app.schemas.artifacts import FunctionalImprovementArtifact, FunctionalInventoryArtifact
from app.services.rubric_evaluator import RubricEvaluator
from app.services.template_renderer.docx_engine import DocxTemplateRenderer
from app.services.template_renderer.xlsx_engine import XlsxTemplateRenderer

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/doc-agent",
    tags=["document-agent"],
    dependencies=[Depends(get_current_user)],
)


ARTIFACT_INTENTS = frozenset({"generic_plan", "generic_report", "template_mutation"})

# Follow-ups that ask to (re)produce the document already open in the conversation. Matched only
# when there is an active artifact, so they never turn an ordinary chat message into a document.
_ARTIFACT_FOLLOW_UP_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bregener",                                              # regenera, regenerar, regenéralo
        r"\bvuelve a (generar|hacer|crear|redactar|escribir)",
        r"\b(gen[eé]ralo|gen[eé]rala|hazlo|hazla|cr[eé]alo|red[aá]ctalo)\s+(de nuevo|otra vez)",
        r"\brehaz|\brehacer",
        r"\b(est[aá]|qued[oó]|sali[oó]|vino|lleg[oó]|aparece)\s+(vac[ií][oa]|en blanco|incomplet[oa]|cortad[oa]|truncad[oa])",
        r"\b(documento|artefacto|archivo|plan|informe)\s+(vac[ií]o|en blanco|incompleto|cortado|truncado)",
        r"\b(no tiene|sin) contenido",
        r"\bcompl[eé]t(alo|ala|alos|alas)\b",
        r"\bcompleta\s+(el|la|las|los)\s+(documento|artefacto|plan|informe|reporte|plantilla|secci[oó]n|secciones)",
        r"\btermina\s+(el|la)\s+(documento|artefacto|plan|informe|reporte|secci[oó]n)",
        r"\bcorrige\s+(el|la)\s+(documento|artefacto|plan|informe|reporte|plantilla)",
        r"\bcontin[uú]a\s+(con\s+)?(el|la)\s+(documento|artefacto|plan|informe|reporte|secci[oó]n)",
        r"\bfalta(n)?\s+(secciones|contenido|el contenido|partes)",
    )
]


def is_artifact_follow_up(prompt: str) -> bool:
    """Whether the message asks to regenerate, complete or fix the current document."""
    text = (prompt or "").strip()
    return bool(text) and any(p.search(text) for p in _ARTIFACT_FOLLOW_UP_PATTERNS)


def infer_active_artifact_intent(artifacts: List[Dict[str, Any]] | None, template_id: Optional[str] = None, has_current_document: bool = False) -> Optional[str]:
    """Intent that produced the conversation's active (latest) artifact, or None without one."""
    if artifacts:
        latest = artifacts[-1]
        stored = str(latest.get("intent") or "")
        if stored in ARTIFACT_INTENTS:
            return stored
        if template_id:
            return "template_mutation"
        title = str(latest.get("title") or "").lower()
        if "plan" in title:
            return "generic_plan"
        return "generic_report"
    if has_current_document:
        return "template_mutation" if template_id else "generic_report"
    return None


def classify_prompt_intent(
    prompt: str,
    mode: Optional[str] = None,
    template_id: Optional[str] = None,
    active_artifact_intent: Optional[str] = None,
) -> str:
    """Classifies user prompt intent into: generic_plan, generic_report, custom feature slug, template_mutation, or chat.

    `active_artifact_intent` is the intent of the conversation's current document, if any: a
    follow-up such as "regenera" or "el documento está vacío" then keeps that intent, even when
    phrased as a question, instead of falling into conversational chat.
    """
    return classify_prompt_intent_by_rules(prompt, mode, template_id, active_artifact_intent)[0]


_QUESTION_STARTS = (
    "¿", "que ", "qué ", "como ", "cómo ", "cual ", "cuál ", "por que", "por qué", "donde ", "dónde ",
    "explica", "cuéntame", "dime",
)


def _looks_like_question(text_lower: str) -> bool:
    return text_lower.startswith(_QUESTION_STARTS) or "?" in text_lower


_MODE_INTENTS = {
    "plan": "generic_plan", "generic_plan": "generic_plan",
    "report": "generic_report", "informe": "generic_report", "generic_report": "generic_report",
    "chat": "chat", "qa": "chat",
    "template": "template_mutation", "template_mutation": "template_mutation",
}
_COMMAND_INTENTS = {
    "plan": "generic_plan", "generic_plan": "generic_plan",
    "report": "generic_report", "informe": "generic_report", "generic_report": "generic_report",
    "plantilla": "template_mutation", "template": "template_mutation", "template_mutation": "template_mutation",
    "pregunta": "ask_product", "question": "ask_product", "ask": "ask_product",
}
_PLAN_PHRASES = (
    "plan de prueba", "plan de implementaci", "plan de trabajo", "genera un plan", "crea un plan", "elabora un plan",
)
_REPORT_PHRASES = ("informe", "reporte", "resumen ejecutivo")
_TEMPLATE_PHRASES = (
    "completa la plantilla",
    "llena la plantilla",
    "genera el documento de mejora",
    "genera el documento funcional",
    "genera el levantamiento",
    "genera el inventario",
    "redacta el documento corporativo",
    "actualiza la plantilla",
    "generar artefacto",
    "genera el artefacto",
    "genera artefacto",
    "crear artefacto",
    "crea el artefacto",
    "generar documento",
    "genera el documento",
    "genera documento",
    "crear documento",
    "crea el documento",
    "redacta el documento",
    "elabora el documento",
    "regenera y completa",
    "regenera el documento",
    "regenerar documento",
    "regenerar el documento",
)


def _command_intent(prompt: str) -> Optional[str]:
    """Intent named by a leading "/command", the command itself when it is not a known one."""
    first_token = prompt.split()[0][1:].lower()
    return _COMMAND_INTENTS.get(first_token, first_token) or None


def _explicit_intent(p_trimmed: str, mode: Optional[str]) -> Optional[str]:
    """The intent the client asked for with a mode or a "/command", if it did."""
    if mode and mode not in {"auto", "default"}:
        return _MODE_INTENTS.get(mode, mode)
    return _command_intent(p_trimmed) if p_trimmed.startswith("/") else None


def _keyword_intent(p_lower: str) -> Optional[str]:
    for intent, phrases in (
        ("generic_plan", _PLAN_PHRASES),
        ("generic_report", _REPORT_PHRASES),
        ("template_mutation", _TEMPLATE_PHRASES),
    ):
        if any(phrase in p_lower for phrase in phrases):
            return intent
    return None


def classify_prompt_intent_by_rules(
    prompt: str,
    mode: Optional[str] = None,
    template_id: Optional[str] = None,
    active_artifact_intent: Optional[str] = None,
) -> tuple[str, bool]:
    """Rule-based intent plus whether a rule actually decided it.

    Undecided (False): the message fell through every rule to the default "chat", or it is a
    question while a document is active (it may ask to change that document).
    """
    p_trimmed = prompt.strip()
    explicit = _explicit_intent(p_trimmed, mode)
    if explicit:
        return explicit, True

    if active_artifact_intent in ARTIFACT_INTENTS and is_artifact_follow_up(p_trimmed):
        return active_artifact_intent, True

    p_lower = p_trimmed.lower()

    # Conversational inquiries and questions should always route to conversational chat
    if _looks_like_question(p_lower):
        return "chat", active_artifact_intent not in ARTIFACT_INTENTS

    # If the user has an active corporate template selected and isn't asking a general question,
    # default to mutating/populating that template artifact directly.
    if template_id and template_id.strip():
        return "template_mutation", True

    keyword_intent = _keyword_intent(p_lower)
    return (keyword_intent, True) if keyword_intent else ("chat", False)


# Undecided messages are sent to the fast model only when they plausibly concern a document, so
# small talk ("gracias", "hola") never pays the extra call.
_DOCUMENT_HINT = re.compile(
    r"\b(documento|doc|plan|informe|reporte|plantilla|matriz|acta|especificaci[oó]n|secci[oó]n|"
    r"artefacto|formato|casos de prueba|requerimientos?|entregable|word|excel|docx|xlsx)\b",
    re.IGNORECASE,
)


def needs_model_classification(prompt: str, decided: bool, active_artifact_intent: Optional[str]) -> bool:
    if decided:
        return False
    return active_artifact_intent in ARTIFACT_INTENTS or bool(_DOCUMENT_HINT.search(prompt or ""))


_DEFAULT_TEMPLATE_MODULES = ("mejora", "funcional", "requerimiento")


def _content_and_extension(detail: Optional[Dict[str, Any]]) -> Optional[tuple[str, str]]:
    """Content and file extension of a template that has text, None for one without."""
    if not detail or not detail.get("content", "").strip():
        return None
    filename = detail.get("filename", "")
    ext = filename.rpartition(".")[2].lower() if "." in filename else "docx"
    return detail["content"].strip(), ext


async def _load_active_template_info(template_id: str | None = None) -> tuple[str, str]:
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


async def _load_active_template_content(template_id: str | None = None) -> str:
    content, _ = await _load_active_template_info(template_id)
    return content


class AgenticPromptRequest(CamelModel):
    prompt: Optional[str] = Field(None, alias="query")
    query: Optional[str] = None
    feature: Optional[str] = "mejoras_doc"
    mode: Optional[str] = "auto"
    images: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    document_state: Optional[CanonicalDocumentState] = Field(None, alias="documentState")
    current_document: Optional[str] = None
    attached_asset_ids: Optional[List[str]] = Field(default_factory=list, alias="attachedAssetIds")
    conversation_history: Optional[List[Dict[str, str]]] = Field(default_factory=list, alias="conversationHistory")
    chat_context: Optional[Union[List[str], str]] = None
    sources: Optional[List[str]] = Field(default_factory=list)
    document_ids: Optional[List[str]] = Field(default_factory=list, alias="documentIds")
    attached_docs: Optional[List[Dict[str, Any]]] = Field(default_factory=list, alias="attachedDocs")
    template_id: Optional[str] = Field(None, alias="templateId")
    run_id: Optional[str] = Field(None, alias="runId")
    conversation_id: Optional[str] = Field(None, alias="conversationId")
    # Ids generated by the client for the user turn and the reply, so server-side persistence and
    # the client autosave refer to the same rows instead of creating duplicates.
    user_message_id: Optional[str] = Field(None, alias="userMessageId", max_length=36)
    assistant_message_id: Optional[str] = Field(None, alias="assistantMessageId", max_length=36)
    provider: Optional[str] = None
    model: Optional[str] = None


    @property
    def prompt_text(self) -> str:
        return self.prompt or self.query or ""

    @property
    def doc_state(self) -> CanonicalDocumentState:
        if self.document_state:
            return self.document_state
        return CanonicalDocumentState(document_id="doc-active", title="Documento de Mejora")


class AgenticPromptResponse(CamelModel):
    intent_detected: str = "general_rag"
    requires_document_mutation: bool = True
    rag_knowledge_used: List[str] = Field(default_factory=list)
    planned_operations: List[Dict[str, Any]] = Field(default_factory=list)
    validation_status: Dict[str, Any] = Field(default_factory=lambda: {"valid": True, "details": []})
    assistant_message: str = ""
    answer: str = ""
    operations: List[Dict[str, Any]] = Field(default_factory=list)
    document_updates: Optional[str] = None


AgenticPromptRequest.model_rebuild()
AgenticPromptResponse.model_rebuild()


class ExportDocxRequest(CamelModel):
    content: str = Field(default="", alias="markdown")
    title: str = "Documento de Especificación Funcional"
    template_id: Optional[str] = Field(None, alias="templateId")
    artifact_data: Optional[Dict[str, Any]] = Field(None, alias="artifactData")

    @property
    def text(self) -> str:
        return self.content


class ExportXlsxRequest(CamelModel):
    title: str = "Matriz de Inventario y Pruebas"
    content: Optional[str] = Field(default="", alias="markdown")
    rows: Optional[List[Dict[str, Any]]] = None
    template_id: Optional[str] = Field(None, alias="templateId")
    artifact_data: Optional[Dict[str, Any]] = Field(None, alias="artifactData")

    @property
    def text(self) -> str:
        return self.content or ""


@router.get("/fixtures")
async def get_document_fixtures():
    """Returns available corporate templates as evaluation fixtures for Univer."""
    templates = await list_templates()
    fixtures = []
    for t in templates:
        filename = t.get("filename", "")
        kind = "spreadsheet" if filename.endswith((".xlsx", ".xls")) else "document"
        fixtures.append({
            "id": t.get("id"),
            "title": t.get("title"),
            "filename": filename,
            "kind": kind,
            "tags": t.get("tags", []),
        })
    return {"fixtures": fixtures}


@router.post("/parse-attachment")
async def parse_chat_attachment(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Parses a document (DOCX, PDF, TXT, MD, XLSX) attached in chat into plain Markdown text.
    Does NOT store or ingest into the permanent knowledge base.
    """
    filename = file.filename or "archivo.txt"
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="El archivo adjunto está vacío.")
    try:
        extracted = extract_text(filename=filename, raw=raw)
        return {
            "filename": filename,
            "content": extracted,
            "char_count": len(extracted),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo extraer texto de {filename}: {exc}")


@router.post("/validate")
def validate_operation(payload: Dict[str, Any]):
    """Validates a proposed canonical operation against current document state."""
    state_data = payload.get("state") or payload.get("documentState")
    op_data = payload.get("operation")
    if not state_data or not op_data:
        raise HTTPException(status_code=400, detail="Missing 'state' or 'operation' in payload.")

    state = CanonicalDocumentState(**state_data)
    op_type = op_data.get("operation")

    if op_type == "insert_image":
        op = InsertImageOperation(**op_data)
    elif op_type == "insert_text":
        op = InsertTextOperation(**op_data)
    elif op_type == "replace_content":
        op = ReplaceContentOperation(**op_data)
    else:
        op = op_data

    valid, message = DocumentOperationValidator.validate(op, state)
    return {"valid": valid, "message": message}



HISTORY_DB_LIMIT = 60


async def _resolve_chat_history(
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

_IMAGE_WORDS = ("imágenes", "imagen", "imagenes", "image", "captura", "screenshot")
_OBSERVACION_WORDS = ("observación", "observaciones", "observacion")
_CORRECTION_WORDS = (
    "corregir", "corrección", "correccion", "corrijas", "corregí", "corregi",
    "cambia", "cambiar", "modifica", "modificar", "actualiza", "actualizar",
    "no es", "erróneo", "erroneo", "incorrecto", "reemplaza", "sustituye",
)
_RESPONSABLES_WORDS = ("responsable", "responsables", "participante", "participantes", "firmas", "pepito", "doctor", "dr")
_SIGNATURE_WORDS = ("pepito", "lider", "líder", "funcional", "responsable", "rol", "firmas")
_DEFAULT_ASSET_IDS = ["img_error_login", "img_flujo_alterno"]


def _mentions(prompt_lower: str, words: tuple[str, ...]) -> bool:
    return any(w in prompt_lower for w in words)


def _asks_a_question(prompt_str: str, active_intent: Optional[str]) -> bool:
    """A question, or a request to rebuild the open document: both go to the LLM, never to the fast handlers.

    "regenera", "el documento está vacío"... would otherwise be taken by the keyword handlers
    ("no es" or "corrige" read as a field correction).
    """
    follow_up = active_intent is not None and is_artifact_follow_up(prompt_str)
    return follow_up or _looks_like_question(prompt_str.strip().lower())


def _is_image_request(prompt_lower: str, is_question: bool) -> bool:
    return not is_question and _mentions(prompt_lower, _IMAGE_WORDS) and _mentions(prompt_lower, _OBSERVACION_WORDS)


def _is_correction_request(prompt_lower: str, is_question: bool) -> bool:
    return not is_question and _mentions(prompt_lower, _CORRECTION_WORDS)


def _is_responsables_request(prompt_lower: str, is_question: bool) -> bool:
    return not is_question and _mentions(prompt_lower, _RESPONSABLES_WORDS)


def _is_fast_operation(prompt_str: str, active_intent: Optional[str]) -> bool:
    """Whether the message is one of the structured operations answered without the LLM."""
    prompt_lower = prompt_str.strip().lower()
    is_question = _asks_a_question(prompt_str, active_intent)
    return (
        _is_image_request(prompt_lower, is_question)
        or _is_correction_request(prompt_lower, is_question)
        or _is_responsables_request(prompt_lower, is_question)
    )


def _operations_response(
    intent: str, knowledge: str, operations: list, validation: tuple[bool, list[str]], message: str,
) -> AgenticPromptResponse:
    ops_dump = [op.model_dump(by_alias=True) for op in operations]
    is_valid, details = validation
    return AgenticPromptResponse(
        intent_detected=intent,
        requires_document_mutation=True,
        rag_knowledge_used=[knowledge],
        planned_operations=ops_dump,
        operations=ops_dump,
        validation_status={"valid": is_valid, "details": details},
        assistant_message=message,
        answer=message,
    )


def _image_operation(position: int, asset_id: str) -> InsertImageOperation:
    caption = f"Evidencia visual #{position} para Observaciones"
    target = TargetLocator(
        section_title="Observaciones", tag="{{OBSERVACIONES}}", position="inside_end", paragraph_index=position,
    )
    asset = AssetLocator(asset_id=asset_id, url=f"/assets/demo/{asset_id}.png", caption=caption, width=480)
    return InsertImageOperation(operation="insert_image", target=target, asset=asset)


def _image_response(req: "AgenticPromptRequest") -> AgenticPromptResponse:
    """Plan the insertion of the attached images in the Observaciones section."""
    asset_ids = req.attached_asset_ids or _DEFAULT_ASSET_IDS
    planned_ops = [_image_operation(position, asset_id) for position, asset_id in enumerate(asset_ids, start=1)]
    results = [DocumentOperationValidator.validate(op, req.doc_state, asset_ids) for op in planned_ops]
    message = f"He procesado tu solicitud y planificado la inserción de {len(planned_ops)} imagen(es) en la sección de 'Observaciones'."
    return _operations_response(
        "insert_asset_in_section",
        "Plantilla Corporativa: Sección Observaciones y Casos de Borde",
        planned_ops,
        (all(valid for valid, _ in results), [msg for _, msg in results]),
        message,
    )


def _correction_operation(prompt_str: str, prompt_lower: str) -> tuple[ReplaceContentOperation, str]:
    """The replacement a correction message asks for, with the message that tells the user."""
    if _mentions(prompt_lower, ("pepito", "lider", "líder")):
        op = ReplaceContentOperation(
            operation="replace_content",
            target=TargetLocator(section_title="Firmas y Responsables", tag="{{FIRMAS}}", position="replace_target"),
            new_content="| Usuario Funcional | Dr. Pepito Pérez | Aprobado |",
        )
        return op, "He corregido el rol del Dr. Pepito Pérez en la sección de Responsables y Firmas, actualizándolo de 'Líder Funcional' a 'Usuario Funcional'."
    section, tag_name = ("Firmas", "FIRMAS") if _mentions(prompt_lower, _SIGNATURE_WORDS) else ("Solución", "SOLUCION")
    op = ReplaceContentOperation(
        operation="replace_content",
        target=TargetLocator(section_title=section, tag=f"{{{{{tag_name}}}}}"),
        new_content=f"Corrección aplicada: {prompt_str}",
    )
    return op, f"He aplicado la corrección en la sección de '{section}'."


def _correction_response(req: "AgenticPromptRequest", prompt_str: str, prompt_lower: str) -> AgenticPromptResponse:
    op, message = _correction_operation(prompt_str, prompt_lower)
    is_valid, detail = DocumentOperationValidator.validate(op, req.doc_state)
    return _operations_response(
        "correct_document_content", "Matriz de Roles y Responsabilidades QA MGMT", [op], (is_valid, [detail]), message,
    )


def _responsables_response(req: "AgenticPromptRequest", prompt_lower: str) -> AgenticPromptResponse:
    role = "Usuario Funcional" if _mentions(prompt_lower, ("usuario", "funcional")) else "Líder Funcional"
    named = _mentions(prompt_lower, ("pepito", "perez", "pérez"))
    name = "Dr. Pepito Pérez" if named else "Participante Asignado"
    op = InsertTextOperation(
        operation="insert_text",
        target=TargetLocator(section_title="Firmas y Responsables", tag="{{FIRMAS}}", position="inside_end"),
        content=f"| {role} | {name} | Aprobado |",
    )
    is_valid, detail = DocumentOperationValidator.validate(op, req.doc_state)
    message = f"He agregado exitosamente a {name} con el rol '{role}' en la tabla de Responsables y Firmas."
    return _operations_response(
        "add_responsables", "Estructura Organizacional del Proyecto", [op], (is_valid, [detail]), message,
    )


def _fast_operation_response(
    req: "AgenticPromptRequest", prompt_str: str, active_intent: Optional[str]
) -> Optional[AgenticPromptResponse]:
    """Answer image, correction and responsables requests with structured operations, or None."""
    prompt_lower = prompt_str.strip().lower()
    is_question = _asks_a_question(prompt_str, active_intent)
    if _is_image_request(prompt_lower, is_question):
        return _image_response(req)
    if _is_correction_request(prompt_lower, is_question):
        return _correction_response(req, prompt_str, prompt_lower)
    if _is_responsables_request(prompt_lower, is_question):
        return _responsables_response(req, prompt_lower)
    return None


@router.post("/agentic-prompt", response_model=AgenticPromptResponse)
async def handle_agentic_prompt(
    req: AgenticPromptRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    chat_repo: ChatRepository = Depends(get_chat_repository),
):
    """
    Agentic RAG orchestrator for document requests.
    Translates raw user prompt + RAG/Document context into structured canonical operations.
    Supports insertions, image attachments, corrections, and modifications.
    """
    user_id = current_user["id"]
    prompt_str = req.prompt_text
    active_intent = await _resolve_active_artifact_intent(req, chat_repo, user_id)

    fast_response = _fast_operation_response(req, prompt_str, active_intent)
    if fast_response:
        return fast_response

    # Intelligent Agentic Chat, Plan/Report Artifacts, or Template Generation
    prepared = await _prepare_chat_run(req, chat_repo, user_id, active_intent)
    cfg = prepared.cfg
    cfg.run_info["protocol"] = "json"

    try:
        accumulated: list[str] = []
        async for chunk in run_agentic_chat_stream(cfg):
            if isinstance(chunk, str):  # typed AgentEvents only matter to streaming clients
                accumulated.append(chunk)
    except Exception as err:
        _log_request_failure(cfg, err, streamed=False)
        raise HTTPException(status_code=502, detail=_format_stream_error(err)) from err

    full_content = "".join(accumulated)
    outcome = _finalize_answer(full_content, prepared)
    conv_id = req.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    await _persist_turn(
        chat_repo,
        req=req,
        user_id=user_id,
        conv_id=conv_id,
        user_text=prompt_str,
        prepared=prepared,
        outcome=outcome,
        full_content=full_content,
    )

    return AgenticPromptResponse(
        intent_detected=prepared.intent,
        requires_document_mutation=outcome.is_template,
        rag_knowledge_used=prepared.sources,
        planned_operations=[],
        operations=[],
        validation_status={"valid": True, "details": ["Agentic generation successful."]},
        assistant_message=outcome.assistant_message,
        answer=full_content,
        document_updates=full_content if outcome.is_template else None,
    )


# ---------------------------------------------------------------------------
# Shared helpers for the agentic chat endpoints
# ---------------------------------------------------------------------------


async def _resolve_active_artifact_intent(
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
class _PreparedRun:
    cfg: AgenticChatConfig
    intent: str
    query_text: str
    sources: List[str]
    template_ext: str


@dataclass
class _AnswerOutcome:
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


async def _prepare_chat_run(
    req: "AgenticPromptRequest",
    chat_repo: ChatRepository,
    user_id: str | None,
    active_intent: Optional[str],
) -> _PreparedRun:
    """Validate the request and build the runner configuration (shared by both endpoints)."""
    _reject_unsupported_model(req)
    prompt_str = req.prompt_text
    chat_ctx_str = _chat_context_text(req.chat_context)
    chat_history = await _resolve_chat_history(req, chat_repo, user_id)

    sources_to_use = req.sources or ["knowledge"]
    intent, intent_info = await _resolve_intent(req, user_id, active_intent)
    query_text = _strip_command(prompt_str)
    template_content, template_ext = await _load_active_template_info(req.template_id)
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
    return _PreparedRun(cfg=cfg, intent=intent, query_text=query_text, sources=sources_to_use, template_ext=template_ext)


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


def _finalize_answer(full_content: str, prepared: _PreparedRun) -> _AnswerOutcome:
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
    return _AnswerOutcome(
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


async def _persist_turn(
    chat_repo: ChatRepository,
    *,
    req: "AgenticPromptRequest",
    user_id: str | None,
    conv_id: str,
    user_text: str,
    prepared: _PreparedRun,
    outcome: _AnswerOutcome,
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


def _log_request_failure(cfg: AgenticChatConfig, err: BaseException, *, streamed: bool, stage: str | None = None) -> None:
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


def _error_code(err: BaseException) -> str:
    return err.code if isinstance(err, AIError) else "run_exception"


CANCEL_POLL_S = 0.5


def _data_line(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


class _ChatStream:
    """One streamed chat run: turns the runner's chunks into the v1 (legacy) or v2 (named events) wire format."""

    def __init__(
        self,
        request: Request,
        req: AgenticPromptRequest,
        chat_repo: ChatRepository,
        user_id: str | None,
        prepared: _PreparedRun,
        v2: bool,
    ) -> None:
        self.request = request
        self.req = req
        self.chat_repo = chat_repo
        self.user_id = user_id
        self.prepared = prepared
        self.cfg = prepared.cfg
        self.v2 = v2
        self.run_id = req.run_id or f"run-{uuid.uuid4().hex[:12]}"
        self.conv_id = req.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
        self.emitter = AgentRunEmitter(run_id=self.run_id, conversation_id=self.conv_id)
        run_registry.register(self.emitter)
        self.last_disconnect_check = 0.0
        self.accumulated: List[str] = []
        self.splitter = ArtifactStreamSplitter()

    async def should_stop(self) -> Optional[str]:
        if self.emitter.is_cancelled:
            return "cancelled"
        now = time.monotonic()
        if now - self.last_disconnect_check >= CANCEL_POLL_S:
            self.last_disconnect_check = now
            if await self.request.is_disconnected():
                self.emitter.request_cancellation(reason="Client disconnected")
                return "disconnected"
        return None

    def _v1_packets_for(self, event: AIAgentEvent) -> List[str]:
        """Map typed runner events onto the legacy step events the v1 client understands."""
        emitter = self.emitter
        data = event.data
        if event.type == "tool_call":
            return [emitter.step_started(f"step-tool-{data.get('id', '')}", f"Usando herramienta: {data.get('name')}").to_sse_packet()]
        if event.type == "tool_result":
            return [emitter.step_completed(f"step-tool-{data.get('id', '')}", f"Herramienta {data.get('name')} finalizada").to_sse_packet()]
        if event.type == "plan":
            sections = data.get("sections") or []
            return [
                emitter.step_started(f"step-section-{i}", f"Sección: {title}").to_sse_packet()
                for i, title in enumerate(sections)
            ]
        if event.type == "status" and data.get("stage") == "section":
            index = data.get("section_index", 0)
            label = f"Sección: {data.get('section_title', '')}"
            if data.get("pending"):
                return [emitter.step_failed(f"step-section-{index}", label, "Sección pendiente").to_sse_packet()]
            return [emitter.step_completed(f"step-section-{index}", label).to_sse_packet()]
        return []

    def _opening_packets(self) -> List[str]:
        intent = self.prepared.intent
        if self.v2:
            return [sse_event("status", {
                "message": "Intención detectada",
                "stage": "classify",
                "intent": intent,
                "run_id": self.run_id,
                "conversation_id": self.conv_id,
            })]
        emitter = self.emitter
        return [
            emitter.started(task_profile=intent, prompt=self.prepared.query_text).to_sse_packet(),
            emitter.step_started("step-classify", "Clasificando intención...").to_sse_packet(),
            _data_line({"type": "intent", "intent": intent}),
            emitter.step_completed("step-classify", f"Intención: {intent}").to_sse_packet(),
            emitter.step_started("step-generate", "Generando contenido...").to_sse_packet(),
        ]

    def _chunk_packets(self, chunk: Any) -> List[str]:
        if isinstance(chunk, AIAgentEvent):
            return [chunk.to_sse()] if self.v2 else self._v1_packets_for(chunk)
        self.accumulated.append(chunk)
        if self.v2:
            return [sse_event(event_type, data) for event_type, data in self.splitter.feed(chunk)]
        return [self.emitter.message_delta(chunk).to_sse_packet(), _data_line({"type": "token", "text": chunk})]

    def _splitter_close_packets(self) -> List[str]:
        if not self.v2:
            return []
        return [sse_event(event_type, data) for event_type, data in self.splitter.close()]

    def _empty_response_packets(self) -> List[str]:
        err_text = "El modelo LLM no generó contenido. Verifica tu conexión o clave de API en Configuración."
        if self.v2:
            return [sse_event("error", {"code": "empty_response", "message": err_text})]
        return [self.emitter.failed("EMPTY_RESPONSE", err_text).to_sse_packet(), _data_line({"type": "error", "message": err_text})]

    def _artifact_packet(self, position: int, art: Dict[str, Any]) -> str:
        artifact_id = art.get("id") or f"art-{position}"
        return self.emitter.artifact_created(
            artifact_id=artifact_id,
            title=art.get("title", "Documento"),
            content=art.get("content", ""),
            extension=art.get("extension", "docx"),
        ).to_sse_packet()

    def _summary_packets(self, outcome: _AnswerOutcome) -> tuple[List[str], Optional[float]]:
        """Artifact, rubric and completion packets of the legacy protocol, plus the artifacts' rubric score."""
        art_dicts = outcome.artifacts
        rubric_score = _evaluate_artifacts_rubric(art_dicts)[0] if art_dicts else None
        if self.v2:
            return [], rubric_score
        emitter = self.emitter
        packets = [self._artifact_packet(position, art) for position, art in enumerate(art_dicts, start=1)]
        packets.append(emitter.step_completed("step-generate", "Generación completada").to_sse_packet())
        if art_dicts:
            packets.append(emitter.step_started("step-rubric", "Evaluando artefactos con rúbricas de calidad...").to_sse_packet())
            packets.append(emitter.step_completed("step-rubric", f"Calidad de artefacto: {rubric_score}/100").to_sse_packet())
        packets.append(emitter.completed(
            final_message=outcome.assistant_message, artifacts=art_dicts, sources=self.prepared.sources,
        ).to_sse_packet())
        return packets, rubric_score

    def _final_packets(self, full_content: str, outcome: _AnswerOutcome, rubric_score: Optional[float]) -> List[str]:
        answer_clean = outcome.clean_answer or full_content
        final_response = {
            "answer": full_content,
            "intent_detected": self.prepared.intent,
            "requires_document_mutation": outcome.is_template,
            "document_updates": full_content if outcome.is_template else None,
            "answer_clean": answer_clean,
            "assistant_message": outcome.assistant_message,
            "artifacts": outcome.artifacts,
            "run_id": self.run_id,
            "conversation_id": self.conv_id,
            "route": self.cfg.run_info.get("route"),
            "truncated": bool(self.cfg.run_info.get("truncated")),
            "rubric_score": rubric_score,
        }
        if self.v2:
            return [sse_event("done", final_response)]
        return [_data_line({"type": "full", "data": final_response}), _data_line({"type": "done"})]

    def _stopped_packets(self, stop: StreamStopped) -> List[str]:
        # The runner was cancelled inside its task and already logged the cancellation.
        # "disconnected": nobody is listening, nothing to send.
        if stop.reason != "cancelled":
            return []
        if self.v2:
            return [sse_event("error", {"code": "cancelled", "message": "Cancelado por el usuario"})]
        return [self.emitter.cancelled("Cancelado por el usuario").to_sse_packet()]

    def _failure_packets(self, err: Exception) -> List[str]:
        _log_request_failure(self.cfg, err, streamed=True)
        err_msg = _format_stream_error(err)
        if self.v2:
            return [sse_event("error", {
                "code": _error_code(err),
                "message": err_msg,
                "retry_after": getattr(err, "retry_after", None),
            })]
        return [self.emitter.failed("RUN_EXCEPTION", err_msg).to_sse_packet(), _data_line({"type": "error", "message": err_msg})]

    async def _complete(self, full_content: str):
        outcome = _finalize_answer(full_content, self.prepared)
        packets, rubric_score = self._summary_packets(outcome)
        for packet in packets:
            yield packet
        await _persist_turn(
            self.chat_repo,
            req=self.req,
            user_id=self.user_id,
            conv_id=self.conv_id,
            user_text=self.prepared.query_text,
            prepared=self.prepared,
            outcome=outcome,
            full_content=full_content,
        )
        for packet in self._final_packets(full_content, outcome, rubric_score):
            yield packet

    async def _run(self):
        for packet in self._opening_packets():
            yield packet
        runner = run_agentic_chat_stream(self.cfg)
        async for chunk in iterate_until_stopped(runner, self.should_stop, poll_s=CANCEL_POLL_S):
            for packet in self._chunk_packets(chunk):
                yield packet
        for packet in self._splitter_close_packets():
            yield packet

        full_content = "".join(self.accumulated)
        if not full_content.strip():
            for packet in self._empty_response_packets():
                yield packet
            return
        async for packet in self._complete(full_content):
            yield packet

    async def stream(self):
        try:
            async for packet in self._run():
                yield packet
        except StreamStopped as stop:
            for packet in self._stopped_packets(stop):
                yield packet
        except Exception as err:
            for packet in self._failure_packets(err):
                yield packet
        finally:
            run_registry.unregister(self.run_id)


def _fast_operation_stream(response: AgenticPromptResponse, v2: bool) -> StreamingResponse:
    async def fast_gen():
        payload = response.model_dump(by_alias=True)
        yield sse_event("done", payload) if v2 else _data_line({"type": "full", "data": payload})

    return StreamingResponse(fast_gen(), media_type="text/event-stream")


@router.post("/agentic-prompt-stream")
async def handle_agentic_prompt_stream(
    request: Request,
    req: AgenticPromptRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    chat_repo: ChatRepository = Depends(get_streaming_chat_repository),
    protocol: str = "v1",
):
    """
    Streaming SSE endpoint for dynamic Agentic multimodal chat, Q&A, and artifacts.

    `protocol=v1` (default, legacy): `data:` lines with run.* envelopes plus `token`/`full` packets.
    `protocol=v2`: named events — status, plan, delta, artifact_start/artifact_delta/artifact_end,
    tool_call, tool_result, usage, error and a final `done` carrying the full response.
    """
    user_id = current_user["id"]
    v2 = protocol == "v2"
    active_intent = await _resolve_active_artifact_intent(req, chat_repo, user_id)

    # Fast non-LLM structured operations (image insertion, corrections, responsibles)
    if _is_fast_operation(req.prompt_text, active_intent):
        res = await handle_agentic_prompt(req, current_user=current_user, chat_repo=chat_repo)
        return _fast_operation_stream(res, v2)

    prepared = await _prepare_chat_run(req, chat_repo, user_id, active_intent)
    prepared.cfg.run_info["protocol"] = "v2" if v2 else "v1"
    return StreamingResponse(
        _ChatStream(request, req, chat_repo, user_id, prepared, v2).stream(), media_type="text/event-stream",
    )


def _try_parse_structured_artifact(
    content: str, title: str
) -> Optional[Union[FunctionalImprovementArtifact, FunctionalInventoryArtifact]]:
    json_str = _json_object_text(content)
    if not json_str:
        return None

    try:
        data = json.loads(json_str)
        data.setdefault("artifact_id", f"art-{uuid.uuid4().hex[:8]}")
        data.setdefault("title", title or "Documento")
        return _structured_artifact_from(data)
    except Exception:
        return None


def _json_object_text(content: str) -> Optional[str]:
    """The JSON object a model answer is, or the one inside its ```json fence."""
    trimmed = content.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        return trimmed
    match = re.search(r"```json\s*(\{.*?\})\s*```", trimmed, re.DOTALL) if "```json" in trimmed else None
    return match.group(1) if match else None


def _structured_artifact_from(
    data: Dict[str, Any],
) -> Optional[Union[FunctionalImprovementArtifact, FunctionalInventoryArtifact]]:
    if "problem_statement" in data or "acceptance_criteria" in data:
        return FunctionalImprovementArtifact(**data)
    if "modules" in data or "project_name" in data:
        return FunctionalInventoryArtifact(**data)
    return None


def _evaluate_artifacts_rubric(art_dicts: List[Dict[str, Any]]) -> tuple[float, str]:
    if not art_dicts:
        return 100.0, "Sin artefactos estructurados"

    scores: List[float] = []
    feedbacks: List[str] = []
    for art in art_dicts:
        score, missing = _rubric_for_artifact(art)
        scores.append(score)
        feedbacks.extend(missing)

    avg_score = round(sum(scores) / len(scores), 1)
    feedback_str = "; ".join(feedbacks) if feedbacks else "Artefactos aprobados por rúbrica."
    return avg_score, feedback_str


def _rubric_for_artifact(art: Dict[str, Any]) -> tuple[float, List[str]]:
    """Rubric score of one artifact and what it is missing; free text only scores by its length."""
    content = art.get("content", "")
    parsed = _try_parse_structured_artifact(content, art.get("title", ""))
    if isinstance(parsed, FunctionalImprovementArtifact):
        res = RubricEvaluator.evaluate_improvement(parsed)
    elif isinstance(parsed, FunctionalInventoryArtifact):
        res = RubricEvaluator.evaluate_inventory(parsed)
    else:
        return (85.0 if len(content.strip()) >= 50 else 50.0), []
    return res.score, ([] if res.approved else res.missing_requirements)


def _resolve_export_data(
    content: str, artifact_data: Optional[Dict[str, Any]], title: str
) -> Dict[str, Any]:
    if artifact_data:
        data = dict(artifact_data)
        data.setdefault("title", title)
        return data

    try:
        parsed = json.loads((content or "").strip())
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        parsed.setdefault("title", title)
        return parsed

    return {"title": title, "content": content, "markdown": content}


def _generate_docx_bytes(req: ExportDocxRequest) -> bytes:
    data = _resolve_export_data(req.content, req.artifact_data, req.title)
    if req.template_id:
        tmpl_path = get_template_file_path(req.template_id)
        if tmpl_path and tmpl_path.suffix.lower() == ".docx":
            return DocxTemplateRenderer.render(tmpl_path, data)

    title_lower = req.title.lower()
    if "levantamiento" in title_lower:
        return create_levantamiento_docx(req.text, title=req.title)
    return create_mejoras_docx(req.text, title=req.title)


def _generate_xlsx_bytes(req: ExportXlsxRequest) -> bytes:
    data = _resolve_export_data(req.text, req.artifact_data, req.title)
    if req.rows:
        data["rows"] = req.rows

    if req.template_id:
        tmpl_path = get_template_file_path(req.template_id)
        if tmpl_path and tmpl_path.suffix.lower() == ".xlsx":
            return XlsxTemplateRenderer.render(tmpl_path, data)

    title_lower = req.title.lower()
    if "inventario" in title_lower or req.text:
        return create_inventario_xlsx(markdown_content=req.text, title=req.title, rows=req.rows)
    return create_qa_matrix_xlsx(title=req.title, rows=req.rows)


def _format_stream_error(err: Exception) -> str:
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


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(run_id: str):
    if not run_registry.cancel_run(run_id, reason="User cancelled run"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {"status": "cancelled", "run_id": run_id}


@router.post("/sessions/{session_id}/cancel")
async def cancel_session_run(session_id: str):
    if not run_registry.cancel_run(session_id, reason="User cancelled run for session"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' has no active run")
    return {"status": "cancelled", "session_id": session_id}


@router.post("/export-docx")
def export_native_docx(req: ExportDocxRequest):
    """Generates and downloads a native Microsoft Word .docx binary file."""
    try:
        docx_bytes = _generate_docx_bytes(req)
        safe_title = re.sub(r'[^a-zA-Z0-9_\-]', '_', req.title)
        filename = f"{safe_title}.docx"

        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
        )
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Error al generar archivo DOCX: {str(err)}")


@router.post("/export-xlsx")
def export_native_xlsx(req: ExportXlsxRequest):
    """Genera y descarga un archivo Excel .xlsx nativo para inventarios de requerimientos o matrices QA."""
    try:
        xlsx_bytes = _generate_xlsx_bytes(req)
        safe_title = re.sub(r'[^a-zA-Z0-9_\-]', '_', req.title)
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.xlsx"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generando XLSX: {exc}") from exc


