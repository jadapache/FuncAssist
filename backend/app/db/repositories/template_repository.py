from __future__ import annotations

import json
import uuid
from typing import Any, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interfaces.template_repository import IAITemplateRepository
from app.db.models import AITemplateModel, AITemplateVersionModel


_NON_PAYLOAD_KEYS = ("id", "template_type", "feature", "version", "updated_by", "created_at", "updated_at")
_OBSOLETE_IDS = ("prompt:transcript_summary", "rubric:transcript_summary")


def _payload_json(data: dict[str, Any]) -> str:
  """What is stored as the template body: everything except the columns that have their own field."""
  return json.dumps({k: v for k, v in data.items() if k not in _NON_PAYLOAD_KEYS}, ensure_ascii=False)


class AITemplateRepository(IAITemplateRepository):
  """PostgreSQL ORM repository for AI prompts, rubrics, and version history."""

  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  async def get_template(self, template_type: str, feature: str) -> Optional[dict[str, Any]]:
    template_id = f"{template_type}:{feature}"
    stmt = select(AITemplateModel).where(AITemplateModel.id == template_id)
    result = await self.session.execute(stmt)
    tmpl = result.scalar_one_or_none()
    return tmpl.to_dict() if tmpl else None

  async def list_templates(
    self, template_type: str, tag: Optional[str] = None
  ) -> List[dict[str, Any]]:
    stmt = select(AITemplateModel).where(AITemplateModel.template_type == template_type)
    if tag:
      stmt = stmt.where(AITemplateModel.tag == tag)
    stmt = stmt.order_by(AITemplateModel.feature.asc())
    result = await self.session.execute(stmt)
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
    stmt = select(AITemplateModel).where(AITemplateModel.id == template_id)
    tmpl = (await self.session.execute(stmt)).scalar_one_or_none()
    if tmpl is None:
      tmpl = self._create_template(template_type, feature, new_data, updated_by, change_summary)
    else:
      self._update_template(tmpl, feature, new_data, updated_by, change_summary)
    await self.session.flush()
    await self.session.refresh(tmpl)
    return tmpl.to_dict()

  def _create_template(
    self,
    template_type: str,
    feature: str,
    new_data: dict[str, Any],
    updated_by: Optional[str],
    change_summary: Optional[str],
  ) -> AITemplateModel:
    template_id = f"{template_type}:{feature}"
    tag = new_data.get("tag")
    version = int(new_data.get("version") or 1)
    payload_json = _payload_json(new_data)
    author = updated_by or "user"
    summary = change_summary or f"Created {template_type} for {feature}"
    tmpl = AITemplateModel(
      id=template_id,
      template_type=template_type,
      feature=feature,
      tag=tag,
      version=version,
      payload_json=payload_json,
      updated_by=author,
    )
    self.session.add(tmpl)
    self.session.add(
      AITemplateVersionModel(
        id=str(uuid.uuid4()),
        template_id=template_id,
        template_type=template_type,
        feature=feature,
        tag=tag,
        version=version,
        payload_json=payload_json,
        change_summary=summary,
        created_by=author,
      )
    )
    return tmpl

  def _update_template(
    self,
    tmpl: AITemplateModel,
    feature: str,
    new_data: dict[str, Any],
    updated_by: Optional[str],
    change_summary: Optional[str],
  ) -> None:
    tag = new_data.get("tag")
    next_version = int(tmpl.version or 1) + 1
    payload_json = _payload_json({**tmpl.to_dict(), **new_data, "feature": feature})

    tmpl.version = next_version
    tmpl.payload_json = payload_json
    tmpl.updated_by = updated_by
    if tag:
      tmpl.tag = tag
    summary = change_summary or f"Updated {tmpl.template_type} for {feature}"

    self.session.add(
      AITemplateVersionModel(
        id=str(uuid.uuid4()),
        template_id=tmpl.id,
        template_type=tmpl.template_type,
        feature=feature,
        tag=tmpl.tag,
        version=next_version,
        payload_json=payload_json,
        change_summary=summary,
        created_by=updated_by,
      )
    )

  async def get_version_history(
    self, template_type: str, feature: str, limit: int = 50
  ) -> List[dict[str, Any]]:
    template_id = f"{template_type}:{feature}"
    stmt = select(AITemplateVersionModel).where(AITemplateVersionModel.template_id == template_id)
    stmt = stmt.order_by(desc(AITemplateVersionModel.version))
    if limit > 0:
      stmt = stmt.limit(limit)
    result = await self.session.execute(stmt)
    versions = result.scalars().all()
    return [v.to_dict() for v in versions]

  async def seed_defaults(
    self,
    default_prompts: dict[str, Any],
    default_rubrics: dict[str, Any],
  ) -> None:
    existing = (await self.session.execute(select(AITemplateModel))).scalars().all()
    existing_ids = {item.id for item in existing}

    for entry in existing:
      if entry.id in _OBSOLETE_IDS:
        await self.session.delete(entry)

    self._seed_missing("prompt", default_prompts, existing_ids)
    self._seed_missing("rubric", default_rubrics, existing_ids)
    await self.session.flush()

  def _seed_missing(self, template_type: str, defaults: dict[str, Any], existing_ids: set[str]) -> None:
    """Add the defaults of one kind that are not stored yet, each with its first history entry."""
    for feature, payload in defaults.items():
      template_id = f"{template_type}:{feature}"
      if template_id in existing_ids:
        continue
      payload_json = _payload_json(payload)
      version = int(payload.get("version") or 1)
      tag = payload.get("tag")
      self.session.add(
        AITemplateModel(
          id=template_id,
          template_type=template_type,
          feature=feature,
          tag=tag,
          version=version,
          payload_json=payload_json,
          updated_by="system",
        )
      )
      self.session.add(
        AITemplateVersionModel(
          id=str(uuid.uuid4()),
          template_id=template_id,
          template_type=template_type,
          feature=feature,
          tag=tag,
          version=version,
          payload_json=payload_json,
          change_summary="Initial system seed",
          created_by="system",
        )
      )
