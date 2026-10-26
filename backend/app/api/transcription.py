from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
import re
import uuid
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from app.core.settings import USER_DATA_DIR
from app.core.storage import load_app_settings


from app.api.transcription_stream import emit_progress
from app.features.inventario.xlsx_builder import create_inventario_xlsx
from app.features.levantamiento.docx_builder import create_levantamiento_docx
from app.features.transcription.service import transcription_service
from app.features.transcription.summarizer import summarize_transcript
from app.features.transcription.storage import (
  delete_transcription_record,
  get_media_entry,
  get_transcription_record,
  list_transcriptions,
  register_local_media_path,
  rename_transcription_speakers,
  save_transcription_record,
  update_transcription_summary,
)
from app.schemas.transcription import (
  RenameSpeakerRequest,
  SaveToKnowledgeRequest,
  SubmitClientTranscriptionRequest,
  TranscribeRequest,
  TranscriptionProgress,
  TranscriptionResult,
  UpdateSummaryRequest,
)

router = APIRouter(prefix="/transcription", tags=["transcription"])


class ExportDocumentRequest(BaseModel):
  content: str = ""
  title: str = "Documento"


from app.features.transcription.local_picker import (
  inspect_local_file,
  open_native_file_dialog_sync,
)


class RegisterLocalPathRequest(BaseModel):
  local_path: str
  title: str = ""
  description: str = ""
  transcription_id: Optional[str] = None


class InspectFileRequest(BaseModel):
  file_path: str


@router.post("/pick-local-file")
async def pick_local_file() -> dict[str, Any]:
  """
  Opens native Windows file dialog to let the user pick a media file on disk.
  Returns path, filename, size, etc. without transferring file bytes.
  """
  path_str = await asyncio.to_thread(open_native_file_dialog_sync)
  if not path_str:
    return {"ok": False, "cancelled": True, "message": "No se seleccionó ningún archivo."}
  info = inspect_local_file(path_str)
  return {"ok": True, "selected": True, **info}


@router.post("/inspect-file")
async def inspect_file(req: InspectFileRequest) -> dict[str, Any]:
  """Inspects a local file path and validates its format and accessibility."""
  return inspect_local_file(req.file_path)


@router.post("/register-local-path")
async def register_local_path(req: RegisterLocalPathRequest) -> dict[str, Any]:
  """
  Zero-copy registration of a local media file already present on disk.
  Avoids transferring gigabytes of video over HTTP in desktop mode.
  """
  tid = req.transcription_id or str(uuid.uuid4())
  try:
    entry = register_local_media_path(
      transcription_id=tid,
      local_path=req.local_path,
      title=req.title,
      description=req.description,
    )
    return {
      "ok": True,
      "media_id": tid,
      "transcription_id": tid,
      "size": entry.get("size_bytes", 0),
      "entry": entry,
      "message": "Archivo local vinculado con éxito.",
    }
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Error vinculando archivo local: {exc}") from exc


@router.post("/transcribe/{media_id}")
async def start_transcription(
  media_id: str,
  background_tasks: BackgroundTasks,
  req: Optional[TranscribeRequest] = None,
) -> dict[str, Any]:
  """Trigger background transcription process for uploaded media."""
  entry = get_media_entry(media_id)
  if not entry:
    raise HTTPException(status_code=404, detail="Archivo multimedia no encontrado.")

  transcribe_cfg = req or TranscribeRequest()
  transcription_id = transcribe_cfg.transcription_id or str(uuid.uuid4())

  async def _run_job():
    try:
      await transcription_service.transcribe_media_async(
        media_id=media_id,
        transcription_id=transcription_id,
        mode=transcribe_cfg.mode,
        language=transcribe_cfg.language,
        model_size=transcribe_cfg.model_size,
        enable_diarization=transcribe_cfg.enable_diarization,
      )
    except Exception as exc:
      # Exception is recorded inside active job status in transcription_service
      pass

  background_tasks.add_task(_run_job)

  return {
    "ok": True,
    "status": "started",
    "transcription_id": transcription_id,
    "media_id": media_id,
  }


