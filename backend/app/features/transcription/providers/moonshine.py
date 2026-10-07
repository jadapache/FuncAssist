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


class MoonshineProvider(TranscriptionProvider):
  provider_id = "moonshine"
  display_name = "Moonshine (Useful Sensors — English only)"

  MODELS = {
    "moonshine-tiny": "UsefulSensors/moonshine-tiny",
    "moonshine-base": "UsefulSensors/moonshine-base",
  }

  def is_available(self) -> bool:
    try:
      import useful_moonshine  # noqa: F401

      return True
    except ImportError:
      try:
        import moonshine  # noqa: F401

        return True
      except ImportError:
        return False

  def _clean_model_id(self, model_id: str) -> str:
    clean = model_id.strip().lower()
    if clean not in self.MODELS:
      if "base" in clean:
        return "moonshine-base"
      return "moonshine-tiny"
    return clean

  def get_model_path(self, model_id: str) -> Optional[Path]:
    clean = self._clean_model_id(model_id)
    d = WHISPER_MODELS_DIR / clean
    return d if d.exists() else None

  def is_model_downloaded(self, model_id: str) -> bool:
    return self.get_model_path(model_id) is not None

  def transcribe(
    self,
    audio_path: Path,
    model_id: str,
    language: Optional[str] = None,
    on_progress: Optional[Callable[[int, str, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
  ) -> TranscriptionResult:
    if language and language.lower() not in ("en", "english", "eng", ""):
      raise ValueError(
        f"El motor Moonshine solo admite audio en inglés ('en'). Para '{language}', utilice Whisper o Faster Whisper."
      )

    try:
      try:
        import useful_moonshine as moonshine
      except ImportError:
        import moonshine
      import soundfile as sf
    except ImportError as exc:
      raise RuntimeError(
        "Para utilizar Moonshine instale las dependencias: 'pip install useful-moonshine soundfile'."
      ) from exc

    if cancel_check and cancel_check():
      raise RuntimeError("Transcripción cancelada por el usuario.")

    if on_progress:
      on_progress(25, "Cargando modelo Moonshine y decodificando audio...", "")

    clean = self._clean_model_id(model_id)
    repo = self.MODELS.get(clean, "UsefulSensors/moonshine-tiny")

    audio, sr = sf.read(str(audio_path), dtype="float32")
    if len(audio.shape) > 1:
      audio = audio.mean(axis=1)

    if sr != 16000:
      try:
        import librosa

        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
      except ImportError:
        pass

    if cancel_check and cancel_check():
      raise RuntimeError("Transcripción cancelada por el usuario.")

    transcript = moonshine.transcribe_with_timestamps(audio, repo)

    segments: List[TranscriptionSegment] = []
    for i, entry in enumerate(transcript):
      if cancel_check and cancel_check():
        raise RuntimeError("Transcripción cancelada por el usuario.")
      text = str(entry.get("text", "")).strip()
      segments.append(
        TranscriptionSegment(
          start=float(entry.get("start", 0.0)),
          end=float(entry.get("end", 0.0)),
          text=text,
          speaker=f"Participante {(i % 2) + 1}",
        )
      )

    full_text = " ".join(s.text for s in segments)
    duration = segments[-1].end if segments else (len(audio) / 16000.0)

    if on_progress:
      on_progress(75, "Transcripción con Moonshine finalizada.", "")

    return TranscriptionResult(
      language="en",
      text=full_text,
      segments=segments,
      duration=duration,
      provider=self.provider_id,
      engine="moonshine",
      model_id=model_id,
    )
