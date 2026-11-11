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


@pytest.mark.parametrize(
    "env_var,target_call",
    [
        ("SECRET_KEY", lambda: getattr(__import__("app.core.secrets", fromlist=["_get_master_secret"]), "_get_master_secret")()),
        ("SECRET_KEY", lambda: getattr(__import__("app.core.storage", fromlist=["_resolve_secret"]), "_resolve_secret")()),
        ("PBKDF2_SALT", lambda: getattr(__import__("app.core.secrets", fromlist=["_get_pbkdf2_salt"]), "_get_pbkdf2_salt")()),
    ],
)
def test_missing_security_credentials_raise_error(monkeypatch, env_var, target_call):
    import app.core.secrets as secrets_mod
    monkeypatch.setattr(secrets_mod, "_MASTER_SECRET_CACHE", None)
    secrets_mod._get_pbkdf2_salt.cache_clear()
    monkeypatch.delenv(env_var, raising=False)

    from types import SimpleNamespace
    fake_settings = SimpleNamespace(secret_key=None, pbkdf2_salt=None)
    monkeypatch.setattr("app.core.settings.get_settings", lambda: fake_settings)
    monkeypatch.setattr("app.core.storage.get_settings", lambda: fake_settings)

    with pytest.raises(RuntimeError, match=f"{env_var} environment variable is required"):
        target_call()


@pytest.mark.parametrize(
    "missing_var,expected_msg",
    [
        ("SECRET_KEY", "SECRET_KEY environment variable is required to start the application"),
        ("PBKDF2_SALT", "PBKDF2_SALT environment variable is required to start the application"),
    ],
)
def test_startup_missing_required_env_fails(monkeypatch, missing_var, expected_msg):
    import app.main as main_mod
    monkeypatch.setenv("SECRET_KEY", "valid-key" if missing_var != "SECRET_KEY" else "")
    monkeypatch.delenv(missing_var, raising=False)

    from types import SimpleNamespace
    fake_settings = SimpleNamespace(
        secret_key="valid-key" if missing_var != "SECRET_KEY" else None,
        pbkdf2_salt="valid-salt" if missing_var != "PBKDF2_SALT" else None,
        cors_origins=[],
    )
    monkeypatch.setattr(main_mod, "get_settings", lambda: fake_settings)

    with pytest.raises(RuntimeError, match=expected_msg):
        main_mod.create_app()