@router.post("/submit-client-transcription")
async def submit_client_transcription(req: SubmitClientTranscriptionRequest) -> dict[str, Any]:
  """
  Receive client-side transcribed text and segments directly from the browser.
  Persists record and generates AI summary without needing heavy media transfer.
  """
  now_iso = datetime.now(timezone.utc).isoformat()
  record: dict[str, Any] = {
    "id": req.id,
    "media_id": req.id,
    "metadata": {
      "title": req.title,
      "description": req.description or "",
      "size_bytes": 0,
      "file_size_formatted": "Procesado en navegador",
      "engine": "Transformers.js (Client-side)",
    },
    "language": req.language or "es",
    "duration_seconds": req.duration_seconds,
    "created_at": now_iso,
    "segments": [seg.model_dump() for seg in req.segments],
    "text": req.text,
    "summary": None,
    "saved_to_knowledge": False,
    "document_id": None,
    "model_info": "Whisper Web (Client)",
  }

  save_transcription_record(record)

  summary_res = None
  if req.generate_summary_now and req.segments:
    try:
      summary_res = await summarize_transcript(record["segments"], title=req.title)
      record["summary"] = summary_res.model_dump()
      update_transcription_summary(req.id, record["summary"])
    except Exception as exc:
      logger.warning("Could not auto-generate summary for client transcription %s: %s", req.id, exc)

  return {
    "ok": True,
    "transcription": record,
    "summary": summary_res.model_dump() if summary_res else None,
    "message": "Transcripción del cliente registrada exitosamente.",
  }


@router.post("/retranscribe/{transcription_id}")
async def retranscribe(
  transcription_id: str,
  background_tasks: BackgroundTasks,
  req: Optional[TranscribeRequest] = None,
) -> dict[str, Any]:
  """Retrigger transcription on an existing transcription record using its preserved audio media."""
  record = get_transcription_record(transcription_id)
  media_id = record.get("media_id") if record else None
  if not media_id:
    entry = get_media_entry(transcription_id)
    if entry:
      media_id = transcription_id
  if not media_id:
    raise HTTPException(status_code=404, detail="Registro de transcripción o archivo multimedia no encontrado.")

  transcribe_cfg = req or TranscribeRequest()

  async def _run_job():
    try:
      await transcription_service.transcribe_media_async(
        media_id=media_id,
        transcription_id=transcription_id,
        mode=transcribe_cfg.mode,
        language=transcribe_cfg.language,
        model_size=transcribe_cfg.model_size,
        enable_diarization=transcribe_cfg.enable_diarization,
      )
    except Exception:
      pass

  background_tasks.add_task(_run_job)

  return {
    "ok": True,
    "status": "started",
    "transcription_id": transcription_id,
    "media_id": media_id,
    "message": "Regeneración de transcripción iniciada con éxito.",
  }


@router.get("/available-models")
async def get_available_models() -> dict[str, Any]:
  """Return available transcription models and active configuration."""
  return transcription_service.get_available_models_info()


@router.post("/cancel/{transcription_id}")
async def cancel_transcription(transcription_id: str) -> dict[str, Any]:
  """Cancel an active transcription process and clean up temporary files."""
  success = transcription_service.cancel_transcription(transcription_id)
  return {"ok": success, "message": "Transcripción cancelada exitosamente."}


@router.get("/status/{transcription_id}")
async def get_transcription_status(transcription_id: str) -> TranscriptionProgress:
  """Poll transcription status and progress."""
  prog = transcription_service.get_job_progress(transcription_id)
  if not prog:
    record = get_transcription_record(transcription_id)
    if record:
      return TranscriptionProgress(
        id=transcription_id,
        media_id=record.get("media_id", ""),
        status="complete",
        stage="complete",
        progress=100,
        message="Transcripción completa.",
        eta="0 s",
        model_info=record.get("model_info", "Whisper Web (Client)"),
      )
    raise HTTPException(status_code=404, detail="Trabajo de transcripción no encontrado.")
  return prog


@router.get("/result/{transcription_id}")
async def get_transcription_result(transcription_id: str) -> TranscriptionResult:
  """Retrieve completed transcript and summary."""
  record = get_transcription_record(transcription_id)
  if not record:
    raise HTTPException(status_code=404, detail="Resultado de transcripción no encontrado.")
  return TranscriptionResult(**record)


@router.post("/generate-summary/{transcription_id}")
async def generate_summary(transcription_id: str) -> dict[str, Any]:
  """Trigger AI summary generation for a completed transcription."""
  record = get_transcription_record(transcription_id)
  if not record:
    raise HTTPException(status_code=404, detail="Transcripción no encontrada.")

  segments = record.get("segments", [])
  meta = record.get("metadata", {})
  title = meta.get("title", "Reunión")

  summary = await summarize_transcript(segments, title=title)
  updated = update_transcription_summary(transcription_id, summary.model_dump())
  return {"ok": True, "summary": summary, "transcription": updated}


