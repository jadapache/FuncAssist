from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.settings import LOCAL_DIR, ensure_local_dirs

MEDIA_DIR = LOCAL_DIR / "media" / "uploads"
TRANSCRIPTIONS_DIR = LOCAL_DIR / "transcriptions"
ACTIVE_JOBS_DIR = LOCAL_DIR / "transcriptions" / "active_jobs"
MEDIA_MANIFEST_PATH = LOCAL_DIR / "media" / "manifest.json"

MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB

SUPPORTED_AUDIO_EXTS = {
  ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".wma", ".aac", ".opus", ".oga", ".weba"
}
SUPPORTED_VIDEO_EXTS = {
  ".mp4", ".webm", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".flv", ".ts"
}
SUPPORTED_FORMATS = SUPPORTED_AUDIO_EXTS | SUPPORTED_VIDEO_EXTS


def ensure_transcription_dirs() -> None:
  ensure_local_dirs()
  MEDIA_DIR.mkdir(parents=True, exist_ok=True)
  TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
  ACTIVE_JOBS_DIR.mkdir(parents=True, exist_ok=True)
  if not MEDIA_MANIFEST_PATH.exists():
    MEDIA_MANIFEST_PATH.write_text("[]", encoding="utf-8")


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


def _load_manifest() -> list[dict[str, Any]]:
  ensure_transcription_dirs()
  try:
    return json.loads(MEDIA_MANIFEST_PATH.read_text(encoding="utf-8"))
  except (json.JSONDecodeError, OSError):
    return []


def _save_manifest(payload: list[dict[str, Any]]) -> None:
  ensure_transcription_dirs()
  MEDIA_MANIFEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_file_hash(data: bytes) -> str:
  sha = hashlib.sha256()
  sha.update(data)
  return sha.hexdigest()


def validate_file(filename: str, size: int) -> tuple[bool, Optional[str]]:
  ext = Path(filename).suffix.lower()
  if not ext or ext not in SUPPORTED_FORMATS:
    supported_list = ", ".join(sorted(SUPPORTED_FORMATS))
    return False, f"Formato '{ext}' no soportado. Formatos admitidos: {supported_list}"
  if size > MAX_FILE_SIZE:
    return False, f"El archivo excede el tamaño máximo permitido de 2GB ({size / (1024 * 1024 * 1024):.2f} GB)."
  return True, None


def save_media_file(
  file_bytes: bytes,
  filename: str,
  title: str,
  description: str = "",
) -> dict[str, Any]:
  ensure_transcription_dirs()
  valid, err = validate_file(filename, len(file_bytes))
  if not valid:
    raise ValueError(err)

  media_id = str(uuid.uuid4())
  file_hash = get_file_hash(file_bytes)
  ext = Path(filename).suffix.lower()
  safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename)
  stored_filename = f"{media_id}_{safe_name}"
  file_path = MEDIA_DIR / stored_filename
  file_path.write_bytes(file_bytes)

  now = datetime.now(timezone.utc).isoformat()
  is_video = ext in SUPPORTED_VIDEO_EXTS
  entry = {
    "id": media_id,
    "filename": filename,
    "stored_filename": stored_filename,
    "path": str(file_path),
    "size_bytes": len(file_bytes),
    "hash": file_hash,
    "is_video": is_video,
    "title": title.strip() or filename,
    "description": description.strip(),
    "created_at": now,
  }

  manifest = _load_manifest()
  manifest.append(entry)
  _save_manifest(manifest)
  return entry


def get_media_destination(filename: str, media_id: Optional[str] = None) -> tuple[str, Path, str]:
  ensure_transcription_dirs()
  mid = media_id or str(uuid.uuid4())
  safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename)
  stored_filename = f"{mid}_{safe_name}"
  file_path = MEDIA_DIR / stored_filename
  return mid, file_path, stored_filename


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
  ensure_transcription_dirs()
  ext = Path(filename).suffix.lower()
  now = datetime.now(timezone.utc).isoformat()
  is_video = ext in SUPPORTED_VIDEO_EXTS
  entry = {
    "id": media_id,
    "filename": filename,
    "stored_filename": stored_filename,
    "path": str(file_path),
    "size_bytes": file_size,
    "hash": file_hash,
    "is_video": is_video,
    "title": title.strip() or filename,
    "description": description.strip(),
    "created_at": now,
  }

  manifest = _load_manifest()
  # Remove existing entry if any
  manifest = [m for m in manifest if m.get("id") != media_id]
  manifest.append(entry)
  _save_manifest(manifest)
  return entry


