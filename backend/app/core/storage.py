"""Local encrypted credential and settings storage (no database)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.secrets import decrypt_ai_settings, encrypt_ai_settings
from app.core.security import machine_fingerprint as _machine_fingerprint
from app.core.settings import CONNECTIONS_DIR, SETTINGS_DIR, ensure_local_dirs, get_settings

try:
  import keyring
except ImportError:  # pragma: no cover
  keyring = None

SERVICE_NAME = "qa-project-mgmt"
KEYRING_USERNAME = "encryption-key"


def _derive_fernet_key(secret: str) -> bytes:

  digest = hashlib.sha256(secret.encode("utf-8")).digest()
  return base64.urlsafe_b64encode(digest)


def _resolve_secret() -> str:
  settings = get_settings()
  if settings.pmqa_secret_key:
    return settings.pmqa_secret_key

  if keyring is not None:
    try:
      stored = keyring.get_password(SERVICE_NAME, KEYRING_USERNAME)
      if stored:
        return stored
      generated = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
      keyring.set_password(SERVICE_NAME, KEYRING_USERNAME, generated)
      return generated
    except Exception:
      pass

  return f"pmqa-local::{_machine_fingerprint()}"


def _fernet() -> Fernet:
  return Fernet(_derive_fernet_key(_resolve_secret()))


def _connection_path(integration_id: str) -> Path:
  ensure_local_dirs()
  return CONNECTIONS_DIR / f"{integration_id}.enc"


def _settings_path(name: str = "app") -> Path:
  ensure_local_dirs()
  return SETTINGS_DIR / f"{name}.json"


def save_connection(integration_id: str, payload: dict[str, Any]) -> None:
  raw = json.dumps(payload, indent=2).encode("utf-8")
  encrypted = _fernet().encrypt(raw)
  _connection_path(integration_id).write_bytes(encrypted)


def load_connection(integration_id: str) -> dict[str, Any] | None:
  path = _connection_path(integration_id)
  if not path.exists():
    return None
  try:
    decrypted = _fernet().decrypt(path.read_bytes())
    return json.loads(decrypted.decode("utf-8"))
  except (InvalidToken, json.JSONDecodeError, OSError):
    return None


def delete_connection(integration_id: str) -> bool:
  path = _connection_path(integration_id)
  if not path.exists():
    return False
  path.unlink()
  return True


def connection_exists(integration_id: str) -> bool:
  return _connection_path(integration_id).exists()


DEFAULT_APP_SETTINGS: dict[str, Any] = {
  "display_name": "Usuario",
  "user_role": "admin",
  "theme": "command-center",
  "selected_repos": [],
  "knowledge_base_path": "",
}


def load_app_settings() -> dict[str, Any]:
  """Load application settings from disk"""
  path = _settings_path()
  if not path.exists():
    return dict(DEFAULT_APP_SETTINGS)
  try:
    stored = json.loads(path.read_text(encoding="utf-8"))
    res = {**DEFAULT_APP_SETTINGS, **stored}
    if "user_role" not in res or not res["user_role"]:
      res["user_role"] = "admin"
    if "display_name" not in res or not res["display_name"]:
      res["display_name"] = "Usuario"
    if "ai" in res and isinstance(res["ai"], dict):
      res["ai"] = decrypt_ai_settings(res["ai"])
    return res
  except (json.JSONDecodeError, OSError):
    return dict(DEFAULT_APP_SETTINGS)


def save_app_settings(payload: dict[str, Any]) -> dict[str, Any]:
  """Save application settings to disk - merges with existing settings"""
  current = load_app_settings()
  current.update(payload)

  to_store = dict(current)
  if "ai" in to_store and isinstance(to_store["ai"], dict):
    to_store["ai"] = encrypt_ai_settings(to_store["ai"])

  path = _settings_path()
  path.write_text(json.dumps(to_store, indent=2), encoding="utf-8")
  return current
