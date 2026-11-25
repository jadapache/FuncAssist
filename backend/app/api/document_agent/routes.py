"""FastAPI router for DocumentAgent, Agentic RAG integration, and Native Document Exports."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_repository, get_current_user, get_streaming_chat_repository
from app.context.knowledge import extract_text
from app.core.document_agent.schema import (
    CanonicalDocumentState,
    InsertImageOperation,
    InsertTextOperation,
    ReplaceContentOperation,
)
from app.core.document_agent.validator import DocumentOperationValidator
from app.core.template_storage import list_templates
from app.db.repositories.history_repository import ChatRepository
from app.services.event_serializer import run_registry

from app.core.document_agent.chat_run import (
    finalize_answer,
    format_stream_error,
    log_request_failure,
    persist_turn,
    prepare_chat_run,
    resolve_active_artifact_intent,
    start_run,
)
from app.core.document_agent.exports import generate_docx_bytes, generate_xlsx_bytes
from app.core.document_agent.fast_operations import fast_operation_response, is_fast_operation
from app.core.document_agent.payloads import AgenticPromptRequest, AgenticPromptResponse, ExportDocxRequest, ExportXlsxRequest
from .streaming import ChatStream, fast_operation_stream

router = APIRouter(
    prefix="/doc-agent",
    tags=["document-agent"],
    dependencies=[Depends(get_current_user)],
)


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
    active_intent = await resolve_active_artifact_intent(req, chat_repo, user_id)

    fast_response = fast_operation_response(req, prompt_str, active_intent)
    if fast_response:
        return fast_response

    # Intelligent Agentic Chat, Plan/Report Artifacts, or Template Generation
    prepared = await prepare_chat_run(req, chat_repo, user_id, active_intent)
    cfg = prepared.cfg
    cfg.run_info["protocol"] = "json"

    try:
        accumulated: list[str] = []
        async for chunk in start_run(cfg):
            if isinstance(chunk, str):  # typed AgentEvents only matter to streaming clients
                accumulated.append(chunk)
    except Exception as err:
        log_request_failure(cfg, err, streamed=False)
        raise HTTPException(status_code=502, detail=format_stream_error(err)) from err

    full_content = "".join(accumulated)
    outcome = finalize_answer(full_content, prepared)
    conv_id = req.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    await persist_turn(
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
    active_intent = await resolve_active_artifact_intent(req, chat_repo, user_id)

    # Fast non-LLM structured operations (image insertion, corrections, responsibles)
    if is_fast_operation(req.prompt_text, active_intent):
        res = await handle_agentic_prompt(req, current_user=current_user, chat_repo=chat_repo)
        return fast_operation_stream(res, v2)

    prepared = await prepare_chat_run(req, chat_repo, user_id, active_intent)
    prepared.cfg.run_info["protocol"] = "v2" if v2 else "v1"
    return StreamingResponse(
        ChatStream(request, req, chat_repo, user_id, prepared, v2).stream(), media_type="text/event-stream",
    )



def _cancel_or_404(run_key: str, reason: str, not_found: str) -> None:
    if not run_registry.cancel_run(run_key, reason=reason):
        raise HTTPException(status_code=404, detail=not_found)


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(run_id: str):
    _cancel_or_404(run_id, "User cancelled run", f"Run '{run_id}' not found")
    return {"status": "cancelled", "run_id": run_id}


@router.post("/sessions/{session_id}/cancel")
async def cancel_session_run(session_id: str):
    _cancel_or_404(session_id, "User cancelled run for session", f"Session '{session_id}' has no active run")
    return {"status": "cancelled", "session_id": session_id}


@router.post("/export-docx")
def export_native_docx(req: ExportDocxRequest):
    """Generates and downloads a native Microsoft Word .docx binary file."""
    try:
        docx_bytes = generate_docx_bytes(req)
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
        xlsx_bytes = generate_xlsx_bytes(req)
        safe_title = re.sub(r'[^a-zA-Z0-9_\-]', '_', req.title)
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.xlsx"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generando XLSX: {exc}") from exc


