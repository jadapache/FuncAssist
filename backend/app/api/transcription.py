from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.ai.templates import list_prompts
from app.api.deps import get_current_user
from app.core.exceptions import FFmpegError
from app.features.inventario.xlsx_builder import create_inventario_xlsx
from app.features.levantamiento.docx_builder import create_levantamiento_docx
from app.features.transcription import config, metrics, records, segments as seg_ops, service, storage
from app.features.transcription.errors import TranscriptionJobError
from app.features.transcription.pipeline import JobOptions
from app.schemas.transcription import (
  RenameSpeakerRequest,
  SaveToKnowledgeRequest,
  SegmentEditRequest,
  SegmentSplitRequest,
  SpeakerEditRequest,
  SubmitClientTranscriptionRequest,
  TranscribeRequest,
  UpdateSummaryRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
  prefix="/transcription",
  tags=["transcription"],
  dependencies=[Depends(get_current_user)],
)

DICTATION_MAX_BYTES = 25 * 1024 * 1024
_ERROR_STATUS = {"file_too_large": 413, "unsupported_format": 415, "no_credentials": 400, "bad_request": 400}


class ExportDocumentRequest(BaseModel):
  content: str = ""
  title: str = "Documento"


class GenerateSummaryRequest(BaseModel):
  feature: Optional[str] = None
  rubric_id: Optional[str] = None


class RegisterLocalPathRequest(BaseModel):
  local_path: str
  title: str = ""
  description: str = ""
  transcription_id: Optional[str] = None


class InspectFileRequest(BaseModel):
  file_path: str


def _http_error(exc: TranscriptionJobError) -> HTTPException:
  return HTTPException(status_code=_ERROR_STATUS.get(exc.code, 422), detail=exc.user_message)


async def load_owned_record(transcription_id: str, user: dict[str, Any]) -> dict[str, Any]:
  """The record if it belongs to the user (owner only, administrators included); 404 otherwise."""
  record = await records.get_record(transcription_id)
  if record is None or not records.can_access(record, user):
    raise HTTPException(status_code=404, detail="Transcripción no encontrada.")
  return record


def _new_id(requested: Optional[str]) -> str:
  if requested and re.fullmatch(r"[A-Za-z0-9_-]{8,64}", requested):
    return requested
  return str(uuid.uuid4())


async def _write_limited(upload: UploadFile, dest: Path, limit: int) -> int:
  size = 0
  with dest.open("wb") as fh:
    while True:
      block = await upload.read(storage.UPLOAD_BLOCK)
      if not block:
        break
      size += len(block)
      if size > limit:
        raise HTTPException(status_code=413, detail=f"El archivo supera el máximo de {limit // (1024 * 1024)} MB.")
      fh.write(block)
  return size


# --- upload and jobs ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_transcription_media(
  file: UploadFile = File(...),
  title: str = Form(""),
  description: str = Form(""),
  transcription_id: Optional[str] = Form(None),
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  """Stream the media file to disk (size-limited) and create the transcription record."""
  tid = _new_id(transcription_id)
  existing = await records.get_record(tid)
  if existing is not None:
    if not records.can_access(existing, current_user):
      raise HTTPException(status_code=409, detail="Identificador de transcripción en uso.")
  try:
    entry = await storage.save_upload(file, tid, title or file.filename or "Reunión", description)
  except TranscriptionJobError as exc:
    raise _http_error(exc) from exc
  await records.save_record(service.media_entry_for_upload(entry, current_user))
  return {
    "ok": True,
    "media_id": tid,
    "transcription_id": tid,
    "size": entry["size_bytes"],
    "entry": entry,
    "message": "Archivo multimedia subido con éxito.",
  }


def _options(req: TranscribeRequest) -> JobOptions:
  return JobOptions(
    language=req.language,
    diarize=req.wants_diarization,
    num_speakers=req.num_speakers,
    vocabulary=req.vocabulary,
    cleanup=req.cleanup,
    summarize=req.summarize,
  )


