"""PostgreSQL ORM repository for Built-in AI models catalog."""

from __future__ import annotations

import json
from typing import Any, List, Optional

from sqlalchemy import select

from app.db.database import get_db, get_sync_db
from app.db.models import AIModelCatalogModel


class BuiltinModelRepository:
  """PostgreSQL ORM repository for built-in AI models."""

  def get_sync(self, model_id: str) -> Optional[dict[str, Any]]:
    clean = model_id.strip()
    with get_sync_db() as db:
      stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == clean)
      row = db.execute(stmt).scalar_one_or_none()
      if row:
        return row.to_dict()
      # Search in aliases / filenames within payload
      stmt_all = select(AIModelCatalogModel).where(
        AIModelCatalogModel.provider.in_(["builtin", "onnx", "local", "faster-whisper", "moonshine"])
      )
      for r in db.execute(stmt_all).scalars().all():
        d = r.to_dict()
        aliases = [a.lower() for a in d.get("aliases", [])]
        if clean.lower() in aliases or clean.lower() == d.get("filename", "").lower():
          return d
      return None

  def list_sync(self, task_type: Optional[str] = None) -> List[dict[str, Any]]:
    with get_sync_db() as db:
      stmt = select(AIModelCatalogModel).where(
        AIModelCatalogModel.provider.in_(["builtin", "onnx", "local", "faster-whisper", "moonshine"])
      )
      if task_type:
        stmt = stmt.where(AIModelCatalogModel.task_type == task_type)
      stmt = stmt.order_by(AIModelCatalogModel.name.asc())
      rows = db.execute(stmt).scalars().all()
      return [r.to_dict() for r in rows]

  async def list(self, task_type: Optional[str] = None) -> List[dict[str, Any]]:
    async with get_db() as db:
      stmt = select(AIModelCatalogModel).where(
        AIModelCatalogModel.provider.in_(["builtin", "onnx", "local", "faster-whisper", "moonshine"])
      )
      if task_type:
        stmt = stmt.where(AIModelCatalogModel.task_type == task_type)
      stmt = stmt.order_by(AIModelCatalogModel.name.asc())
      result = await db.execute(stmt)
      return [r.to_dict() for r in result.scalars().all()]

  def bulk_upsert_sync(self, models: List[dict[str, Any]]) -> int:
    with get_sync_db() as db:
      count = 0
      for m in models:
        mid = m.get("id")
        if not mid:
          continue
        prov = m.get("provider", "builtin")
        task_type = m.get("task_type", "chat_writing")
        name = m.get("name", mid)
        is_free = bool(m.get("is_free", True))
        tier_type = m.get("tier_type", "free")
        payload_json = json.dumps(m, ensure_ascii=False)

        stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == mid)
        row = db.execute(stmt).scalar_one_or_none()

        if row is None:
          row = AIModelCatalogModel(
            id=mid,
            provider=prov,
            task_type=task_type,
            name=name,
            is_free=is_free,
            tier_type=tier_type,
            payload_json=payload_json,
          )
          db.add(row)
        else:
          row.provider = prov
          row.task_type = task_type
          row.name = name
          row.is_free = is_free
          row.tier_type = tier_type
          row.payload_json = payload_json
        count += 1
      db.commit()
      return count

