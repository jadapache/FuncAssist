import json
import pytest
from app.core.secrets import (
    encrypt_secret,
    decrypt_secret,
    is_encrypted,
    encrypt_ai_settings,
    decrypt_ai_settings,
)
from app.core.storage import save_app_settings, load_app_settings, _CACHE_APP_SETTINGS


def test_secret_encrypt_and_decrypt():
    raw_key = "gsk_test1234567890abcdef"
    
    encrypted = encrypt_secret(raw_key)
    assert is_encrypted(encrypted)
    assert encrypted.startswith("enc::")
    assert encrypted != raw_key

    # Re-encrypting should return same encrypted string
    re_encrypted = encrypt_secret(encrypted)
    assert re_encrypted == encrypted

    decrypted = decrypt_secret(encrypted)
    assert decrypted == raw_key


def test_decrypt_unencrypted_fallback():
    raw_text = "plain_unencrypted_text"
    assert is_encrypted(raw_text) is False
    assert decrypt_secret(raw_text) == raw_text


def test_ai_settings_dict_encryption():
    ai_config = {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "groq_api_key": "gsk_sample123",
        "openai_api_key": "sk-proj-sample456",
    }

    encrypted_dict = encrypt_ai_settings(ai_config)
    assert encrypted_dict["provider"] == "groq"
    assert is_encrypted(encrypted_dict["groq_api_key"])
    assert is_encrypted(encrypted_dict["openai_api_key"])

    decrypted_dict = decrypt_ai_settings(encrypted_dict)
    assert decrypted_dict["groq_api_key"] == "gsk_sample123"
    assert decrypted_dict["openai_api_key"] == "sk-proj-sample456"


def test_storage_encryption_roundtrip():
    ai_payload = {
        "ai": {
            "provider": "groq",
            "groq_api_key": "gsk_real_secret_key_999",
        }
    }
    save_app_settings(ai_payload)

    # Inspect stored raw state in storage/cache (no JSON file on disk)
    stored_groq_key = _CACHE_APP_SETTINGS["ai"]["groq_api_key"]
    
    # Assert key is encrypted in stored state
    assert stored_groq_key.startswith("enc::")
    assert "gsk_real_secret_key_999" not in stored_groq_key

    # Assert load_app_settings decrypts key in memory
    loaded = load_app_settings()
    assert loaded["ai"]["groq_api_key"] == "gsk_real_secret_key_999"


def test_missing_secret_key_raises_error(monkeypatch):
    import app.core.secrets as secrets_mod
    monkeypatch.setattr(secrets_mod, "_MASTER_SECRET_CACHE", None)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    from types import SimpleNamespace
    fake_settings = SimpleNamespace(secret_key=None)
    monkeypatch.setattr("app.core.settings.get_settings", lambda: fake_settings)

    with pytest.raises(RuntimeError, match="SECRET_KEY environment variable is required"):
        secrets_mod._get_master_secret()


def test_storage_resolve_secret_missing_raises_error(monkeypatch):
    import app.core.storage as storage_mod
    monkeypatch.delenv("SECRET_KEY", raising=False)
    from types import SimpleNamespace
    fake_settings = SimpleNamespace(secret_key=None)
    monkeypatch.setattr(storage_mod, "get_settings", lambda: fake_settings)

    with pytest.raises(RuntimeError, match="SECRET_KEY environment variable is required"):
        storage_mod._resolve_secret()


def test_startup_missing_secret_key_fails(monkeypatch):
    import app.main as main_mod
    monkeypatch.delenv("SECRET_KEY", raising=False)
    from types import SimpleNamespace
    fake_settings = SimpleNamespace(secret_key=None, cors_origins=[])
    monkeypatch.setattr(main_mod, "get_settings", lambda: fake_settings)

    with pytest.raises(RuntimeError, match="SECRET_KEY environment variable is required to start the application"):
        main_mod.create_app()

