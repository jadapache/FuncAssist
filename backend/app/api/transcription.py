from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import get_current_user

from app.core.exceptions import FFmpegError
from app.core.settings import USER_DATA_DIR
from app.core.storage import allocate_transcription_folder, load_app_settings


from app.api.transcription_stream import emit_progress
from app.features.inventario.xlsx_builder import create_inventario_xlsx
from app.features.levantamiento.docx_builder import create_levantamiento_docx
from app.features.transcription.service import transcription_service
from app.features.transcription.summarizer import summarize_transcript
from app.features.transcription import storage


def get_media_entry(*args, **kwargs):
  return storage.get_media_entry(*args, **kwargs)


def get_transcription_record(*args, **kwargs):
  return storage.get_transcription_record(*args, **kwargs)


def save_transcription_record(*args, **kwargs):
  return storage.save_transcription_record(*args, **kwargs)


def list_transcriptions(*args, **kwargs):
  return storage.list_transcriptions(*args, **kwargs)


def delete_transcription_record(*args, **kwargs):
  return storage.delete_transcription_record(*args, **kwargs)


def update_transcription_summary(*args, **kwargs):
  return storage.update_transcription_summary(*args, **kwargs)


def rename_transcription_speakers(*args, **kwargs):
  return storage.rename_transcription_speakers(*args, **kwargs)


def register_local_media_path(*args, **kwargs):
  return storage.register_local_media_path(*args, **kwargs)
from app.schemas.transcription import (
  RenameSpeakerRequest,
  SaveToKnowledgeRequest,
  SubmitClientTranscriptionRequest,
  TranscribeRequest,
  TranscriptionProgress,
  TranscriptionResult,
  UpdateSummaryRequest,
)

router = APIRouter(
  prefix="/transcription",
  tags=["transcription"],
  dependencies=[Depends(get_current_user)],
)


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


@router.post("/upload")
async def upload_transcription_media(
  file: UploadFile = File(...),
  title: str = Form(""),
  description: str = Form(""),
  transcription_id: Optional[str] = Form(None),
) -> dict[str, Any]:
  """Upload media file to the server for cloud or server-side transcription."""
  tid = transcription_id or str(uuid.uuid4())
  content = await file.read()
  
  if not content:
    raise HTTPException(status_code=400, detail="El archivo multimedia está vacío.")

  try:
    from app.core.storage import allocate_transcription_folder
    entry = allocate_transcription_folder(
      transcription_id=tid,
      file_bytes=content,
      original_filename=file.filename or "media.mp3",
      title=title or file.filename or "Reunión",
      description=description,
    )
    size = entry.get("size_bytes", len(content)) if isinstance(entry, dict) else len(content)
    return {
      "ok": True,
      "media_id": tid,
      "transcription_id": tid,
      "size": size,
      "entry": entry,
      "message": "Archivo multimedia subido con éxito.",
    }
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Error al guardar archivo: {exc}") from exc


def _process_audio_extraction(upload_file: UploadFile, input_path: Path, output_path: Path) -> Path:
  with input_path.open("wb") as buffer:
    shutil.copyfileobj(upload_file.file, buffer)
  from app.features.transcription.ffmpeg_utils import extract_audio_track
  result = extract_audio_track(input_path, output_path, validate=True)
  if isinstance(result, tuple):
    return result[0]
  return result


@router.post("/extract-audio")
async def extract_audio_endpoint(
  background_tasks: BackgroundTasks,
  file: UploadFile = File(...),
) -> FileResponse:
  """Extract audio from video container (.mkv, .wmv, .avi, etc.) or compressed audio to 16 kHz WAV using FFmpeg."""
  suffix = Path(file.filename or "media.mkv").suffix.lower() or ".mkv"
  temp_dir = Path(tempfile.mkdtemp(prefix="funcassist_audio_"))
  temp_input = temp_dir / f"input{suffix}"
  temp_output = temp_dir / "extracted_16k.wav"

  try:
    result_path = await asyncio.to_thread(_process_audio_extraction, file, temp_input, temp_output)
  except FFmpegError as exc:
    shutil.rmtree(temp_dir, ignore_errors=True)
    raise HTTPException(status_code=422, detail=f"Error de FFmpeg al extraer audio: {exc.detail}") from exc
  except Exception as exc:
    shutil.rmtree(temp_dir, ignore_errors=True)
    err_str = str(exc)
    code = 422 if "ffmpeg" in err_str.lower() or "audio" in err_str.lower() else 500
    raise HTTPException(status_code=code, detail=f"Error al procesar archivo: {err_str}") from exc

  if not result_path.exists() or result_path == temp_input:
    shutil.rmtree(temp_dir, ignore_errors=True)
    raise HTTPException(
      status_code=422,
      detail="No se pudo extraer la pista de audio con FFmpeg. Verifica el formato del archivo.",
    )

  def cleanup():
    shutil.rmtree(temp_dir, ignore_errors=True)

  background_tasks.add_task(cleanup)

  return FileResponse(
    path=str(result_path),
    media_type="audio/wav",
    filename="audio_16k.wav",
  )


@router.post("/transcribe/{media_id}")
async def start_transcription(
  media_id: str,
  background_tasks: BackgroundTasks,
  req: Optional[TranscribeRequest] = None,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  """Trigger background transcription process for uploaded media."""
  entry = get_media_entry(media_id)
  if not entry:
    raise HTTPException(status_code=404, detail="Archivo multimedia no encontrado.")

  transcribe_cfg = req or TranscribeRequest()
  transcription_id = transcribe_cfg.transcription_id or str(uuid.uuid4())
  user_id = current_user.get("id")

  media_title = entry.get("title") or entry.get("original_filename") or "Transcripción"
  transcription_service.init_job(
    transcription_id=transcription_id,
    media_id=media_id,
    title=media_title,
    model_info=transcribe_cfg.model_size or "Whisper",
  )

  async def _run_job():
    try:
      await transcription_service.transcribe_media_async(
        media_id=media_id,
        transcription_id=transcription_id,
        mode=transcribe_cfg.mode,
        language=transcribe_cfg.language,
        model_size=transcribe_cfg.model_size,
        enable_diarization=transcribe_cfg.enable_diarization,
        user_id=user_id,
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


@router.get("/available-models")
async def get_available_models(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
  """Return available transcription models and active configuration."""
  return transcription_service.get_available_models_info(user_id=current_user.get("id"))


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
async def dictate_audio(
  file: UploadFile = File(...),
  current_user: dict[str, Any] = Depends(get_current_user),
):
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
    from app.features.transcription.whisper_cloud import WhisperCloudService
    cloud_service = WhisperCloudService(user_id=current_user.get("id"))
    res = await cloud_service.transcribe(temp_file, language="es")
    transcribed_text = (res.get("text") or "").strip()
    return {"text": transcribed_text, "filename": file.filename}
  except ValueError as val_err:
    logger.warning("Voice dictation credentials missing: %s", val_err)
    return {
      "text": "",
      "error": str(val_err),
      "filename": file.filename,
    }
  except Exception as exc:
    logger.exception("Voice dictation transcription failed: %s", exc)
    return {
      "text": "",
      "error": "Error al transcribir audio de voz.",
      "filename": file.filename,
    }
  finally:
    if temp_file.exists():
      try:
        temp_file.unlink()
      except Exception:
        pass

