import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional, Tuple

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


def _get_signing_key() -> bytes:
    settings = get_settings()
    secret = settings.secret_key or os.getenv("SECRET_KEY")
    if not secret or not secret.strip():
        raise RuntimeError("SECRET_KEY environment variable is required for application security and tokens.")
    return hashlib.sha256(secret.strip().encode("utf-8")).digest()


def create_access_token(payload: Dict[str, Any], expires_in_seconds: int = 86400 * 7) -> str:
    """Genera un token Bearer firmado usando HMAC-SHA256."""
    data = dict(payload)
    data["exp"] = int(time.time()) + expires_in_seconds
    raw_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")

    signature = hmac.new(_get_signing_key(), b64_payload.encode("ascii"), hashlib.sha256).digest()
    b64_sig = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")

    return f"{b64_payload}.{b64_sig}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Valida la firma y fecha de expiracion del token Bearer."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        b64_payload, b64_sig = parts

        # Verify signature
        expected_sig = hmac.new(_get_signing_key(), b64_payload.encode("ascii"), hashlib.sha256).digest()
        expected_b64_sig = base64.urlsafe_b64encode(expected_sig).decode("ascii").rstrip("=")

        if not hmac.compare_digest(b64_sig, expected_b64_sig):
            return None

        # Restore padding for base64 decoding
        padded = b64_payload + "=" * (-len(b64_payload) % 4)
        raw_bytes = base64.urlsafe_b64decode(padded)
        data = json.loads(raw_bytes.decode("utf-8"))

        if data.get("exp", 0) < time.time():
            return None  # Token expired

        return data
    except Exception:
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
