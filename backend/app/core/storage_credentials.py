"""User provider credentials persistence (Entity: user_provider_credentials).

Stores and retrieves encrypted API keys per user and external AI provider
using SecretStore with AES-256-GCM authenticated encryption.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import select

from app.core.secret_store import secret_store
from app.core.secrets import decrypt_secret
from app.db.models import UserProviderCredentialModel

logger = logging.getLogger(__name__)


def save_user_credential(
  user_id: str,
  provider: str,
  raw_key: str,
  db: Optional[Any] = None,
) -> str:
  """Store an encrypted API key credential for a user and provider."""
  if not user_id or not provider or not raw_key or not raw_key.strip():
    return ""

  clean_key = raw_key.strip()
  purpose = f"byok_{provider}"

  def _persist(session: Any) -> str:
    secret_id = secret_store.create_secret(
      user_id=user_id,
      purpose=purpose,
      plain_value=clean_key,
      db=session,
    )
    enc_ref = f"sec::{secret_id}"

    cred = session.scalar(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id,
        UserProviderCredentialModel.provider == provider,
      )
    )
    if cred:
      cred.secret_id = secret_id
      cred.secret_ref = enc_ref
      cred.status = "active"
      cred.validation_error = None
    else:
      cred = UserProviderCredentialModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        provider=provider,
        secret_id=secret_id,
        secret_ref=enc_ref,
        status="active",
      )
      session.add(cred)
    return secret_id

  if db is not None:
    return _persist(db)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      res = _persist(session)
      session.commit()
      return res
  except Exception as exc:
    logger.error("Failed saving credential for user %s, provider %s: %s", user_id, provider, exc)
    raise


def load_user_credential(user_id: str, provider: str, db: Optional[Any] = None) -> str:
  """Retrieve and decrypt an API key credential for a user and provider."""
  if not user_id or not provider:
    return ""

  def _read(session: Any) -> str:
    cred = session.scalar(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id,
        UserProviderCredentialModel.provider == provider,
      )
    )
    if not cred:
      return ""

    ref_or_id = cred.secret_id or cred.secret_ref
    if ref_or_id:
      try:
        val = secret_store.get_secret(
          user_id=user_id,
          secret_id_or_ref=ref_or_id,
          purpose=f"byok_{provider}",
          db=session,
        )
        if val:
          return val
      except Exception as exc:
        logger.debug("SecretStore read error for %s/%s: %s", user_id, provider, exc)

      if cred.secret_ref:
        return decrypt_secret(cred.secret_ref)
    return ""

  if db is not None:
    return _read(db)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      return _read(session)
  except Exception as exc:
    logger.debug("Failed reading credential for user %s, provider %s: %s", user_id, provider, exc)
  return ""


def delete_user_credential(user_id: str, provider: str, db: Optional[Any] = None) -> bool:
  """Delete a provider credential and its associated secret."""
  if not user_id or not provider:
    return False

  def _delete(session: Any) -> bool:
    cred = session.scalar(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id,
        UserProviderCredentialModel.provider == provider,
      )
    )
    if not cred:
      return False

    secret_ref = cred.secret_id or cred.secret_ref
    if secret_ref:
      try:
        secret_store.delete_secret(user_id, secret_ref, db=session)
      except Exception as exc:
        logger.debug("Could not delete secret entity: %s", exc)

    session.delete(cred)
    return True

  if db is not None:
    return _delete(db)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      res = _delete(session)
      session.commit()
      return res
  except Exception as exc:
    logger.error("Failed deleting credential for %s/%s: %s", user_id, provider, exc)
    raise


def list_user_credentials_info(user_id: str, db: Optional[Any] = None) -> List[dict[str, Any]]:
  """List public, non-secret metadata of configured provider credentials."""
  if not user_id:
    return []

  def _list(session: Any) -> List[dict[str, Any]]:
    creds = session.scalars(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id
      )
    ).all()
    return [
      {
        "provider": c.provider,
        "status": c.status,
        "is_configured": True,
        "last_validated_at": c.last_validated_at.isoformat() if c.last_validated_at else None,
        "validation_error": c.validation_error,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
      }
      for c in creds
    ]

  if db is not None:
    return _list(db)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      return _list(session)
  except Exception as exc:
    logger.debug("Failed listing credentials for %s: %s", user_id, exc)
    return []


def update_credential_validation(
  user_id: str,
  provider: str,
  status: str,
  error_msg: Optional[str] = None,
  db: Optional[Any] = None,
) -> None:
  """Update last validation timestamp and result without storing secret details."""
  def _update(session: Any) -> None:
    cred = session.scalar(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id,
        UserProviderCredentialModel.provider == provider,
      )
    )
    if cred:
      cred.status = status
      cred.last_validated_at = datetime.now(timezone.utc)
      cred.validation_error = error_msg

  if db is not None:
    _update(db)
    return

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      _update(session)
      session.commit()
  except Exception as exc:
    logger.debug("Failed updating credential validation: %s", exc)


def load_all_user_credentials(user_id: str, db: Optional[Any] = None) -> dict[str, str]:
  """Retrieve and decrypt all provider API keys for a user."""
  results: dict[str, str] = {}
  if not user_id:
    return results

  for prov in ("openai", "claude", "groq", "gemini"):
    val = load_user_credential(user_id, prov, db=db)
    if val:
      results[f"{prov}_api_key"] = val

  return results
