from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

from app.api.transcription_stream import emit_progress_sync, set_main_loop
from app.context.knowledge import ingest_document
from app.core.storage import load_app_settings
from app.features.transcription.diarization import SpeakerDiarization
from app.features.transcription.storage import (
  delete_active_job_progress,
  delete_transcription_record,
  get_media_entry,
  get_media_path,
  get_transcription_record,
  load_active_job_progress,
  save_active_job_progress,
  save_transcription_record,
  update_media_entry_after_audio_extraction,
)
from app.features.transcription.summarizer import summarize_transcript
from app.features.transcription.whisper_cloud import WhisperCloudService
from app.features.transcription.whisper_local import (
  WhisperLocalService,
  delete_model_file,
  download_model_file,
  extract_audio_track,
  get_local_models_info,
)
from app.schemas.transcription import (
  MediaMetadata,
  TranscriptionProgress,
  TranscriptionResult,
  TranscriptionSegment,
  TranscriptionSummary,
)

logger = logging.getLogger(__name__)

# In-memory progress tracking for active jobs
_ACTIVE_JOBS: Dict[str, TranscriptionProgress] = {}
_CANCELLED_JOBS: Set[str] = set()


def _format_eta(seconds: float) -> str:
  if seconds <= 0:
    return "unos segundos"
  mins = int(seconds // 60)
  secs = int(seconds % 60)
  if mins > 0:
    return f"~{mins} min {secs} s"
  return f"~{secs} s"


class TranscriptionService:
  def __init__(self):
    self.local_service = WhisperLocalService()
    self.cloud_service = WhisperCloudService()
    self.diarizer = SpeakerDiarization()

  def _update_progress(self, job_progress: TranscriptionProgress) -> None:
    _ACTIVE_JOBS[job_progress.id] = job_progress
    try:
      save_active_job_progress(job_progress.model_dump())
    except Exception as exc:
      logger.warning(f"Could not persist active job progress for {job_progress.id}: {exc}")
    try:
      emit_progress_sync(job_progress.id, job_progress.model_dump())
    except Exception as exc:
      logger.warning(f"Could not emit SSE progress for {job_progress.id}: {exc}")

  def get_job_progress(self, transcription_id: str) -> Optional[TranscriptionProgress]:
    if transcription_id in _ACTIVE_JOBS:
      return _ACTIVE_JOBS[transcription_id]

    # Check if active status was persisted on disk
    persisted = load_active_job_progress(transcription_id)
    if persisted:
      try:
        prog = TranscriptionProgress(**persisted)
        _ACTIVE_JOBS[transcription_id] = prog
        return prog
      except Exception:
        pass

    # Check if already completed and stored in final transcriptions
    record = get_transcription_record(transcription_id)
    if record:
      return TranscriptionProgress(
        id=transcription_id,
        media_id=record.get("media_id", ""),
        status="complete",
        stage="complete",
        progress=100,
        message="Transcripción completada con éxito.",
        eta="0 s",
        model_info=record.get("model_info", "Whisper"),
      )
    return None

  def cancel_transcription(self, transcription_id: str) -> bool:
    """Cancels an active or pending transcription job and cleans up files."""
    _CANCELLED_JOBS.add(transcription_id)
    if transcription_id in _ACTIVE_JOBS:
      job = _ACTIVE_JOBS[transcription_id]
      job.status = "cancelled"
      job.stage = "cancelled"
      job.message = "Transcripción cancelada por el usuario."
      job.progress = 0
      job.eta = None
      self._update_progress(job)

      # Clean up uploaded media file immediately
      if job.media_id:
        media_path = get_media_path(job.media_id)
        if media_path and media_path.exists():
          try:
            media_path.unlink()
          except OSError:
            pass

    delete_active_job_progress(transcription_id)
    delete_transcription_record(transcription_id)
    return True

  def get_available_models_info(self) -> dict[str, Any]:
    """Inspects system settings and returns available and active transcription models."""
    ai_cfg = load_app_settings().get("ai", {})
    provider = (ai_cfg.get("transcription_provider") or "auto").lower()
    model = ai_cfg.get("transcription_model") or "whisper-large-v3"
    groq_key = bool(
      ai_cfg.get("transcription_groq_api_key")
      or ai_cfg.get("groq_api_key")
      or os.getenv("GROQ_API_KEY")
    )
    openai_key = bool(
      ai_cfg.get("transcription_openai_api_key")
      or ai_cfg.get("openai_api_key")
      or os.getenv("OPENAI_API_KEY")
    )
    local_avail = self.local_service.is_available()

    available = []
    if local_avail:
      available.append("local")
    if groq_key:
      available.append("groq")
    if openai_key:
      available.append("openai")

    active_label = "Whisper Auto"
    if provider in ("local", "builtin") or (provider == "auto" and local_avail and not groq_key and not openai_key):
      active_label = f"Whisper Local ({model or 'base'})"
    elif provider == "groq" or (groq_key and provider in ("groq", "auto", "cloud")):
      active_label = f"Groq Whisper ({model or 'whisper-large-v3'})"
    elif provider == "openai" or (openai_key and provider in ("openai", "auto", "cloud")):
      active_label = f"OpenAI Whisper ({model or 'whisper-1'})"

    return {
      "configured_provider": provider,
      "configured_model": model,
      "local_available": local_avail,
      "groq_configured": groq_key,
      "openai_configured": openai_key,
      "available_providers": available,
      "active_model_label": active_label,
    }

  def get_local_whisper_models(self) -> List[Dict[str, Any]]:
    """Lists local Whisper models and their download status in the cache."""
    return get_local_models_info()

  async def download_local_whisper_model(
    self,
    model_id: str,
    progress_callback: Optional[Any] = None,
  ) -> Path:
    """Downloads a local Whisper model file asynchronously."""
    clean_id = model_id.replace("whisper-", "")
    return await asyncio.to_thread(download_model_file, clean_id, progress_callback)

  def delete_local_whisper_model(self, model_id: str) -> bool:
    """Deletes a downloaded local Whisper model file from disk."""
    clean_id = model_id.replace("whisper-", "")
    return delete_model_file(clean_id)

  async def transcribe_media_async(
    self,
    media_id: str,
    transcription_id: str,
    mode: str = "auto",
    language: Optional[str] = None,
    model_size: Optional[str] = None,
    enable_diarization: bool = True,
  ) -> TranscriptionResult:
    # Clear any previous cancel flag
    if transcription_id in _CANCELLED_JOBS:
      _CANCELLED_JOBS.remove(transcription_id)

    # Determine active model info label from settings
    model_info_data = self.get_available_models_info()
    active_model_label = model_info_data.get("active_model_label", "Whisper")

    media_entry = get_media_entry(media_id)
    if not media_entry:
      prog = TranscriptionProgress(
        id=transcription_id,
        media_id=media_id,
        status="failed",
        stage="failed",
        progress=0,
        message="Archivo multimedia no encontrado.",
        error="Media file not found in storage.",
        model_info=active_model_label,
      )
      self._update_progress(prog)
      raise FileNotFoundError(f"Media entry {media_id} not found.")

    media_path = get_media_path(media_id)
    if not media_path or not media_path.exists():
      prog = TranscriptionProgress(
        id=transcription_id,
        media_id=media_id,
        status="failed",
        stage="failed",
        progress=0,
        message="El archivo en disco no existe.",
        error="Media file missing on disk.",
        model_info=active_model_label,
      )
      self._update_progress(prog)
      raise FileNotFoundError(f"Media file on disk for {media_id} not found.")

    # Up-front validation: check if any provider is available
    has_local = model_info_data.get("local_available", False)
    has_groq = model_info_data.get("groq_configured", False)
    has_openai = model_info_data.get("openai_configured", False)

    if not has_local and not has_groq and not has_openai:
      err_msg = (
        "No se encontró ninguna clave de API configurada para Groq u OpenAI, ni un modelo Whisper local. "
        "Por favor configure su API Key en la sección de Ajustes."
      )
      prog = TranscriptionProgress(
        id=transcription_id,
        media_id=media_id,
        status="failed",
        stage="failed",
        progress=0,
        message="No hay ningún motor de transcripción configurado.",
        error=err_msg,
        model_info=active_model_label,
      )
      self._update_progress(prog)
      raise ValueError(err_msg)

    set_main_loop(asyncio.get_running_loop())
    start_time = time.time()

    def _check_cancelled():
      if transcription_id in _CANCELLED_JOBS:
        raise asyncio.CancelledError(f"Job {transcription_id} was cancelled by user.")

    media_title = media_entry.get("title", "Reunión de Requerimientos")

    try:
      # 1. Start Preprocessing
      _check_cancelled()
      self._update_progress(
        TranscriptionProgress(
          id=transcription_id,
          media_id=media_id,
          title=media_title,
          status="preprocessing",
          stage="preprocessing",
          progress=15,
          message="Extrayendo y normalizando pista de audio...",
          eta=_format_eta(45),
          model_info=active_model_label,
        )
      )

      audio_track_path = media_path
      if media_entry.get("is_video"):
        audio_candidate = media_path.with_suffix(".wav")
        audio_track_path = await asyncio.to_thread(extract_audio_track, media_path, audio_candidate)
        if audio_track_path != media_path:
          update_media_entry_after_audio_extraction(media_id, audio_track_path)

      _check_cancelled()

      # 2. Transcribing with smooth progress ticker and live frame updates
      self._update_progress(
        TranscriptionProgress(
          id=transcription_id,
          media_id=media_id,
          title=media_title,
          status="transcribing",
          stage="transcribing",
          progress=20,
          message=f"Decodificando audio con {active_model_label}...",
          eta=_format_eta(35),
          model_info=active_model_label,
        )
      )

      def _on_local_progress(prog_pct: int, message: str, eta_str: str):
        if transcription_id in _ACTIVE_JOBS and _ACTIVE_JOBS[transcription_id].status == "transcribing":
          _ACTIVE_JOBS[transcription_id].progress = prog_pct
          _ACTIVE_JOBS[transcription_id].message = message
          _ACTIVE_JOBS[transcription_id].eta = eta_str
          _ACTIVE_JOBS[transcription_id].title = media_title
          save_active_job_progress(_ACTIVE_JOBS[transcription_id].model_dump())
          emit_progress_sync(transcription_id, _ACTIVE_JOBS[transcription_id].model_dump())

      def _local_cancel_check() -> bool:
        return transcription_id in _CANCELLED_JOBS

      transcription_output: Dict[str, Any] = {}
      used_mode = mode.lower()

      ai_cfg = load_app_settings().get("ai", {})
      cfg_provider = (ai_cfg.get("transcription_provider") or "").lower()

      is_local_requested = (
        used_mode in ("local", "builtin")
        or (used_mode == "auto" and cfg_provider in ("local", "builtin"))
      )

      if is_local_requested or (used_mode == "auto" and self.local_service.is_available() and not has_groq and not has_openai):
        target_size = model_size or ai_cfg.get("transcription_model") or "base"
        if target_size.startswith("whisper-"):
          target_size = target_size.replace("whisper-", "")
        self.local_service = WhisperLocalService(model_size=target_size)
        transcription_output = await asyncio.to_thread(
          self.local_service.transcribe,
          audio_track_path,
          language=language,
          on_progress=_on_local_progress,
          cancel_check=_local_cancel_check,
        )
      else:
        # Cloud mode (Groq or OpenAI)
        transcription_output = await self.cloud_service.transcribe(audio_track_path, language=language)

      _check_cancelled()

      # 3. Speaker Diarization
      self._update_progress(
        TranscriptionProgress(
          id=transcription_id,
          media_id=media_id,
          title=media_title,
          status="diarizing",
          stage="diarizing",
          progress=75,
          message="Identificando interlocutores y segmentando turnos de habla...",
          eta=_format_eta(15),
          model_info=active_model_label,
        )
      )

      raw_segments = transcription_output.get("segments", [])
      if enable_diarization and raw_segments:
        labeled_segments = await asyncio.to_thread(self.diarizer.diarize_segments, raw_segments, audio_track_path)
      else:
        labeled_segments = raw_segments

      _check_cancelled()

      # 4. Summarization
      self._update_progress(
        TranscriptionProgress(
          id=transcription_id,
          media_id=media_id,
          title=media_title,
          status="summarizing",
          stage="summarizing",
          progress=88,
          message="Extrayendo resumen ejecutivo, participantes y requerimientos con IA...",
          eta=_format_eta(5),
          model_info=active_model_label,
        )
      )

      meeting_title = media_entry.get("title") or "Reunión de Requerimientos"
      summary = await summarize_transcript(labeled_segments, title=meeting_title)

      _check_cancelled()

      # 5. Finalize and Save
      now = datetime.now(timezone.utc).isoformat()
      typed_segments = [
        TranscriptionSegment(
          start=float(s.get("start", 0.0)),
          end=float(s.get("end", 0.0)),
          speaker=s.get("speaker", "Participante 1"),
          text=s.get("text", "").strip(),
        )
        for s in labeled_segments
      ]

      file_bytes_val = media_entry.get("size_bytes", 0)
      if file_bytes_val > 0:
        if file_bytes_val >= 1024 * 1024 * 1024:
          size_fmt = f"{file_bytes_val / (1024 * 1024 * 1024):.1f} GB"
        elif file_bytes_val >= 1024 * 1024:
          size_fmt = f"{file_bytes_val / (1024 * 1024):.1f} MB"
        else:
          size_fmt = f"{file_bytes_val / 1024:.1f} KB"
      else:
        size_fmt = None

      result = TranscriptionResult(
        id=transcription_id,
        media_id=media_id,
        metadata=MediaMetadata(
          title=media_entry.get("title", "Reunión"),
          description=media_entry.get("description", ""),
          size_bytes=file_bytes_val if file_bytes_val > 0 else None,
          file_size_formatted=size_fmt,
        ),
        language=transcription_output.get("language", language or "es"),
        duration_seconds=float(transcription_output.get("duration", 0.0)),
        created_at=now,
        segments=typed_segments,
        text=transcription_output.get("text", ""),
        summary=summary,
        saved_to_knowledge=False,
      )

      save_transcription_record(result.model_dump())

      final_prog = TranscriptionProgress(
        id=transcription_id,
        media_id=media_id,
        title=media_title,
        status="complete",
        stage="complete",
        progress=100,
        message="Transcripción y análisis completados con éxito.",
        eta="0 s",
        model_info=active_model_label,
      )
      self._update_progress(final_prog)
      delete_active_job_progress(transcription_id)

      return result

    except asyncio.CancelledError:
      prog = TranscriptionProgress(
        id=transcription_id,
        media_id=media_id,
        status="cancelled",
        stage="cancelled",
        progress=0,
        message="Transcripción cancelada.",
        model_info=active_model_label,
      )
      self._update_progress(prog)
      delete_active_job_progress(transcription_id)
      raise

    except Exception as exc:
      logger.exception(f"Error in transcription job {transcription_id}: {exc}")
      prog = TranscriptionProgress(
        id=transcription_id,
        media_id=media_id,
        status="failed",
        stage="failed",
        progress=0,
        message=f"Error en la transcripción: {exc}",
        error=str(exc),
        model_info=active_model_label,
      )
      self._update_progress(prog)
      raise

  def save_to_knowledge_base(
    self,
    transcription_id: str,
    custom_tags: list[str] | None = None,
  ) -> dict[str, Any]:
    record = get_transcription_record(transcription_id)
    if not record:
      raise ValueError(f"Transcription {transcription_id} not found.")

    metadata = record.get("metadata", {})
    title = metadata.get("title", "Reunion")
    summary = record.get("summary") or {}
    segments = record.get("segments", [])

    lines = [f"Transcripción de Reunión: {title}\n"]
    if summary:
      lines.append("Resumen Ejecutivo")
      lines.append("-" * 60)
      if summary.get("participants"):
        lines.append(f"Participantes: {', '.join(summary['participants'])}")
      if summary.get("topics"):
        lines.append(f"Temas: {', '.join(summary['topics'])}")
      if summary.get("decisions"):
        lines.append(f"Decisiones: {', '.join(summary['decisions'])}")
      if summary.get("requirements"):
        lines.append(f"Requerimientos: {', '.join(summary['requirements'])}")
      if summary.get("action_items"):
        lines.append(f"Compromisos: {', '.join(summary['action_items'])}")
      lines.append("")

    lines.append("Diálogo Completo Transcrito")
    lines.append("-" * 60)
    for s in segments:
      mins = int(s.get("start", 0) // 60)
      secs = int(s.get("start", 0) % 60)
      lines.append(f"[{mins:02d}:{secs:02d}] {s.get('speaker', 'Participante')}: {s.get('text', '')}")

    full_txt = "\n".join(lines)
    tags = ["reunion", "transcripcion"] + (custom_tags or [])
    clean_filename = title if title.lower().endswith(".txt") else f"{title}.txt"

    doc_entry = ingest_document(
      filename=clean_filename,
      raw=full_txt.encode("utf-8"),
      tags=list(set(tags)),
    )

    record["saved_to_knowledge"] = True
    record["document_id"] = doc_entry.get("id")
    save_transcription_record(record)

    return {
      "ok": True,
      "document_id": doc_entry.get("id"),
      "message": "Transcripción guardada e indexada en la Base de Conocimiento.",
    }


transcription_service = TranscriptionService()
