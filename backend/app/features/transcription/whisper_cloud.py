from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from app.ai.providers.factory import get_ai_settings

logger = logging.getLogger(__name__)


class WhisperCloudService:
  def __init__(self, provider: str = "groq", api_key: Optional[str] = None):
    self.provider = provider.lower()
    self.api_key = api_key

  def _resolve_credentials(self) -> tuple[str, str, str]:
    config = get_ai_settings()
    prov = (self.provider or config.get("transcription_provider") or "auto").lower()
    configured_model = config.get("transcription_model")

    groq_key = (
      self.api_key
      or config.get("transcription_groq_api_key")
      or config.get("groq_api_key")
      or os.getenv("GROQ_API_KEY", "")
    )
    openai_key = (
      self.api_key
      or config.get("transcription_openai_api_key")
      or config.get("openai_api_key")
      or os.getenv("OPENAI_API_KEY", "")
    )

    if prov in {"groq", "auto"}:
      if groq_key:
        model = configured_model if configured_model and "whisper" in configured_model else "whisper-large-v3"
        return "groq", groq_key, model

    if prov in {"openai", "auto"}:
      if openai_key:
        model = configured_model if configured_model and "whisper" in configured_model else "whisper-1"
        return "openai", openai_key, model

    # Fallback checking any available key
    if groq_key:
      return "groq", groq_key, configured_model or "whisper-large-v3"

    if openai_key:
      return "openai", openai_key, configured_model or "whisper-1"

    raise ValueError(
      "No se encontró una clave de API válida para transcripción en la nube. "
      "Configura tu Groq API Key o OpenAI API Key en Ajustes."
    )

  async def transcribe(
    self,
    audio_path: Path,
    language: Optional[str] = None,
    response_format: str = "verbose_json",
  ) -> Dict[str, Any]:
    provider, key, model = self._resolve_credentials()

    if not audio_path.exists():
      raise FileNotFoundError(f"El archivo de audio '{audio_path}' no existe.")

    # Select endpoint
    if provider == "groq":
      url = "https://api.groq.com/openai/v1/audio/transcriptions"
    else:
      url = "https://api.openai.com/v1/audio/transcriptions"

    headers = {
      "Authorization": f"Bearer {key}",
    }

    data: Dict[str, Any] = {
      "model": model,
      "response_format": response_format,
    }
    if language:
      data["language"] = language

    effective_audio_path = audio_path
    temp_compressed_path: Optional[Path] = None

    # If file size is large (>20MB) or uncompressed WAV, compress with ffmpeg to compact 48k mono MP3
    file_size = audio_path.stat().st_size
    if file_size > 20 * 1024 * 1024 or audio_path.suffix.lower() in {".wav", ".mkv", ".mp4", ".avi", ".webm", ".mov", ".flac"}:
      import shutil
      import subprocess
      ffmpeg_cmd = shutil.which("ffmpeg")
      if ffmpeg_cmd:
        comp_candidate = audio_path.parent / f"compressed_{audio_path.stem}.mp3"
        try:
          cmd = [
            ffmpeg_cmd,
            "-y",
            "-i", str(audio_path),
            "-vn",
            "-acodec", "libmp3lame",
            "-b:a", "48k",
            "-ar", "16000",
            "-ac", "1",
            str(comp_candidate),
          ]
          subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
          if comp_candidate.exists() and comp_candidate.stat().st_size > 0:
            effective_audio_path = comp_candidate
            temp_compressed_path = comp_candidate
            logger.info(f"Compressed audio for cloud upload: {file_size} -> {comp_candidate.stat().st_size} bytes")
        except Exception as e:
          logger.warning(f"Could not compress audio with ffmpeg: {e}")

    filename = effective_audio_path.name
    content_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"

    try:
      async with httpx.AsyncClient(timeout=300.0) as client:
        with open(effective_audio_path, "rb") as f:
          files = {
            "file": (filename, f, content_type),
          }
          response = await client.post(url, headers=headers, data=data, files=files)

        if response.status_code != 200:
          err_detail = response.text
          try:
            err_json = response.json()
            err_detail = err_json.get("error", {}).get("message", err_detail)
          except Exception:
            pass
          raise RuntimeError(f"Error del servicio de transcripción {provider} ({response.status_code}): {err_detail}")

        res_data = response.json()
    finally:
      if temp_compressed_path and temp_compressed_path.exists():
        try:
          temp_compressed_path.unlink()
        except Exception:
          pass

    # Parse response
    detected_lang = res_data.get("language", language or "es")
    full_text = res_data.get("text", "").strip()
    raw_segments = res_data.get("segments", [])
    duration = float(res_data.get("duration", 0.0))

    formatted_segments: List[Dict[str, Any]] = []

    if raw_segments:
      for idx, seg in enumerate(raw_segments):
        formatted_segments.append({
          "start": float(seg.get("start", 0.0)),
          "end": float(seg.get("end", 0.0)),
          "text": seg.get("text", "").strip(),
          "speaker": f"Participante {(idx % 2) + 1}",
        })
    else:
      # If verbose_json was not returned or had no segments, create a single segment
      formatted_segments.append({
        "start": 0.0,
        "end": duration,
        "text": full_text,
        "speaker": "Participante 1",
      })

    return {
      "language": detected_lang,
      "text": full_text,
      "segments": formatted_segments,
      "duration": duration,
      "provider": provider,
      "model": model,
    }

  def estimate_cost(self, duration_seconds: float) -> float:
    # OpenAI Whisper: ~$0.006 per minute. Groq Whisper: ~$0.0018 per minute.
    minutes = duration_seconds / 60.0
    if self.provider == "groq":
      return minutes * 0.0018
    return minutes * 0.006
