"""SecretStore implementation providing AES-256-GCM authenticated encryption for user secrets.

Complies with OWASP Secrets Management & Cryptographic Storage recommendations:
- Isolated per user and purpose with Authenticated Additional Data (AAD)
- Random 96-bit (12-byte) nonce per encryption
- Authenticity verification on decryption
- Safe error handling without logging or leaking secrets
- Backward compatibility with legacy Fernet encrypted tokens
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import uuid
from typing import Any, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, select

from app.core.secrets import _derive_fernet_key, _get_master_secret, _get_pbkdf2_salt, decrypt_secret, is_encrypted
from app.db.models import AuditEventModel, UserSecretModel

logger = logging.getLogger(__name__)

SECRET_REF_PREFIX = "sec::"
CURRENT_KEY_VERSION = 1


def _derive_aes_key(master_secret: str) -> bytes:
  """Derive a 256-bit (32-byte) key for AES-GCM using PBKDF2-HMAC-SHA256."""
  salt = _get_pbkdf2_salt()
  return hashlib.pbkdf2_hmac(
    "sha256",
    master_secret.encode("utf-8"),
    salt,
    iterations=100_000,
    dklen=32,
  )


def _get_aesgcm() -> AESGCM:
  """Return an AESGCM cipher instance initialized with the derived master key."""
  master = _get_master_secret()
  key = _derive_aes_key(master)
  return AESGCM(key)


def _make_aad(user_id: str, purpose: str, secret_id: str) -> bytes:
  """Build Authenticated Additional Data binding ciphertext to user, purpose and id."""
  return f"{user_id}:{purpose}:{secret_id}".encode("utf-8")


def _extract_secret_id(secret_id_or_ref: str) -> str:
  """Normalize a secret reference or raw UUID to a secret id."""
  if not secret_id_or_ref:
    return ""
  if secret_id_or_ref.startswith(SECRET_REF_PREFIX):
    return secret_id_or_ref[len(SECRET_REF_PREFIX):]
  return secret_id_or_ref.strip()


class SecretStore:
  """Manages encrypted secrets lifecycle in the user_secrets database table."""

  def __init__(self) -> None:
    pass

  def create_secret(
    self,
    user_id: str,
    purpose: str,
    plain_value: str,
    db: Optional[Any] = None,
  ) -> str:
    """Encrypt and persist a secret, returning its unique secret id."""
    if not user_id or not purpose or not plain_value:
      raise ValueError("user_id, purpose, and plain_value are required")

    secret_id = str(uuid.uuid4())
    nonce = secrets.token_bytes(12)
    aad = _make_aad(user_id, purpose, secret_id)
    aesgcm = _get_aesgcm()

    ciphertext = aesgcm.encrypt(nonce, plain_value.encode("utf-8"), aad)
    b64_cipher = base64.b64encode(ciphertext).decode("utf-8")
    b64_nonce = base64.b64encode(nonce).decode("utf-8")

    def _persist(session: Any) -> None:
      record = UserSecretModel(
        id=secret_id,
        user_id=user_id,
        purpose=purpose,
        ciphertext=b64_cipher,
        nonce=b64_nonce,
        key_version=CURRENT_KEY_VERSION,
      )
      session.add(record)

    self._run_in_session(_persist, db)
    return secret_id

  def get_secret(
    self,
    user_id: str,
    secret_id_or_ref: str,
    purpose: Optional[str] = None,
    db: Optional[Any] = None,
  ) -> str:
    """Retrieve and decrypt a secret, verifying ownership and optional purpose."""
    if not user_id or not secret_id_or_ref:
      return ""

    if is_encrypted(secret_id_or_ref):
      return decrypt_secret(secret_id_or_ref)

    secret_id = _extract_secret_id(secret_id_or_ref)

    def _read(session: Any) -> Optional[UserSecretModel]:
      stmt = select(UserSecretModel).where(UserSecretModel.id == secret_id)
      return session.scalar(stmt)

    record = self._run_in_session(_read, db)
    if not record:
      return ""

    if record.user_id != user_id:
      self._record_audit_event(
        user_id=user_id,
        action="secret_access_denied",
        resource_id=secret_id,
        db=db,
      )
      raise PermissionError("Unauthorized access to requested secret")

    if purpose and record.purpose != purpose:
      raise ValueError("Secret purpose mismatch")

    return self._decrypt_record(record, user_id)

  def _decrypt_record(self, record: UserSecretModel, user_id: str) -> str:
    """Decrypt a UserSecretModel record with AES-256-GCM verification."""
    try:
      nonce = base64.b64decode(record.nonce)
      ciphertext = base64.b64decode(record.ciphertext)
      aad = _make_aad(user_id, record.purpose, record.id)
      aesgcm = _get_aesgcm()
      decrypted = aesgcm.decrypt(nonce, ciphertext, aad)
      return decrypted.decode("utf-8")
    except Exception as exc:
      logger.warning("Decryption failed for secret %s: %s", record.id, exc)
      return ""

  def rotate_secret(
    self,
    user_id: str,
    secret_id_or_ref: str,
    new_plain_value: str,
    db: Optional[Any] = None,
  ) -> str:
    """Rotate an existing secret with a fresh nonce and ciphertext."""
    if not user_id or not secret_id_or_ref or not new_plain_value:
      raise ValueError("Invalid parameters for rotate_secret")

    secret_id = _extract_secret_id(secret_id_or_ref)

    def _rotate(session: Any) -> str:
      stmt = select(UserSecretModel).where(UserSecretModel.id == secret_id)
      record = session.scalar(stmt)
      if not record or record.user_id != user_id:
        raise PermissionError("Secret not found or access denied")

      nonce = secrets.token_bytes(12)
      aad = _make_aad(user_id, record.purpose, secret_id)
      aesgcm = _get_aesgcm()
      ciphertext = aesgcm.encrypt(nonce, new_plain_value.encode("utf-8"), aad)

      record.ciphertext = base64.b64encode(ciphertext).decode("utf-8")
      record.nonce = base64.b64encode(nonce).decode("utf-8")
      record.key_version = CURRENT_KEY_VERSION
      return secret_id

    return self._run_in_session(_rotate, db)

  def delete_secret(
    self,
    user_id: str,
    secret_id_or_ref: str,
    db: Optional[Any] = None,
  ) -> bool:
    """Delete a secret from persistent storage if owned by user."""
    if not user_id or not secret_id_or_ref:
      return False

    secret_id = _extract_secret_id(secret_id_or_ref)

    def _delete(session: Any) -> bool:
      stmt = select(UserSecretModel).where(UserSecretModel.id == secret_id)
      record = session.scalar(stmt)
      if not record:
        return False
      if record.user_id != user_id:
        raise PermissionError("Cannot delete secret owned by another user")

      session.delete(record)
      return True

    return self._run_in_session(_delete, db)

  def validate_secret_access(
    self,
    user_id: str,
    secret_id_or_ref: str,
    expected_purpose: Optional[str] = None,
    db: Optional[Any] = None,
  ) -> bool:
    """Check if the secret exists and belongs to the specified user."""
    if not user_id or not secret_id_or_ref:
      return False
    secret_id = _extract_secret_id(secret_id_or_ref)

    def _check(session: Any) -> bool:
      stmt = select(UserSecretModel).where(UserSecretModel.id == secret_id)
      record = session.scalar(stmt)
      if not record or record.user_id != user_id:
        return False
      if expected_purpose and record.purpose != expected_purpose:
        return False
      return True

    return bool(self._run_in_session(_check, db))

  def _record_audit_event(
    self,
    user_id: str,
    action: str,
    resource_id: str,
    db: Optional[Any] = None,
  ) -> None:
    """Write an entry to audit_events for security monitoring."""
    def _audit(session: Any) -> None:
      event = AuditEventModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=action,
        resource_type="secret",
        resource_id=resource_id,
      )
      session.add(event)

    try:
      self._run_in_session(_audit, db)
    except Exception as exc:
      logger.debug("Failed logging audit event: %s", exc)

  def _run_in_session(self, func_op: Any, db: Optional[Any] = None) -> Any:
    """Execute a callable inside the passed session or a new sync session."""
    if db is not None:
      return func_op(db)
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      res = func_op(session)
      session.commit()
      return res


# Singleton accessor
secret_store = SecretStore()

