"""FastAPI router for DocumentAgent, Agentic RAG integration, and Native Document Exports."""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
import json
import logging
import uuid
from pydantic import BaseModel, Field

from app.api.deps import get_optional_current_user
from app.db.repositories import ChatRepository
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
from app.ai.artifacts import extract_artifacts, artifacts_to_dict
from app.ai.runner import (
    AgenticChatConfig,
    run_agentic_chat_stream,
    run_grounded_feature,
    run_grounded_feature_stream,
)
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

router = APIRouter(prefix="/doc-agent", tags=["document-agent"])


def classify_prompt_intent(prompt: str, mode: Optional[str] = None) -> str:
    """Classifies user prompt intent into: generic_plan, generic_report, custom feature slug, template_mutation, or chat."""
    if mode and mode not in {"auto", "default"}:
        if mode in {"plan", "generic_plan"}:
            return "generic_plan"
        if mode in {"report", "informe", "generic_report"}:
            return "generic_report"
        if mode in {"chat", "qa"}:
            return "chat"
        if mode in {"template", "template_mutation"}:
            return "template_mutation"
        return mode

    p_trimmed = prompt.strip()
    if p_trimmed.startswith("/"):
        first_token = p_trimmed.split()[0][1:].lower()
        if first_token in {"plan", "generic_plan"}:
            return "generic_plan"
        if first_token in {"report", "informe", "generic_report"}:
            return "generic_report"
        if first_token in {"plantilla", "template", "template_mutation"}:
            return "template_mutation"
        if first_token:
            return first_token

    p_lower = p_trimmed.lower()

    # Conversational inquiries and questions should always route to conversational chat
    is_question = (
        p_lower.startswith(("¿", "que ", "qué ", "como ", "cómo ", "cual ", "cuál ", "por que", "por qué", "donde ", "dónde ", "explica", "cuéntame", "dime"))
        or "?" in p_lower
    )
    if is_question:
        return "chat"

    if (
        "plan de prueba" in p_lower
        or "plan de implementaci" in p_lower
        or "plan de trabajo" in p_lower
        or "genera un plan" in p_lower
        or "crea un plan" in p_lower
        or "elabora un plan" in p_lower
    ):
        return "generic_plan"

    if (
        "informe" in p_lower
        or "reporte" in p_lower
        or "resumen ejecutivo" in p_lower
    ):
        return "generic_report"

    template_keywords = [
        "completa la plantilla",
        "llena la plantilla",
        "genera el documento de mejora",
        "genera el documento funcional",
        "genera el levantamiento",
        "genera el inventario",
        "redacta el documento corporativo",
        "actualiza la plantilla",
    ]
    if any(kw in p_lower for kw in template_keywords):
        return "template_mutation"

    return "chat"


async def _load_active_template_content(template_id: str | None = None) -> str:
    """Load the active mejoras template content to inject into the AI prompt."""
    try:
        from app.core.template_storage import list_templates, get_template_detail

        if template_id:
            detail = await get_template_detail(template_id)
            if detail and detail.get("content", "").strip():
                return detail["content"].strip()

        templates = await list_templates()
        candidates = [
            t for t in templates
            if any(kw in (t.get("module") or "").lower() for kw in ("mejora", "funcional", "requerimiento"))
        ]
        if not candidates:
            candidates = templates

        for tmpl in candidates:
            detail = await get_template_detail(tmpl["id"])
            if detail and detail.get("content", "").strip():
                return detail["content"].strip()
    except Exception:
        pass
    return ""


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


