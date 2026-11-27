"""On-disk layout of transcriptions: `USER_DATA_DIR/transcriptions/<id>/`.

    media.<ext>        uploaded file (removed once audio.wav exists)
    audio.wav          16 kHz mono PCM extracted by the pipeline
    chunks/            chunk_NNN.mp3 + chunk_NNN.json (per-chunk results, used to resume)
    plan.json          speech regions / chunk plan of the last run

Database access lives in `records.py`; this module never touches the database.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import UploadFile

from app.core.settings import APP_TRANSCRIPTIONS_DIR, USER_TRANSCRIPTIONS_DIR, ensure_local_dirs
from app.features.transcription import config
from app.features.transcription.errors import TranscriptionJobError

logger = logging.getLogger(__name__)

TRANSCRIPTIONS_DIR = USER_TRANSCRIPTIONS_DIR

SUPPORTED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".wma", ".aac", ".opus", ".oga", ".weba"}
SUPPORTED_VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".flv", ".ts"}
SUPPORTED_FORMATS = SUPPORTED_AUDIO_EXTS | SUPPORTED_VIDEO_EXTS
UPLOAD_BLOCK = 1024 * 1024


def ensure_transcription_dirs() -> None:
  ensure_local_dirs()
  TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
  APP_TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)


_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def get_transcription_dir(transcription_id: str) -> Path:
  """Folder of one transcription; raises if the id could escape the transcriptions directory."""
  if not _ID_RE.fullmatch(str(transcription_id)):
    raise TranscriptionJobError("bad_request", "Identificador de transcripción no válido.")
  base = os.path.realpath(TRANSCRIPTIONS_DIR)
  folder = os.path.realpath(os.path.join(base, transcription_id))
  if not folder.startswith(base + os.sep):
    raise TranscriptionJobError("bad_request", "Identificador de transcripción no válido.")
  return Path(folder)


def chunks_dir(transcription_id: str) -> Path:
  return get_transcription_dir(transcription_id) / "chunks"


def get_file_hash(data: bytes) -> str:
  return hashlib.sha256(data).hexdigest()


def format_size_bytes(bytes_val: int) -> str:
  if bytes_val >= 1024 ** 3:
    return f"{bytes_val / 1024 ** 3:.1f} GB"
  if bytes_val >= 1024 ** 2:
    return f"{bytes_val / 1024 ** 2:.1f} MB"
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


def _stored_media(folder: Path) -> Optional[Path]:
  """audio.wav, else the first uploaded media.<ext> with a supported extension."""
  if not folder.exists():
    return None
  audio_wav = folder / "audio.wav"
  if audio_wav.exists():
    return audio_wav
  return next((item for item in sorted(folder.glob("media.*")) if item.is_file() and item.suffix.lower() in SUPPORTED_FORMATS), None)


def _registered_source(record: Optional[dict[str, Any]]) -> Optional[Path]:
  """The local file a desktop-mode record points at, when it still exists inside an allowed root."""
  if not (record and config.desktop_mode()):
    return None
  source = (record.get("metadata") or {}).get("source_path")
  path = Path(source) if source else None
  return path if path and path.is_file() and is_allowed_local_path(path) else None


def find_media_file(transcription_id: str, record: Optional[dict[str, Any]] = None) -> Optional[Path]:
  """audio.wav, else the uploaded media.<ext>, else a registered local source path (desktop mode)."""
  return _stored_media(get_transcription_dir(transcription_id)) or _registered_source(record)


def has_media(transcription_id: str, record: Optional[dict[str, Any]] = None) -> bool:
  return find_media_file(transcription_id, record) is not None


def _media_entry(transcription_id: str, filename: str, stored: str, path: Path, size: int, digest: str, title: str, description: str) -> dict[str, Any]:
  ext = Path(filename).suffix.lower()
  return {
    "id": transcription_id,
    "transcription_id": transcription_id,
    "original_filename": filename,
    "filename": filename,
    "stored_filename": stored,
    "path": str(path),
    "size_bytes": size,
    "file_size_formatted": format_size_bytes(size),
    "hash": digest,
    "is_video": ext in SUPPORTED_VIDEO_EXTS,
    "title": title,
    "description": description,
    "created_at": datetime.now(timezone.utc).isoformat(),
  }


async def _stream_to_file(upload: UploadFile, tmp: Path, limit: int) -> tuple[int, str]:
  """Write the upload in 1 MB blocks; returns its size and SHA-256, refusing anything over `limit` bytes."""
  digest = hashlib.sha256()
  size = 0
  with tmp.open("wb") as fh:
    while block := await upload.read(UPLOAD_BLOCK):
      size += len(block)
      if size > limit:
        raise TranscriptionJobError("file_too_large", f"El archivo supera el máximo de {limit // (1024 * 1024)} MB.")
      digest.update(block)
      fh.write(block)
  if size == 0:
    raise TranscriptionJobError("unsupported_format", "El archivo multimedia está vacío.")
  return size, digest.hexdigest()


async def save_upload(upload: UploadFile, transcription_id: str, title: str, description: str = "") -> dict[str, Any]:
  """Stream an upload to disk in 1 MB blocks, enforcing the size limit; returns the media entry."""
  filename = upload.filename or "media.mp3"
  ok, err = validate_file(filename, 1)
  if not ok:
    raise TranscriptionJobError("unsupported_format", err)
  ensure_transcription_dirs()
  folder = get_transcription_dir(transcription_id)
  folder.mkdir(exist_ok=True)  # ensure_transcription_dirs created its parent
  # Only a known extension from the allow-list reaches the file name, never raw upload text.
  ext = next(e for e in SUPPORTED_FORMATS if e == Path(filename).suffix.lower())
  stored = f"media{ext}"
  dest = folder / stored
  tmp = folder / f".{stored}.part"
  try:
    size, digest = await _stream_to_file(upload, tmp, config.max_upload_bytes())
    tmp.replace(dest)
  except BaseException:
    tmp.unlink(missing_ok=True)
    if not any(folder.iterdir()):
      folder.rmdir()
    raise
  return _media_entry(transcription_id, filename, stored, dest, size, digest, title.strip() or filename, description.strip())


def match_local_root(raw: str | Path) -> Optional[tuple[str, str]]:
  """Resolve a user-supplied local path to `(real_path, root_prefix)` for the TRANSCRIPTION_LOCAL_ROOTS
  entry containing it, or None. Callers must still guard with `real_path.startswith(root_prefix)`
  right before touching the file, so the check sits next to the file access."""
  text = str(raw).strip().strip("'\"")
  if not text:
    return None
  resolved = os.path.realpath(text)
  for root in config.local_roots():
    prefix = os.path.realpath(root).rstrip(os.sep) + os.sep
    if resolved.startswith(prefix):
      return resolved, prefix
  return None


def is_allowed_local_path(path: str | Path) -> bool:
  return match_local_root(path) is not None


def _allowed_local_file(local_path: str) -> Path:
  """The existing local file inside TRANSCRIPTION_LOCAL_ROOTS, in desktop mode only."""
  match = match_local_root(local_path) if config.desktop_mode() else None
  if match is None or not match[0].startswith(match[1]):
    raise TranscriptionJobError("bad_request", "Ruta local no permitida.")
  path = Path(match[0])
  if not path.is_file():
    raise TranscriptionJobError("bad_request", f"El archivo local no existe o no es accesible: {local_path}")
  return path


def local_media_entry(transcription_id: str, local_path: str, title: str, description: str = "") -> dict[str, Any]:
  """Desktop mode only: reference a file inside TRANSCRIPTION_LOCAL_ROOTS without copying it."""
  path = _allowed_local_file(local_path)
  size = path.stat().st_size
  ok, err = validate_file(path.name, size)
  if not ok:
    raise TranscriptionJobError("unsupported_format", err)
  get_transcription_dir(transcription_id).mkdir(parents=True, exist_ok=True)
  entry = _media_entry(transcription_id, path.name, path.name, path, size, "", title.strip() or path.name, description.strip())
  entry["source_path"] = str(path)
  return entry


def initial_record(entry: dict[str, Any], user_id: Optional[str]) -> dict[str, Any]:
  """Record saved right after upload so the user-assigned title survives."""
  meta: dict[str, Any] = {"title": entry["title"], "file_size_formatted": entry.get("file_size_formatted")}
  meta["description"] = entry.get("description", "")
  meta["size_bytes"] = entry.get("size_bytes", 0)
  if entry.get("source_path"):
    meta["source_path"] = entry["source_path"]
  return {
    "id": entry["id"],
    "media_id": entry["id"],
    "user_id": user_id,
    "metadata": meta,
    "original_filename": entry["original_filename"],
    "stored_filename": entry["stored_filename"],
    "path": entry["path"],
    "created_at": entry["created_at"],
    "status": "uploaded",
    "language": "es",
    "duration_seconds": 0.0,
    "segments": [],
    "text": "",
    "summary": None,
    "summary_status": "skipped",
    "source": "cloud",
    "media": entry,
  }


def remove_original_after_extraction(transcription_id: str) -> None:
  """Once audio.wav exists the uploaded container is no longer needed."""
  folder = get_transcription_dir(transcription_id)
  if not (folder / "audio.wav").exists():
    return
  for item in folder.glob("media.*"):
    try:
      item.unlink()
    except OSError as exc:
      logger.warning("Could not delete original media %s: %s", item, exc)


def delete_folder(transcription_id: str) -> None:
  shutil.rmtree(get_transcription_dir(transcription_id), ignore_errors=True)


def delete_chunks(transcription_id: str) -> None:
  shutil.rmtree(chunks_dir(transcription_id), ignore_errors=True)
