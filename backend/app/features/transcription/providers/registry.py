from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.features.transcription.providers.base import (
  TranscriptionProvider,
  TranscriptionResult,
  TranscriptionSegment,
)

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, TranscriptionProvider] = {}


def register_provider(provider: TranscriptionProvider) -> None:
  _REGISTRY[provider.provider_id] = provider


def get_provider(provider_id: str) -> Optional[TranscriptionProvider]:
  return _REGISTRY.get(provider_id)


def list_all_providers() -> List[TranscriptionProvider]:
  return list(_REGISTRY.values())


def list_available_providers() -> List[TranscriptionProvider]:
  return [p for p in _REGISTRY.values() if p.is_available()]


def _bootstrap() -> None:
  try:
    from app.features.transcription.providers.openai_whisper import OpenAIWhisperProvider

    register_provider(OpenAIWhisperProvider())
  except Exception as exc:
    logger.debug(f"OpenAIWhisperProvider registration error: {exc}")

  try:
    from app.features.transcription.providers.faster_whisper import FasterWhisperProvider

    register_provider(FasterWhisperProvider())
  except Exception as exc:
    logger.debug(f"FasterWhisperProvider registration error: {exc}")

  try:
    from app.features.transcription.providers.moonshine import MoonshineProvider

    register_provider(MoonshineProvider())
  except Exception as exc:
    logger.debug(f"MoonshineProvider registration error: {exc}")

  try:
    from app.features.transcription.providers.onnx_provider import OnnxTranscriptionProvider

    register_provider(OnnxTranscriptionProvider())
  except Exception as exc:
    logger.debug(f"OnnxTranscriptionProvider registration error: {exc}")


_bootstrap()