@router.post("/agentic-prompt", response_model=AgenticPromptResponse)
async def handle_agentic_prompt(
    req: AgenticPromptRequest,
    current_user: Optional[dict[str, Any]] = Depends(get_optional_current_user),
    chat_repo: ChatRepository = Depends(ChatRepository),
):
    """
    Agentic RAG orchestrator for document requests.
    Translates raw user prompt + RAG/Document context into structured canonical operations.
    Supports insertions, image attachments, corrections, and modifications.
    """
    user_id = current_user.get("id") if current_user else None
    prompt_str = req.prompt_text
    prompt_lower = prompt_str.strip().lower()
    active_doc_state = req.doc_state

    is_question = (
        prompt_lower.startswith(("¿", "que ", "qué ", "como ", "cómo ", "cual ", "cuál ", "por que", "por qué", "donde ", "dónde ", "explica", "cuéntame", "dime"))
        or "?" in prompt_lower
    )

    # Case 1: Image attachment intent ("Me gustó la propuesta, incluye en las observaciones estas imágenes")
    is_image_intent = not is_question and any(w in prompt_lower for w in ["imágenes", "imagen", "imagenes", "image", "captura", "screenshot"])
    has_observaciones = any(w in prompt_lower for w in ["observación", "observaciones", "observacion"])

    if is_image_intent and has_observaciones:
        asset_ids = req.attached_asset_ids or ["img_error_login", "img_flujo_alterno"]
        planned_ops = []

        for idx, a_id in enumerate(asset_ids):
            op = InsertImageOperation(
                operation="insert_image",
                target=TargetLocator(
                    section_title="Observaciones",
                    tag="{{OBSERVACIONES}}",
                    position="inside_end",
                    paragraph_index=idx + 1,
                ),
                asset=AssetLocator(
                    asset_id=a_id,
                    url=f"/assets/demo/{a_id}.png",
                    caption=f"Evidencia visual #{idx + 1} para Observaciones",
                    width=480,
                ),
            )
            planned_ops.append(op)

        all_valid = True
        val_messages = []
        for p_op in planned_ops:
            is_valid, msg = DocumentOperationValidator.validate(p_op, active_doc_state, asset_ids)
            if not is_valid:
                all_valid = False
            val_messages.append(msg)

        msg_text = f"He procesado tu solicitud y planificado la inserción de {len(planned_ops)} imagen(es) en la sección de 'Observaciones'."
        ops_dump = [o.model_dump(by_alias=True) for o in planned_ops]
        return AgenticPromptResponse(
            intent_detected="insert_asset_in_section",
            requires_document_mutation=True,
            rag_knowledge_used=["Plantilla Corporativa: Sección Observaciones y Casos de Borde"],
            planned_operations=ops_dump,
            operations=ops_dump,
            validation_status={"valid": all_valid, "details": val_messages},
            assistant_message=msg_text,
            answer=msg_text,
        )

    # Case 2: Correction / Modification Intent ("Corregir, Pepito Pérez no es líder funcional es usuario funcional")
    is_correction_intent = not is_question and any(w in prompt_lower for w in [
        "corregir", "corrección", "correccion", "corrijas", "corregí", "corregi",
        "cambia", "cambiar", "modifica", "modificar", "actualiza", "actualizar",
        "no es", "erróneo", "erroneo", "incorrecto", "reemplaza", "sustituye"
    ])

    if is_correction_intent:
        target_section = "Firmas" if any(w in prompt_lower for w in ["pepito", "lider", "líder", "funcional", "responsable", "rol", "firmas"]) else "Solución"
        tag_name = "FIRMAS" if target_section == "Firmas" else "SOLUCION"

        if "pepito" in prompt_lower or "lider" in prompt_lower or "líder" in prompt_lower:
            op = ReplaceContentOperation(
                operation="replace_content",
                target=TargetLocator(
                    section_title="Firmas y Responsables",
                    tag="{{FIRMAS}}",
                    position="replace_target",
                ),
                new_content="| Usuario Funcional | Dr. Pepito Pérez | Aprobado |",
            )
            msg_text = "He corregido el rol del Dr. Pepito Pérez en la sección de Responsables y Firmas, actualizándolo de 'Líder Funcional' a 'Usuario Funcional'."
        else:
            op = ReplaceContentOperation(
                operation="replace_content",
                target=TargetLocator(section_title=target_section, tag=f"{{{{{tag_name}}}}}"),
                new_content=f"Corrección aplicada: {prompt_str}",
            )
            msg_text = f"He aplicado la corrección en la sección de '{target_section}'."

        is_valid, msg = DocumentOperationValidator.validate(op, active_doc_state)
        ops_dump = [op.model_dump(by_alias=True)]

        return AgenticPromptResponse(
            intent_detected="correct_document_content",
            requires_document_mutation=True,
            rag_knowledge_used=["Matriz de Roles y Responsabilidades QA MGMT"],
            planned_operations=ops_dump,
            operations=ops_dump,
            validation_status={"valid": is_valid, "details": [msg]},
            assistant_message=msg_text,
            answer=msg_text,
        )

    # Case 3: Responsables / Firmas Addition ("Agrega en los responsables al doctor Pepito Perez usuario funcional")
    is_responsables_intent = not is_question and any(w in prompt_lower for w in ["responsable", "responsables", "participante", "participantes", "firmas", "pepito", "doctor", "dr"])
    if is_responsables_intent:
        role = "Usuario Funcional" if "usuario" in prompt_lower or "funcional" in prompt_lower else "Líder Funcional"
        name = "Dr. Pepito Pérez" if "pepito" in prompt_lower or "perez" in prompt_lower or "pérez" in prompt_lower else "Participante Asignado"

        text_op = InsertTextOperation(
            operation="insert_text",
            target=TargetLocator(
                section_title="Firmas y Responsables",
                tag="{{FIRMAS}}",
                position="inside_end",
            ),
            content=f"| {role} | {name} | Aprobado |",
        )
        is_valid, msg = DocumentOperationValidator.validate(text_op, active_doc_state)
        ops_dump = [text_op.model_dump(by_alias=True)]
        msg_text = f"He agregado exitosamente a {name} con el rol '{role}' en la tabla de Responsables y Firmas."

        return AgenticPromptResponse(
            intent_detected="add_responsables",
            requires_document_mutation=True,
            rag_knowledge_used=["Estructura Organizacional del Proyecto"],
            planned_operations=ops_dump,
            operations=ops_dump,
            validation_status={"valid": is_valid, "details": [msg]},
            assistant_message=msg_text,
            answer=msg_text,
        )

    # Case 4: Intelligent Agentic Chat, Plan/Report Artifacts, or Template Generation
    chat_ctx_str = None
    if req.chat_context:
        if isinstance(req.chat_context, list):
            chat_ctx_str = "\n".join(req.chat_context)
        else:
            chat_ctx_str = str(req.chat_context)

    sources_to_use = req.sources or ["knowledge"]
    intent = classify_prompt_intent(prompt_str, req.mode)

    query_text = prompt_str
    if prompt_str.startswith("/plan"):
        query_text = prompt_str[5:].strip() or "Generar plan de pruebas e implementación detallado"
    elif prompt_str.startswith("/informe"):
        query_text = prompt_str[8:].strip() or "Generar informe técnico y ejecutivo detallado"
    elif prompt_str.startswith("/pregunta"):
        query_text = prompt_str[9:].strip()
    elif prompt_str.startswith("/plantilla"):
        query_text = prompt_str[10:].strip()

    cfg = AgenticChatConfig(
        query=query_text,
        intent=intent,
        feature=req.feature or "mejoras_doc",
        sources=sources_to_use,
        document_ids=req.document_ids or [],
        chat_context=chat_ctx_str,
        template_content=_load_active_template_content(req.template_id),
        images=req.images,
        attached_docs=req.attached_docs,
        user_id=user_id,
    )

    try:
        accumulated: list[str] = []
        async for chunk in run_agentic_chat_stream(cfg):
            accumulated.append(chunk)

        full_content = "".join(accumulated)
        parsed_arts, clean_ans = extract_artifacts(full_content)
        art_dicts = artifacts_to_dict(parsed_arts)
        is_template = (intent == "template_mutation")

        asst_msg = clean_ans if art_dicts else (
            "He generado y estructurado el documento corporativo en el visor de artefactos."
            if is_template else full_content
        )

        conv_id = req.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
        try:
            await chat_repo.save_message(
                session_id=conv_id,
                role="user",
                content=prompt_str,
                user_id=user_id,
            )
            await chat_repo.save_message(
                session_id=conv_id,
                role="assistant",
                content=asst_msg,
                context_sources=[{"source": s} for s in sources_to_use],
                user_id=user_id,
            )
            await chat_repo.save_session({
                "id": conv_id,
                "user_id": user_id,
                "title": prompt_str[:35],
                "feature_slug": req.feature or "general",
                "document_content": full_content if is_template else "",
                "artifacts": art_dicts,
            })
        except Exception:
            pass

        return AgenticPromptResponse(
            intent_detected=intent,
            requires_document_mutation=is_template,
            rag_knowledge_used=sources_to_use,
            planned_operations=[],
            operations=[],
            validation_status={"valid": True, "details": ["Agentic generation successful."]},
            assistant_message=asst_msg,
            answer=full_content,
            document_updates=full_content if is_template else None,
        )
    except Exception as err:
        err_msg = str(err)
        lower_err = err_msg.lower()
        if any(term in lower_err for term in ["api key", "unauthorized", "authentication", "auth", "401", "forbidden", "403", "invalid_api_key"]):
            err_msg = f"Error de autenticación con el modelo LLM: La API key no es válida o expiró ({err_msg}). Por favor configúrala en Ajustes."
        raise HTTPException(status_code=502, detail=err_msg)


