from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.settings import USER_DATA_DIR, ensure_local_dirs

logger = logging.getLogger(__name__)

TRANSCRIPTIONS_DIR = USER_DATA_DIR / "transcriptions"
ACTIVE_JOBS_DIR = TRANSCRIPTIONS_DIR / "active_jobs"

SUPPORTED_AUDIO_EXTS = {
  ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".wma", ".aac", ".opus", ".oga", ".weba"
}
SUPPORTED_VIDEO_EXTS = {
  ".mp4", ".webm", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".flv", ".ts"
}
SUPPORTED_FORMATS = SUPPORTED_AUDIO_EXTS | SUPPORTED_VIDEO_EXTS


def ensure_transcription_dirs() -> None:
  ensure_local_dirs()
  TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
  ACTIVE_JOBS_DIR.mkdir(parents=True, exist_ok=True)


def get_transcription_dir(transcription_id: str) -> Path:
  return TRANSCRIPTIONS_DIR / transcription_id


def get_transcription_json_path(transcription_id: str) -> Path:
  return get_transcription_dir(transcription_id) / "transcription.json"


def get_media_path_for_transcription(transcription_id: str) -> Optional[Path]:
  """Find the media file in the transcription subfolder, prioritizing audio.wav."""
  folder = get_transcription_dir(transcription_id)
  if not folder.exists():
    return None
  audio_wav = folder / "audio.wav"
  if audio_wav.exists():
    return audio_wav
  for ext in SUPPORTED_FORMATS:
    candidate = folder / f"media{ext}"
    if candidate.exists():
      return candidate
  # Check if there is any media.* file
  for item in folder.glob("media.*"):
    if item.is_file() and item.suffix.lower() in SUPPORTED_FORMATS:
      return item
  return None


def get_audio_path_for_transcription(transcription_id: str) -> Optional[Path]:
  """Return audio.wav or the first available media file."""
  return get_media_path_for_transcription(transcription_id)


def get_file_hash(data: bytes) -> str:
  sha = hashlib.sha256()
  sha.update(data)
  return sha.hexdigest()


def _format_size_bytes(bytes_val: int) -> str:
  if bytes_val >= 1024 * 1024 * 1024:
    return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"
  if bytes_val >= 1024 * 1024:
    return f"{bytes_val / (1024 * 1024):.1f} MB"
  if bytes_val >= 1024:
    return f"{bytes_val / 1024:.1f} KB"
  return f"{bytes_val} B"


def validate_file(filename: str, size: int) -> tuple[bool, Optional[str]]:
  ext = Path(filename).suffix.lower()
  if not ext or ext not in SUPPORTED_FORMATS:
    supported_list = ", ".join(sorted(SUPPORTED_FORMATS))
    return False, f"Formato '{ext}' no soportado. Formatos admitidos: {supported_list}"
  if size <= 0:
    return False, "El archivo está vacío."
  return True, None


def allocate_transcription_folder(
  transcription_id: str,
  file_bytes: bytes,
  original_filename: str,
  title: str,
  description: str = "",
) -> dict[str, Any]:
  """
  Create the GUID subfolder and write the original media file into it.
  Returns a media metadata dictionary for the transcription record.
  """
  ensure_transcription_dirs()
  valid, err = validate_file(original_filename, len(file_bytes))
  if not valid:
    raise ValueError(err)

  folder = get_transcription_dir(transcription_id)
  folder.mkdir(parents=True, exist_ok=True)

  ext = Path(original_filename).suffix.lower()
  media_dest = folder / f"media{ext}"
  media_dest.write_bytes(file_bytes)

  is_video = ext in SUPPORTED_VIDEO_EXTS
  file_hash = get_file_hash(file_bytes)
  now = datetime.now(timezone.utc).isoformat()

  return {
    "id": transcription_id,
    "transcription_id": transcription_id,
    "original_filename": original_filename,
    "filename": original_filename,
    "stored_filename": f"media{ext}",
    "path": str(media_dest),
    "size_bytes": len(file_bytes),
    "file_size_formatted": _format_size_bytes(len(file_bytes)),
    "is_video": is_video,
    "hash": file_hash,
    "title": title.strip() or original_filename,
    "description": description.strip(),
    "created_at": now,
  }


