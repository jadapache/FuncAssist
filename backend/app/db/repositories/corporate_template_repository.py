from __future__ import annotations

import json
from typing import Any, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interfaces.corporate_template_repository import ICorporateTemplateRepository
from app.db.models import CorporateTemplateModel


def _template_columns(item: dict[str, Any], template_id: str) -> dict[str, Any]:
  """The stored columns of a corporate template, with the defaults for whatever the item leaves out."""
  filename = item.get("filename") or f"{template_id}.docx"
  return {
    "id": template_id,
    "title": item.get("title") or "Plantilla Corporativa",
    "filename": filename,
    "stored_filename": item.get("stored_filename") or filename,
    "file_type": item.get("file_type") or "docx",
    "file_size": int(item.get("file_size") or 0),
    "module": item.get("module") or "general",
    "tags_json": json.dumps(item.get("tags") or [], ensure_ascii=False),
  }


class CorporateTemplateRepository(ICorporateTemplateRepository):
  """PostgreSQL ORM repository for corporate document templates with injected AsyncSession."""

  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  async def get(self, template_id: str) -> Optional[dict[str, Any]]:
    stmt = select(CorporateTemplateModel).where(CorporateTemplateModel.id == template_id)
    result = await self.session.execute(stmt)
    row = result.scalar_one_or_none()
    return row.to_dict() if row else None

  async def list(self) -> List[dict[str, Any]]:
    stmt = select(CorporateTemplateModel).order_by(CorporateTemplateModel.title.asc())
    result = await self.session.execute(stmt)
    items = result.scalars().all()
    return [item.to_dict() for item in items]

  async def upsert(self, item: dict[str, Any]) -> dict[str, Any]:
    tid = item.get("id")
    if not tid:
      raise ValueError("La plantilla corporativa debe tener un 'id'")

    columns = _template_columns(item, tid)
    stmt = select(CorporateTemplateModel).where(CorporateTemplateModel.id == tid)
    row = (await self.session.execute(stmt)).scalar_one_or_none()
    if row is None:
      row = CorporateTemplateModel(**columns, custom_content=item.get("custom_content"))
      self.session.add(row)
    else:
      for name, value in columns.items():
        setattr(row, name, value)
      if item.get("custom_content") is not None:
        row.custom_content = item["custom_content"]

    await self.session.flush()
    await self.session.refresh(row)
    return row.to_dict()

  async def delete(self, template_id: str) -> bool:
    stmt = select(CorporateTemplateModel).where(CorporateTemplateModel.id == template_id)
    result = await self.session.execute(stmt)
    row = result.scalar_one_or_none()
    if row:
      await self.session.delete(row)
      await self.session.flush()
      return True
    return False
