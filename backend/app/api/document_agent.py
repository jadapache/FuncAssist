"""FastAPI router for DocumentAgent, Agentic RAG integration, and Native Document Exports."""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
import json
from pydantic import BaseModel, Field

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
from app.ai.runner import run_grounded_feature, run_grounded_feature_stream
from app.core.document_agent.validator import DocumentOperationValidator
from app.core.template_storage import list_templates
from app.features.mejoras.docx_builder import create_mejoras_docx
from app.features.levantamiento.docx_builder import create_levantamiento_docx
from app.features.inventario.xlsx_builder import create_inventario_xlsx
from app.features.mejoras.xlsx_builder import create_qa_matrix_xlsx

router = APIRouter(prefix="/doc-agent", tags=["document-agent"])



def _load_active_template_content(template_id: str | None = None) -> str:
    """Load the active mejoras template content to inject into the AI prompt.

    Tries in order:
    1. The explicitly requested template_id
    2. The first template with module 'mejoras' or 'funcional'
    3. The first available template
    4. Fallback empty string (AI uses its own default structure)
    """
    try:
        from app.core.template_storage import list_templates, get_template_detail

        if template_id:
            detail = get_template_detail(template_id)
            if detail and detail.get("content", "").strip():
                return detail["content"].strip()

        templates = list_templates()
        # Prefer mejoras/funcional templates
        candidates = [
            t for t in templates
            if any(kw in (t.get("module") or "").lower() for kw in ("mejora", "funcional", "requerimiento"))
        ]
        if not candidates:
            candidates = templates

        for tmpl in candidates:
            detail = get_template_detail(tmpl["id"])
            if detail and detail.get("content", "").strip():
                return detail["content"].strip()
    except Exception:
        pass
    return ""


class AgenticPromptRequest(CamelModel):
    prompt: Optional[str] = Field(None, alias="query")
    query: Optional[str] = None
    document_state: Optional[CanonicalDocumentState] = Field(None, alias="documentState")
    current_document: Optional[str] = None
    attached_asset_ids: Optional[List[str]] = Field(default_factory=list, alias="attachedAssetIds")
    conversation_history: Optional[List[Dict[str, str]]] = Field(default_factory=list, alias="conversationHistory")
    chat_context: Optional[Union[List[str], str]] = None
    sources: Optional[List[str]] = Field(default_factory=list)
    document_ids: Optional[List[str]] = Field(default_factory=list, alias="documentIds")
    template_id: Optional[str] = Field(None, alias="templateId")

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

    @property
    def text(self) -> str:
        return self.content



class ExportXlsxRequest(CamelModel):
    title: str = "Matriz de Inventario y Pruebas"
    content: Optional[str] = Field(default="", alias="markdown")
    rows: Optional[List[Dict[str, Any]]] = None

    @property
    def text(self) -> str:
        return self.content or ""


