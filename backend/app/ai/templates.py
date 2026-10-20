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

  if _DB_SEEDED:
    return


  try:
    import uuid

    from sqlalchemy import select

    from app.db.models import AITemplateModel, AITemplateVersionModel


    with get_sync_db() as db:

      stmt = select(AITemplateModel)

      result = db.execute(stmt)

      items = result.scalars().all()

      existing_ids = {item.id for item in items}


      has_new = False

      for feature, payload in DEFAULT_PROMPTS.items():

        template_id = f"prompt:{feature}"

        if template_id not in existing_ids:

          cleaned_payload = {

            k: v for k, v in payload.items()

            if k not in ("id", "template_type", "feature", "version", "updated_by", "created_at", "updated_at")

          }

          payload_json = json.dumps(cleaned_payload, ensure_ascii=False)

          version = int(payload.get("version") or 1)

          tmpl = AITemplateModel(
            id=template_id,
            template_type="prompt",
            feature=feature,

            version=version,

            payload_json=payload_json,

            updated_by="system",
          )

          version_entry = AITemplateVersionModel(

            id=str(uuid.uuid4()),
            template_id=template_id,
            template_type="prompt",
            feature=feature,

            version=version,

            payload_json=payload_json,

            change_summary="Initial system seed",

            created_by="system",
          )

          db.add(tmpl)

          db.add(version_entry)

          has_new = True


      for feature, payload in DEFAULT_RUBRICS.items():

        template_id = f"rubric:{feature}"

        if template_id not in existing_ids:

          cleaned_payload = {

            k: v for k, v in payload.items()

            if k not in ("id", "template_type", "feature", "version", "updated_by", "created_at", "updated_at")

          }

          payload_json = json.dumps(cleaned_payload, ensure_ascii=False)

          version = int(payload.get("version") or 1)

          tmpl = AITemplateModel(
            id=template_id,

            template_type="rubric",
            feature=feature,

            version=version,

            payload_json=payload_json,

            updated_by="system",
          )

          version_entry = AITemplateVersionModel(

            id=str(uuid.uuid4()),
            template_id=template_id,

            template_type="rubric",
            feature=feature,

            version=version,

            payload_json=payload_json,

            change_summary="Initial system seed",

            created_by="system",
          )

          db.add(tmpl)

          db.add(version_entry)

          has_new = True


      if has_new:

        db.commit()


    _DB_SEEDED = True

  except Exception:

    # If DB is temporarily unavailable or during offline setup, allow caller to fallback
    pass



def ensure_ai_files() -> None:

  """Ensure prompts and rubrics are seeded in PostgreSQL."""
  ensure_ai_templates_seeded()


async def list_prompts() -> list[dict[str, Any]]:
  ensure_ai_templates_seeded()

  try:

    items = await _repo.list_templates("prompt")

    if items:
      return items

  except Exception:
    pass

  return [dict(DEFAULT_PROMPTS[f]) for f in sorted(DEFAULT_PROMPTS.keys())]



async def list_rubrics() -> list[dict[str, Any]]:
  ensure_ai_templates_seeded()

  try:

    items = await _repo.list_templates("rubric")

    if items:
      return items

  except Exception:
    pass

  return [dict(DEFAULT_RUBRICS[f]) for f in sorted(DEFAULT_RUBRICS.keys())]



async def get_prompt(feature: str) -> dict[str, Any]:
  ensure_ai_templates_seeded()

  try:

    item = await _repo.get_template("prompt", feature)

    if item:
      return item

  except Exception:
    pass


  if feature in DEFAULT_PROMPTS:

    return dict(DEFAULT_PROMPTS[feature])

  raise KeyError(f"Unknown prompt feature: {feature}")



async def get_rubric(feature: str) -> dict[str, Any]:
  ensure_ai_templates_seeded()

  try:

    item = await _repo.get_template("rubric", feature)

    if item:
      return item

  except Exception:
    pass


  if feature in DEFAULT_RUBRICS:

    return dict(DEFAULT_RUBRICS[feature])

  raise KeyError(f"Unknown rubric feature: {feature}")



def rubric_to_text(rubric: dict[str, Any]) -> str:

  criteria = rubric.get("criteria") or []

  return "\n".join(f"- {item}" for item in criteria)



async def get_template_history(template_type: str, feature: str, limit: int = 50) -> list[dict[str, Any]]:

  """Return chronological version audit history for a prompt or rubric."""

  return await _repo.get_version_history(template_type, feature, limit=limit)



async def save_prompt(

  feature: str,

  payload: dict[str, Any],

  updated_by: str | None = None,

  change_summary: str | None = None,

) -> dict[str, Any]:
  ensure_ai_templates_seeded()

  current = await get_prompt(feature)

  next_version = int(current.get("version") or 1) + 1

  merged = {**current, **payload, "feature": feature, "version": next_version}


  try:

    return await _repo.save_template_update(
      template_type="prompt",
      feature=feature,

      new_data=merged,

      updated_by=updated_by,

      change_summary=change_summary or f"Updated prompt for {feature}",
    )

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

    return await _repo.save_template_update(

      template_type="rubric",
      feature=feature,

      new_data=merged,

      updated_by=updated_by,

      change_summary=change_summary or f"Updated rubric for {feature}",
    )

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

    return await _repo.save_template_update(
      template_type="prompt",
      feature=feature,

      new_data=default_payload,

      updated_by=updated_by,

      change_summary="Reset prompt to factory default",
    )

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

    return await _repo.save_template_update(

      template_type="rubric",
      feature=feature,

      new_data=default_payload,

      updated_by=updated_by,

      change_summary="Reset rubric to factory default",
    )

  except Exception:
    return default_payload