def get_media_destination(filename: str, media_id: Optional[str] = None) -> tuple[str, Path, str]:
  """
  Returns (transcription_id, file_path, stored_filename) for streaming upload.
  """
  ensure_transcription_dirs()
  tid = media_id or str(uuid.uuid4())
  folder = get_transcription_dir(tid)
  folder.mkdir(parents=True, exist_ok=True)
  ext = Path(filename).suffix.lower()
  stored_filename = f"media{ext}"
  file_path = folder / stored_filename
  return tid, file_path, stored_filename


def register_saved_media_file(
  media_id: str,
  filename: str,
  stored_filename: str,
  file_path: Path,
  file_size: int,
  file_hash: str,
  title: str,
  description: str = "",
) -> dict[str, Any]:
  """
  Registers a media file streamed directly to disk in its GUID subfolder.
  """
  ensure_transcription_dirs()
  ext = Path(filename).suffix.lower()
  now = datetime.now(timezone.utc).isoformat()
  is_video = ext in SUPPORTED_VIDEO_EXTS

  return {
    "id": media_id,
    "transcription_id": media_id,
    "original_filename": filename,
    "filename": filename,
    "stored_filename": stored_filename,
    "path": str(file_path),
    "size_bytes": file_size,
    "file_size_formatted": _format_size_bytes(file_size),
    "hash": file_hash,
    "is_video": is_video,
    "title": title.strip() or filename,
    "description": description.strip(),
    "created_at": now,
  }


def save_media_file(
  file_bytes: bytes,
  filename: str,
  title: str,
  description: str = "",
) -> dict[str, Any]:
  """
  Backward-compatible helper: saves file in a new GUID folder.
  """
  tid = str(uuid.uuid4())
  return allocate_transcription_folder(
    transcription_id=tid,
    file_bytes=file_bytes,
    original_filename=filename,
    title=title,
    description=description,
  )


def get_media_entry(media_id: str) -> Optional[dict[str, Any]]:
  """
  Retrieves media metadata for a transcription.
  """
  folder = get_transcription_dir(media_id)
  media_path = get_media_path_for_transcription(media_id)
  if not media_path or not media_path.exists():
    return None

  record = get_transcription_record(media_id)
  if record and record.get("media"):
    m = record["media"]
    return {
      "id": media_id,
      "transcription_id": media_id,
      "original_filename": m.get("original_filename", media_path.name),
      "filename": m.get("original_filename", media_path.name),
      "stored_filename": m.get("stored_filename", media_path.name),
      "path": str(media_path),
      "size_bytes": m.get("size_bytes", media_path.stat().st_size),
      "file_size_formatted": m.get("file_size_formatted", _format_size_bytes(media_path.stat().st_size)),
      "is_video": m.get("is_video", media_path.suffix.lower() in SUPPORTED_VIDEO_EXTS),
      "hash": m.get("hash", ""),
      "title": record.get("metadata", {}).get("title", media_path.stem),
      "description": record.get("metadata", {}).get("description", ""),
      "created_at": record.get("created_at", ""),
    }

  # Build from on-disk file
  size = media_path.stat().st_size
  ext = media_path.suffix.lower()
  return {
    "id": media_id,
    "transcription_id": media_id,
    "original_filename": media_path.name,
    "filename": media_path.name,
    "stored_filename": media_path.name,
    "path": str(media_path),
    "size_bytes": size,
    "file_size_formatted": _format_size_bytes(size),
    "is_video": ext in SUPPORTED_VIDEO_EXTS,
    "hash": "",
    "title": media_path.stem,
    "description": "",
    "created_at": datetime.now(timezone.utc).isoformat(),
  }


def get_media_path(media_id: str) -> Optional[Path]:
  return get_media_path_for_transcription(media_id)


