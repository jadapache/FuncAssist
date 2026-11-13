"""User preferences persistence (Entity: user_preferences).

Handles non-secret user settings (inference model, transcription model, UI settings).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select

from app.db.repositories.settings_repository import SettingsRepository

logger = logging.getLogger(__name__)

CORE_PREFERENCE_FIELDS = {
  "inference_provider",
  "inference_model",
  "transcription_provider",
  "transcription_model",
  "language",
}


def get_user_preferences(user_id: str, db: Optional[Any] = None) -> dict[str, Any]:
  """Retrieve non-secret preferences for a user from user_preferences table."""
  if not user_id:
    return {}

  if db is not None:
    repo = SettingsRepository(session=db)
    return repo.get_user_preferences(user_id) or {}

  try:
    from app.db.unit_of_work import SyncUnitOfWork
    with SyncUnitOfWork() as uow:
      return uow.settings.get_user_preferences(user_id) or {}
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

  if db is not None:
    repo = SettingsRepository(session=db)
    return repo.save_user_preferences(user_id, payload)

  try:
    from app.db.unit_of_work import SyncUnitOfWork
    with SyncUnitOfWork() as uow:
      res = uow.settings.save_user_preferences(user_id, payload)
      uow.commit()
      return res
  except Exception as exc:
    logger.error("Failed saving user_preferences for %s: %s", user_id, exc)
    raise
