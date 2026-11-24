"""
Cifrado de secretos en reposo (llaves de API, tokens de integraciones, configuración de conexiones).

Esquema: AES-256-GCM (cifrado autenticado, AEAD).
- Llave de 256 bits derivada con PBKDF2-HMAC-SHA256 (100.000 iteraciones) desde SECRET_KEY y
  PBKDF2_SALT, que entrega OpenBao (SECRET_KEY_FILE / PBKDF2_SALT_FILE).
- Nonce aleatorio de 96 bits por operación; etiqueta de autenticación de 128 bits.
- Formato de texto: "gcm::" + base64url(nonce || ciphertext || tag).
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from functools import lru_cache
from typing import Any, Dict

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SECRET_PREFIX = "gcm::"
NONCE_SIZE = 12
PBKDF2_ITERATIONS = 100_000


def _get_master_secret() -> str:
    """Obtiene la clave maestra (SECRET_KEY, cargada desde SECRET_KEY_FILE)."""
    secret = os.getenv("SECRET_KEY")
    if not secret:
        from app.core.settings import get_settings

        secret = get_settings().secret_key
    if not secret or not secret.strip():
        raise RuntimeError("SECRET_KEY is required for encryption (provided by OpenBao via SECRET_KEY_FILE).")
    return secret.strip()


def _get_pbkdf2_salt() -> bytes:
    salt = os.getenv("PBKDF2_SALT")
    if not salt:
        from app.core.settings import get_settings

        salt = get_settings().pbkdf2_salt
    if not salt or not salt.strip():
        raise RuntimeError("PBKDF2_SALT is required for encryption (provided by OpenBao via PBKDF2_SALT_FILE).")
    return salt.strip().encode("utf-8")


@lru_cache(maxsize=4)
def _derive_key(master_secret: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", master_secret.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32)


def derive_aes_key() -> bytes:
    """Llave AES-256 (32 bytes) derivada del secreto maestro."""
    return _derive_key(_get_master_secret(), _get_pbkdf2_salt())


def get_aesgcm() -> AESGCM:
    return AESGCM(derive_aes_key())


def encrypt_bytes(data: bytes, aad: bytes | None = None) -> str:
    """Cifra bytes con AES-256-GCM y retorna el token "gcm::...". """
    nonce = secrets.token_bytes(NONCE_SIZE)
    sealed = get_aesgcm().encrypt(nonce, data, aad)
    return SECRET_PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def decrypt_bytes(token: str, aad: bytes | None = None) -> bytes:
    """Descifra un token "gcm::..."; lanza InvalidTag si fue alterado o la llave no corresponde."""
    if not token.startswith(SECRET_PREFIX):
        raise ValueError("Token sin prefijo gcm::")
    raw = base64.urlsafe_b64decode(token[len(SECRET_PREFIX):].encode("ascii"))
    return get_aesgcm().decrypt(raw[:NONCE_SIZE], raw[NONCE_SIZE:], aad)


def is_encrypted(text: str | None) -> bool:
    """Verifica si una cadena está cifrada con AES-256-GCM (prefijo gcm::)."""
    return bool(text) and text.startswith(SECRET_PREFIX)


def encrypt_secret(plain_text: str | None) -> str:
    """Cifra un secreto en texto plano. Si ya está cifrado o está vacío, lo retorna sin alterar."""
    if not plain_text or not plain_text.strip():
        return ""
    plain_text = plain_text.strip()
    if is_encrypted(plain_text):
        return plain_text
    return encrypt_bytes(plain_text.encode("utf-8"))


def decrypt_secret(cipher_text: str | None) -> str:
    """Descifra un secreto "gcm::". Un valor sin prefijo se retorna tal cual (texto plano)."""
    if not cipher_text or not cipher_text.strip():
        return ""
    cipher_text = cipher_text.strip()
    if not is_encrypted(cipher_text):
        return cipher_text
    try:
        return decrypt_bytes(cipher_text).decode("utf-8")
    except (InvalidTag, ValueError):
        return ""


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

