"""AI prompt templates and rubrics persisted in PostgreSQL with audit history."""

from __future__ import annotations


import json

from typing import Any


from app.ai.seeds import DEFAULT_PROMPTS, DEFAULT_RUBRICS
from app.db.repositories.template_repository import AITemplateRepository


_DB_SEEDED = False
DEFAULT_TRANSCRIPT_SUMMARY_FEATURE = "transcript_summary_standard_meeting"


def ensure_ai_templates_seeded() -> None:
  """Seed default prompts and rubrics into PostgreSQL if they do not exist."""
  global _DB_SEEDED
  if _DB_SEEDED:
    return

  try:
    import asyncio
    from app.db.unit_of_work import AsyncUnitOfWork

    async def _seed():
      async with AsyncUnitOfWork() as uow:
        await uow.ai_templates.seed_defaults(DEFAULT_PROMPTS, DEFAULT_RUBRICS)
        await uow.commit()

    try:
      loop = asyncio.get_running_loop()
      loop.create_task(_seed())
    except RuntimeError:
      asyncio.run(_seed())

    _DB_SEEDED = True
  except Exception:
    # If DB is temporarily unavailable or during offline setup, allow caller to fallback
    pass


def ensure_ai_files() -> None:
  """Ensure prompts and rubrics are seeded in PostgreSQL."""
  ensure_ai_templates_seeded()


async def list_prompts(tag: str | None = None) -> list[dict[str, Any]]:
  ensure_ai_templates_seeded()
  try:
    from app.db.unit_of_work import AsyncUnitOfWork
    async with AsyncUnitOfWork() as uow:
      items = await uow.ai_templates.list_templates("prompt", tag=tag)
      if items:
        return items
  except Exception:
    pass

  prompts = [dict(DEFAULT_PROMPTS[f]) for f in sorted(DEFAULT_PROMPTS.keys())]
  if tag:
    return [p for p in prompts if p.get("tag") == tag]
  return prompts


async def list_rubrics(tag: str | None = None) -> list[dict[str, Any]]:
  ensure_ai_templates_seeded()
  try:
    from app.db.unit_of_work import AsyncUnitOfWork
    async with AsyncUnitOfWork() as uow:
      items = await uow.ai_templates.list_templates("rubric", tag=tag)
      if items:
        return items
  except Exception:
    pass

  rubrics = [dict(DEFAULT_RUBRICS[f]) for f in sorted(DEFAULT_RUBRICS.keys())]
  if tag:
    return [r for r in rubrics if r.get("tag") == tag]
  return rubrics


async def get_prompt(feature: str) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  resolved_feature = (
    DEFAULT_TRANSCRIPT_SUMMARY_FEATURE
    if feature == "transcript_summary"
    else feature
  )
  try:
    from app.db.unit_of_work import AsyncUnitOfWork
    async with AsyncUnitOfWork() as uow:
      item = await uow.ai_templates.get_template("prompt", resolved_feature)
      if item:
        return item
  except Exception:
    pass

  if resolved_feature in DEFAULT_PROMPTS:
    return dict(DEFAULT_PROMPTS[resolved_feature])

  raise KeyError(f"Unknown prompt feature: {feature}")


async def get_rubric(feature: str) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  resolved_feature = (
    DEFAULT_TRANSCRIPT_SUMMARY_FEATURE
    if feature == "transcript_summary"
    else feature
  )
  try:
    from app.db.unit_of_work import AsyncUnitOfWork
    async with AsyncUnitOfWork() as uow:
      item = await uow.ai_templates.get_template("rubric", resolved_feature)
      if item:
        return item
  except Exception:
    pass

  if resolved_feature in DEFAULT_RUBRICS:
    return dict(DEFAULT_RUBRICS[resolved_feature])

  raise KeyError(f"Unknown rubric feature: {feature}")



def rubric_to_text(rubric: dict[str, Any]) -> str:

  criteria = rubric.get("criteria") or []

  return "\n".join(f"- {item}" for item in criteria)



async def get_template_history(template_type: str, feature: str, limit: int = 50) -> list[dict[str, Any]]:

  """Return chronological version audit history for a prompt or rubric."""
  from app.db.unit_of_work import AsyncUnitOfWork
  async with AsyncUnitOfWork() as uow:
    return await uow.ai_templates.get_version_history(template_type, feature, limit=limit)



async def save_prompt(
  feature: str,
  payload: dict[str, Any],
  updated_by: str | None = None,
  change_summary: str | None = None,
) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  try:
    current = await get_prompt(feature)
    next_version = int(current.get("version") or 1) + 1
    merged = {**current, **payload, "feature": feature, "version": next_version}
  except KeyError:
    next_version = int(payload.get("version") or 1)
    merged = {
      "version": next_version,
      "feature": feature,
      "allowed_sources": payload.get("allowed_sources") or ["knowledge"],
      "system": payload.get("system", ""),
      "user_template": payload.get("user_template", "{query}\n\n{context}"),
      **payload,
    }

  try:
    from app.db.unit_of_work import AsyncUnitOfWork
    async with AsyncUnitOfWork() as uow:
      res = await uow.ai_templates.save_template_update(
        template_type="prompt",
        feature=feature,
        new_data=merged,
        updated_by=updated_by,
        change_summary=change_summary or f"Updated prompt for {feature}",
      )
      await uow.commit()
      return res
  except Exception:
    return merged



async def save_rubric(
  feature: str,
  payload: dict[str, Any],
  updated_by: str | None = None,
  change_summary: str | None = None,
) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  current = await get_rubric(feature)
  next_version = int(current.get("version") or 1) + 1
  merged = {**current, **payload, "feature": feature, "version": next_version}

  try:
    from app.db.unit_of_work import AsyncUnitOfWork
    async with AsyncUnitOfWork() as uow:
      res = await uow.ai_templates.save_template_update(
        template_type="rubric",
        feature=feature,
        new_data=merged,
        updated_by=updated_by,
        change_summary=change_summary or f"Updated rubric for {feature}",
      )
      await uow.commit()
      return res
  except Exception:
    return merged


async def reset_prompt(
  feature: str,
  updated_by: str | None = None,
) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  if feature not in DEFAULT_PROMPTS:
    raise KeyError(f"No default prompt found for feature: {feature}")

  current = await get_prompt(feature)
  next_version = int(current.get("version") or 1) + 1
  default_payload = dict(DEFAULT_PROMPTS[feature])
  default_payload["version"] = next_version

  try:
    from app.db.unit_of_work import AsyncUnitOfWork
    async with AsyncUnitOfWork() as uow:
      res = await uow.ai_templates.save_template_update(
        template_type="prompt",
        feature=feature,
        new_data=default_payload,
        updated_by=updated_by,
        change_summary="Reset prompt to factory default",
      )
      await uow.commit()
      return res
  except Exception:
    return default_payload


async def reset_rubric(
  feature: str,
  updated_by: str | None = None,
) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  if feature not in DEFAULT_RUBRICS:
    raise KeyError(f"No default rubric found for feature: {feature}")

  current = await get_rubric(feature)
  next_version = int(current.get("version") or 1) + 1
  default_payload = dict(DEFAULT_RUBRICS[feature])
  default_payload["version"] = next_version

  try:
    from app.db.unit_of_work import AsyncUnitOfWork
    async with AsyncUnitOfWork() as uow:
      res = await uow.ai_templates.save_template_update(
        template_type="rubric",
        feature=feature,
        new_data=default_payload,
        updated_by=updated_by,
        change_summary="Reset rubric to factory default",
      )
      await uow.commit()
      return res
  except Exception:
    return default_payload
