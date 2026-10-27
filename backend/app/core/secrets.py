"""
Módulo de gestión de secretos y cifrado para llaves de API (API Keys) de modelos de IA.
Basado en cifrado simétrico Fernet (cryptography.fernet) para proteger credenciales en archivos JSON.
"""

from __future__ import annotations

import base64
from functools import lru_cache
import hashlib
import os
import secrets
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

SECRET_PREFIX = "enc::"

_MASTER_SECRET_CACHE: str | None = None


def _get_master_secret() -> str:
    """Obtiene la clave maestra estrictamente desde variables de entorno."""
    global _MASTER_SECRET_CACHE
    if _MASTER_SECRET_CACHE:
        return _MASTER_SECRET_CACHE

    secret = os.getenv("SECRET_KEY")
    if not secret:
        try:
            from app.core.settings import get_settings
            settings = get_settings()
            secret = settings.secret_key
        except Exception:
            pass

    if secret and secret.strip():
        _MASTER_SECRET_CACHE = secret.strip()
        return _MASTER_SECRET_CACHE

    raise RuntimeError(
        "SECRET_KEY environment variable is required for encryption and security. "
        "Please define SECRET_KEY in your .env file or container environment."
    )


@lru_cache(maxsize=8)
def _get_pbkdf2_salt() -> bytes:
    salt = os.getenv("PBKDF2_SALT")
    if not salt:
        try:
            from app.core.settings import get_settings
            salt = get_settings().pbkdf2_salt
        except Exception:
            pass
    resolved = (salt).strip()
    return resolved.encode("utf-8")


@lru_cache(maxsize=8)
def _derive_fernet_key(secret: str) -> bytes:
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        _get_pbkdf2_salt(),
        iterations=100_000,
        dklen=32,
    )
    return base64.urlsafe_b64encode(derived)


def _get_fernet() -> Fernet:
    """Deriva una clave Fernet válida a partir del secreto maestro."""
    key = _derive_fernet_key(_get_master_secret())
    return Fernet(key)


def is_encrypted(text: str | None) -> bool:
    """Verifica si una cadena de texto está cifrada con el prefijo correspondiente."""
    if not text:
        return False
    return text.startswith(SECRET_PREFIX)


def encrypt_secret(plain_text: str | None) -> str:
    """
    Cifra una llave de API o secreto en texto plano.
    Retorna la cadena cifrada con el prefijo 'enc::'. Si el valor ya está cifrado o está vacío, lo retorna sin alterar.
    """
    if not plain_text or not plain_text.strip():
        return ""
    plain_text = plain_text.strip()
    if is_encrypted(plain_text):
        return plain_text

    fernet = _get_fernet()
    encrypted_bytes = fernet.encrypt(plain_text.encode("utf-8"))
    return f"{SECRET_PREFIX}{encrypted_bytes.decode('utf-8')}"


def decrypt_secret(cipher_text: str | None) -> str:
    """
    Descifra un secreto cifrado con el prefijo 'enc::'.
    Si la cadena no está cifrada o el descifrado falla, retorna el texto original de forma segura (fallback).
    """
    if not cipher_text or not cipher_text.strip():
        return ""
    cipher_text = cipher_text.strip()
    if not is_encrypted(cipher_text):
        return cipher_text

    raw_token = cipher_text[len(SECRET_PREFIX):]
    try:
        fernet = _get_fernet()
        decrypted_bytes = fernet.decrypt(raw_token.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except (InvalidToken, Exception):
        return cipher_text


API_KEY_FIELDS = {
    "openai_api_key",
    "claude_api_key",
    "groq_api_key",
    "gemini_api_key",
    "api_key",
    "transcription_groq_api_key",
    "transcription_openai_api_key",
}


def encrypt_ai_settings(ai_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Cifra todos los campos de llaves de API presentes en el diccionario de configuración de IA."""
    result = dict(ai_dict)
    for field in API_KEY_FIELDS:
        val = result.get(field)
        if val and isinstance(val, str):
            result[field] = encrypt_secret(val)
    return result


def decrypt_ai_settings(ai_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Descifra todos los campos de llaves de API presentes en el diccionario de configuración de IA."""
    result = dict(ai_dict)
    for field in API_KEY_FIELDS:
        val = result.get(field)
        if val and isinstance(val, str):
            result[field] = decrypt_secret(val)
    return result

