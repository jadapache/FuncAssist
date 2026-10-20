"""AI prompt templates and rubrics persisted in PostgreSQL with audit history."""

from __future__ import annotations

import json
from typing import Any

from app.ai.seeds import DEFAULT_PROMPTS, DEFAULT_RUBRICS



from app.db.database import get_sync_db
from app.db.repositories.template_repository import AITemplateRepository

_repo = AITemplateRepository()
_DB_SEEDED = False


def ensure_ai_templates_seeded() -> None:
  """Seed default prompts and rubrics into PostgreSQL if they do not exist."""
  global _DB_SEEDED
  try:
    for feature, payload in DEFAULT_PROMPTS.items():
      existing = _repo.get_template_sync("prompt", feature)
      if existing is None:
        _repo.upsert_template_sync(
          template_type="prompt",
          feature=feature,
          payload=payload,
          version=int(payload.get("version") or 1),
          change_summary="Initial system seed",
          record_history=True,
        )
    for feature, payload in DEFAULT_RUBRICS.items():
      existing = _repo.get_template_sync("rubric", feature)
      if existing is None:
        _repo.upsert_template_sync(
          template_type="rubric",
          feature=feature,
          payload=payload,
          version=int(payload.get("version") or 1),
          change_summary="Initial system seed",
          record_history=True,
        )
    _DB_SEEDED = True
  except Exception:
    # If DB is temporarily unavailable or during offline setup, allow caller to fallback
    pass


def ensure_ai_files() -> None:
  """Ensure prompts and rubrics are seeded in PostgreSQL."""
  ensure_ai_templates_seeded()


def list_prompts() -> list[dict[str, Any]]:
  ensure_ai_templates_seeded()
  try:
    items = _repo.list_templates_sync("prompt")
    if items:
      return items
  except Exception:
    pass
  return [dict(DEFAULT_PROMPTS[f]) for f in sorted(DEFAULT_PROMPTS.keys())]


def list_rubrics() -> list[dict[str, Any]]:
  ensure_ai_templates_seeded()
  try:
    items = _repo.list_templates_sync("rubric")
    if items:
      return items
  except Exception:
    pass
  return [dict(DEFAULT_RUBRICS[f]) for f in sorted(DEFAULT_RUBRICS.keys())]


def get_prompt(feature: str) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  try:
    item = _repo.get_template_sync("prompt", feature)
    if item:
      return item
  except Exception:
    pass

  if feature in DEFAULT_PROMPTS:
    return dict(DEFAULT_PROMPTS[feature])
  raise KeyError(f"Unknown prompt feature: {feature}")


def get_rubric(feature: str) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  try:
    item = _repo.get_template_sync("rubric", feature)
    if item:
      return item
  except Exception:
    pass

  if feature in DEFAULT_RUBRICS:
    return dict(DEFAULT_RUBRICS[feature])
  raise KeyError(f"Unknown rubric feature: {feature}")


def save_prompt(
  feature: str,
  payload: dict[str, Any],
  updated_by: str | None = None,
  change_summary: str | None = None,
) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  current = get_prompt(feature)
  next_version = int(current.get("version") or 1) + 1
  merged = {**current, **payload, "feature": feature, "version": next_version}

  try:
    return _repo.upsert_template_sync(
      template_type="prompt",
      feature=feature,
      payload=merged,
      version=next_version,
      updated_by=updated_by,
      change_summary=change_summary or f"Updated prompt for {feature}",
      record_history=True,
    )
  except Exception:
    return merged


def save_rubric(
  feature: str,
  payload: dict[str, Any],
  updated_by: str | None = None,
  change_summary: str | None = None,
) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  current = get_rubric(feature)
  next_version = int(current.get("version") or 1) + 1
  merged = {**current, **payload, "feature": feature, "version": next_version}

  try:
    return _repo.upsert_template_sync(
      template_type="rubric",
      feature=feature,
      payload=merged,
      version=next_version,
      updated_by=updated_by,
      change_summary=change_summary or f"Updated rubric for {feature}",
      record_history=True,
    )
  except Exception:
    return merged


def rubric_to_text(rubric: dict[str, Any]) -> str:
  criteria = rubric.get("criteria") or []
  return "\n".join(f"- {item}" for item in criteria)


def reset_prompt(
  feature: str,
  updated_by: str | None = None,
) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  if feature not in DEFAULT_PROMPTS:
    raise KeyError(f"No default prompt found for feature: {feature}")

  current = get_prompt(feature)
  next_version = int(current.get("version") or 1) + 1
  default_payload = dict(DEFAULT_PROMPTS[feature])
  default_payload["version"] = next_version

  try:
    return _repo.upsert_template_sync(
      template_type="prompt",
      feature=feature,
      payload=default_payload,
      version=next_version,
      updated_by=updated_by,
      change_summary="Reset prompt to factory default",
      record_history=True,
    )
  except Exception:
    return default_payload


def reset_rubric(
  feature: str,
  updated_by: str | None = None,
) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  if feature not in DEFAULT_RUBRICS:
    raise KeyError(f"No default rubric found for feature: {feature}")

  current = get_rubric(feature)
  next_version = int(current.get("version") or 1) + 1
  default_payload = dict(DEFAULT_RUBRICS[feature])
  default_payload["version"] = next_version

  try:
    return _repo.upsert_template_sync(
      template_type="rubric",
      feature=feature,
      payload=default_payload,
      version=next_version,
      updated_by=updated_by,
      change_summary="Reset rubric to factory default",
      record_history=True,
    )
  except Exception:
    return default_payload


def get_template_history(template_type: str, feature: str, limit: int = 50) -> list[dict[str, Any]]:
  """Return chronological version audit history for a prompt or rubric."""
  template_id = f"{template_type}:{feature}"
  with get_sync_db() as db:
    from sqlalchemy import desc, select
    from app.db.models import AITemplateVersionModel
    stmt = (
      select(AITemplateVersionModel)
      .where(AITemplateVersionModel.template_id == template_id)
      .order_by(desc(AITemplateVersionModel.version))
    )
    if limit > 0:
      stmt = stmt.limit(limit)
    result = db.execute(stmt)
    versions = result.scalars().all()
    return [v.to_dict() for v in versions]
