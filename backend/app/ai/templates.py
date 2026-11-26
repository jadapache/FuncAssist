"""AI prompt templates and rubrics persisted in PostgreSQL with audit history."""

from __future__ import annotations

from functools import partial
from typing import Any

from app.ai.seeds import DEFAULT_PROMPTS, DEFAULT_RUBRICS


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


def _defaults(kind: str) -> dict[str, dict[str, Any]]:
  return DEFAULT_PROMPTS if kind == "prompt" else DEFAULT_RUBRICS


async def _list_templates(kind: str, tag: str | None) -> list[dict[str, Any]]:
  """Stored templates of a kind, else the built-in defaults; both optionally filtered by tag."""
  ensure_ai_templates_seeded()
  try:
    from app.db.unit_of_work import AsyncUnitOfWork
    async with AsyncUnitOfWork() as uow:
      items = await uow.ai_templates.list_templates(kind, tag=tag)
      if items:
        return items
  except Exception:
    pass

  defaults = _defaults(kind)
  templates = [dict(defaults[f]) for f in sorted(defaults)]
  return [t for t in templates if t.get("tag") == tag] if tag else templates


async def list_prompts(tag: str | None = None) -> list[dict[str, Any]]:
  return await _list_templates("prompt", tag)


async def list_rubrics(tag: str | None = None) -> list[dict[str, Any]]:
  return await _list_templates("rubric", tag)


async def _get_template(kind: str, feature: str) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  resolved_feature = DEFAULT_TRANSCRIPT_SUMMARY_FEATURE if feature == "transcript_summary" else feature
  try:
    from app.db.unit_of_work import AsyncUnitOfWork
    async with AsyncUnitOfWork() as uow:
      item = await uow.ai_templates.get_template(kind, resolved_feature)
      if item:
        return item
  except Exception:
    pass

  defaults = _defaults(kind)
  if resolved_feature in defaults:
    return dict(defaults[resolved_feature])

  raise KeyError(f"Unknown {kind} feature: {feature}")


async def get_prompt(feature: str) -> dict[str, Any]:
  return await _get_template("prompt", feature)


async def get_rubric(feature: str) -> dict[str, Any]:
  return await _get_template("rubric", feature)


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

  return await _save_template("prompt", feature, merged, updated_by, change_summary or f"Updated prompt for {feature}")



async def _save_template(
  kind: str, feature: str, data: dict[str, Any], updated_by: str | None, change_summary: str
) -> dict[str, Any]:
  """Persist a new template version; when the database is unavailable the data is returned unsaved."""
  try:
    from app.db.unit_of_work import AsyncUnitOfWork
    async with AsyncUnitOfWork() as uow:
      res = await uow.ai_templates.save_template_update(
        template_type=kind,
        feature=feature,
        new_data=data,
        updated_by=updated_by,
        change_summary=change_summary,
      )
      await uow.commit()
      return res
  except Exception:
    return data


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
  return await _save_template("rubric", feature, merged, updated_by, change_summary or f"Updated rubric for {feature}")


async def _reset_template(kind: str, feature: str, updated_by: str | None = None) -> dict[str, Any]:
  ensure_ai_templates_seeded()
  defaults = _defaults(kind)
  if feature not in defaults:
    raise KeyError(f"No default {kind} found for feature: {feature}")

  current = await _get_template(kind, feature)
  default_payload = dict(defaults[feature])
  default_payload["version"] = int(current.get("version") or 1) + 1
  return await _save_template(kind, feature, default_payload, updated_by, f"Reset {kind} to factory default")


# reset_prompt(feature, updated_by=None) / reset_rubric(feature, updated_by=None)
reset_prompt = partial(_reset_template, "prompt")
reset_rubric = partial(_reset_template, "rubric")
