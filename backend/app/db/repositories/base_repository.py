from __future__ import annotations

from typing import Any, Generic, List, Optional, Type, TypeVar
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interfaces.base_repository import IBaseRepository

ModelType = TypeVar("ModelType")


class BaseRepository(IBaseRepository[ModelType], Generic[ModelType]):
  """Implementación base asíncrona de SQLAlchemy para IBaseRepository."""

  def __init__(self, session: AsyncSession, model_cls: Type[ModelType]) -> None:
    self.session = session
    self.model_cls = model_cls

  async def get_by_id(self, entity_id: str) -> Optional[ModelType]:
    stmt = select(self.model_cls).where(getattr(self.model_cls, "id") == entity_id)
    result = await self.session.execute(stmt)
    return result.scalar_one_or_none()

  async def list(self, limit: int = 100, offset: int = 0) -> List[ModelType]:
    stmt = select(self.model_cls).limit(limit).offset(offset)
    result = await self.session.execute(stmt)
    return list(result.scalars().all())

  async def delete(self, entity_id: str) -> bool:
    stmt = select(self.model_cls).where(getattr(self.model_cls, "id") == entity_id)
    result = await self.session.execute(stmt)
    item = result.scalar_one_or_none()
    if not item:
      return False
    await self.session.delete(item)
    await self.session.flush()
    return True
