"""PostgreSQL-backed settings and credential storage via SQLAlchemy ORM.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.core.secrets import decrypt_ai_settings, encrypt_ai_settings
from app.core.settings import get_settings
from app.db.models import SettingModel

logger = logging.getLogger(__name__)

# In-memory fallbacks when database is initializing or during tests
_CACHE_APP_SETTINGS: dict[str, Any] = {}
_CACHE_CONNECTIONS: dict[str, bytes] = {}


def _derive_fernet_key(secret: str) -> bytes:
  digest = hashlib.sha256(secret.encode("utf-8")).digest()
  return base64.urlsafe_b64encode(digest)


def _resolve_secret() -> str:
  settings = get_settings()
  secret = settings.secret_key or os.getenv("SECRET_KEY")
  if secret and secret.strip():
    return secret.strip()

  raise RuntimeError(
    "SECRET_KEY environment variable is required for application storage and encryption. "
    "Please define SECRET_KEY in your .env or container environment."
  )


def _fernet() -> Fernet:
  return Fernet(_derive_fernet_key(_resolve_secret()))


def save_connection(integration_id: str, payload: dict[str, Any]) -> None:
  """Save encrypted connection payload to PostgreSQL settings table via SQLAlchemy ORM."""
  raw = json.dumps(payload, indent=2).encode("utf-8")
  encrypted = _fernet().encrypt(raw)
  key = f"conn:{integration_id}"
  _CACHE_CONNECTIONS[integration_id] = encrypted

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as db:
      setting = db.scalar(select(SettingModel).where(SettingModel.key == key))
      if setting:
        setting.value_json = encrypted.decode("ascii")
      else:
        setting = SettingModel(key=key, value_json=encrypted.decode("ascii"))
        db.add(setting)
      db.commit()
  except Exception as exc:
    logger.debug("Failed to persist connection to PostgreSQL, kept in memory: %s", exc)


def load_connection(integration_id: str) -> dict[str, Any] | None:
  """Load encrypted connection payload from PostgreSQL settings table via SQLAlchemy ORM."""
  key = f"conn:{integration_id}"
  encrypted: bytes | None = _CACHE_CONNECTIONS.get(integration_id)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as db:
      setting = db.scalar(select(SettingModel).where(SettingModel.key == key))
      if setting and setting.value_json:
        encrypted = setting.value_json.encode("ascii")
        _CACHE_CONNECTIONS[integration_id] = encrypted
  except Exception as exc:
    logger.debug("Could not read connection from PostgreSQL: %s", exc)

  if not encrypted:
    return None

  try:
    decrypted = _fernet().decrypt(encrypted)
    return json.loads(decrypted.decode("utf-8"))
  except (InvalidToken, json.JSONDecodeError, OSError):
    return None


def delete_connection(integration_id: str) -> bool:
  """Delete connection from PostgreSQL settings table and memory via SQLAlchemy ORM."""
  key = f"conn:{integration_id}"
  existed = integration_id in _CACHE_CONNECTIONS
  _CACHE_CONNECTIONS.pop(integration_id, None)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as db:
      setting = db.scalar(select(SettingModel).where(SettingModel.key == key))
      if setting:
        db.delete(setting)
        db.commit()
        return True
      return existed
  except Exception as exc:
    logger.debug("Could not delete connection from PostgreSQL: %s", exc)
    return existed


def connection_exists(integration_id: str) -> bool:
  """Check if connection exists in PostgreSQL or memory via SQLAlchemy ORM."""
  if integration_id in _CACHE_CONNECTIONS:
    return True

  key = f"conn:{integration_id}"
  try:
    from app.db.database import get_sync_db
    with get_sync_db() as db:
      setting = db.scalar(select(SettingModel.key).where(SettingModel.key == key))
      return setting is not None
  except Exception:
    return False


DEFAULT_APP_SETTINGS: dict[str, Any] = {
  "display_name": "Usuario",
  "user_role": "admin",
  "theme": "command-center",
  "selected_repos": [],
}


def load_app_settings() -> dict[str, Any]:
  """Load application settings from PostgreSQL settings table via SQLAlchemy ORM (with memory fallback)."""
  res = dict(DEFAULT_APP_SETTINGS)

  # Check in-memory cache first as baseline
  if _CACHE_APP_SETTINGS:
    res.update(_CACHE_APP_SETTINGS)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as db:
      setting = db.scalar(select(SettingModel).where(SettingModel.key == "app"))
      if setting and setting.value_json:
        stored = json.loads(setting.value_json)
        if isinstance(stored, dict):
          res.update(stored)
          _CACHE_APP_SETTINGS.clear()
          _CACHE_APP_SETTINGS.update(stored)
  except Exception as exc:
    logger.debug("Could not load app settings from PostgreSQL: %s", exc)

  if "user_role" not in res or not res["user_role"]:
    res["user_role"] = "admin"
  if "display_name" not in res or not res["display_name"]:
    res["display_name"] = "Usuario"
  if "ai" in res and isinstance(res["ai"], dict):
    res["ai"] = decrypt_ai_settings(res["ai"])

  return res


def save_app_settings(payload: dict[str, Any]) -> dict[str, Any]:
  """Save application settings to PostgreSQL settings table via SQLAlchemy ORM (no JSON file writes)."""
  current = load_app_settings()
  current.update(payload)

  to_store = dict(current)
  if "ai" in to_store and isinstance(to_store["ai"], dict):
    to_store["ai"] = encrypt_ai_settings(to_store["ai"])

  _CACHE_APP_SETTINGS.clear()
  _CACHE_APP_SETTINGS.update(to_store)

  try:
    from app.db.database import get_sync_db
    value_json = json.dumps(to_store, ensure_ascii=False)
    with get_sync_db() as db:
      setting = db.scalar(select(SettingModel).where(SettingModel.key == "app"))
      if setting:
        setting.value_json = value_json
      else:
        setting = SettingModel(key="app", value_json=value_json)
        db.add(setting)
      db.commit()
  except Exception as exc:
    logger.debug("Failed to persist app settings to PostgreSQL, kept in memory: %s", exc)

  return current


def load_user_ai_settings(user_id: Optional[str] = None) -> dict[str, Any]:
  """Load AI settings for a specific user ID, falling back to global settings."""
  if not user_id:
    return load_app_settings().get("ai") or {}

  key = f"user_ai:{user_id}"
  try:
    from app.db.database import get_sync_db
    with get_sync_db() as db:
      setting = db.scalar(select(SettingModel).where(SettingModel.key == key))
      if setting and setting.value_json:
        stored = json.loads(setting.value_json)
        if isinstance(stored, dict):
          return decrypt_ai_settings(stored)
  except Exception as exc:
    logger.debug("Could not read user AI settings from DB: %s", exc)

  # Fallback to global AI settings
  return load_app_settings().get("ai") or {}


def save_user_ai_settings(user_id: str, ai_data: dict[str, Any]) -> dict[str, Any]:
  """Save user-specific AI settings in PostgreSQL settings table with encryption."""
  current = load_user_ai_settings(user_id)
  current.update(ai_data)

  to_store = encrypt_ai_settings(dict(current))
  key = f"user_ai:{user_id}"

  try:
    from app.db.database import get_sync_db
    value_json = json.dumps(to_store, ensure_ascii=False)
    with get_sync_db() as db:
      setting = db.scalar(select(SettingModel).where(SettingModel.key == key))
      if setting:
        setting.value_json = value_json
      else:
        setting = SettingModel(key=key, value_json=value_json)
        db.add(setting)
      db.commit()
  except Exception as exc:
    logger.debug("Failed to persist user AI settings to DB: %s", exc)

  return current

