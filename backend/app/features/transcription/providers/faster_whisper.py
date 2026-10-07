from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.core.settings import WHISPER_MODELS_DIR
from app.features.transcription.providers.base import (
  TranscriptionProvider,
  TranscriptionResult,
  TranscriptionSegment,
)

logger = logging.getLogger(__name__)


class FasterWhisperProvider(TranscriptionProvider):
  provider_id = "faster-whisper"
  display_name = "Faster Whisper (CTranslate2)"

  SUPPORTED_MODELS = ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]
  HF_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "Systran/faster-whisper-large-v3-turbo",
  }

  def is_available(self) -> bool:
    try:
      from faster_whisper import WhisperModel  # noqa: F401

      return True
    except ImportError:
      return False

  def _clean_model_id(self, model_id: str) -> str:
    clean = model_id.strip().lower()
    clean = clean.replace("fw-", "").replace("faster-whisper-", "").replace("whisper-", "")
    return clean

  def _model_dir(self, model_id: str) -> Path:
    clean = self._clean_model_id(model_id)
    return WHISPER_MODELS_DIR / f"faster-whisper-{clean}"

  def get_model_path(self, model_id: str) -> Optional[Path]:
    d = self._model_dir(model_id)
    if (d / "model.bin").exists():
      return d
    return None

  def is_model_downloaded(self, model_id: str) -> bool:
    d = self._model_dir(model_id)
    return (d / "model.bin").exists()

  def transcribe(
    self,
    audio_path: Path,
    model_id: str,
    language: Optional[str] = None,
    on_progress: Optional[Callable[[int, str, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
  ) -> TranscriptionResult:
    try:
      from faster_whisper import WhisperModel
    except ImportError as exc:
      raise RuntimeError(
        "El paquete 'faster-whisper' no está instalado. Ejecute 'pip install faster-whisper'."
      ) from exc

    clean = self._clean_model_id(model_id)
    model_dir = self._model_dir(clean)
    model_source = str(model_dir) if (model_dir / "model.bin").exists() else self.HF_REPOS.get(clean, clean)

    logger.info(f"Loading faster-whisper model: {model_source}")
    model = WhisperModel(
      model_source,
      device="auto",
      compute_type="auto",
      download_root=str(WHISPER_MODELS_DIR),
    )

    segments_gen, info = model.transcribe(
      str(audio_path),
      language=language,
      beam_size=5,
    )

    segments: List[TranscriptionSegment] = []
    full_text_parts: List[str] = []
    total_duration = info.duration or 1.0

    for i, seg in enumerate(segments_gen):
      if cancel_check and cancel_check():
        raise RuntimeError("Transcripción cancelada por el usuario.")
      text = seg.text.strip()
      segments.append(
        TranscriptionSegment(
          start=float(seg.start),
          end=float(seg.end),
          text=text,
          speaker=f"Participante {(i % 2) + 1}",
        )
      )
      full_text_parts.append(text)
      if on_progress:
        pct = min(79, 20 + int((seg.end / total_duration) * 55))
        on_progress(pct, f"Segmento {i+1}: {text[:40]}...", "")

    return TranscriptionResult(
      language=info.language or language or "es",
      text=" ".join(full_text_parts),
      segments=segments,
      duration=total_duration,
      provider=self.provider_id,
      engine="faster-whisper",
      model_id=model_id,
    )