@router.put("/summary/{transcription_id}")
async def update_summary(
  transcription_id: str,
  body: UpdateSummaryRequest,
) -> dict[str, Any]:
  """Update/edit the meeting summary."""
  updated = update_transcription_summary(transcription_id, body.summary.model_dump())
  if not updated:
    raise HTTPException(status_code=404, detail="Transcripción no encontrada.")
  return {"ok": True, "transcription": updated}


@router.put("/speakers/{transcription_id}")
async def rename_speakers(
  transcription_id: str,
  body: RenameSpeakerRequest,
) -> dict[str, Any]:
  """Rename speaker labels across transcript segments and summary."""
  updated = rename_transcription_speakers(transcription_id, body.speaker_map)
  if not updated:
    raise HTTPException(status_code=404, detail="Transcripción no encontrada.")
  return {"ok": True, "transcription": updated}


@router.post("/save-to-knowledge/{transcription_id}")
async def save_to_knowledge_base(
  transcription_id: str,
  body: Optional[SaveToKnowledgeRequest] = None,
) -> dict[str, Any]:
  """Save transcript and summary into the Knowledge Base for RAG retrieval."""
  try:
    tags = body.custom_tags if body else []
    return transcription_service.save_to_knowledge_base(transcription_id, custom_tags=tags)
  except ValueError as exc:
    logger.exception("ValueError in save_to_knowledge_base: %s", exc)
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except Exception as exc:
    logger.exception("Unhandled error in save_to_knowledge_base: %s", exc)
    raise HTTPException(status_code=500, detail=f"Error guardando en biblioteca: {exc}") from exc


@router.get("/list")
async def list_all_transcriptions() -> dict[str, Any]:
  """List all saved transcriptions."""
  items = list_transcriptions()
  return {"transcriptions": items}


@router.delete("/{transcription_id}")
async def delete_transcription(transcription_id: str) -> dict[str, Any]:
  """Delete a transcription and its associated media file."""
  success = delete_transcription_record(transcription_id)
  if not success:
    raise HTTPException(status_code=404, detail="Transcripción no encontrada o no pudo eliminarse.")
  return {"ok": True, "message": "Transcripción eliminada con éxito."}


@router.post("/export/inventario")
async def export_inventario(req: ExportDocumentRequest) -> Response:
  """Export Inventario document as formatted .xlsx binary."""
  try:
    xlsx_bytes = create_inventario_xlsx(markdown_content=req.content, title=req.title)
    safe_title = re.sub(r"[^a-zA-Z0-9_\-]", "_", req.title) or "Inventario_Requerimientos"
    filename = f"Inventario_{safe_title}.xlsx"
    return Response(
      content=xlsx_bytes,
      media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Error al generar XLSX de Inventario: {exc}") from exc


@router.post("/export/levantamiento")
async def export_levantamiento(req: ExportDocumentRequest) -> Response:
  """Export Levantamiento document as formatted .docx binary."""
  try:
    docx_bytes = create_levantamiento_docx(req.content, title=req.title)
    safe_title = re.sub(r"[^a-zA-Z0-9_\-]", "_", req.title) or "Levantamiento_Requerimientos"
    filename = f"Levantamiento_{safe_title}.docx"
    return Response(
      content=docx_bytes,
      media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Error al generar DOCX de Levantamiento: {exc}") from exc


@router.post("/dictate")
async def dictate_audio(file: UploadFile = File(...)):
  """Transcribe a short voice dictation audio snippet for chat composition."""
  content = await file.read()
  if not content:
    raise HTTPException(status_code=400, detail="Audio recording is empty.")

  suffix = Path(file.filename or "audio.webm").suffix or ".webm"
  temp_dir = USER_DATA_DIR / "temp_voice"
  temp_dir.mkdir(parents=True, exist_ok=True)
  temp_file = temp_dir / f"voice_{uuid.uuid4().hex[:8]}{suffix}"

  try:
    temp_file.write_bytes(content)
    ai_cfg = load_app_settings().get("ai", {})
    provider_id = (ai_cfg.get("transcription_provider") or "auto").lower()
    model_id = ai_cfg.get("transcription_model") or "base"

    from app.features.transcription.service import _resolve_provider
    engine = _resolve_provider(provider_id, model_id)
    res = await asyncio.to_thread(engine.transcribe, str(temp_file))
    transcribed_text = res.text.strip() if res else ""
    return {"text": transcribed_text, "filename": file.filename}
  except Exception as exc:
    logger.warning(f"Voice dictation transcription failed: {exc}")
    return {"text": "", "error": str(exc), "filename": file.filename}
  finally:
    if temp_file.exists():
      try:
        temp_file.unlink()
      except Exception:
        pass

