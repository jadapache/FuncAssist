from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.interfaces.settings_repository import ISettingsRepository
from app.db.models import SettingModel, UserPreferencesModel

logger = logging.getLogger(__name__)

CORE_PREFERENCE_FIELDS = {
  "inference_provider",
  "inference_model",
  "transcription_provider",
  "transcription_model",
  "language",
}


class SettingsRepository(ISettingsRepository):
  """Implementación PostgreSQL SQLAlchemy para ISettingsRepository."""

  def __init__(self, session: Session) -> None:
    self.session = session

  def get_setting(self, key: str) -> Optional[str]:
    stmt = select(SettingModel).where(SettingModel.key == key)
    item = self.session.scalar(stmt)
    return item.value_json if item else None

  def set_setting(self, key: str, value_json: str) -> None:
    stmt = select(SettingModel).where(SettingModel.key == key)
    item = self.session.scalar(stmt)
    if item:
      item.value_json = value_json
    else:
      item = SettingModel(key=key, value_json=value_json)
      self.session.add(item)
    self.session.flush()

  def get_all_settings(self) -> Dict[str, str]:
    stmt = select(SettingModel)
    rows = self.session.scalars(stmt).all()
    return {r.key: r.value_json for r in rows if r.key and r.value_json is not None}

  def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
    if not user_id:
      return None
    stmt = select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
    prefs = self.session.scalar(stmt)
    if prefs:
      res = prefs.to_dict()
      extra = res.pop("settings_json", {}) or {}
      return {**extra, **res}
    return None

  def save_user_preferences(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    if not user_id:
      return updates
    stmt = select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
    item = self.session.scalar(stmt)
    if not item:
      item = UserPreferencesModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        settings_json={},
      )
      self.session.add(item)

    extra = dict(item.settings_json or {})
    for k, v in updates.items():
      if k in ("inference_provider", "provider"):
        item.inference_provider = v
      elif k in ("inference_model", "model"):
        item.inference_model = v
      elif k in ("language", "lang"):
        item.language = v
      elif k in CORE_PREFERENCE_FIELDS:
        setattr(item, k, v)
      elif k not in ("user_id", "id"):
        extra[k] = v
    item.settings_json = extra
    self.session.flush()
    res = item.to_dict()
    extra = res.pop("settings_json", {}) or {}
    return {**extra, **res}
