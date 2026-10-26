from __future__ import annotations

import json
import uuid
from typing import Any, List, Optional

from sqlalchemy import desc, select

from app.db.database import get_db
from app.db.models import AITemplateModel, AITemplateVersionModel


class AITemplateRepository:
  """PostgreSQL ORM repository for AI prompts, rubrics, and version history."""

  async def get_template(self, template_type: str, feature: str) -> Optional[dict[str, Any]]:
    template_id = f"{template_type}:{feature}"
    async with get_db() as db:
      stmt = select(AITemplateModel).where(AITemplateModel.id == template_id)
      result = await db.execute(stmt)
      tmpl = result.scalar_one_or_none()
      return tmpl.to_dict() if tmpl else None

  async def list_templates(self, template_type: str) -> List[dict[str, Any]]:
    async with get_db() as db:
      stmt = (
        select(AITemplateModel)
        .where(AITemplateModel.template_type == template_type)
        .order_by(AITemplateModel.feature.asc())
      )
      result = await db.execute(stmt)
      items = result.scalars().all()
      return [item.to_dict() for item in items]

  async def save_template_update(
    self,
    template_type: str,
    feature: str,
    new_data: dict[str, Any],
    updated_by: Optional[str] = None,
    change_summary: Optional[str] = None,
  ) -> dict[str, Any]:
    template_id = f"{template_type}:{feature}"
    async with get_db() as db:
      stmt = select(AITemplateModel).where(AITemplateModel.id == template_id)
      result = await db.execute(stmt)
      tmpl = result.scalar_one_or_none()

      if tmpl is None:
        raise KeyError(f"Template not found: {template_type}:{feature}")

      # Merge current payload with new data
      current_dict = tmpl.to_dict()
      merged = {**current_dict, **new_data, "feature": feature}
      next_version = int(tmpl.version or 1) + 1

      cleaned_payload = {
        k: v for k, v in merged.items()
        if k not in ("id", "template_type", "feature", "version", "updated_by", "created_at", "updated_at")
      }
      payload_json = json.dumps(cleaned_payload, ensure_ascii=False)

      tmpl.version = next_version
      tmpl.payload_json = payload_json
      tmpl.updated_by = updated_by

      version_entry = AITemplateVersionModel(
        id=str(uuid.uuid4()),
        template_id=template_id,
        template_type=template_type,
        feature=feature,
        version=next_version,
        payload_json=payload_json,
        change_summary=change_summary or f"Updated {template_type} for {feature}",
        created_by=updated_by,
      )
      db.add(version_entry)

      await db.commit()
      return tmpl.to_dict()

  async def get_version_history(
    self, template_type: str, feature: str, limit: int = 50
  ) -> List[dict[str, Any]]:
    template_id = f"{template_type}:{feature}"
    async with get_db() as db:
      stmt = (
        select(AITemplateVersionModel)
        .where(AITemplateVersionModel.template_id == template_id)
        .order_by(desc(AITemplateVersionModel.version))
      )
      if limit > 0:
        stmt = stmt.limit(limit)
      result = await db.execute(stmt)
      versions = result.scalars().all()
      return [v.to_dict() for v in versions]
