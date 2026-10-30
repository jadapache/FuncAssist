from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.core.settings import USER_DATA_DIR
from app.features.transcription.storage import (
  SUPPORTED_FORMATS,
  SUPPORTED_VIDEO_EXTS,
  _format_size_bytes,
  validate_file,
)

logger = logging.getLogger(__name__)


def open_native_file_dialog_sync() -> Optional[str]:
  """
  Desktop file picker disabled in web environment.
  External file ingestion is handled via web multipart upload (/api/transcription/upload).
  """
  logger.info("open_native_file_dialog_sync called in web environment; native dialog is disabled")
  return None


def inspect_local_file(file_path_str: str) -> dict[str, Any]:
  """
  Inspects a local file path within allowed application storage directories.
  Direct host path inspection is disabled in production web mode.
  """
  raw_path = file_path_str.strip('\'"')
  if not raw_path or "\x00" in raw_path:
    return {
      "ok": False,
      "exists": False,
      "error": "Ruta con caracteres inválidos",
    }

  try:
    p = Path(raw_path).resolve()
    safe_root = Path(USER_DATA_DIR).resolve()
    p.relative_to(safe_root)
  except (ValueError, Exception):
    return {
      "ok": False,
      "exists": False,
      "error": "La selección directa de archivos locales está deshabilitada. Use el formulario de subida web.",
    }

  ext = p.suffix.lower()
  if not ext or ext not in SUPPORTED_FORMATS:
    supported_list = ", ".join(sorted(SUPPORTED_FORMATS))
    return {
      "ok": False,
      "exists": False,
      "error": f"Formato '{ext}' no soportado. Formatos admitidos: {supported_list}",
    }

  if not p.exists() or not p.is_file():
    return {
      "ok": False,
      "exists": False,
      "error": f"El archivo no existe: {file_path_str}",
    }

  size = p.stat().st_size
  valid, err = validate_file(p.name, size)
  if not valid:
    return {
      "ok": False,
      "exists": True,
      "error": err,
    }

  return {
    "ok": True,
    "exists": True,
    "path": str(p),
    "filename": p.name,
    "size_bytes": size,
    "size_formatted": _format_size_bytes(size),
    "is_video": ext in SUPPORTED_VIDEO_EXTS,
  }
