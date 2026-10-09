from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from app.features.transcription.storage import (
  SUPPORTED_FORMATS,
  SUPPORTED_VIDEO_EXTS,
  _format_size_bytes,
  validate_file,
)

logger = logging.getLogger(__name__)

SUPPORTED_FILTER = (
  "Archivos Multimedia (*.mp3;*.mp4;*.wav;*.m4a;*.webm;*.ogg;*.flac;*.aac;*.opus;*.mkv;*.mov)|"
  "*.mp3;*.mp4;*.wav;*.m4a;*.webm;*.ogg;*.flac;*.aac;*.opus;*.mkv;*.mov|"
  "Todos los archivos (*.*)|*.*"
)


def open_native_file_dialog_sync() -> Optional[str]:
  """
  Opens the native Windows OpenFileDialog without blocking with any GUI toolkit.
  Uses STA PowerShell subprocess.
  """
  ps_script = f"""
  [System.Reflection.Assembly]::LoadWithPartialName("System.windows.forms") | Out-Null
  $dialog = New-Object System.Windows.Forms.OpenFileDialog
  $dialog.Filter = "{SUPPORTED_FILTER}"
  $dialog.Title = "Seleccionar grabación de audio o video para transcripción"
  $dialog.Multiselect = $false
  $dialog.RestoreDirectory = $true
  if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
      [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
      Write-Output $dialog.FileName
  }}
  """
  try:
    creation_flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
      creation_flags = subprocess.CREATE_NO_WINDOW

    res = subprocess.run(
      ["powershell.exe", "-NoProfile", "-Sta", "-Command", ps_script],
      capture_output=True,
      text=True,
      encoding="utf-8",
      errors="ignore",
      timeout=300,
      creationflags=creation_flags,
    )
    out = (res.stdout or "").strip()
    if out and Path(out).exists() and Path(out).is_file():
      return str(Path(out).resolve())
    return None
  except Exception as exc:
    logger.warning(f"Error opening native file dialog: {exc}")
    return None


def inspect_local_file(file_path_str: str) -> dict[str, Any]:
  """Inspects an existing local file and returns metadata."""
  p = Path(file_path_str.strip('\'"'))
  if not p.exists() or not p.is_file():
    return {
      "ok": False,
      "exists": False,
      "error": f"El archivo no existe: {file_path_str}",
    }

  size = p.stat().st_size
  ext = p.suffix.lower()
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
    "path": str(p.resolve()),
    "filename": p.name,
    "size_bytes": size,
    "size_formatted": _format_size_bytes(size),
    "is_video": ext in SUPPORTED_VIDEO_EXTS,
  }
