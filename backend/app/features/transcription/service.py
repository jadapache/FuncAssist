from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.api.transcription_stream import emit_progress_sync, set_main_loop
from app.context.knowledge import ingest_document
from app.core.storage import load_app_settings
from app.features.transcription.diarization import SpeakerDiarization
from app.features.transcription.ffmpeg_utils import extract_audio_track
from app.features.transcription.audio_analyzer import AudioAnalyzer
from app.core.exceptions import TranscriptionError, AudioAnalysisError, FFmpegError
from app.features.transcription.storage import (
  delete_active_job_progress,
  delete_transcription_record,
  get_media_entry,
  get_media_path_for_transcription,
  get_transcription_dir,
  get_transcription_record,
  load_active_job_progress,
  save_active_job_progress,
  save_transcription_record,
  update_media_entry_after_audio_extraction,
)
from app.features.transcription.summarizer import summarize_transcript
from app.features.transcription.whisper_cloud import WhisperCloudService
from app.schemas.transcription import (
  MediaMetadata,
  TranscriptionProgress,
  TranscriptionResult,
  TranscriptionSegment,
)

logger = logging.getLogger(__name__)

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
    self.cloud_service = WhisperCloudService()
    self.diarizer = SpeakerDiarization()
    self.audio_analyzer = AudioAnalyzer()

  def _update_progress(self, job_progress: TranscriptionProgress) -> None:
    _ACTIVE_JOBS[job_progress.id] = job_progress
    if job_progress.status in ("complete", "cancelled"):
      delete_active_job_progress(job_progress.id)
    else:
      try:
        save_active_job_progress(job_progress.model_dump())
      except Exception as exc:
        logger.warning("Could not persist active job progress for %s: %s", job_progress.id, exc)
    try:
      emit_progress_sync(job_progress.id, job_progress.model_dump())
    except Exception as exc:
      logger.warning("Could not emit SSE progress for %s: %s", job_progress.id, exc)

  def init_job(
    self,
    transcription_id: str,
    media_id: str,
    title: str = "",
    model_info: str = "Whisper",
  ) -> TranscriptionProgress:
    prog = TranscriptionProgress(
      id=transcription_id,
      media_id=media_id,
      title=title or "Transcripción",
      status="pending",
      stage="pending",
      progress=0,
      message="Iniciando trabajo de transcripción...",
      model_info=model_info,
    )
    self._update_progress(prog)
    return prog

  def get_job_progress(self, transcription_id: str) -> Optional[TranscriptionProgress]:
    if transcription_id in _ACTIVE_JOBS:
      return _ACTIVE_JOBS[transcription_id]

    persisted = load_active_job_progress(transcription_id)
    if persisted:
      try:
        prog = TranscriptionProgress(**persisted)
        _ACTIVE_JOBS[transcription_id] = prog
        return prog
      except Exception:
        pass

    record = get_transcription_record(transcription_id)
    if record:
      return TranscriptionProgress(
        id=transcription_id,
        media_id=record.get("media_id", transcription_id),
        status="complete",
        stage="complete",
        progress=100,
        message="Transcripción completada con éxito.",
        eta="0 s",
        model_info=record.get("model_info", "Whisper Web (Client)"),
      )
    return None

  def cancel_transcription(self, transcription_id: str) -> bool:
    _CANCELLED_JOBS.add(transcription_id)
    if transcription_id in _ACTIVE_JOBS:
      job = _ACTIVE_JOBS[transcription_id]
      job.status = "cancelled"
      job.stage = "cancelled"
      job.message = "Transcripción cancelada por el usuario."
      job.progress = 0
      job.eta = None
      self._update_progress(job)

    delete_active_job_progress(transcription_id)
    delete_transcription_record(transcription_id)
    return True

  def get_available_models_info(self, user_id: Optional[str] = None) -> dict[str, Any]:
    from app.ai.providers.factory import get_ai_settings
    ai_cfg = get_ai_settings(user_id=user_id)
    provider = (ai_cfg.get("transcription_provider") or "browser_asr").lower()
    model = ai_cfg.get("transcription_model") or "onnx-community/whisper-base"
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

    available = ["browser_asr"]
    if groq_key:
      available.append("groq")
    if openai_key:
      available.append("openai")

    if provider == "groq" or (groq_key and provider in ("cloud", "auto")):
      active_label = f"Groq Whisper ({model or 'whisper-large-v3'})"
    elif provider == "openai":
      active_label = f"OpenAI Whisper ({model or 'whisper-1'})"
    else:
      active_label = f"Transformers.js Navegador ({model or 'whisper-base'})"

    return {
      "configured_provider": provider,
      "configured_model": model,
      "local_available": True,
      "local_engines": ["browser-transformers"],
      "groq_configured": groq_key,
      "openai_configured": openai_key,
      "available_providers": available,
      "active_model_label": active_label,
    }

  async def transcribe_media_async(
    self,
    media_id: str,
    transcription_id: str,
    mode: str = "auto",
    language: Optional[str] = None,
    model_size: Optional[str] = None,
    enable_diarization: bool = True,
    user_id: Optional[str] = None,
  ) -> TranscriptionResult:
    if transcription_id in _CANCELLED_JOBS:
      _CANCELLED_JOBS.remove(transcription_id)

    model_info_data = self.get_available_models_info(user_id=user_id)
    active_model_label = model_info_data.get("active_model_label", "Whisper")

    media_entry = get_media_entry(media_id) or get_media_entry(transcription_id)
    if not media_entry:
      self._fail_job(transcription_id, media_id, "Archivo multimedia no encontrado.", active_model_label)
      raise FileNotFoundError(f"Media entry {media_id} not found.")

    media_path = get_media_path_for_transcription(transcription_id) or get_media_path_for_transcription(media_id)
    if not media_path or not media_path.exists():
      self._fail_job(transcription_id, media_id, "El archivo en disco no existe.", active_model_label)
      raise AudioAnalysisError(f"Media file on disk for {transcription_id} not found.", filename=getattr(media_path, "name", str(media_path)))

    has_groq = model_info_data.get("groq_configured", False)
    has_openai = model_info_data.get("openai_configured", False)
    if not has_groq and not has_openai:
      err_msg = (
        "La transcripción en servidor requiere una clave de API externa configurada (Groq u OpenAI). "
        "Para transcripción local sin enviar datos a la nube, utiliza el modo navegador."
      )
      self._fail_job(transcription_id, media_id, err_msg, active_model_label)
      raise ValueError(err_msg)

    set_main_loop(asyncio.get_running_loop())
    media_title = media_entry.get("title", "Reunión de Requerimientos")
    
    # NEW: Analyze audio duration and validate integrity
    try:
      duration_seconds = await asyncio.to_thread(
        self.audio_analyzer.get_duration_seconds, media_path
      )
      logger.info(f"Audio duration: {duration_seconds:.1f}s ({duration_seconds/60:.1f} min)")
      
      # Update media entry with duration
      media_entry["duration_seconds"] = duration_seconds
    except AudioAnalysisError as e:
      self._fail_job(
        transcription_id, media_id,
        f"No se pudo analizar el archivo: {e.detail}",
        active_model_label
      )
      raise
    
    # Validate audio integrity before processing
    try:
      is_valid, error_msg = await asyncio.to_thread(
        self.audio_analyzer.validate_audio_integrity, media_path
      )
      if not is_valid:
        self._fail_job(
          transcription_id, media_id,
          f"Archivo de audio inválido: {error_msg}",
          active_model_label
        )
        raise AudioAnalysisError(error_msg or "Audio validation failed", filename=media_path.name)
    except AudioAnalysisError:
      raise
    except Exception as e:
      self._fail_job(
        transcription_id, media_id,
        f"Error validando audio: {str(e)}",
        active_model_label
      )
      raise AudioAnalysisError(str(e), filename=media_path.name)
    
    audio_track_path = await self._preprocess_media(transcription_id, media_id, media_path, media_entry, media_title, active_model_label)
    return await self._execute_cloud_pipeline(transcription_id, media_id, audio_track_path, media_entry, media_title, active_model_label, language, enable_diarization, user_id=user_id)

  def _fail_job(self, transcription_id: str, media_id: str, message: str, model_info: str) -> None:
    prog = TranscriptionProgress(
      id=transcription_id,
      media_id=media_id,
      status="failed",
      stage="failed",
      progress=0,
      message=message,
      error=message,
      model_info=model_info,
    )
    self._update_progress(prog)
    
    # Guardar record fallido en BD para que no devuelva 404
    failed_record = {
      "id": transcription_id,
      "media_id": media_id,
      "text": "",
      "segments": [],
      "language": "es",
      "duration_seconds": 0.0,
      "created_at": datetime.now(timezone.utc).isoformat(),
      "metadata": {"title": "Error en transcripción"},
      "summary": None,
      "saved_to_knowledge": False,
      "document_id": None,
      "status": "failed",
      "error": message,
      "model_info": model_info,
    }
    try:
      save_transcription_record(failed_record)
    except Exception as exc:
      logger.warning("Could not persist failed transcription record: %s", exc)

  def _validate_transcription_result(
    self,
    cloud_raw: dict[str, Any],
    audio_path: Path,
  ) -> None:
    """
    Validate that transcription result is not empty and is valid.
    
    Checks:
    - Text is not empty or whitespace
    - Segments exist and have content
    - Duration returned matches audio file (within tolerance)
    
    Args:
        cloud_raw: Raw response from cloud transcription API
        audio_path: Path to the audio file that was transcribed
        
    Raises:
        TranscriptionError: If validation fails
    """
    # Check text is not empty
    text = cloud_raw.get("text", "").strip()
    if not text:
        raise TranscriptionError("Transcription result is empty (no text detected)")
    
    # Check segments exist and have content
    segments = cloud_raw.get("segments", [])
    if not segments:
        raise TranscriptionError("Transcription result has no segments")
    
    # Verify at least one segment has text
    has_content = any(s.get("text", "").strip() for s in segments)
    if not has_content:
        raise TranscriptionError("All transcription segments are empty")
    
    # Check duration matches (within 10% tolerance)
    returned_duration = float(cloud_raw.get("duration", 0))
    if returned_duration <= 0:
        raise TranscriptionError("Returned duration is invalid")
    
    # Verify audio file duration for comparison
    try:
        from app.features.transcription.audio_analyzer import AudioAnalyzer
        analyzer = AudioAnalyzer()
        expected_duration = analyzer.get_duration_seconds(audio_path)
        
        # Allow 10% tolerance
        tolerance = expected_duration * 0.1
        if abs(returned_duration - expected_duration) > tolerance:
            logger.warning(
                f"Duration mismatch: expected {expected_duration:.1f}s, "
                f"got {returned_duration:.1f}s (tolerance: {tolerance:.1f}s)"
            )
    except Exception as exc:
        logger.warning(f"Could not verify audio duration: {exc}")
    
    logger.info(
        f"Transcription result validated: {len(text)} chars, "
        f"{len(segments)} segments, {returned_duration:.1f}s duration"
    )

  async def _preprocess_media(self, transcription_id: str, media_id: str, media_path: Path, media_entry: dict[str, Any], media_title: str, active_model_label: str) -> Path:
    self._update_progress(
      TranscriptionProgress(
        id=transcription_id,
        media_id=media_id,
        title=media_title,
        status="preprocessing",
        stage="preprocessing",
        progress=15,
        message="Normalizando pista de audio para API externa...",
        eta=_format_eta(30),
        model_info=active_model_label,
      )
    )

    audio_track_path = media_path
    if media_entry.get("is_video") or media_path.suffix.lower() != ".wav":
      transcription_folder = get_transcription_dir(transcription_id)
      audio_candidate = transcription_folder / "audio.wav"
      try:
        audio_track_path, success = await asyncio.to_thread(
          extract_audio_track, media_path, audio_candidate, validate=True
        )
        if not success:
          raise FFmpegError(f"Audio extraction returned failure status")
      except FFmpegError as e:
        self._fail_job(
          transcription_id, media_id,
          f"Error al procesar audio: {e.detail}",
          active_model_label
        )
        raise
      
      if audio_candidate.exists() and audio_track_path == audio_candidate:
        if media_path != audio_candidate and media_path.exists() and str(media_path.resolve()).startswith(str(transcription_folder.resolve())):
          try:
            media_path.unlink()
          except Exception as exc:
            logger.warning("Could not delete non-wav file %s: %s", media_path, exc)
        update_media_entry_after_audio_extraction(transcription_id, audio_track_path)
    return audio_track_path

  async def _execute_cloud_pipeline(
    self,
    transcription_id: str,
    media_id: str,
    audio_track_path: Path,
    media_entry: dict[str, Any],
    media_title: str,
    active_model_label: str,
    language: Optional[str],
    enable_diarization: bool,
    user_id: Optional[str] = None,
  ) -> TranscriptionResult:
    self._update_progress(
      TranscriptionProgress(
        id=transcription_id,
        media_id=media_id,
        title=media_title,
        status="transcribing",
        stage="transcribing",
        progress=35,
        message="Procesando transcripción con API remota...",
        eta=_format_eta(20),
        model_info=active_model_label,
      )
    )

    cloud_service = WhisperCloudService(user_id=user_id)
    cloud_raw = await cloud_service.transcribe(audio_track_path, language=language)
    
    # Validate result is not empty
    try:
      self._validate_transcription_result(cloud_raw, audio_track_path)
    except TranscriptionError as e:
      self._fail_job(transcription_id, media_id, str(e), active_model_label)
      raise
    
    raw_segments = cloud_raw.get("segments", [])
    if enable_diarization and raw_segments:
      labeled_segments = await asyncio.to_thread(self.diarizer.diarize_segments, raw_segments, audio_track_path)
    else:
      labeled_segments = raw_segments

    try:
      summary = await summarize_transcript(labeled_segments, title=media_title)
    except Exception as exc:
      logger.warning("Could not auto-generate summary during transcription: %s", exc)
      summary = None
    return self._persist_result(transcription_id, media_entry, audio_track_path, cloud_raw, labeled_segments, summary, active_model_label)

  def _persist_result(
    self,
    transcription_id: str,
    media_entry: dict[str, Any],
    audio_track_path: Path,
    cloud_raw: dict[str, Any],
    labeled_segments: list[dict[str, Any]],
    summary: Any,
    active_model_label: str,
  ) -> TranscriptionResult:
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

    result = TranscriptionResult(
      id=transcription_id,
      media_id=transcription_id,
      metadata=MediaMetadata(
        title=media_entry.get("title", "Reunión"),
        description=media_entry.get("description", ""),
        size_bytes=media_entry.get("size_bytes", 0),
        file_size_formatted=None,
      ),
      language=cloud_raw.get("language", "es"),
      duration_seconds=float(cloud_raw.get("duration", 0.0)),
      created_at=now,
      segments=typed_segments,
      text=cloud_raw.get("text", ""),
      summary=summary,
      saved_to_knowledge=False,
    )

    result_dict = result.model_dump()
    result_dict["provider"] = "cloud_api"
    result_dict["engine"] = "external_cloud_whisper"
    save_transcription_record(result_dict)

    final_prog = TranscriptionProgress(
      id=transcription_id,
      media_id=transcription_id,
      title=media_entry.get("title", "Reunión"),
      status="complete",
      stage="complete",
      progress=100,
      message="Transcripción completada con éxito.",
      eta="0 s",
      model_info=active_model_label,
    )
    self._update_progress(final_prog)
    delete_active_job_progress(transcription_id)
    return result

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
      lines.append("Resumen Ejecutivo\n" + ("-" * 60))
      for field, label in [
        ("participants", "Participantes"),
        ("topics", "Temas"),
        ("decisions", "Decisiones"),
        ("requirements", "Requerimientos"),
        ("action_items", "Compromisos"),
      ]:
        if summary.get(field):
          lines.append(f"{label}: {', '.join(summary[field])}")
      lines.append("")

    lines.append("Diálogo Completo Transcrito\n" + ("-" * 60))
    for s in segments:
      mins = int(s.get("start", 0) // 60)
      secs = int(s.get("start", 0) % 60)
      lines.append(f"[{mins:02d}:{secs:02d}] {s.get('speaker', 'Participante')}: {s.get('text', '')}")

    clean_filename = title if title.lower().endswith(".txt") else f"{title}.txt"
    doc_entry = ingest_document(
      filename=clean_filename,
      raw="\n".join(lines).encode("utf-8"),
      tags=list(set(["reunion", "transcripcion"] + (custom_tags or []))),
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
