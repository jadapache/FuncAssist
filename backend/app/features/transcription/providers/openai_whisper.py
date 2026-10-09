from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.features.transcription.providers.base import (
  TranscriptionProvider,
  TranscriptionResult,
  TranscriptionSegment,
)


class OpenAIWhisperProvider(TranscriptionProvider):
  provider_id = "whisper-python"
  display_name = "Whisper (openai-whisper)"

  def is_available(self) -> bool:
    try:
      import whisper  # noqa: F401

      return True
    except ImportError:
      return False

  def _clean_model_id(self, model_id: str) -> str:
    clean = model_id.replace("whisper-", "").replace("fw-", "").replace("faster-whisper-", "").strip().lower()
    valid_sizes = {
      "tiny", "tiny.en", "base", "base.en", "small", "small.en",
      "medium", "medium.en", "large", "large-v1", "large-v2", "large-v3", "large-v3-turbo", "turbo"
    }
    if clean not in valid_sizes:
      if "tiny" in clean:
        return "tiny"
      if "small" in clean:
        return "small"
      if "medium" in clean:
        return "medium"
      if "large" in clean and "turbo" in clean:
        return "large-v3-turbo"
      if "large" in clean:
        return "large-v3"
      return "base"
    return clean

  def get_model_path(self, model_id: str) -> Optional[Path]:
    from app.features.transcription.whisper_local import get_whisper_cache_dir

    clean = self._clean_model_id(model_id)
    path = get_whisper_cache_dir() / f"{clean}.pt"
    return path if path.exists() else None

  def is_model_downloaded(self, model_id: str) -> bool:
    path = self.get_model_path(model_id)
    return path is not None and path.stat().st_size > 1024 * 1024

  def transcribe(
    self,
    audio_path: Path,
    model_id: str,
    language: Optional[str] = None,
    on_progress: Optional[Callable[[int, str, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
  ) -> TranscriptionResult:
    from app.features.transcription.whisper_local import WhisperLocalService

    clean = self._clean_model_id(model_id)
    svc = WhisperLocalService(model_size=clean)
    raw = svc.transcribe(
      audio_path,
      language=language,
      on_progress=on_progress,
      cancel_check=cancel_check,
    )

    segments = [
      TranscriptionSegment(
        start=float(s.get("start", 0.0)),
        end=float(s.get("end", 0.0)),
        text=s.get("text", "").strip(),
        speaker=s.get("speaker", "Participante 1"),
      )
      for s in raw.get("segments", [])
    ]

    return TranscriptionResult(
      language=raw.get("language", language or "es"),
      text=raw.get("text", "").strip(),
      segments=segments,
      duration=float(raw.get("duration", 0.0)),
      provider=self.provider_id,
      engine="openai-whisper",
      model_id=model_id,
    )