@router.post("/transcribe/{media_id}")
async def start_transcription(
  media_id: str,
  req: Optional[TranscribeRequest] = None,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  """Queue the cloud pipeline for uploaded media. Progress: /status, /progress-stream."""
  cfg = req or TranscribeRequest()
  record = await load_owned_record(cfg.transcription_id or media_id, current_user)
  try:
    await service.start_job(record, current_user, _options(cfg))
  except TranscriptionJobError as exc:
    raise _http_error(exc) from exc
  return {"ok": True, "status": "queued", "transcription_id": record["id"], "media_id": record["id"]}


@router.post("/retry/{transcription_id}")
async def retry_transcription(transcription_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
  """Restart a failed/interrupted/cancelled job; chunks already transcribed are reused."""
  record = await load_owned_record(transcription_id, current_user)
  try:
    await service.retry_job(record, current_user)
  except TranscriptionJobError as exc:
    raise _http_error(exc) from exc
  return {"ok": True, "status": "queued", "transcription_id": record["id"], "media_id": record["id"]}


@router.post("/cancel/{transcription_id}")
async def cancel_transcription(transcription_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
  """Cancel a job: the task, ffmpeg and provider requests stop; the record stays as `cancelled`."""
  record = await load_owned_record(transcription_id, current_user)
  from app.features.transcription.jobs import job_manager

  ok = await job_manager.cancel(record["id"])
  return {"ok": ok, "message": "Transcripción cancelada."}


@router.get("/jobs/active")
async def get_active_jobs(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
  return {"jobs": await service.active_jobs(current_user)}


@router.get("/status/{transcription_id}")
async def get_transcription_status(transcription_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
  record = await load_owned_record(transcription_id, current_user)
  return service.job_status(record)


@router.get("/result/{transcription_id}")
async def get_transcription_result(transcription_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
  record = await load_owned_record(transcription_id, current_user)
  record.pop("user_id", None)
  return record


@router.get("/list")
async def list_all_transcriptions(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
  items = await records.list_records(current_user)
  for item in items:
    item.pop("user_id", None)
  return {"transcriptions": items}


@router.delete("/{transcription_id}")
async def delete_transcription(transcription_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
  record = await load_owned_record(transcription_id, current_user)
  if not await service.delete_transcription(record):
    raise HTTPException(status_code=404, detail="Transcripción no encontrada o no pudo eliminarse.")
  return {"ok": True, "message": "Transcripción eliminada con éxito."}


@router.post("/submit-client-transcription")
async def submit_client_transcription(
  req: SubmitClientTranscriptionRequest,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  """Persist a transcript decoded in the browser (rule cleanup applied here)."""
  try:
    saved, summary = await service.submit_client_transcription(req.model_dump(), current_user)
  except TranscriptionJobError as exc:
    raise _http_error(exc) from exc
  saved.pop("user_id", None)
  return {
    "ok": True,
    "transcription": saved,
    "summary": summary,
    "message": "Transcripción del cliente registrada exitosamente.",
  }


@router.get("/available-models")
async def get_available_models(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
  return service.get_available_models_info(user_id=current_user.get("id"))


@router.get("/stats")
async def get_transcription_stats(limit: int = 500, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
  """Aggregated metrics of the caller's own jobs."""
  entries = await asyncio.to_thread(metrics.read_entries, max(1, min(limit, 5000)))
  entries = [e for e in entries if str(e.get("user_id")) == str(current_user.get("id"))]
  return {"count": len(entries), **metrics.summarize(entries)}


# --- summaries ---------------------------------------------------------------------------------


@router.get("/summary-templates")
async def get_summary_templates(tag: Optional[str] = "transcript_summary") -> dict[str, Any]:
  prompts = await list_prompts(tag=tag or "transcript_summary")
  templates = [
    {
      "id": p.get("feature"),
      "title": p.get("title") or p.get("feature"),
      "description": p.get("description", ""),
      "tag": p.get("tag", "transcript_summary"),
    }
    for p in prompts
  ]
  return {"templates": templates}


@router.post("/generate-summary/{transcription_id}")
async def generate_summary(
  transcription_id: str,
  body: Optional[GenerateSummaryRequest] = None,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  record = await load_owned_record(transcription_id, current_user)
  feature = (body.feature or body.rubric_id) if body else None
  summary, updated = await service.generate_summary(record, current_user, feature)
  updated.pop("user_id", None)
  return {"ok": True, "summary": summary, "transcription": updated}


@router.put("/summary/{transcription_id}")
async def update_summary(
  transcription_id: str,
  body: UpdateSummaryRequest,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  record = await load_owned_record(transcription_id, current_user)
  payload = body.summary.model_dump()
  updated = await records.update_record(record["id"], lambda r: r.update(summary=payload, summary_status="done"))
  if not updated:
    raise HTTPException(status_code=404, detail="Transcripción no encontrada.")
  updated.pop("user_id", None)
  return {"ok": True, "transcription": updated}


# --- speakers and segments ---------------------------------------------------------------------


async def _edit(transcription_id: str, user: dict[str, Any], mutate: Any) -> dict[str, Any]:
  record = await load_owned_record(transcription_id, user)
  try:
    updated = await records.update_record(record["id"], mutate)
  except seg_ops.EditError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  if not updated:
    raise HTTPException(status_code=404, detail="Transcripción no encontrada.")
  updated.pop("user_id", None)
  return {"ok": True, "transcription": updated}


@router.patch("/{transcription_id}/speakers")
async def edit_speakers(
  transcription_id: str,
  body: SpeakerEditRequest,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  merge = [{"from": m.source, "into": m.into} for m in body.merge or []]
  return await _edit(transcription_id, current_user, lambda r: seg_ops.apply_speaker_edits(r, body.rename, merge))


@router.put("/speakers/{transcription_id}")
async def rename_speakers(
  transcription_id: str,
  body: RenameSpeakerRequest,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  """Legacy rename by display name; a name equal to another speaker's merges both."""
  return await _edit(transcription_id, current_user, lambda r: seg_ops.rename_by_name(r, body.speaker_map))


@router.patch("/{transcription_id}/segments/{segment_id}")
async def edit_segment(
  transcription_id: str,
  segment_id: str,
  body: SegmentEditRequest,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  return await _edit(
    transcription_id,
    current_user,
    lambda r: seg_ops.edit_segment(
      r, segment_id,
      speaker_id=body.speaker_id,
      new_speaker_name=body.new_speaker_name,
      text=body.text,
      marked=body.marked,
    ),
  )


@router.post("/{transcription_id}/segments/{segment_id}/split")
async def split_segment(
  transcription_id: str,
  segment_id: str,
  body: SegmentSplitRequest,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  return await _edit(transcription_id, current_user, lambda r: seg_ops.split_segment(r, segment_id, body.at))


@router.post("/save-to-knowledge/{transcription_id}")
async def save_to_knowledge_base(
  transcription_id: str,
  body: Optional[SaveToKnowledgeRequest] = None,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  record = await load_owned_record(transcription_id, current_user)
  try:
    return await service.save_to_knowledge_base(record, custom_tags=body.custom_tags if body else [])
  except Exception as exc:
    logger.exception("Unhandled error in save_to_knowledge_base: %s", exc)
    raise HTTPException(status_code=500, detail=f"Error guardando en biblioteca: {exc}") from exc


# --- audio utilities ---------------------------------------------------------------------------


def _process_audio_extraction(input_path: Path, output_path: Path) -> Path:
  from app.features.transcription.ffmpeg_utils import extract_audio_track

  result = extract_audio_track(input_path, output_path, validate=True)
  return result[0] if isinstance(result, tuple) else result


@router.post("/extract-audio")
async def extract_audio_endpoint(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> FileResponse:
  """Extract audio from any container to 16 kHz mono WAV (used by the browser path for large files)."""
  suffix = Path(file.filename or "media.mkv").suffix.lower() or ".mkv"
  if suffix not in storage.SUPPORTED_FORMATS:
    raise HTTPException(status_code=415, detail=f"Formato '{suffix}' no soportado.")
  temp_dir = Path(tempfile.mkdtemp(prefix="funcassist_audio_"))
  temp_input = temp_dir / f"input{suffix}"
  temp_output = temp_dir / "extracted_16k.wav"
  try:
    await _write_limited(file, temp_input, config.max_upload_bytes())
    result_path = await asyncio.to_thread(_process_audio_extraction, temp_input, temp_output)
  except HTTPException:
    shutil.rmtree(temp_dir, ignore_errors=True)
    raise
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
    raise HTTPException(status_code=422, detail="No se pudo extraer la pista de audio con FFmpeg. Verifica el formato del archivo.")

  background_tasks.add_task(shutil.rmtree, temp_dir, True)
  return FileResponse(path=str(result_path), media_type="audio/wav", filename="audio_16k.wav")


@router.post("/dictate")
async def dictate_audio(file: UploadFile = File(...), current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
  """Transcribe a short voice dictation snippet for chat composition."""
  from app.core.settings import USER_DATA_DIR
  from app.features.transcription.whisper_cloud import transcribe_short_audio

  suffix = Path(file.filename or "audio.webm").suffix or ".webm"
  temp_dir = USER_DATA_DIR / "temp_voice"
  temp_dir.mkdir(parents=True, exist_ok=True)
  temp_file = temp_dir / f"voice_{uuid.uuid4().hex[:8]}{suffix}"
  try:
    size = await _write_limited(file, temp_file, DICTATION_MAX_BYTES)
    if size == 0:
      raise HTTPException(status_code=400, detail="Audio recording is empty.")
    text = await transcribe_short_audio(temp_file, current_user.get("id"), language="es")
    return {"text": text, "filename": file.filename}
  except HTTPException:
    raise
  except TranscriptionJobError as exc:
    logger.warning("Voice dictation failed (%s): %s", exc.code, exc.detail or exc.user_message)
    return {"text": "", "error": exc.user_message, "filename": file.filename}
  except Exception as exc:
    logger.exception("Voice dictation transcription failed: %s", exc)
    return {"text": "", "error": "Error al transcribir audio de voz.", "filename": file.filename}
  finally:
    temp_file.unlink(missing_ok=True)


# --- exports -----------------------------------------------------------------------------------


@router.post("/export/inventario")
async def export_inventario(req: ExportDocumentRequest) -> Response:
  try:
    xlsx_bytes = create_inventario_xlsx(markdown_content=req.content, title=req.title)
    safe_title = re.sub(r"[^a-zA-Z0-9_\-]", "_", req.title) or "Inventario_Requerimientos"
    return Response(
      content=xlsx_bytes,
      media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      headers={"Content-Disposition": f'attachment; filename="Inventario_{safe_title}.xlsx"'},
    )
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Error al generar XLSX de Inventario: {exc}") from exc


@router.post("/export/levantamiento")
async def export_levantamiento(req: ExportDocumentRequest) -> Response:
  try:
    docx_bytes = create_levantamiento_docx(req.content, title=req.title)
    safe_title = re.sub(r"[^a-zA-Z0-9_\-]", "_", req.title) or "Levantamiento_Requerimientos"
    return Response(
      content=docx_bytes,
      media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      headers={"Content-Disposition": f'attachment; filename="Levantamiento_{safe_title}.docx"'},
    )
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Error al generar DOCX de Levantamiento: {exc}") from exc


# --- desktop mode only -------------------------------------------------------------------------

if config.desktop_mode():
  from app.features.transcription.local_picker import inspect_local_file, open_native_file_dialog_sync

  @router.post("/pick-local-file")
  async def pick_local_file() -> dict[str, Any]:
    path_str = await asyncio.to_thread(open_native_file_dialog_sync)
    if not path_str:
      return {"ok": False, "cancelled": True, "message": "No se seleccionó ningún archivo."}
    if not storage.is_allowed_local_path(Path(path_str)):
      raise HTTPException(status_code=403, detail="Ruta local no permitida.")
    return {"ok": True, "selected": True, **inspect_local_file(path_str)}

  @router.post("/inspect-file")
  async def inspect_file(req: InspectFileRequest) -> dict[str, Any]:
    if not storage.is_allowed_local_path(Path(req.file_path)):
      raise HTTPException(status_code=403, detail="Ruta local no permitida.")
    return inspect_local_file(req.file_path)

  @router.post("/register-local-path")
  async def register_local_path(req: RegisterLocalPathRequest, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    tid = _new_id(req.transcription_id)
    try:
      entry = storage.local_media_entry(tid, req.local_path, req.title, req.description)
    except TranscriptionJobError as exc:
      raise _http_error(exc) from exc
    await records.save_record(service.media_entry_for_upload(entry, current_user))
    return {"ok": True, "media_id": tid, "transcription_id": tid, "size": entry["size_bytes"], "entry": entry,
            "message": "Archivo local vinculado con éxito."}
