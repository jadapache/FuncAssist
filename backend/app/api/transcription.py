from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from app.api.transcription_stream import emit_progress
from app.features.inventario.xlsx_builder import create_inventario_xlsx
from app.features.levantamiento.docx_builder import create_levantamiento_docx
from app.features.transcription.service import transcription_service
from app.features.transcription.summarizer import summarize_transcript
from app.features.transcription.storage import (
  delete_transcription_record,
  get_media_destination,
  get_media_entry,
  get_transcription_record,
  list_transcriptions,
  register_saved_media_file,
  rename_transcription_speakers,
  save_media_file,
  update_transcription_summary,
  validate_file,
)
from app.schemas.transcription import (
  RenameSpeakerRequest,
  SaveToKnowledgeRequest,
  TranscribeRequest,
  TranscriptionProgress,
  TranscriptionResult,
  UpdateSummaryRequest,
)

router = APIRouter(prefix="/transcription", tags=["transcription"])


class ExportDocumentRequest(BaseModel):
  content: str = ""
  title: str = "Documento"


@router.post("/upload")
async def upload_media(
  file: UploadFile = File(...),
  title: str = Form(...),
  description: str = Form(default=""),
) -> dict[str, Any]:
  """Upload media file (audio or video) for transcription."""
  content = await file.read()
  if not content:
    raise HTTPException(status_code=400, detail="El archivo subido está vacío.")

  try:
    entry = save_media_file(
      file_bytes=content,
      filename=file.filename or "audio_file",
      title=title,
      description=description,
    )
    return {
      "ok": True,
      "media_id": entry["id"],
      "entry": entry,
      "message": "Archivo multimedia cargado con éxito.",
    }
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Error procesando archivo: {exc}") from exc


@router.post("/upload-stream")
async def upload_stream(
  file: UploadFile = File(...),
  title: str = Form(...),
  description: str = Form(default=""),
) -> dict[str, Any]:
  """
  Stream-based file upload with real-time progress tracking.
  Writes file chunks to disk without memory overhead and emits SSE progress.
  """
  transcription_id = str(uuid.uuid4())
  filename = file.filename or "audio_file"
  media_id, file_path, stored_filename = get_media_destination(filename)

  sha = hashlib.sha256()
  received_bytes = 0
  chunk_size = 1024 * 1024  # 1MB chunks

  await emit_progress(transcription_id, {
    "stage": "uploading",
    "progress": 0,
    "message": f"Iniciando subida de {filename}...",
    "model_info": "Whisper",
  })

  try:
    with open(file_path, "wb") as out_f:
      while True:
        chunk = await file.read(chunk_size)
        if not chunk:
          break
        out_f.write(chunk)
        sha.update(chunk)
        received_bytes += len(chunk)

    if received_bytes == 0:
      if file_path.exists():
        file_path.unlink()
      raise HTTPException(status_code=400, detail="El archivo subido está vacío.")

    valid, err = validate_file(filename, received_bytes)
    if not valid:
      if file_path.exists():
        file_path.unlink()
      raise HTTPException(status_code=400, detail=err or "Archivo no válido.")

    file_hash = sha.hexdigest()
    entry = register_saved_media_file(
      media_id=media_id,
      filename=filename,
      stored_filename=stored_filename,
      file_path=file_path,
      file_size=received_bytes,
      file_hash=file_hash,
      title=title,
      description=description,
    )

    await emit_progress(transcription_id, {
      "stage": "uploading",
      "progress": 10,
      "message": "Archivo cargado con éxito. Preparando procesamiento...",
    })

    return {
      "ok": True,
      "media_id": media_id,
      "transcription_id": transcription_id,
      "size": received_bytes,
      "filename": filename,
      "entry": entry,
      "message": "Archivo multimedia cargado con éxito.",
    }
  except HTTPException:
    raise
  except Exception as exc:
    if file_path.exists():
      try:
        file_path.unlink()
      except Exception:
        pass
    await emit_progress(transcription_id, {
      "stage": "failed",
      "progress": 0,
      "message": f"Error en la subida: {exc}",
    })
    raise HTTPException(status_code=500, detail=f"Error en subida de archivo: {exc}") from exc


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
        model_info=record.get("model_info", "Whisper"),
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
