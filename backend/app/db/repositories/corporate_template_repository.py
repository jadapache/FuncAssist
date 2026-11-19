from __future__ import annotations

import json
from typing import Any, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interfaces.corporate_template_repository import ICorporateTemplateRepository
from app.db.models import CorporateTemplateModel


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

    title = item.get("title") or "Plantilla Corporativa"
    filename = item.get("filename") or f"{tid}.docx"
    stored_filename = item.get("stored_filename") or filename
    file_type = item.get("file_type") or "docx"
    file_size = int(item.get("file_size") or 0)
    module = item.get("module") or "general"
    tags = item.get("tags") or []
    custom_content = item.get("custom_content")

    stmt = select(CorporateTemplateModel).where(CorporateTemplateModel.id == tid)
    result = await self.session.execute(stmt)
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
      self.session.add(row)
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

    await self.session.flush()
    if hasattr(self.session, "refresh"):
      res = self.session.refresh(row)
      import inspect
      if inspect.isawaitable(res):
        await res
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
