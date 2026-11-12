"""User personal integrations persistence (e.g. personal OAuth Jira).

Stores encrypted access and refresh tokens scoped strictly to (user_id, provider)
and maintains synchronization with UserJiraConnectionModel and SecretStore.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select

from app.core.secret_store import secret_store
from app.core.secrets import decrypt_secret, encrypt_secret
from app.core.storage_cache import _CACHE_CONNECTIONS, make_user_conn_cache_key
from app.db.repositories.integration_repository import IntegrationRepository

logger = logging.getLogger(__name__)


def save_user_integration(
  user_id: str,
  provider: str,
  payload: dict[str, Any],
  db: Optional[Any] = None,
) -> None:
  """Save encrypted personal integration payload scoped strictly to user_id and provider."""
  if not user_id or not provider:
    raise ValueError("user_id and provider are required to save a user integration.")

  payload = dict(payload)
  payload.setdefault("status", "connected")
  raw = json.dumps(payload, ensure_ascii=False)
  enc_str = encrypt_secret(raw)

  cache_key = make_user_conn_cache_key(user_id, provider)
  _CACHE_CONNECTIONS[cache_key] = enc_str.encode("utf-8")

  access_token = payload.get("access_token")
  refresh_token = payload.get("refresh_token")

  access_secret_id: Optional[str] = None
  refresh_secret_id: Optional[str] = None

  def _persist(session: Any) -> None:
    nonlocal access_secret_id, refresh_secret_id
    if access_token:
      access_secret_id = secret_store.create_secret(
        user_id=user_id,
        purpose=f"{provider}_access_token",
        plain_value=access_token,
        db=session,
      )
    if refresh_token:
      refresh_secret_id = secret_store.create_secret(
        user_id=user_id,
        purpose=f"{provider}_refresh_token",
        plain_value=refresh_token,
        db=session,
      )

    enc_access = f"sec::{access_secret_id}" if access_secret_id else (encrypt_secret(access_token) if access_token else None)
    enc_refresh = f"sec::{refresh_secret_id}" if refresh_secret_id else (encrypt_secret(refresh_token) if refresh_token else None)

    scopes = payload.get("scopes") or []
    scopes_json = json.dumps(scopes) if isinstance(scopes, list) else str(scopes)

    jira_extra = None
    if provider == "jira":
      jira_extra = {
        "jira_url": payload.get("jira_url") or payload.get("base_url") or payload.get("site_url"),
        "cloud_id": payload.get("cloud_id"),
        "account_email": payload.get("account_email") or payload.get("email"),
        "account_id": payload.get("account_id") or payload.get("external_account_id"),
        "access_token_secret_id": access_secret_id,
        "refresh_token_secret_id": refresh_secret_id,
      }

    repo = IntegrationRepository(session=session)
    repo.save_user_integration(
      user_id=user_id,
      provider=provider,
      external_account_id=payload.get("account_id") or payload.get("external_account_id"),
      external_account_name=payload.get("account_name") or payload.get("display_name"),
      access_token_ref=enc_access,
      refresh_token_ref=enc_refresh,
      expires_at=payload.get("expires_at"),
      scopes_json=scopes_json,
      connection_metadata_json=enc_str,
      status=payload.get("status") or "connected",
      jira_extra=jira_extra,
    )

  if db is not None:
    _persist(db)
    return

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      _persist(session)
      session.commit()
  except Exception as exc:
    logger.error("Failed to persist user integration to DB: %s", exc)
    raise


def load_user_integration(
  user_id: str,
  provider: str,
  db: Optional[Any] = None,
) -> dict[str, Any] | None:
  """Load and decrypt user integration payload for specific user_id and provider."""
  if not user_id or not provider:
    return None

  cache_key = make_user_conn_cache_key(user_id, provider)
  enc_bytes = _CACHE_CONNECTIONS.get(cache_key)
  enc_str: str | None = enc_bytes.decode("utf-8") if enc_bytes else None

  try:
    if db is not None:
      repo = IntegrationRepository(session=db)
      item = repo.get_user_integration(user_id, provider)
    else:
      from app.db.database import get_sync_db
      with get_sync_db() as session:
        repo = IntegrationRepository(session=session)
        item = repo.get_user_integration(user_id, provider)

    if item and item.get("connection_metadata_json"):
      enc_str = item["connection_metadata_json"]
      _CACHE_CONNECTIONS[cache_key] = enc_str.encode("utf-8")
    elif item is None and db is None:
      _CACHE_CONNECTIONS.pop(cache_key, None)
      return None
  except Exception as exc:
    logger.debug("Could not read user_integrations: %s", exc)

  if not enc_str:
    return None

  try:
    decrypted = decrypt_secret(enc_str)
    return json.loads(decrypted)
  except Exception as exc:
    logger.warning("Decryption failed for user integration %s/%s: %s", user_id, provider, exc)
    return None


def delete_user_integration(
  user_id: str,
  provider: str,
  db: Optional[Any] = None,
) -> bool:
  """Delete a user integration from DB and in-memory cache."""
  if not user_id or not provider:
    return False

  cache_key = make_user_conn_cache_key(user_id, provider)
  existed = cache_key in _CACHE_CONNECTIONS
  _CACHE_CONNECTIONS.pop(cache_key, None)

  if db is not None:
    repo = IntegrationRepository(session=db)
    deleted = repo.delete_user_integration(user_id, provider)
    return bool(deleted or existed)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      repo = IntegrationRepository(session=session)
      deleted = repo.delete_user_integration(user_id, provider)
      session.commit()
      return bool(deleted or existed)
  except Exception as exc:
    logger.error("Failed deleting user integration %s/%s: %s", user_id, provider, exc)
    raise


def user_integration_exists(
  user_id: str,
  provider: str,
  db: Optional[Any] = None,
) -> bool:
  """Check whether a user has an active connection configured."""
  data = load_user_integration(user_id, provider, db=db)
  return data is not None and data.get("status", "connected") == "connected"