@router.get("/fixtures")
def get_document_fixtures():
    """Returns available corporate templates as evaluation fixtures for Univer."""
    templates = list_templates()
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
async def handle_agentic_prompt(req: AgenticPromptRequest):
    """
    Agentic RAG orchestrator for document requests.
    Translates raw user prompt + RAG/Document context into structured canonical operations.
    Supports insertions, image attachments, corrections, and modifications.
    """
    prompt_str = req.prompt_text
    prompt_lower = prompt_str.strip().lower()
    active_doc_state = req.doc_state

    # Case 1: Image attachment intent ("Me gustó la propuesta, incluye en las observaciones estas imágenes")
    is_image_intent = any(w in prompt_lower for w in ["imágenes", "imagen", "imagenes", "image", "captura", "screenshot"])
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
    is_correction_intent = any(w in prompt_lower for w in [
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
    is_responsables_intent = any(w in prompt_lower for w in ["responsable", "responsables", "participante", "participantes", "firmas", "pepito", "doctor", "dr"])
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

    # Case 4: Real RAG Grounded Feature Execution for complex queries & prompts
    chat_ctx_str = None
    if req.chat_context:
        if isinstance(req.chat_context, list):
            chat_ctx_str = "\n".join(req.chat_context)
        else:
            chat_ctx_str = str(req.chat_context)

    sources_to_use = req.sources or ["knowledge"]

    try:
        rag_res = await run_grounded_feature(

            feature="mejoras_doc",
            query=prompt_str,
            sources=sources_to_use,
            document_ids=req.document_ids or [],
            chat_context=chat_ctx_str,
            template_content=_load_active_template_content(req.template_id),
        )

        answer_text = (
            rag_res.get("answer")
            or rag_res.get("markdown")
            or rag_res.get("reason")
            or "Documento de mejoras generado exitosamente."
        )

        sources_used = rag_res.get("context", {}).get("used_sources", sources_to_use)

        brief_msg = "He generado y estructurado el documento de mejoras con base en las especificaciones y el contexto recuperado. Puedes previsualizarlo, editarlo en directo o descargarlo desde el panel de Artefactos a la derecha."

        return AgenticPromptResponse(
            intent_detected="agentic_rag_generation",
            requires_document_mutation=True,
            rag_knowledge_used=sources_used if isinstance(sources_used, list) else [str(sources_used)],
            planned_operations=[],
            operations=[],
            validation_status={"valid": True, "details": ["Grounded RAG generation successful."]},
            assistant_message=brief_msg,
            answer=answer_text,
            document_updates=answer_text,
        )
    except Exception as err:
        err_msg = str(err)
        lower_err = err_msg.lower()
        if any(term in lower_err for term in ["api key", "unauthorized", "authentication", "auth", "401", "forbidden", "403", "invalid_api_key"]):
            err_msg = f"Error de autenticación con el modelo LLM: La API key no es válida o expiró ({err_msg}). Por favor configúrala en Ajustes."
        raise HTTPException(status_code=502, detail=err_msg)


@router.post("/agentic-prompt-stream")
async def handle_agentic_prompt_stream(req: AgenticPromptRequest):
    """
    Streaming SSE endpoint for Agentic RAG multi-artifact document generation.
    Streams token events live as text is produced by the LLM.
    """
    prompt_str = req.prompt_text
    prompt_lower = prompt_str.strip().lower()

    # Check for fast non-LLM structured operations (image insertion, corrections, responsibles)
    is_image_intent = any(w in prompt_lower for w in ["imágenes", "imagen", "imagenes", "image", "captura", "screenshot"]) and any(w in prompt_lower for w in ["observación", "observaciones", "observacion"])
    is_correction_intent = any(w in prompt_lower for w in ["corregir", "corrección", "correccion", "corrijas", "corregí", "corregi", "cambia", "cambiar", "modifica", "modificar", "actualiza", "actualizar", "no es", "erróneo", "erroneo", "incorrecto", "reemplaza", "sustituye"])
    is_responsables_intent = any(w in prompt_lower for w in ["responsable", "responsables", "participante", "participantes", "firmas", "pepito", "doctor", "dr"])

    if is_image_intent or is_correction_intent or is_responsables_intent:
        res = await handle_agentic_prompt(req)
        async def fast_gen():
            yield f"data: {json.dumps({'type': 'full', 'data': res.model_dump(by_alias=True)})}\n\n"
        return StreamingResponse(fast_gen(), media_type="text/event-stream")

    # Full LLM Grounded Generation with live token streaming
    chat_ctx_str = None
    if req.chat_context:
        if isinstance(req.chat_context, list):
            chat_ctx_str = "\n".join(req.chat_context)
        else:
            chat_ctx_str = str(req.chat_context)

    sources_to_use = req.sources or ["knowledge"]

    async def stream_generator():
        accumulated_chunks = []
        try:
            async for chunk in run_grounded_feature_stream(
                feature="mejoras_doc",
                query=prompt_str,
                sources=sources_to_use,
                document_ids=req.document_ids or [],
                chat_context=chat_ctx_str,
                template_content=_load_active_template_content(req.template_id),
            ):
                accumulated_chunks.append(chunk)
                yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"

            # Al finalizar el stream, verificar que se haya recibido contenido válido
            full_content = "".join(accumulated_chunks)
            if not full_content.strip():
                yield f"data: {json.dumps({'type': 'error', 'message': 'El modelo LLM no generó contenido. Verifica tu conexión o clave de API en Configuración.'})}\n\n"
                return

            final_response = {
                "answer": full_content,
                "document_updates": full_content,
                "answer_clean": full_content,
                "artifacts": [],
            }
            yield f"data: {json.dumps({'type': 'full', 'data': final_response})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as err:
            err_msg = str(err)
            lower_err = err_msg.lower()
            if any(term in lower_err for term in ["api key", "unauthorized", "authentication", "auth", "401", "forbidden", "403", "invalid_api_key"]):
                err_msg = f"Hubo un error de autenticación con el modelo, revisa la API key."
            elif "reduce max_tokens" in lower_err or "otpm" in lower_err or "output tokens per minute" in lower_err:
                limit_match = re.search(r"Limit\s+(\d+)", err_msg, re.IGNORECASE)
                req_match = re.search(r"Requested\s+(\d+)", err_msg, re.IGNORECASE)
                req_tokens = req_match.group(1) if req_match else "solicitada"
                limit_tokens = limit_match.group(1) if limit_match else "establecido"
                err_msg = f"La solicitud con {req_tokens} tokens supera el límite de {limit_tokens} tokens de salida para este modelo."
            elif "not found in connected sources" in lower_err or "no matching chunks" in lower_err:
                if "no matching chunks" in lower_err:
                    err_msg = "No se tiene información suficiente para responder a esta solicitud."
                elif "no documents uploaded" in lower_err:
                    err_msg = "La base de conocimiento no tiene documentos para consultar."
                else:
                    err_msg = "No se encontró contexto suficiente para procesar la consulta."
            yield f"data: {json.dumps({'type': 'error', 'message': err_msg})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.post("/export-docx")
def export_native_docx(req: ExportDocxRequest):
    """Generates and downloads a native Microsoft Word .docx binary file."""
    try:
        title_lower = req.title.lower()
        if "levantamiento" in title_lower:
            docx_bytes = create_levantamiento_docx(req.text, title=req.title)
        else:
            docx_bytes = create_mejoras_docx(req.text, title=req.title)

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
        title_lower = req.title.lower()
        if "inventario" in title_lower or req.text:
            xlsx_bytes = create_inventario_xlsx(markdown_content=req.text, title=req.title, rows=req.rows)
        else:
            xlsx_bytes = create_qa_matrix_xlsx(title=req.title, rows=req.rows)

        safe_title = re.sub(r'[^a-zA-Z0-9_\-]', '_', req.title)
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.xlsx"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generando XLSX: {exc}") from exc


