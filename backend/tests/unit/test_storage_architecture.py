"""Unit tests for modular storage sub-systems and public facade."""

import pytest
from app.core import (
  storage,
  storage_ai,
  storage_cache,
  storage_credentials,
  storage_integrations,
  storage_preferences,
  storage_settings,
)
from app.core.storage_cache import _CACHE_CONNECTIONS, make_conn_cache_key


def test_public_facade_exports():
  """Assert that storage.py exports all required legacy functions and symbols."""
  expected_symbols = [
    "save_connection",
    "load_connection",
    "delete_connection",
    "connection_exists",
    "get_user_preferences",
    "save_user_preferences",
    "save_user_credential",
    "load_user_credential",
    "load_all_user_credentials",
    "get_setting",
    "set_setting",
    "load_app_settings",
    "save_app_settings",
    "load_user_ai_settings",
    "save_user_ai_settings",
    "_CACHE_APP_SETTINGS",
    "_CACHE_CONNECTIONS",
    "DEFAULT_APP_SETTINGS",
    "_resolve_secret",
  ]
  for sym in expected_symbols:
    assert hasattr(storage, sym), f"Symbol {sym} missing from storage facade"


def test_user_preferences_isolation():
  """Test saving and getting preferences isolated per user."""
  storage_cache.clear_storage_caches()
  user_a = "user-alpha"
  user_b = "user-beta"

  storage.save_user_preferences(user_a, {
    "inference_provider": "groq",
    "inference_model": "llama-3.3-70b",
    "theme_color": "emerald",
  })
  storage.save_user_preferences(user_b, {
    "inference_provider": "openai",
    "inference_model": "gpt-4o",
    "theme_color": "sapphire",
  })

  prefs_a = storage.get_user_preferences(user_a)
  prefs_b = storage.get_user_preferences(user_b)

  assert prefs_a["inference_provider"] == "groq"
  assert prefs_a["theme_color"] == "emerald"

  assert prefs_b["inference_provider"] == "openai"
  assert prefs_b["theme_color"] == "sapphire"


def test_user_credentials_encryption_and_isolation():
  """Test storing and decrypting external provider credentials per user."""
  user_1 = "usr-creds-1"
  user_2 = "usr-creds-2"

  storage.save_user_credential(user_1, "groq", "gsk_user1_secret_999")
  storage.save_user_credential(user_2, "groq", "gsk_user2_secret_888")

  assert storage.load_user_credential(user_1, "groq") == "gsk_user1_secret_999"
  assert storage.load_user_credential(user_2, "groq") == "gsk_user2_secret_888"

  all_1 = storage.load_all_user_credentials(user_1)
  assert all_1.get("groq_api_key") == "gsk_user1_secret_999"


def test_organization_integrations_isolation_and_cache():
  """Test that organization integrations are strictly isolated and not cross-accessible."""
  storage_cache.clear_storage_caches()
  org_a = "org-acme"
  org_b = "org-globex"

  storage.save_connection("jira", {"client_id": "acme_id", "client_secret": "acme_sec"}, org_id=org_a)
  storage.save_connection("jira", {"client_id": "globex_id", "client_secret": "globex_sec"}, org_id=org_b)

  # Check cache keys are composite
  key_a = make_conn_cache_key(org_a, "jira")
  key_b = make_conn_cache_key(org_b, "jira")
  assert key_a != key_b
  assert key_a in _CACHE_CONNECTIONS
  assert key_b in _CACHE_CONNECTIONS

  conn_a = storage.load_connection("jira", org_id=org_a)
  conn_b = storage.load_connection("jira", org_id=org_b)

  assert conn_a["client_id"] == "acme_id"
  assert conn_b["client_id"] == "globex_id"

  # Delete from org_a only
  assert storage.delete_connection("jira", org_id=org_a) is True
  assert storage.load_connection("jira", org_id=org_a) is None
  assert storage.connection_exists("jira", org_id=org_a) is False

  # org_b should remain unaffected
  assert storage.connection_exists("jira", org_id=org_b) is True
  assert storage.load_connection("jira", org_id=org_b)["client_id"] == "globex_id"


