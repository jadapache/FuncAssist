from __future__ import annotations

import json
import uuid
from typing import Any, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interfaces.template_repository import IAITemplateRepository
from app.db.models import AITemplateModel, AITemplateVersionModel


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
    stmt = (
      select(AITemplateModel)
      .where(AITemplateModel.template_type == template_type)
    )
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
    tag = new_data.get("tag")
    stmt = select(AITemplateModel).where(AITemplateModel.id == template_id)
    result = await self.session.execute(stmt)
    tmpl = result.scalar_one_or_none()

    if tmpl is None:
      version = int(new_data.get("version") or 1)
      cleaned_payload = {
        k: v for k, v in new_data.items()
        if k not in ("id", "template_type", "feature", "version", "updated_by", "created_at", "updated_at")
      }
      payload_json = json.dumps(cleaned_payload, ensure_ascii=False)
      tmpl = AITemplateModel(
        id=template_id,
        template_type=template_type,
        feature=feature,
        tag=tag,
        version=version,
        payload_json=payload_json,
        updated_by=updated_by or "user",
      )
      self.session.add(tmpl)
      version_entry = AITemplateVersionModel(
        id=str(uuid.uuid4()),
        template_id=template_id,
        template_type=template_type,
        feature=feature,
        tag=tag,
        version=version,
        payload_json=payload_json,
        change_summary=change_summary or f"Created {template_type} for {feature}",
        created_by=updated_by or "user",
      )
      self.session.add(version_entry)
      await self.session.flush()
      return tmpl.to_dict()

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
    if tag:
      tmpl.tag = tag

    version_entry = AITemplateVersionModel(
      id=str(uuid.uuid4()),
      template_id=template_id,
      template_type=template_type,
      feature=feature,
      tag=tag or tmpl.tag,
      version=next_version,
      payload_json=payload_json,
      change_summary=change_summary or f"Updated {template_type} for {feature}",
      created_by=updated_by,
    )
    self.session.add(version_entry)
    await self.session.flush()
    return tmpl.to_dict()

  async def get_version_history(
    self, template_type: str, feature: str, limit: int = 50
  ) -> List[dict[str, Any]]:
    template_id = f"{template_type}:{feature}"
    stmt = (
      select(AITemplateVersionModel)
      .where(AITemplateVersionModel.template_id == template_id)
      .order_by(desc(AITemplateVersionModel.version))
    )
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
    stmt = select(AITemplateModel)
    result = await self.session.execute(stmt)
    items = result.scalars().all()
    existing_ids = {item.id for item in items}

    for obsolete_id in ("prompt:transcript_summary", "rubric:transcript_summary"):
      if obsolete_id in existing_ids:
        obs_res = await self.session.execute(
          select(AITemplateModel).where(AITemplateModel.id == obsolete_id)
        )
        obs_entry = obs_res.scalar_one_or_none()
        if obs_entry:
          await self.session.delete(obs_entry)

    for feature, payload in default_prompts.items():
      template_id = f"prompt:{feature}"
      if template_id not in existing_ids:
        cleaned_payload = {
          k: v for k, v in payload.items()
          if k not in ("id", "template_type", "feature", "version", "updated_by", "created_at", "updated_at")
        }
        payload_json = json.dumps(cleaned_payload, ensure_ascii=False)
        version = int(payload.get("version") or 1)
        tag = payload.get("tag")

        tmpl = AITemplateModel(
          id=template_id,
          template_type="prompt",
          feature=feature,
          tag=tag,
          version=version,
          payload_json=payload_json,
          updated_by="system",
        )
        version_entry = AITemplateVersionModel(
          id=str(uuid.uuid4()),
          template_id=template_id,
          template_type="prompt",
          feature=feature,
          tag=tag,
          version=version,
          payload_json=payload_json,
          change_summary="Initial system seed",
          created_by="system",
        )
        self.session.add(tmpl)
        self.session.add(version_entry)

    for feature, payload in default_rubrics.items():
      template_id = f"rubric:{feature}"
      if template_id not in existing_ids:
        cleaned_payload = {
          k: v for k, v in payload.items()
          if k not in ("id", "template_type", "feature", "version", "updated_by", "created_at", "updated_at")
        }
        payload_json = json.dumps(cleaned_payload, ensure_ascii=False)
        version = int(payload.get("version") or 1)
        tag = payload.get("tag")

        tmpl = AITemplateModel(
          id=template_id,
          template_type="rubric",
          feature=feature,
          tag=tag,
          version=version,
          payload_json=payload_json,
          updated_by="system",
        )
        version_entry = AITemplateVersionModel(
          id=str(uuid.uuid4()),
          template_id=template_id,
          template_type="rubric",
          feature=feature,
          tag=tag,
          version=version,
          payload_json=payload_json,
          change_summary="Initial system seed",
          created_by="system",
        )
        self.session.add(tmpl)
        self.session.add(version_entry)

    await self.session.flush()
