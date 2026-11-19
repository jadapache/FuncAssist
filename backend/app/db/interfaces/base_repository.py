from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, List, Optional, TypeVar

T = TypeVar("T")


class IBaseRepository(ABC, Generic[T]):
  """Contrato base para repositorios de persistencia."""

  @abstractmethod
  async def get_by_id(self, entity_id: str) -> Optional[T]:
    """Obtiene una entidad por su identificador primario."""
    pass

  @abstractmethod
  async def list(self, limit: int = 100, offset: int = 0) -> List[T]:
    """Lista entidades con paginación básica."""
    pass

  @abstractmethod
  async def delete(self, entity_id: str) -> bool:
    """Elimina una entidad por su identificador primario."""
    pass
