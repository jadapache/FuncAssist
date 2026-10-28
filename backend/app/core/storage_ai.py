"""Composition and persistence of AI settings across preferences and credentials."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.storage_credentials import (
  load_all_user_credentials,
  save_user_credential,
)
from app.core.storage_preferences import (
  get_user_preferences,
  save_user_preferences,
)
from app.core.storage_settings import load_app_settings

logger = logging.getLogger(__name__)

PROVIDER_KEY_MAP = {
  "openai": "openai_api_key",
  "claude": "claude_api_key",
  "groq": "groq_api_key",
  "gemini": "gemini_api_key",
  "transcription_groq": "transcription_groq_api_key",
  "transcription_openai": "transcription_openai_api_key",
}


def load_user_ai_settings(user_id: Optional[str] = None) -> dict[str, Any]:
  """Load user AI configuration from user_preferences and user_provider_credentials."""
  if not user_id:
    return load_app_settings().get("ai") or {}

  ai_config: dict[str, Any] = {}

  # 1. Non-secret preferences from user_preferences
  prefs = get_user_preferences(user_id)
  if prefs:
    if prefs.get("inference_provider"):
      ai_config["provider"] = prefs["inference_provider"]
    if prefs.get("inference_model"):
      ai_config["model"] = prefs["inference_model"]
    if prefs.get("transcription_provider"):
      ai_config["transcription_provider"] = prefs["transcription_provider"]
    if prefs.get("transcription_model"):
      ai_config["transcription_model"] = prefs["transcription_model"]
    for pk in ["voice_command_provider", "voice_command_model", "ollama_base_url"]:
      if prefs.get(pk):
        ai_config[pk] = prefs[pk]

  # 2. Encrypted credentials from user_provider_credentials (BYOK strictly per user)
  creds = load_all_user_credentials(user_id)
  ai_config.update(creds)

  global_ai = load_app_settings().get("ai") or {}
  # Only inherit non-secret settings (model defaults, ollama url), never private keys
  non_secret_global = {
    k: v for k, v in global_ai.items()
    if not k.endswith("_api_key") and k != "api_key"
  }
  merged = dict(non_secret_global)
  merged.update({k: v for k, v in ai_config.items() if v is not None})
  return merged


def _build_preference_payload(ai_data: dict[str, Any]) -> dict[str, Any]:
  """Extract non-secret preference fields from incoming AI configuration."""
  pref_payload: dict[str, Any] = {}
  provider = ai_data.get("provider") or ai_data.get("inference_provider")
  if provider:
    pref_payload["inference_provider"] = provider
  model = ai_data.get("model") or ai_data.get("inference_model")
  if model:
    pref_payload["inference_model"] = model
  if "transcription_provider" in ai_data:
    pref_payload["transcription_provider"] = ai_data["transcription_provider"]
  if "transcription_model" in ai_data:
    pref_payload["transcription_model"] = ai_data["transcription_model"]
  for k in ["voice_command_provider", "voice_command_model", "ollama_base_url", "language"]:
    if k in ai_data:
      pref_payload[k] = ai_data[k]
  return pref_payload


def _execute_save_ai_atomic(
  session: Any,
  user_id: str,
  ai_data: dict[str, Any],
) -> None:
  """Persist preferences and credentials in a single transactional session without committing."""
  # 1. Non-secret preferences
  pref_payload = _build_preference_payload(ai_data)
  if pref_payload:
    save_user_preferences(user_id, pref_payload, db=session)

  # 2. Encrypted provider credentials
  for prov, field in PROVIDER_KEY_MAP.items():
    if field in ai_data and ai_data[field]:
      save_user_credential(user_id, prov, ai_data[field], db=session)


def save_user_ai_settings(
  user_id: str,
  ai_data: dict[str, Any],
  db: Optional[Any] = None,
) -> None:
  """Save user-scoped AI preferences and encrypted provider credentials atomically."""
  if not user_id:
    raise ValueError("user_id is required to save user AI settings.")

  if db is not None:
    _execute_save_ai_atomic(db, user_id, ai_data)
    return

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      _execute_save_ai_atomic(session, user_id, ai_data)
      session.commit()
  except Exception as exc:
    logger.error("Failed saving user AI settings for %s: %s", user_id, exc)
    raise
