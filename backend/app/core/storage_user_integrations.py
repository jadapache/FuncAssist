"""User personal integrations persistence (e.g. personal OAuth Jira).

Stores encrypted access and refresh tokens scoped strictly to (user_id, provider).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select

from app.core.secrets import decrypt_secret, encrypt_secret
from app.core.storage_cache import _CACHE_CONNECTIONS, make_user_conn_cache_key
from app.db.models import UserIntegrationModel

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

  raw = json.dumps(payload, ensure_ascii=False)
  enc_str = encrypt_secret(raw)

  cache_key = make_user_conn_cache_key(user_id, provider)
  _CACHE_CONNECTIONS[cache_key] = enc_str.encode("utf-8")

  access_token = payload.get("access_token")
  refresh_token = payload.get("refresh_token")
  enc_access = encrypt_secret(access_token) if access_token else None
  enc_refresh = encrypt_secret(refresh_token) if refresh_token else None

  scopes = payload.get("scopes") or []
  scopes_json = json.dumps(scopes) if isinstance(scopes, list) else str(scopes)

  metadata = {
    k: v for k, v in payload.items()
    if k not in ("access_token", "refresh_token", "scopes", "user_id", "provider")
  }
  metadata_json = json.dumps(metadata)

  def _persist(session: Any) -> None:
    item = session.scalar(
      select(UserIntegrationModel).where(
        UserIntegrationModel.user_id == user_id,
        UserIntegrationModel.provider == provider,
      )
    )
    if item:
      item.external_account_id = payload.get("account_id") or payload.get("external_account_id")
      item.external_account_name = payload.get("account_name") or payload.get("display_name")
      item.access_token_ref = enc_access
      item.refresh_token_ref = enc_refresh
      item.expires_at = payload.get("expires_at")
      item.scopes_json = scopes_json
      item.connection_metadata_json = enc_str
      item.status = payload.get("status") or "connected"
    else:
      new_item = UserIntegrationModel(
        id=str(uuid.uuid4()),
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
      )
      session.add(new_item)

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

  def _query(session: Any) -> Any:
    return session.scalar(
      select(UserIntegrationModel).where(
        UserIntegrationModel.user_id == user_id,
        UserIntegrationModel.provider == provider,
      )
    )

  try:
    if db is not None:
      item = _query(db)
    else:
      from app.db.database import get_sync_db
      with get_sync_db() as session:
        item = _query(session)

    if item and item.connection_metadata_json:
      enc_str = item.connection_metadata_json
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

  def _delete(session: Any) -> bool:
    item = session.scalar(
      select(UserIntegrationModel).where(
        UserIntegrationModel.user_id == user_id,
        UserIntegrationModel.provider == provider,
      )
    )
    if item:
      session.delete(item)
      return True
    return existed

  if db is not None:
    return _delete(db)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      res = _delete(session)
      session.commit()
      return res
  except Exception as exc:
    logger.error("Could not delete user integration from DB: %s", exc)
    raise


def user_integration_exists(
  user_id: str,
  provider: str,
  db: Optional[Any] = None,
) -> bool:
  """Check if a user integration exists in memory or DB."""
  if not user_id or not provider:
    return False

  cache_key = make_user_conn_cache_key(user_id, provider)
  if cache_key in _CACHE_CONNECTIONS:
    return True

  def _exists(session: Any) -> bool:
    item = session.scalar(
      select(UserIntegrationModel.id).where(
        UserIntegrationModel.user_id == user_id,
        UserIntegrationModel.provider == provider,
      )
    )
    return item is not None

  if db is not None:
    return _exists(db)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as session:
      return _exists(session)
  except Exception:
    return False

