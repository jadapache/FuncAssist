from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class IAIModelCatalogRepository(ABC):
  """Contrato para el catálogo de modelos de IA."""

  @abstractmethod
  def get(self, model_id: str) -> Optional[dict[str, Any]]:
    pass

  @abstractmethod
  def list(self, task_type: Optional[str] = None) -> List[dict[str, Any]]:
    pass

  @abstractmethod
  def delete_free_models(self) -> int:
    pass

  @abstractmethod
  def bulk_upsert(self, models: List[dict[str, Any]]) -> int:
    pass

  @abstractmethod
  def replace_external(self, models: List[dict[str, Any]]) -> int:
    pass
