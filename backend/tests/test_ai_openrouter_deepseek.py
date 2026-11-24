"""OpenRouter and DeepSeek must be usable end to end: settings, key storage, encryption and resolution."""

from __future__ import annotations

import pytest

from app.ai.providers import factory
from app.ai.providers.registry import find_provider_spec
from app.core import secrets, storage_ai, storage_credentials

NEW_PROVIDERS = [
  ("openrouter", "openrouter_api_key", "OPENROUTER_API_KEY"),
  ("deepseek", "deepseek_api_key", "DEEPSEEK_API_KEY"),
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
  for _, _, env in NEW_PROVIDERS:
    monkeypatch.delenv(env, raising=False)
  factory.clear_provider_cache()
  yield
  factory.clear_provider_cache()


@pytest.mark.parametrize("provider,field,env", NEW_PROVIDERS)
def test_registry_config_key_matches_settings_field(provider, field, env):
  assert find_provider_spec(provider).config_key == field


@pytest.mark.parametrize("provider,field,env", NEW_PROVIDERS)
def test_get_ai_settings_reads_stored_key(monkeypatch, provider, field, env):
  monkeypatch.setattr(factory, "load_app_settings", lambda: {"ai": {field: "stored-key"}})
  assert factory.get_ai_settings()[field] == "stored-key"


@pytest.mark.parametrize("provider,field,env", NEW_PROVIDERS)
def test_get_ai_settings_falls_back_to_env(monkeypatch, provider, field, env):
  monkeypatch.setattr(factory, "load_app_settings", lambda: {"ai": {}})
  monkeypatch.setenv(env, "env-key")
  assert factory.get_ai_settings()[field] == "env-key"


@pytest.mark.parametrize("provider,field,env", NEW_PROVIDERS)
def test_resolve_provider_uses_stored_key(monkeypatch, provider, field, env):
  monkeypatch.setattr(factory, "load_app_settings", lambda: {"ai": {field: "stored-key"}})
  resolved = factory.resolve_provider(provider)
  assert resolved.id == provider
  assert resolved.api_key == "stored-key"


@pytest.mark.parametrize("provider,field,env", NEW_PROVIDERS)
def test_resolve_provider_without_key_fails(monkeypatch, provider, field, env):
  monkeypatch.setattr(factory, "load_app_settings", lambda: {"ai": {}})
  with pytest.raises(ValueError, match="API key"):
    factory.resolve_provider(provider)


@pytest.mark.parametrize("provider,field,env", NEW_PROVIDERS)
def test_key_field_is_encrypted_and_decrypted(provider, field, env):
  assert field in secrets.API_KEY_FIELDS
  encrypted = secrets.encrypt_ai_settings({field: "plain-secret"})
  assert encrypted[field] != "plain-secret"
  assert encrypted[field].startswith(secrets.SECRET_PREFIX)
  assert secrets.decrypt_ai_settings(encrypted)[field] == "plain-secret"


@pytest.mark.parametrize("provider,field,env", NEW_PROVIDERS)
def test_provider_key_map_covers_new_providers(provider, field, env):
  assert storage_ai.PROVIDER_KEY_MAP[provider] == field


def test_user_credentials_are_loaded_for_new_providers(monkeypatch):
  stored = {"openrouter": "or-key", "deepseek": "ds-key", "groq": ""}
  monkeypatch.setattr(storage_credentials, "load_user_credential", lambda uid, prov, db=None: stored.get(prov, ""))
  result = storage_credentials.load_all_user_credentials("u1")
  assert result == {"openrouter_api_key": "or-key", "deepseek_api_key": "ds-key"}


def test_saving_ai_settings_persists_new_provider_keys(monkeypatch):
  saved: list[tuple[str, str, str]] = []
  monkeypatch.setattr(storage_ai, "save_user_preferences", lambda *a, **k: None)
  monkeypatch.setattr(
    storage_ai, "save_user_credential", lambda uid, prov, key, db=None: saved.append((uid, prov, key))
  )
  storage_ai._execute_save_ai_atomic(object(), "u1", {"openrouter_api_key": "or-key", "deepseek_api_key": "ds-key"})
  assert ("u1", "openrouter", "or-key") in saved
  assert ("u1", "deepseek", "ds-key") in saved
