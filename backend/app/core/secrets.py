"""
Módulo de gestión de secretos y cifrado para llaves de API (API Keys) de modelos de IA.
Basado en cifrado simétrico Fernet (cryptography.fernet) para proteger credenciales en archivos JSON.
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

from app.core.security import machine_fingerprint as _machine_fingerprint

SECRET_PREFIX = "enc::"



def _get_master_secret() -> str:
    """Obtiene la clave maestra desde variables de entorno o la huella del sistema."""
    secret = os.getenv("PMQA_SECRET_KEY") or os.getenv("SECRET_KEY")
    if secret:
        return secret
    return f"qa-mgmt-local-secret::{_machine_fingerprint()}"


def _get_fernet() -> Fernet:
    """Deriva una clave Fernet válida a partir del secreto maestro."""
    secret_bytes = _get_master_secret().encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_bytes).digest())
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
