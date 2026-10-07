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

  def get_model_path(self, model_id: str) -> Optional[Path]:
    from app.features.transcription.whisper_local import get_whisper_cache_dir

    clean = model_id.replace("whisper-", "").strip().lower()
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

    clean = model_id.replace("whisper-", "").strip().lower()
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
