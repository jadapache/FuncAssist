"""User provider credentials persistence (Entity: user_provider_credentials).

Stores and retrieves encrypted API keys per user and external AI provider.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select

from app.core.secrets import decrypt_secret, encrypt_secret
from app.db.models import UserProviderCredentialModel

logger = logging.getLogger(__name__)


def save_user_credential(
  user_id: str,
  provider: str,
  raw_key: str,
  db: Optional[Any] = None,
) -> None:
  """Store an encrypted API key credential for a user and provider."""
  if not user_id or not provider or not raw_key or not raw_key.strip():
    return

  enc_ref = encrypt_secret(raw_key.strip())

  def _persist(session: Any) -> None:
    cred = session.scalar(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id,
        UserProviderCredentialModel.provider == provider,
      )
    )
    if cred:
      cred.secret_ref = enc_ref
      cred.status = "active"
    else:
      cred = UserProviderCredentialModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        provider=provider,
        secret_ref=enc_ref,
        status="active",
      )
      session.add(cred)

  if db is not None:
    _persist(db)
    return

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      _persist(session)
      session.commit()
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
    if cred and cred.secret_ref:
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


def load_all_user_credentials(user_id: str, db: Optional[Any] = None) -> dict[str, str]:
  """Retrieve and decrypt all provider API keys for a user."""
  results: dict[str, str] = {}
  if not user_id:
    return results

  def _read_all(session: Any) -> dict[str, str]:
    all_creds = session.scalars(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id,
        UserProviderCredentialModel.status == "active",
      )
    ).all()
    res: dict[str, str] = {}
    for c in all_creds:
      if c.secret_ref:
        plain = decrypt_secret(c.secret_ref)
        res[f"{c.provider}_api_key"] = plain
    return res

  if db is not None:
    return _read_all(db)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      return _read_all(session)
  except Exception as exc:
    logger.debug("Failed loading credentials for user %s: %s", user_id, exc)
  return results