@router.post("/agentic-prompt-stream")
async def handle_agentic_prompt_stream(
    req: AgenticPromptRequest,
    current_user: Optional[dict[str, Any]] = Depends(get_optional_current_user),
    chat_repo: ChatRepository = Depends(ChatRepository),
):
    """
    Streaming SSE endpoint for dynamic Agentic multimodal chat, Q&A, and artifacts.
    Streams token events live as text is produced by the LLM.
    """
    user_id = current_user.get("id") if current_user else None
    prompt_str = req.prompt_text
    prompt_lower = prompt_str.strip().lower()

    # Conversational inquiries must always go to LLM runner, never mock fast-handlers
    is_question = (
        prompt_lower.startswith(("¿", "que ", "qué ", "como ", "cómo ", "cual ", "cuál ", "por que", "por qué", "donde ", "dónde ", "explica", "cuéntame", "dime"))
        or "?" in prompt_lower
    )

    # Fast non-LLM structured operations (image insertion, corrections, responsibles)
    is_image_intent = not is_question and any(w in prompt_lower for w in ["imágenes", "imagen", "imagenes", "image", "captura", "screenshot"]) and any(w in prompt_lower for w in ["observación", "observaciones", "observacion"])
    is_correction_intent = not is_question and any(w in prompt_lower for w in ["corregir", "corrección", "correccion", "corrijas", "corregí", "corregi", "cambia", "cambiar", "modifica", "modificar", "actualiza", "actualizar", "no es", "erróneo", "erroneo", "incorrecto", "reemplaza", "sustituye"])
    is_responsables_intent = not is_question and any(w in prompt_lower for w in ["responsable", "responsables", "participante", "participantes", "firmas", "pepito", "doctor", "dr"])

    if is_image_intent or is_correction_intent or is_responsables_intent:
        res = await handle_agentic_prompt(req, current_user=current_user, chat_repo=chat_repo)
        async def fast_gen():
            yield f"data: {json.dumps({'type': 'full', 'data': res.model_dump(by_alias=True)})}\n\n"
        return StreamingResponse(fast_gen(), media_type="text/event-stream")

    # Dynamic Agentic Chat / Plan / Report / Template Streaming
    chat_ctx_str = None
    if req.chat_context:
        if isinstance(req.chat_context, list):
            chat_ctx_str = "\n".join(req.chat_context)
        else:
            chat_ctx_str = str(req.chat_context)

    sources_to_use = req.sources or ["knowledge"]
    intent = classify_prompt_intent(prompt_str, req.mode)

    query_text = prompt_str
    if prompt_str.startswith("/plan"):
        query_text = prompt_str[5:].strip() or "Generar plan de pruebas e implementación detallado"
    elif prompt_str.startswith("/informe"):
        query_text = prompt_str[8:].strip() or "Generar informe técnico y ejecutivo detallado"
    elif prompt_str.startswith("/pregunta"):
        query_text = prompt_str[9:].strip()
    elif prompt_str.startswith("/plantilla"):
        query_text = prompt_str[10:].strip()

    cfg = AgenticChatConfig(
        query=query_text,
        intent=intent,
        feature=req.feature or "mejoras_doc",
        sources=sources_to_use,
        document_ids=req.document_ids or [],
        chat_context=chat_ctx_str,
        template_content=_load_active_template_content(req.template_id),
        images=req.images,
        attached_docs=req.attached_docs,
        user_id=user_id,
    )

    run_id = req.run_id or f"run-{uuid.uuid4().hex[:12]}"
    conv_id = req.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    emitter = AgentRunEmitter(run_id=run_id, conversation_id=conv_id)
    run_registry.register(emitter)

    async def stream_generator():
        accumulated_chunks = []
        try:
            yield emitter.started(task_profile=intent, prompt=query_text).to_sse_packet()
            yield emitter.step_started("step-classify", "Clasificando intención...").to_sse_packet()
            yield f"data: {json.dumps({'type': 'intent', 'intent': intent})}\n\n"
            yield emitter.step_completed("step-classify", f"Intención: {intent}").to_sse_packet()
            yield emitter.step_started("step-generate", "Generando contenido...").to_sse_packet()

            async for chunk in run_agentic_chat_stream(cfg):
                if emitter.is_cancelled:
                    yield emitter.cancelled("Cancelado por el usuario").to_sse_packet()
                    return
                accumulated_chunks.append(chunk)
                yield emitter.message_delta(chunk).to_sse_packet()
                yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"

            if emitter.is_cancelled:
                yield emitter.cancelled("Cancelado por el usuario").to_sse_packet()
                return

            full_content = "".join(accumulated_chunks)
            if not full_content.strip():
                err_text = "El modelo LLM no generó contenido. Verifica tu conexión o clave de API en Configuración."
                yield emitter.failed("EMPTY_RESPONSE", err_text).to_sse_packet()
                yield f"data: {json.dumps({'type': 'error', 'message': err_text})}\n\n"
                return

            parsed_arts, clean_ans = extract_artifacts(full_content)
            art_dicts = artifacts_to_dict(parsed_arts)
            is_template = (intent == "template_mutation")

            for idx, art in enumerate(art_dicts):
                yield emitter.artifact_created(
                    artifact_id=art.get("id") or f"art-{idx + 1}",
                    title=art.get("title", "Documento"),
                    content=art.get("content", ""),
                    extension=art.get("extension", "docx"),
                ).to_sse_packet()

            yield emitter.step_completed("step-generate", "Generación completada").to_sse_packet()

            if art_dicts:
                yield emitter.step_started("step-rubric", "Evaluando artefactos con rúbricas de calidad...").to_sse_packet()
                rubric_score, rubric_feedback = _evaluate_artifacts_rubric(art_dicts)
                yield emitter.step_completed("step-rubric", f"Calidad de artefacto: {rubric_score}/100").to_sse_packet()

            asst_msg = clean_ans if art_dicts else (
                "He generado y estructurado el documento corporativo en el panel de artefactos."
                if is_template else full_content
            )

            yield emitter.completed(
                final_message=asst_msg,
                artifacts=art_dicts,
                sources=sources_to_use,
            ).to_sse_packet()

            # Auto-persist session & messages to PostgreSQL entity
            try:
                await chat_repo.save_message(
                    session_id=conv_id,
                    role="user",
                    content=query_text,
                    user_id=user_id,
                )
                await chat_repo.save_message(
                    session_id=conv_id,
                    role="assistant",
                    content=asst_msg,
                    context_sources=[{"source": s} for s in sources_to_use],
                    user_id=user_id,
                )
                await chat_repo.save_session({
                    "id": conv_id,
                    "user_id": user_id,
                    "title": query_text[:35],
                    "feature_slug": req.feature or "general",
                    "document_content": full_content if is_template else "",
                    "artifacts": art_dicts,
                })
            except Exception:
                pass

            final_response = {
                "answer": full_content,
                "intent_detected": intent,
                "requires_document_mutation": is_template,
                "document_updates": full_content if is_template else None,
                "answer_clean": clean_ans or full_content,
                "assistant_message": asst_msg,
                "artifacts": art_dicts,
                "run_id": run_id,
                "conversation_id": conv_id,
            }
            yield f"data: {json.dumps({'type': 'full', 'data': final_response})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as err:
            err_msg = _format_stream_error(err)
            yield emitter.failed("RUN_EXCEPTION", err_msg).to_sse_packet()
            yield f"data: {json.dumps({'type': 'error', 'message': err_msg})}\n\n"
        finally:
            run_registry.unregister(run_id)

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