def update_media_entry_after_audio_extraction(media_id: str, audio_path: Path) -> Optional[dict[str, Any]]:
  """
  Hook called after audio extraction to .wav.
  Removes any non-wav original media file from the GUID subfolder and updates the stored_filename.
  """
  folder = get_transcription_dir(media_id)
  if folder.exists():
    for ext in SUPPORTED_FORMATS:
      if ext != ".wav":
        orig = folder / f"media{ext}"
        if orig.exists():
          try:
            orig.unlink()
          except Exception as exc:
            logger.warning(f"Could not delete original non-wav file {orig}: {exc}")

  record = get_transcription_record(media_id)
  if record and "media" in record:
    record["media"]["stored_filename"] = audio_path.name
    record["media"]["is_video"] = False
    if audio_path.exists():
      size = audio_path.stat().st_size
      record["media"]["size_bytes"] = size
      record["media"]["file_size_formatted"] = _format_size_bytes(size)
    save_transcription_record(record)
  return get_media_entry(media_id)


def save_active_job_progress(progress_dict: dict[str, Any]) -> None:
  ensure_transcription_dirs()
  job_id = progress_dict.get("id")
  if job_id:
    path = ACTIVE_JOBS_DIR / f"{job_id}.json"
    path.write_text(json.dumps(progress_dict, indent=2, ensure_ascii=False), encoding="utf-8")


def load_active_job_progress(job_id: str) -> Optional[dict[str, Any]]:
  ensure_transcription_dirs()
  path = ACTIVE_JOBS_DIR / f"{job_id}.json"
  if path.exists():
    try:
      return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
      return None
  return None


def delete_active_job_progress(job_id: str) -> None:
  ensure_transcription_dirs()
  path = ACTIVE_JOBS_DIR / f"{job_id}.json"
  if path.exists():
    try:
      path.unlink()
    except Exception:
      pass


def save_transcription_record(record: dict[str, Any]) -> dict[str, Any]:
  ensure_transcription_dirs()
  transcription_id = record.get("id") or str(uuid.uuid4())
  record["id"] = transcription_id

  folder = get_transcription_dir(transcription_id)
  folder.mkdir(parents=True, exist_ok=True)

  json_path = get_transcription_json_path(transcription_id)
  json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

  # Write plain-text sidecar files when content is available
  if record.get("text"):
    try:
      (folder / "transcript.txt").write_text(record["text"], encoding="utf-8")
    except Exception as exc:
      logger.warning(f"Could not write transcript.txt for {transcription_id}: {exc}")

  summary = record.get("summary")
  if summary and isinstance(summary, dict):
    summary_lines = []
    if summary.get("participants"):
      summary_lines.append("## Participantes\n" + "\n".join(f"- {p}" for p in summary["participants"]))
    if summary.get("topics"):
      summary_lines.append("## Temas\n" + "\n".join(f"- {t}" for t in summary["topics"]))
    if summary.get("decisions"):
      summary_lines.append("## Decisiones\n" + "\n".join(f"- {d}" for d in summary["decisions"]))
    if summary.get("requirements"):
      summary_lines.append("## Requerimientos\n" + "\n".join(f"- {r}" for r in summary["requirements"]))
    if summary.get("action_items"):
      summary_lines.append("## Acciones\n" + "\n".join(f"- {a}" for a in summary["action_items"]))
    if summary_lines:
      try:
        (folder / "summary.txt").write_text("\n\n".join(summary_lines), encoding="utf-8")
      except Exception as exc:
        logger.warning(f"Could not write summary.txt for {transcription_id}: {exc}")

  return record


def _enrich_record_metadata(record: dict[str, Any]) -> dict[str, Any]:
  meta = record.setdefault("metadata", {})
  if not meta.get("size_bytes") or not meta.get("file_size_formatted") or meta.get("size_bytes", 0) <= 35:
    media_block = record.get("media")
    if media_block and media_block.get("size_bytes"):
      m_size = int(media_block["size_bytes"])
      meta["size_bytes"] = m_size
      meta["file_size_formatted"] = _format_size_bytes(m_size)
      return record

    dur = float(record.get("duration_seconds", 0.0))
    if dur > 0:
      approx = int(dur * 16000)
      meta["size_bytes"] = approx
      meta["file_size_formatted"] = _format_size_bytes(approx)
    elif not meta.get("file_size_formatted"):
      meta["size_bytes"] = 1200000
      meta["file_size_formatted"] = "1.2 MB"
  return record


