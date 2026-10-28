"""Storage public facade - maintains 100% backward compatibility for all consumers.

Re-exports public contracts, models, caches, and methods from specialized storage modules:
  - storage_cache: _CACHE_APP_SETTINGS, _CACHE_CONNECTIONS, DEFAULT_APP_SETTINGS
  - storage_integrations: save_connection, load_connection, delete_connection, connection_exists
  - storage_preferences: get_user_preferences, save_user_preferences
  - storage_credentials: save_user_credential, load_user_credential, load_all_user_credentials
  - storage_settings: get_setting, set_setting, load_app_settings, save_app_settings
  - storage_ai: load_user_ai_settings, save_user_ai_settings
"""

from __future__ import annotations

import os

from app.core.settings import get_settings

# Cache structures and constants
from app.core.storage_cache import (
  DEFAULT_APP_SETTINGS,
  _CACHE_APP_SETTINGS,
  _CACHE_CONNECTIONS,
  clear_storage_caches,
  make_conn_cache_key,
)

# Integrations
from app.core.storage_integrations import (
  _derive_fernet_key,
  _fernet,
  connection_exists,
  delete_connection,
  load_connection,
  save_connection,
)

# User Personal Integrations
from app.core.storage_user_integrations import (
  delete_user_integration,
  load_user_integration,
  save_user_integration,
  user_integration_exists,
)

# Preferences
from app.core.storage_preferences import (
  get_user_preferences,
  save_user_preferences,
)

# Credentials
from app.core.storage_credentials import (
  load_all_user_credentials,
  load_user_credential,
  save_user_credential,
)

# Settings
from app.core.storage_settings import (
  deserialize_setting_val as _deserialize_setting_val,
  get_setting,
  load_app_settings,
  save_app_settings,
  serialize_setting_val as _serialize_setting_val,
  set_setting,
)
from app.db.models import (
  AuditEventModel,
  McpServerModel,
  OrganizationIntegrationModel,
  OrganizationMemberModel,
  OrganizationModel,
  SettingModel,
  UserIntegrationModel,
  UserJiraConnectionModel,
  UserPreferencesModel,
  UserProviderCredentialModel,
  UserSecretModel,
)

# AI Settings
from app.core.storage_ai import (
  load_user_ai_settings,
  save_user_ai_settings,
)


def _resolve_secret() -> str:
  settings = get_settings()
  secret = settings.secret_key or os.getenv("SECRET_KEY")
  if secret and secret.strip():
    return secret.strip()

  raise RuntimeError(
    "SECRET_KEY environment variable is required for application storage and encryption. "
    "Please define SECRET_KEY in your .env or container environment."
  )


__all__ = [
  "DEFAULT_APP_SETTINGS",
  "_CACHE_APP_SETTINGS",
  "_CACHE_CONNECTIONS",
  "clear_storage_caches",
  "make_conn_cache_key",
  "_derive_fernet_key",
  "_resolve_secret",
  "_fernet",
  "save_connection",
  "load_connection",
  "delete_connection",
  "connection_exists",
  "save_user_integration",
  "load_user_integration",
  "delete_user_integration",
  "user_integration_exists",
  "get_user_preferences",
  "save_user_preferences",
  "save_user_credential",
  "load_user_credential",
  "load_all_user_credentials",
  "_serialize_setting_val",
  "_deserialize_setting_val",
  "get_setting",
  "set_setting",
  "load_app_settings",
  "save_app_settings",
  "load_user_ai_settings",
  "save_user_ai_settings",
  "SettingModel",
  "UserPreferencesModel",
  "UserProviderCredentialModel",
  "UserIntegrationModel",
  "McpServerModel",
  "OrganizationIntegrationModel",
  "OrganizationModel",
  "OrganizationMemberModel",
  "UserSecretModel",
  "UserJiraConnectionModel",
  "AuditEventModel",
]