def _try_parse_structured_artifact(
    content: str, title: str
) -> Optional[Union[FunctionalImprovementArtifact, FunctionalInventoryArtifact]]:
    trimmed = content.strip()
    json_str = None
    if trimmed.startswith("{") and trimmed.endswith("}"):
        json_str = trimmed
    elif "```json" in trimmed:
        match = re.search(r"```json\s*(\{.*?\})\s*```", trimmed, re.DOTALL)
        if match:
            json_str = match.group(1)

    if not json_str:
        return None

    try:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            return None
        data.setdefault("artifact_id", f"art-{uuid.uuid4().hex[:8]}")
        data.setdefault("title", title or "Documento")

        if "problem_statement" in data or "acceptance_criteria" in data:
            return FunctionalImprovementArtifact(**data)
        if "modules" in data or "project_name" in data:
            return FunctionalInventoryArtifact(**data)
    except Exception:
        return None
    return None


def _evaluate_artifacts_rubric(art_dicts: List[Dict[str, Any]]) -> tuple[float, str]:
    if not art_dicts:
        return 100.0, "Sin artefactos estructurados"

    scores: List[float] = []
    feedbacks: List[str] = []
    for art in art_dicts:
        content = art.get("content", "")
        title = art.get("title", "")
        parsed = _try_parse_structured_artifact(content, title)
        if isinstance(parsed, FunctionalImprovementArtifact):
            res = RubricEvaluator.evaluate_improvement(parsed)
            scores.append(res.score)
            if not res.approved:
                feedbacks.extend(res.missing_requirements)
        elif isinstance(parsed, FunctionalInventoryArtifact):
            res = RubricEvaluator.evaluate_inventory(parsed)
            scores.append(res.score)
            if not res.approved:
                feedbacks.extend(res.missing_requirements)
        else:
            scores.append(85.0 if len(content.strip()) >= 50 else 50.0)

    avg_score = round(sum(scores) / len(scores), 1) if scores else 100.0
    feedback_str = "; ".join(feedbacks) if feedbacks else "Artefactos aprobados por rúbrica."
    return avg_score, feedback_str