def get_transcription_record(transcription_id: str) -> Optional[dict[str, Any]]:
  ensure_transcription_dirs()
  json_path = get_transcription_json_path(transcription_id)
  if json_path.exists():
    try:
      data = json.loads(json_path.read_text(encoding="utf-8"))
      return _enrich_record_metadata(data)
    except (json.JSONDecodeError, OSError):
      return None

  # Fallback for flat layout (prior to migration)
  legacy_flat = TRANSCRIPTIONS_DIR / f"{transcription_id}.json"
  if legacy_flat.exists() and not legacy_flat.is_dir():
    try:
      data = json.loads(legacy_flat.read_text(encoding="utf-8"))
      return _enrich_record_metadata(data)
    except (json.JSONDecodeError, OSError):
      return None

  return None


def list_transcriptions() -> list[dict[str, Any]]:
  ensure_transcription_dirs()
  records: list[dict[str, Any]] = []

  for subfolder in TRANSCRIPTIONS_DIR.iterdir():
    if not subfolder.is_dir() or subfolder.name == "active_jobs":
      # Check legacy flat file if not active_jobs
      if subfolder.is_file() and subfolder.suffix == ".json":
        try:
          data = json.loads(subfolder.read_text(encoding="utf-8"))
          records.append(_enrich_record_metadata(data))
        except Exception:
          pass
      continue

    json_path = subfolder / "transcription.json"
    if json_path.exists():
      try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        records.append(_enrich_record_metadata(data))
      except Exception:
        continue

  records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
  return records


def update_transcription_summary(transcription_id: str, summary_data: dict[str, Any]) -> Optional[dict[str, Any]]:
  record = get_transcription_record(transcription_id)
  if not record:
    return None
  record["summary"] = summary_data
  save_transcription_record(record)
  return record


def rename_transcription_speakers(transcription_id: str, speaker_map: dict[str, str]) -> Optional[dict[str, Any]]:
  record = get_transcription_record(transcription_id)
  if not record:
    return None

  segments = record.get("segments", [])
  for seg in segments:
    current_spk = seg.get("speaker", "")
    if current_spk in speaker_map:
      seg["speaker"] = speaker_map[current_spk]

  summary = record.get("summary")
  if summary and isinstance(summary, dict):
    participants = summary.get("participants", [])
    new_participants = []
    for p in participants:
      new_participants.append(speaker_map.get(p, p))
    summary["participants"] = new_participants

  # Rebuild full text if desired
  lines = []
  for seg in segments:
    lines.append(f"{seg.get('speaker', 'Speaker')}: {seg.get('text', '')}")
  record["text"] = "\n".join(lines)

  save_transcription_record(record)
  return record


def delete_transcription_record(transcription_id: str) -> bool:
  ensure_transcription_dirs()
  folder = get_transcription_dir(transcription_id)
  deleted = False

  if folder.exists() and folder.is_dir():
    shutil.rmtree(folder, ignore_errors=True)
    deleted = True

  legacy_flat = TRANSCRIPTIONS_DIR / f"{transcription_id}.json"
  if legacy_flat.exists() and legacy_flat.is_file():
    try:
      legacy_flat.unlink()
      deleted = True
    except OSError:
      pass

  return deleted


def cleanup_old_files(ttl_hours: int = 24) -> int:
  ensure_transcription_dirs()
  removed_count = 0
  now = datetime.now(timezone.utc).timestamp()
  ttl_seconds = ttl_hours * 3600

  for subfolder in TRANSCRIPTIONS_DIR.iterdir():
    if not subfolder.is_dir() or subfolder.name == "active_jobs":
      continue
    json_path = subfolder / "transcription.json"
    if json_path.exists():
      try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        created_str = data.get("created_at")
        if created_str:
          created_dt = datetime.fromisoformat(created_str).timestamp()
          if (now - created_dt) > ttl_seconds:
            shutil.rmtree(subfolder, ignore_errors=True)
            removed_count += 1
      except Exception:
        pass

  return removed_count
