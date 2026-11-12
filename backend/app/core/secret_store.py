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
from app.db.interfaces.secret_repository import IUserSecretRepository
from app.db.repositories.secret_repository import UserSecretRepository

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

  def __init__(self, repo_factory: Optional[Any] = None) -> None:
    self.repo_factory = repo_factory

  def _get_repo(self, db: Optional[Any] = None, session_manager: Optional[Any] = None) -> tuple[IUserSecretRepository, Optional[Any]]:
    if db is not None:
      return UserSecretRepository(session=db), None
    if self.repo_factory:
      return self.repo_factory(), None
    from app.db.database import get_sync_db
    cm = get_sync_db()
    session = cm.__enter__()
    return UserSecretRepository(session=session), (cm, session)

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

    repo, cm_tuple = self._get_repo(db)
    try:
      repo.create(
        secret_id=secret_id,
        user_id=user_id,
        purpose=purpose,
        ciphertext=b64_cipher,
        nonce=b64_nonce,
        key_version=CURRENT_KEY_VERSION,
      )
      if cm_tuple:
        cm, session = cm_tuple
        session.commit()
    finally:
      if cm_tuple:
        cm, session = cm_tuple
        cm.__exit__(None, None, None)

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
    repo, cm_tuple = self._get_repo(db)
    try:
      record = repo.get_by_id(secret_id)
      if not record:
        return ""

      if record.get("user_id") != user_id:
        repo.record_audit_event(
          user_id=user_id,
          action="secret_access_denied",
          resource_type="secret",
          resource_id=secret_id,
        )
        if cm_tuple:
          cm, session = cm_tuple
          session.commit()
        raise PermissionError("Unauthorized access to requested secret")

      if purpose and record.get("purpose") != purpose:
        raise ValueError("Secret purpose mismatch")

      return self._decrypt_record(record, user_id)
    finally:
      if cm_tuple:
        cm, session = cm_tuple
        cm.__exit__(None, None, None)

  def _decrypt_record(self, record: dict[str, Any], user_id: str) -> str:
    """Decrypt a secret record with AES-256-GCM verification."""
    try:
      nonce = base64.b64decode(record["nonce"])
      ciphertext = base64.b64decode(record["ciphertext"])
      aad = _make_aad(user_id, record["purpose"], record["id"])
      aesgcm = _get_aesgcm()
      decrypted = aesgcm.decrypt(nonce, ciphertext, aad)
      return decrypted.decode("utf-8")
    except Exception as exc:
      logger.warning("Decryption failed for secret %s: %s", record.get("id"), exc)
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
    repo, cm_tuple = self._get_repo(db)
    try:
      record = repo.get_by_id(secret_id)
      if not record or record.get("user_id") != user_id:
        raise PermissionError("Secret not found or access denied")

      nonce = secrets.token_bytes(12)
      aad = _make_aad(user_id, record["purpose"], secret_id)
      aesgcm = _get_aesgcm()
      ciphertext = aesgcm.encrypt(nonce, new_plain_value.encode("utf-8"), aad)

      repo.update_ciphertext(
        secret_id=secret_id,
        user_id=user_id,
        ciphertext=base64.b64encode(ciphertext).decode("utf-8"),
        nonce=base64.b64encode(nonce).decode("utf-8"),
        key_version=CURRENT_KEY_VERSION,
      )
      if cm_tuple:
        cm, session = cm_tuple
        session.commit()
      return secret_id
    finally:
      if cm_tuple:
        cm, session = cm_tuple
        cm.__exit__(None, None, None)

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
    repo, cm_tuple = self._get_repo(db)
    try:
      record = repo.get_by_id(secret_id)
      if not record:
        return False
      if record.get("user_id") != user_id:
        raise PermissionError("Cannot delete secret owned by another user")

      deleted = repo.delete(secret_id, user_id)
      if cm_tuple:
        cm, session = cm_tuple
        session.commit()
      return deleted
    finally:
      if cm_tuple:
        cm, session = cm_tuple
        cm.__exit__(None, None, None)

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
    repo, cm_tuple = self._get_repo(db)
    try:
      record = repo.get_by_id(secret_id)
      if not record or record.get("user_id") != user_id:
        return False
      if expected_purpose and record.get("purpose") != expected_purpose:
        return False
      return True
    finally:
      if cm_tuple:
        cm, session = cm_tuple
        cm.__exit__(None, None, None)

  def _record_audit_event(
    self,
    user_id: str,
    action: str,
    resource_id: str,
    db: Optional[Any] = None,
  ) -> None:
    repo, cm_tuple = self._get_repo(db)
    try:
      repo.record_audit_event(
        user_id=user_id,
        action=action,
        resource_type="secret",
        resource_id=resource_id,
      )
      if cm_tuple:
        cm, session = cm_tuple
        session.commit()
    finally:
      if cm_tuple:
        cm, session = cm_tuple
        cm.__exit__(None, None, None)


# Singleton accessor
secret_store = SecretStore()