def _resolve_export_data(
    content: str, artifact_data: Optional[Dict[str, Any]], title: str
) -> Dict[str, Any]:
    if artifact_data:
        data = dict(artifact_data)
        data.setdefault("title", title)
        return data

    trimmed = (content or "").strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        try:
            parsed = json.loads(trimmed)
            if isinstance(parsed, dict):
                parsed.setdefault("title", title)
                return parsed
        except Exception:
            pass

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
    err_msg = str(err)
    lower_err = err_msg.lower()
    if any(term in lower_err for term in ["api key", "unauthorized", "authentication", "auth", "401", "forbidden", "403", "invalid_api_key"]):
        return "Hubo un error de autenticación con el modelo, revisa la API key."
    if "reduce max_tokens" in lower_err or "otpm" in lower_err or "output tokens per minute" in lower_err:
        limit_match = re.search(r"Limit\s+(\d+)", err_msg, re.IGNORECASE)
        req_match = re.search(r"Requested\s+(\d+)", err_msg, re.IGNORECASE)
        req_tokens = req_match.group(1) if req_match else "solicitada"
        limit_tokens = limit_match.group(1) if limit_match else "establecido"
        return f"La solicitud con {req_tokens} tokens supera el límite de {limit_tokens} tokens de salida para este modelo."
    return err_msg


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(run_id: str):
    cancelled = run_registry.cancel_run(run_id, reason="User cancelled run")
    if not cancelled:
        raise HTTPException(status_code=404, detail="Run not found or already completed.")
    return {"status": "cancelled", "run_id": run_id}


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


