from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Iterable, List, Optional


class ITranscriptionRepository(ABC):
  """Contrato asíncrono para transcripciones."""

  @abstractmethod
  async def get(self, transcription_id: str) -> Optional[dict[str, Any]]:
    pass

  @abstractmethod
  async def list(self, user_id: Optional[str] = None) -> List[dict[str, Any]]:
    pass

  @abstractmethod
  async def list_by_status(self, statuses: Iterable[str], user_id: Optional[str] = None) -> List[dict[str, Any]]:
    pass

  @abstractmethod
  async def upsert(self, record: dict[str, Any]) -> dict[str, Any]:
    pass

  @abstractmethod
  async def update_progress(
    self,
    transcription_id: str,
    snapshot: dict[str, Any],
    *,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
  ) -> bool:
    pass

  @abstractmethod
  async def assign_owner(self, user_id: str, only_unowned: bool = True) -> int:
    pass

  @abstractmethod
  async def delete(self, transcription_id: str) -> bool:
    pass
