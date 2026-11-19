from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class ITranscriptionRepository(ABC):
  """Contrato asíncrono para transcripciones."""

  @abstractmethod
  async def get(self, transcription_id: str) -> Optional[dict[str, Any]]:
    pass

  @abstractmethod
  async def list(self) -> List[dict[str, Any]]:
    pass

  @abstractmethod
  async def upsert(self, record: dict[str, Any]) -> dict[str, Any]:
    pass

  @abstractmethod
  async def delete(self, transcription_id: str) -> bool:
    pass
