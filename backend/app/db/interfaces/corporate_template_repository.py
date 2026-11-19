from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class ICorporateTemplateRepository(ABC):
  """Contrato para plantillas corporativas."""

  @abstractmethod
  async def get(self, template_id: str) -> Optional[dict[str, Any]]:
    pass

  @abstractmethod
  async def list(self) -> List[dict[str, Any]]:
    pass

  @abstractmethod
  async def upsert(self, item: dict[str, Any]) -> dict[str, Any]:
    pass

  @abstractmethod
  async def delete(self, template_id: str) -> bool:
    pass
