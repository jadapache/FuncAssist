"""Granular application settings, fallbacks, and serialization helpers (Entity: settings)."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy import select

from app.core.secrets import (
  API_KEY_FIELDS,
  decrypt_ai_settings,
  decrypt_secret,
  encrypt_ai_settings,
  encrypt_secret,
)
from app.core.storage_cache import _CACHE_APP_SETTINGS, DEFAULT_APP_SETTINGS
from app.core.storage_preferences import save_user_preferences
from app.db.models import SettingModel, UserPreferencesModel

logger = logging.getLogger(__name__)


def serialize_setting_val(key: str, value: Any) -> str:
  """Serialize a setting value, encrypting secret keys if appropriate."""
  val_to_store = value
  if key in API_KEY_FIELDS and isinstance(val_to_store, str):
    val_to_store = encrypt_secret(val_to_store)
  elif key == "ai" and isinstance(val_to_store, dict):
    val_to_store = encrypt_ai_settings(val_to_store)
  return json.dumps(val_to_store, ensure_ascii=False)


def deserialize_setting_val(key: str, value_json: str) -> Any:
  """Deserialize a setting value, decrypting secret keys if appropriate."""
  try:
    parsed = json.loads(value_json)
  except Exception:
    parsed = value_json

  if key in API_KEY_FIELDS and isinstance(parsed, str):
    return decrypt_secret(parsed)
  if key == "ai" and isinstance(parsed, dict):
    return decrypt_ai_settings(parsed)
  return parsed


def get_setting(
  key: str,
  default: Any = None,
  user_id: Optional[str] = None,
  db: Optional[Any] = None,
) -> Any:
  """Retrieve a specific setting entry for a user, falling back to global scope."""
  target_user = user_id or ""

  def _read(session: Any) -> Any:
    item = session.scalar(
      select(SettingModel).where(SettingModel.key == key)
    )
    if item is not None and item.value_json is not None:
      return deserialize_setting_val(key, item.value_json)
    return None

  if db is not None:
    val = _read(db)
    if val is not None:
      return val

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      val = _read(session)
      if val is not None:
        return val
  except Exception as exc:
    logger.debug("Failed reading setting %s from DB: %s", key, exc)

  if _CACHE_APP_SETTINGS and key in _CACHE_APP_SETTINGS:
    return deserialize_setting_val(key, json.dumps(_CACHE_APP_SETTINGS[key]))
  return default


def set_setting(
  key: str,
  value: Any,
  user_id: Optional[str] = None,
  db: Optional[Any] = None,
) -> None:
  """Save a single setting record per key in settings entity."""
  target_user = user_id or ""
  serialized = serialize_setting_val(key, value)

  def _persist(session: Any) -> None:
    item = session.scalar(
      select(SettingModel).where(SettingModel.key == key)
    )
    if item:
      item.value_json = serialized
    else:
      item = SettingModel(key=key, value_json=serialized)
      session.add(item)

  if db is not None:
    _persist(db)
    return

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      _persist(session)
      session.commit()
  except Exception as exc:
    logger.error("Failed writing setting %s to DB: %s", key, exc)
    raise


def load_app_settings(user_id: Optional[str] = None) -> dict[str, Any]:
  """Load application settings from user preferences and global settings."""
  res = dict(DEFAULT_APP_SETTINGS)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as db:
      global_rows = db.scalars(
        select(SettingModel)
      ).all()

      for row in global_rows:
        if row.key.startswith("conn:") or row.key.startswith("user_ai:"):
          continue
        res[row.key] = deserialize_setting_val(row.key, row.value_json)

        prefs = db.scalar(
          select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        if prefs:
          pdict = prefs.to_dict()
          extra = pdict.pop("settings_json", {}) or {}
          res.update(extra)
          res.update({k: v for k, v in pdict.items() if v is not None})
  except Exception as exc:
    logger.debug("Could not load app settings from DB: %s", exc)

  if _CACHE_APP_SETTINGS:
    for ck, cv in _CACHE_APP_SETTINGS.items():
      if ck not in res or res[ck] is None:
        res[ck] = cv

  if "user_role" not in res or not res["user_role"]:
    res["user_role"] = "admin"
  if "display_name" not in res or not res["display_name"]:
    res["display_name"] = "Usuario"
  if "ai" in res and isinstance(res["ai"], dict):
    res["ai"] = decrypt_ai_settings(res["ai"])

  return res


def save_app_settings(payload: dict[str, Any], user_id: Optional[str] = None) -> dict[str, Any]:
  """Save application settings and update user preferences if user_id is provided."""
  target_user = user_id or ""
  for k, v in payload.items():
    set_setting(k, v, user_id=target_user)

  if target_user:
    save_user_preferences(target_user, payload)

  for k, v in payload.items():
    if k == "ai" and isinstance(v, dict):
      _CACHE_APP_SETTINGS[k] = encrypt_ai_settings(v)
    elif k in API_KEY_FIELDS and isinstance(v, str):
      _CACHE_APP_SETTINGS[k] = encrypt_secret(v)
    else:
      _CACHE_APP_SETTINGS[k] = v

  return load_app_settings(user_id=target_user if target_user else None)

