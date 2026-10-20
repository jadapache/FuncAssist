from __future__ import annotations

import json
from typing import Any, List, Optional

from sqlalchemy import desc, select

from app.db.database import get_db, get_sync_db
from app.db.models import AIModelCatalogModel, CorporateTemplateModel


class CorporateTemplateRepository:
  """PostgreSQL ORM repository for corporate document templates."""

  def get_sync(self, template_id: str) -> Optional[dict[str, Any]]:
    with get_sync_db() as db:
      stmt = select(CorporateTemplateModel).where(CorporateTemplateModel.id == template_id)
      result = db.execute(stmt)
      row = result.scalar_one_or_none()
      return row.to_dict() if row else None

  def list_sync(self) -> List[dict[str, Any]]:
    with get_sync_db() as db:
      stmt = select(CorporateTemplateModel).order_by(CorporateTemplateModel.title.asc())
      result = db.execute(stmt)
      items = result.scalars().all()
      return [item.to_dict() for item in items]

  def upsert_sync(self, item: dict[str, Any]) -> dict[str, Any]:
    tid = item.get("id")
    if not tid:
      raise ValueError("Corporate template must have an 'id'")

    title = item.get("title") or "Plantilla Corporativa"
    filename = item.get("filename") or f"{tid}.docx"
    stored_filename = item.get("stored_filename") or filename
    file_type = item.get("file_type") or "docx"
    file_size = int(item.get("file_size") or 0)
    module = item.get("module") or "general"
    tags = item.get("tags") or []
    custom_content = item.get("custom_content")

    with get_sync_db() as db:
      stmt = select(CorporateTemplateModel).where(CorporateTemplateModel.id == tid)
      result = db.execute(stmt)
      row = result.scalar_one_or_none()

      if row is None:
        row = CorporateTemplateModel(
          id=tid,
          title=title,
          filename=filename,
          stored_filename=stored_filename,
          file_type=file_type,
          file_size=file_size,
          module=module,
          tags_json=json.dumps(tags, ensure_ascii=False),
          custom_content=custom_content,
        )
        db.add(row)
      else:
        row.title = title
        row.filename = filename
        row.stored_filename = stored_filename
        row.file_type = file_type
        row.file_size = file_size
        row.module = module
        row.tags_json = json.dumps(tags, ensure_ascii=False)
        if custom_content is not None:
          row.custom_content = custom_content

      db.commit()
      db.refresh(row)
      return row.to_dict()

  def delete_sync(self, template_id: str) -> bool:
    with get_sync_db() as db:
      stmt = select(CorporateTemplateModel).where(CorporateTemplateModel.id == template_id)
      result = db.execute(stmt)
      row = result.scalar_one_or_none()
      if row:
        db.delete(row)
        db.commit()
        return True
      return False


class AIModelCatalogRepository:
  """PostgreSQL ORM repository for AI model catalog."""

  def get_sync(self, model_id: str) -> Optional[dict[str, Any]]:
    with get_sync_db() as db:
      stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == model_id)
      result = db.execute(stmt)
      row = result.scalar_one_or_none()
      return row.to_dict() if row else None

  def list_sync(self, task_type: Optional[str] = None) -> List[dict[str, Any]]:
    with get_sync_db() as db:
      stmt = select(AIModelCatalogModel)
      if task_type:
        stmt = stmt.where(AIModelCatalogModel.task_type == task_type)
      stmt = stmt.order_by(AIModelCatalogModel.name.asc())
      result = db.execute(stmt)
      items = result.scalars().all()
      return [item.to_dict() for item in items]

  def bulk_upsert_sync(self, models: List[dict[str, Any]]) -> int:
    with get_sync_db() as db:
      count = 0
      for m in models:
        mid = m.get("id")
        if not mid:
          continue
        prov = m.get("provider", "groq")
        task_type = m.get("task_type", "chat_writing")
        name = m.get("name", mid)
        is_free = bool(m.get("is_free", False))
        tier_type = m.get("tier_type", "free" if is_free else "paid")
        payload_json = json.dumps(m, ensure_ascii=False)

        stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == mid)
        result = db.execute(stmt)
        row = result.scalar_one_or_none()

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
