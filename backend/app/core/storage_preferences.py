"""User preferences persistence (Entity: user_preferences).

Handles non-secret user settings (inference model, transcription model, UI settings).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.db.models import UserPreferencesModel

logger = logging.getLogger(__name__)

CORE_PREFERENCE_FIELDS = {
  "inference_provider",
  "inference_model",
  "transcription_provider",
  "transcription_model",
}


def get_user_preferences(user_id: str, db: Optional[Any] = None) -> dict[str, Any]:
  """Retrieve non-secret preferences for a user from user_preferences table."""
  if not user_id:
    return {}

  def _read(session: Any) -> dict[str, Any]:
    prefs = session.scalar(
      select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
    )
    if prefs:
      res = prefs.to_dict()
      extra = res.pop("settings_json", {}) or {}
      return {**extra, **res}
    return {}

  if db is not None:
    return _read(db)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      return _read(session)
  except Exception as exc:
    logger.debug("Failed reading user_preferences for %s: %s", user_id, exc)
  return {}


def save_user_preferences(
  user_id: str,
  payload: dict[str, Any],
  db: Optional[Any] = None,
) -> dict[str, Any]:
  """Save non-secret preferences for a user to user_preferences table."""
  if not user_id:
    return payload

  def _persist(session: Any) -> dict[str, Any]:
    item = session.scalar(
      select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
    )
    if not item:
      item = UserPreferencesModel(user_id=user_id, settings_json={})
      session.add(item)

    extra = dict(item.settings_json or {})
    for k, v in payload.items():
      if k in ("inference_provider", "provider"):
        item.inference_provider = v
      elif k in ("inference_model", "model"):
        item.inference_model = v
      elif k in CORE_PREFERENCE_FIELDS:
        setattr(item, k, v)
      elif k != "user_id":
        extra[k] = v
    item.settings_json = extra
    res = item.to_dict()
    extra = res.pop("settings_json", {}) or {}
    return {**extra, **res}

  if db is not None:
    return _persist(db)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      result = _persist(session)
      session.commit()
      return result
  except Exception as exc:
    logger.error("Failed saving user_preferences for %s: %s", user_id, exc)
    raise