def get_media_entry(media_id: str) -> Optional[dict[str, Any]]:
  manifest = _load_manifest()
  for item in manifest:
    if item.get("id") == media_id:
      return item
  return None


def get_media_path(media_id: str) -> Optional[Path]:
  entry = get_media_entry(media_id)
  if not entry:
    return None
  path = Path(entry.get("path", ""))
  if path.exists():
    return path
  candidate = MEDIA_DIR / entry.get("stored_filename", "")
  if candidate.exists():
    return candidate
  return None


def save_transcription_record(record: dict[str, Any]) -> dict[str, Any]:
  ensure_transcription_dirs()
  transcription_id = record.get("id") or str(uuid.uuid4())
  record["id"] = transcription_id
  file_path = TRANSCRIPTIONS_DIR / f"{transcription_id}.json"
  file_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
  return record


def _format_size_bytes(bytes_val: int) -> str:
  if bytes_val >= 1024 * 1024 * 1024:
    return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"
  if bytes_val >= 1024 * 1024:
    return f"{bytes_val / (1024 * 1024):.1f} MB"
  if bytes_val >= 1024:
    return f"{bytes_val / 1024:.1f} KB"
  return f"{bytes_val} B"


def _enrich_record_metadata(record: dict[str, Any], manifest_map: Optional[dict[str, Any]] = None) -> dict[str, Any]:
  meta = record.setdefault("metadata", {})
  if not meta.get("size_bytes") or not meta.get("file_size_formatted") or meta.get("size_bytes", 0) <= 35:
    media_id = record.get("media_id")
    if manifest_map and media_id in manifest_map:
      media_entry = manifest_map[media_id]
      m_size = media_entry.get("size_bytes")
      if m_size and int(m_size) > 35:
        meta["size_bytes"] = int(m_size)
        meta["file_size_formatted"] = _format_size_bytes(int(m_size))
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
  file_path = TRANSCRIPTIONS_DIR / f"{transcription_id}.json"
  if not file_path.exists():
    return None
  try:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    return _enrich_record_metadata(data)
  except (json.JSONDecodeError, OSError):
    return None


def list_transcriptions() -> list[dict[str, Any]]:
  ensure_transcription_dirs()
  records: list[dict[str, Any]] = []
  manifest_map = {m.get("id"): m for m in _load_manifest()}
  for file_path in TRANSCRIPTIONS_DIR.glob("*.json"):
    try:
      data = json.loads(file_path.read_text(encoding="utf-8"))
      records.append(_enrich_record_metadata(data, manifest_map))
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
  record = get_transcription_record(transcription_id)
  if record:
    media_id = record.get("media_id")
    if media_id:
      media_path = get_media_path(media_id)
      if media_path and media_path.exists():
        try:
          media_path.unlink()
        except OSError:
          pass
      manifest = _load_manifest()
      _save_manifest([m for m in manifest if m.get("id") != media_id])

  file_path = TRANSCRIPTIONS_DIR / f"{transcription_id}.json"
  if file_path.exists():
    try:
      file_path.unlink()
      return True
    except OSError:
      return False
  return False


def cleanup_old_files(ttl_hours: int = 24) -> int:
  ensure_transcription_dirs()
  removed_count = 0
  now = datetime.now(timezone.utc).timestamp()
  ttl_seconds = ttl_hours * 3600

  manifest = _load_manifest()
  remaining_manifest = []

  for entry in manifest:
    try:
      created_str = entry.get("created_at")
      if created_str:
        created_dt = datetime.fromisoformat(created_str).timestamp()
        if (now - created_dt) > ttl_seconds:
          file_path = Path(entry.get("path", ""))
          if file_path.exists():
            file_path.unlink()
          removed_count += 1
          continue
    except Exception:
      pass
    remaining_manifest.append(entry)

  _save_manifest(remaining_manifest)
  return removed_count
