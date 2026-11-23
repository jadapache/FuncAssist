import hashlib
import hmac
import os
import secrets
import time
from typing import Any, Dict, Optional, Tuple

import jwt

from app.core.settings import get_settings

PBKDF2_ITERATIONS = 100_000


def generate_salt(length: int = 16) -> str:
    """Genera un salt aleatorio seguro en formato hexadecimal."""
    return secrets.token_hex(length)


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Aplica derivacion segura de contrasenas usando PBKDF2-HMAC-SHA256 con Salt."""
    if not salt:
        salt = generate_salt()
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return pwd_hash, salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verifica si la contrasena ingresada coincide con el hash almacenado mediante PBKDF2-HMAC-SHA256."""
    computed_hash, _ = hash_password(password, salt=salt)
    return hmac.compare_digest(computed_hash, password_hash)


JWT_ALGORITHM = "HS256"
JWT_ISSUER = "funcassist"
ACCESS_TOKEN_TTL_SECONDS = 60 * 60 * 12 


def _get_signing_key() -> bytes:
    settings = get_settings()
    secret = settings.secret_key or os.getenv("SECRET_KEY")
    if not secret or not secret.strip():
        raise RuntimeError("SECRET_KEY environment variable is required for application security and tokens.")
    return hashlib.sha256(secret.strip().encode("utf-8")).digest()


def create_access_token(payload: Dict[str, Any], expires_in_seconds: int = ACCESS_TOKEN_TTL_SECONDS) -> str:
    """Genera un JWT (RFC 7519) firmado con HS256 mediante PyJWT."""
    now = int(time.time())
    claims = dict(payload)
    claims.update({"iat": now, "nbf": now, "exp": now + expires_in_seconds, "iss": JWT_ISSUER})
    return jwt.encode(claims, _get_signing_key(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Valida firma, algoritmo, emisor y expiracion del JWT. Retorna None si no es valido."""
    try:
        return jwt.decode(
            token,
            _get_signing_key(),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except jwt.PyJWTError:
        return None


def machine_fingerprint() -> str:
    """Genera una huella digital unica para el equipo local.

    Combinacion de atributos del sistema operativo y del directorio home.
    Usada como factor en la derivacion de claves de cifrado locales.
    """
    import platform
    from pathlib import Path

    parts = [
        platform.node(),
        platform.system(),
        platform.machine(),
        str(Path.home()),
    ]
    return "|".join(parts)


def set_session_cookie(response: Any, token: str) -> None:
    """Entrega el JWT en una cookie HttpOnly + Secure + SameSite=Strict (no accesible desde JS)."""
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=ACCESS_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/api",
    )


def clear_session_cookie(response: Any) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/api",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
    )
