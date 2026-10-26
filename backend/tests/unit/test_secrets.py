import json
import pytest
from unittest.mock import MagicMock, patch
from app.core.secrets import (
    encrypt_secret,
    decrypt_secret,
    is_encrypted,
    encrypt_ai_settings,
    decrypt_ai_settings,
    _get_master_secret,
    _derive_fernet_key,
)
from cryptography.fernet import Fernet
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


def test_master_secret_from_env():
    with patch.dict("os.environ", {"PMQA_SECRET_KEY": "env-custom-master-secret"}):
        assert _get_master_secret() == "env-custom-master-secret"


def test_master_secret_from_legacy_file(tmp_path):
    legacy_file = tmp_path / "secret.key"
    legacy_file.write_text("legacy-file-secret", encoding="utf-8")

    with patch.dict("os.environ", {}, clear=True), \
         patch("app.core.secrets.SETTINGS_DIR", tmp_path):
        assert _get_master_secret() == "legacy-file-secret"


def test_master_secret_from_keyring(tmp_path):
    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = "keyring-stored-secret"

    with patch.dict("os.environ", {}, clear=True), \
         patch("app.core.secrets.SETTINGS_DIR", tmp_path), \
         patch("app.core.secrets.keyring", mock_keyring):
        assert _get_master_secret() == "keyring-stored-secret"
        assert not (tmp_path / "secret.key").exists()


def test_master_secret_fallback_to_fingerprint(tmp_path):
    with patch.dict("os.environ", {}, clear=True), \
         patch("app.core.secrets.SETTINGS_DIR", tmp_path), \
         patch("app.core.secrets.keyring", None), \
         patch("app.core.secrets._machine_fingerprint", return_value="test-fingerprint"):
        secret = _get_master_secret()
        assert secret == "qa-mgmt-local-secret::test-fingerprint"
        assert not (tmp_path / "secret.key").exists()


def test_derive_fernet_key_pbkdf2():
    key1 = _derive_fernet_key("test-master-secret-123")
    key2 = _derive_fernet_key("test-master-secret-123")
    assert key1 == key2
    assert len(key1) == 44
    fernet = Fernet(key1)
    token = fernet.encrypt(b"secure_data")
    assert fernet.decrypt(token) == b"secure_data"

