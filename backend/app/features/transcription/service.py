"""Transcription use cases used by the API layer (cloud jobs, browser submissions, edits, knowledge)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.features.transcription import config, records, storage
from app.features.transcription.cleanup import apply_rules, group_turns
from app.features.transcription.diarization import build_speaker_map
from app.features.transcription.errors import TranscriptionJobError
from app.features.transcription.jobs import job_manager
from app.features.transcription.pipeline import JobOptions
from app.features.transcription.segments import ensure_segment_ids, full_text, normalize_record
from app.features.transcription.summarizer import format_timestamp, summarize_transcript
from app.features.transcription.whisper_cloud import available_providers

logger = logging.getLogger(__name__)


def _active_model_label(provider: str, model: str, keys: dict[str, bool]) -> str:
  """Which engine a job would use right now, for display."""
  if provider == "groq" or (keys["groq"] and provider in ("cloud", "auto")):
    return f"Groq Whisper ({model if 'whisper' in model and '/' not in model else 'whisper-large-v3'})"
  if provider == "openai" or (keys["openai"] and provider in ("cloud", "auto")):
    return "OpenAI Whisper (whisper-1)"
  return f"Transformers.js Navegador ({model})"


def get_available_models_info(user_id: Optional[str] = None) -> dict[str, Any]:
  from app.ai.providers.factory import get_ai_settings

  cfg = get_ai_settings(user_id=user_id)
  provider = (cfg.get("transcription_provider") or "browser_asr").lower()
  model = cfg.get("transcription_model") or "onnx-community/whisper-base"
  keys = available_providers(user_id)
  diarization = (cfg.get("transcription_diarization") or "auto").lower()
  return {
    "configured_provider": provider,
    "configured_model": model,
    "local_available": True,
    "local_engines": ["browser-transformers"],
    "groq_configured": keys["groq"],
    "openai_configured": keys["openai"],
    "available_providers": ["browser_asr"] + [p for p in ("groq", "openai") if keys[p]],
    "active_model_label": _active_model_label(provider, model, keys),
    "diarization_available": keys["openai"] and diarization != "off",
    # Default of the "identify speakers" option for in-browser jobs (pyannote + WeSpeaker in a worker).
    "browser_diarization": (cfg.get("transcription_browser_diarization") or "off").lower() == "on",
  }


# --- cloud jobs --------------------------------------------------------------------------------


async def start_job(record: dict[str, Any], user: dict[str, Any], options: JobOptions) -> dict[str, Any]:
  if not record.get("has_media"):
    raise TranscriptionJobError(
      "bad_request",
      "Esta transcripción no tiene el archivo en el servidor. Vuelve a subirlo para transcribirlo de nuevo.",
    )
  title = (record.get("metadata") or {}).get("title") or "Transcripción"
  return await job_manager.start(
    record["id"], str(user.get("id")), options, title=title, previous=record.get("progress"),
  )


async def retry_job(record: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
  options = JobOptions.from_dict(record.get("job_options"))
  return await start_job(record, user, options)


def _derived_status(record: dict[str, Any]) -> dict[str, Any]:
  """Progress snapshot for a record that never reported one (uploaded, browser or legacy records)."""
  status = record.get("status") or "complete"
  stage = "complete" if status in {"completed", "complete", "uploaded"} and record.get("segments") else status
  done = stage == "complete"
  return {
    "id": record["id"],
    "media_id": record["id"],
    "title": (record.get("metadata") or {}).get("title"),
    "status": stage,
    "stage": stage,
    "stage_progress": 1.0 if done else 0.0,
    "progress": 100 if done else 0,
    "message": "Transcripción completada." if done else (record.get("error") or ""),
    "eta": None,
    "eta_seconds": None,
    "chunks_done": 0,
    "chunks_total": 0,
    "queue_position": None,
    "error": record.get("error"),
    "error_code": record.get("error_code"),
    "retryable": bool(record.get("retryable")),
    "summary_status": record.get("summary_status"),
    "model_info": record.get("model_info"),
    "seq": 0,
    "timestamp": None,
    "live_segments": [],
  }


def job_status(record: dict[str, Any]) -> dict[str, Any]:
  """Live snapshot when the job runs in this process, else the persisted one, else derived from status."""
  live = job_manager.snapshot(record["id"])
  if live:
    return live
  stored = record.get("progress")
  if isinstance(stored, dict) and stored.get("stage"):
    return {**stored, "summary_status": record.get("summary_status") or stored.get("summary_status")}
  return _derived_status(record)


async def active_jobs(user: dict[str, Any]) -> list[dict[str, Any]]:
  from app.features.transcription.progress import ACTIVE_STAGES

  items = await records.list_by_status(ACTIVE_STAGES, user_id=str(user.get("id")))
  return [job_status(item) for item in items]


# --- browser submissions -----------------------------------------------------------------------


def _client_segment(seg: dict[str, Any]) -> dict[str, Any]:
  text_raw = seg.get("text_raw") if seg.get("text_raw") is not None else seg.get("text", "")
  speaker_id = seg.get("speaker_id") or "S1"
  return {"id": seg.get("id"), "start": float(seg.get("start", 0.0)), "end": float(seg.get("end", 0.0)), "speaker_id": speaker_id, "text_raw": text_raw}


def _client_segments(payload: dict[str, Any]) -> list[dict[str, Any]]:
  """Segments as the browser sent them, with timings as numbers and `text_raw` always present."""
  segments = [_client_segment(seg) for seg in payload.get("segments") or []]
  ensure_segment_ids(segments)
  return segments


def _client_cleanup_mode(settings: dict[str, Any]) -> str:
  mode = (settings.get("transcription_cleanup") or config.default_cleanup_mode()).lower()
  return "rules" if mode == "llm" else mode  # the browser path never sends text to a cloud LLM implicitly


def _client_record(payload: dict[str, Any], user: dict[str, Any], segments: list[dict[str, Any]], stats: Any, mode: str, browser_diarized: bool) -> dict[str, Any]:
  title = payload.get("title") or "Reunión"
  description = payload.get("description") or ""
  record: dict[str, Any] = {"id": payload["id"], "media_id": payload["id"], "user_id": str(user.get("id"))}
  record["metadata"] = {"title": title, "description": description, "engine": "Transformers.js (Client-side)"}
  record["language"] = payload.get("language") or "es"
  record["duration_seconds"] = float(payload.get("duration_seconds") or 0.0)
  record["created_at"] = datetime.now(timezone.utc).isoformat()
  record.update(segments=segments, speakers=build_speaker_map(segments), diarization="browser" if browser_diarized else "none")
  record.update(summary=None, saved_to_knowledge=False, document_id=None, error=None, error_code=None)
  record.update(summary_status="pending" if payload.get("generate_summary_now") else "skipped")
  record.update(model_info="Whisper Web (Client)", status="complete", source="browser", cleanup=stats.to_dict(mode))
  record.update(turn_gap_s=config.turn_gap_s(), consent=payload.get("consent"))
  normalize_record(record)
  record["text"] = full_text(record["segments"]) or (payload.get("text") or "")
  return record


async def _auto_summary(saved: dict[str, Any], user: dict[str, Any]) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
  """Summarize a freshly saved browser transcript; a failure is recorded on it, never raised."""
  try:
    result = await summarize_transcript(saved["segments"], title=saved["metadata"]["title"], user_id=str(user.get("id")))
    summary = result.model_dump()
    return await records.update_record(saved["id"], lambda r: r.update(summary=summary, summary_status="done")) or saved, summary
  except asyncio.CancelledError:
    raise
  except Exception as exc:
    message = getattr(exc, "detail", None) or str(exc)
    logger.warning("Could not auto-generate summary for client transcription %s: %s", saved["id"], message)
    failed = await records.update_record(saved["id"], lambda r: r.update(summary_status="failed", summary_error=str(message)[:500]))
    return failed or saved, None


async def _require_free_id(transcription_id: str, user: dict[str, Any]) -> None:
  existing = await records.get_record(transcription_id)
  if existing is not None and not records.can_access(existing, user):
    raise TranscriptionJobError("bad_request", "Identificador de transcripción en uso.")


async def submit_client_transcription(payload: dict[str, Any], user: dict[str, Any]) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
  """Persist a transcript decoded in the browser; the rule cleanup is applied here (one implementation)."""
  from app.ai.providers.factory import get_ai_settings

  await _require_free_id(payload["id"], user)
  settings = get_ai_settings(user_id=str(user.get("id")))
  mode = _client_cleanup_mode(settings)
  segments, stats = apply_rules(_client_segments(payload), mode=mode, language=payload.get("language") or "es", extra_fillers=settings.get("transcription_fillers") or [])
  segments = [s for s in segments if (s.get("text_raw") or "").strip()]
  # Speaker ids come from the browser's own diarization when it ran; otherwise everything is S1.
  browser_diarized = payload.get("diarization") == "browser"
  if not browser_diarized:
    for seg in segments:
      seg["speaker_id"] = "S1"

  saved = await records.save_record(_client_record(payload, user, segments, stats, mode, browser_diarized))
  if payload.get("generate_summary_now") and saved.get("segments"):
    return await _auto_summary(saved, user)
  return saved, None


# --- summaries and knowledge -------------------------------------------------------------------


async def generate_summary(record: dict[str, Any], user: dict[str, Any], feature: Optional[str]) -> tuple[Any, dict[str, Any]]:
  title = (record.get("metadata") or {}).get("title") or "Reunión"
  await records.update_record(record["id"], lambda r: r.update(summary_status="running"))
  try:
    summary = await summarize_transcript(
      record.get("segments") or [],
      title=title,
      feature=feature or "transcript_summary_standard_meeting",
      user_id=str(user.get("id")),
    )
  except BaseException:
    await records.update_record(record["id"], lambda r: r.update(summary_status="failed"))
    raise
  payload = summary.model_dump()
  updated = await records.update_record(record["id"], lambda r: r.update(summary=payload, summary_status="done", summary_error=None))
  return summary, updated or record


_SUMMARY_LIST_LABELS = (
  ("participants", "Participantes"),
  ("topics", "Temas"),
  ("decisions", "Decisiones"),
  ("requirements", "Requerimientos"),
  ("action_items", "Compromisos"),
)


def _summary_lines(summary: dict[str, Any]) -> list[str]:
  lines = ["Resumen Ejecutivo\n" + ("-" * 60)]
  if summary.get("summary_text"):
    lines.append(str(summary["summary_text"]))
  lines.extend(f"{label}: {', '.join(summary[field])}" for field, label in _SUMMARY_LIST_LABELS if summary.get(field))
  return lines + [""]


def _knowledge_text(record: dict[str, Any], title: str) -> str:
  """The transcript as plain text for the knowledge base: summary first, then the dialogue by turns."""
  lines = [f"Transcripción de Reunión: {title}\n"]
  summary = record.get("summary") or {}
  if summary:
    lines.extend(_summary_lines(summary))
  lines.append("Diálogo Completo Transcrito\n" + ("-" * 60))
  turns = group_turns(record.get("segments") or [], float(record.get("turn_gap_s") or config.turn_gap_s()))
  lines.extend(f"[{format_timestamp(turn['start'])}] {turn['speaker']}: {turn['text']}" for turn in turns)
  return "\n".join(lines)


async def save_to_knowledge_base(record: dict[str, Any], custom_tags: Optional[list[str]] = None) -> dict[str, Any]:
  from app.context.knowledge import ingest_document

  title = (record.get("metadata") or {}).get("title", "Reunión")
  clean_filename = title if title.lower().endswith(".txt") else f"{title}.txt"
  tags = list({"reunion", "transcripcion", *(custom_tags or [])})
  doc_entry = await asyncio.to_thread(ingest_document, filename=clean_filename, raw=_knowledge_text(record, title).encode("utf-8"), tags=tags)
  document_id = doc_entry.get("id")
  await records.update_record(record["id"], lambda r: r.update(saved_to_knowledge=True, document_id=document_id))
  return {
    "ok": True,
    "document_id": document_id,
    "message": "Transcripción guardada e indexada en la Base de Conocimiento.",
  }


async def delete_transcription(record: dict[str, Any]) -> bool:
  if job_manager.is_running(record["id"]):
    await job_manager.cancel(record["id"])
  return await records.delete_record(record["id"])


def media_entry_for_upload(entry: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
  return storage.initial_record(entry, str(user.get("id")))
