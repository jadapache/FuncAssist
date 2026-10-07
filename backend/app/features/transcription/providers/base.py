from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class TranscriptionSegment:
  start: float
  end: float
  text: str
  speaker: str = "Participante 1"


@dataclass
class TranscriptionResult:
  language: str
  text: str
  segments: List[TranscriptionSegment]
  duration: float
  provider: str
  engine: str
  model_id: str


class TranscriptionProvider(ABC):
  """
  Abstract base for all built-in transcription engines.
  Concrete providers implement is_available(), get_model_path(), is_model_downloaded(), and transcribe().
  """

  provider_id: str
  display_name: str

  @abstractmethod
  def is_available(self) -> bool:
    """Return True if all required dependencies and binaries are present."""
    ...

  @abstractmethod
  def get_model_path(self, model_id: str) -> Optional[Path]:
    """Return the on-disk path for the given model_id, or None if not downloaded."""
    ...

  @abstractmethod
  def is_model_downloaded(self, model_id: str) -> bool:
    ...

  @abstractmethod
  def transcribe(
    self,
    audio_path: Path,
    model_id: str,
    language: Optional[str] = None,
    on_progress: Optional[Callable[[int, str, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
  ) -> TranscriptionResult:
    ...

  def list_supported_models(self) -> List[Dict[str, Any]]:
    """Return list of model entries supported by this provider."""
    return []