def test_multi_tenant_same_provider_full_lifecycle():
  """Verify two organizations with same provider for read, update, delete, and isolation."""
  storage_cache.clear_storage_caches()
  org_1 = "tenant-1"
  org_2 = "tenant-2"

  # Initial save
  storage.save_connection("github", {"token": "ghp_org1", "owner": "corp-1"}, org_id=org_1)
  storage.save_connection("github", {"token": "ghp_org2", "owner": "corp-2"}, org_id=org_2)

  assert storage.load_connection("github", org_id=org_1)["token"] == "ghp_org1"
  assert storage.load_connection("github", org_id=org_2)["token"] == "ghp_org2"

  # Update org_1 only
  storage.save_connection("github", {"token": "ghp_org1_updated", "owner": "corp-1"}, org_id=org_1)
  assert storage.load_connection("github", org_id=org_1)["token"] == "ghp_org1_updated"
  assert storage.load_connection("github", org_id=org_2)["token"] == "ghp_org2"

  # Delete org_1
  storage.delete_connection("github", org_id=org_1)
  assert storage.load_connection("github", org_id=org_1) is None
  assert storage.load_connection("github", org_id=org_2)["token"] == "ghp_org2"

  # Cache key check
  assert make_conn_cache_key(org_1, "github") not in _CACHE_CONNECTIONS
  assert make_conn_cache_key(org_2, "github") in _CACHE_CONNECTIONS


def test_pbkdf2_salt_required_without_fallback(monkeypatch):
  """Verify that PBKDF2_SALT is mandatory and raises RuntimeError when missing."""
  from app.core import secrets as secrets_mod
  from types import SimpleNamespace

  monkeypatch.delenv("PBKDF2_SALT", raising=False)
  secrets_mod._get_pbkdf2_salt.cache_clear()
  monkeypatch.setattr("app.core.settings.get_settings", lambda: SimpleNamespace(pbkdf2_salt=None))

  with pytest.raises(RuntimeError, match="PBKDF2_SALT environment variable is required"):
    secrets_mod._get_pbkdf2_salt()


def test_atomic_transaction_rollback_on_partial_failure(monkeypatch):
  """Test that save_user_ai_settings performs atomic rollback on failure without partial data."""
  from tests.fake_session import GLOBAL_FAKE_STORAGE, FakeSyncSession
  from app.db import database as db_module

  GLOBAL_FAKE_STORAGE.clear()
  db_module.set_sync_session_override(lambda: FakeSyncSession(GLOBAL_FAKE_STORAGE))

  target_user = "user-atomic-test"

  # Monkeypatch save_user_credential to raise an error during write
  def fail_credential(*args, **kwargs):
    raise RuntimeError("Simulated credential storage write failure")

  monkeypatch.setattr("app.core.storage_ai.save_user_credential", fail_credential)

  with pytest.raises(RuntimeError, match="Simulated credential storage write failure"):
    storage.save_user_ai_settings(target_user, {
      "provider": "openai",
      "model": "gpt-4o",
      "openai_api_key": "sk-test-fail-key",
    })

  # Verify preferences were rolled back and NOT persisted in fake storage
  prefs = storage.get_user_preferences(target_user)
  assert prefs == {} or prefs.get("inference_provider") is None

  # Clean up override
  db_module.set_sync_session_override(None)


def test_ai_settings_composition():
  """Test that load_user_ai_settings merges preferences and credentials."""
  user_test = "user-ai-composite"

  storage.save_user_preferences(user_test, {
    "inference_provider": "gemini",
    "inference_model": "gemini-1.5-pro",
  })
  storage.save_user_credential(user_test, "gemini", "gemini-secret-test-key")

  ai_cfg = storage.load_user_ai_settings(user_test)
  assert ai_cfg["provider"] == "gemini"
  assert ai_cfg["model"] == "gemini-1.5-pro"
  assert ai_cfg["gemini_api_key"] == "gemini-secret-test-key"
  storage.save_user_credential(user_test, "gemini", "gemini-secret-test-key")

  ai_cfg = storage.load_user_ai_settings(user_test)
  assert ai_cfg["provider"] == "gemini"
  assert ai_cfg["model"] == "gemini-1.5-pro"
  assert ai_cfg["gemini_api_key"] == "gemini-secret-test-key"

