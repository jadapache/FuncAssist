"""User personal integrations persistence (e.g. personal OAuth Jira).

Stores encrypted access and refresh tokens scoped strictly to (user_id, provider)
and maintains synchronization with UserJiraConnectionModel and SecretStore.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from functools import reduce
from typing import Any, Iterator, Optional

from app.core.secret_store import secret_store
from app.core.secrets import decrypt_secret, encrypt_secret
from app.core.storage_cache import _CACHE_CONNECTIONS, make_user_conn_cache_key
from app.db.repositories.integration_repository import IntegrationRepository

logger = logging.getLogger(__name__)


@contextmanager
def _session_scope(db: Optional[Any], failure: str, *failure_args: Any) -> Iterator[Any]:
  """The caller's session as it is, or a new transaction that commits when the block succeeds."""
  if db is not None:
    yield db
    return
  try:
    from app.db.unit_of_work import SyncUnitOfWork

    with SyncUnitOfWork() as uow:
      yield uow.session
      uow.commit()
  except Exception as exc:
    logger.error(failure, *failure_args, exc)
    raise


def _first(payload: dict[str, Any], *keys: str) -> Any:
  """The first truthy value among the keys (the last one's value when none is)."""
  return reduce(lambda found, key: found or payload.get(key), keys, None)


def _store_token(session: Any, user_id: str, provider: str, kind: str, token: Optional[str]) -> tuple[Optional[str], Optional[str]]:
  """The reference to keep in the row and the id of the secret that holds the token.

  A token goes to the secret store; when the store gives no id the token is kept encrypted in the row.
  """
  if not token:
    return None, None
  secret_id = secret_store.create_secret(user_id=user_id, purpose=f"{provider}_{kind}_token", plain_value=token, db=session)
  if secret_id:
    return f"sec::{secret_id}", secret_id
  return encrypt_secret(token), None


def _scopes_json(payload: dict[str, Any]) -> str:
  scopes = payload.get("scopes") or []
  return json.dumps(scopes) if isinstance(scopes, list) else str(scopes)


def _jira_extra(payload: dict[str, Any], access_secret_id: Optional[str], refresh_secret_id: Optional[str]) -> dict[str, Any]:
  return {
    "jira_url": _first(payload, "jira_url", "base_url", "site_url"),
    "cloud_id": payload.get("cloud_id"),
    "account_email": _first(payload, "account_email", "email"),
    "account_id": _first(payload, "account_id", "external_account_id"),
    "access_token_secret_id": access_secret_id,
    "refresh_token_secret_id": refresh_secret_id,
  }


def _persist(session: Any, user_id: str, provider: str, payload: dict[str, Any], enc_str: str) -> None:
  access_ref, access_secret_id = _store_token(session, user_id, provider, "access", payload.get("access_token"))
  refresh_ref, refresh_secret_id = _store_token(session, user_id, provider, "refresh", payload.get("refresh_token"))
  status = payload.get("status") or "connected"
  jira_extra = _jira_extra(payload, access_secret_id, refresh_secret_id) if provider == "jira" else None
  IntegrationRepository(session=session).save_user_integration(
    user_id=user_id,
    provider=provider,
    external_account_id=_first(payload, "account_id", "external_account_id"),
    external_account_name=_first(payload, "account_name", "display_name"),
    access_token_ref=access_ref,
    refresh_token_ref=refresh_ref,
    expires_at=payload.get("expires_at"),
    scopes_json=_scopes_json(payload),
    connection_metadata_json=enc_str,
    status=status,
    jira_extra=jira_extra,
  )


def save_user_integration(
  user_id: str,
  provider: str,
  payload: dict[str, Any],
  db: Optional[Any] = None,
) -> None:
  """Save encrypted personal integration payload scoped strictly to user_id and provider."""
  if not user_id or not provider:
    raise ValueError("user_id and provider are required to save a user integration.")

  payload = {"status": "connected", **payload}
  enc_str = encrypt_secret(json.dumps(payload, ensure_ascii=False))
  _CACHE_CONNECTIONS[make_user_conn_cache_key(user_id, provider)] = enc_str.encode("utf-8")

  with _session_scope(db, "Failed to persist user integration to DB: %s") as session:
    _persist(session, user_id, provider, payload, enc_str)


def _fetch_row(user_id: str, provider: str, db: Optional[Any]) -> Optional[dict[str, Any]]:
  if db is not None:
    return IntegrationRepository(session=db).get_user_integration(user_id, provider)
  from app.db.unit_of_work import SyncUnitOfWork

  with SyncUnitOfWork() as uow:
    return uow.integrations.get_user_integration(user_id, provider)


def _decrypted_payload(enc_str: Optional[str], user_id: str, provider: str) -> dict[str, Any] | None:
  if not enc_str:
    return None
  try:
    return json.loads(decrypt_secret(enc_str))
  except Exception as exc:
    logger.warning("Decryption failed for user integration %s/%s: %s", user_id, provider, exc)
    return None


def load_user_integration(
  user_id: str,
  provider: str,
  db: Optional[Any] = None,
) -> dict[str, Any] | None:
  """Load and decrypt user integration payload for specific user_id and provider.

  The database is the source of truth: a row replaces the cached value and no row drops it. When the
  database cannot be read the cached value is used.
  """
  if not user_id or not provider:
    return None

  cache_key = make_user_conn_cache_key(user_id, provider)
  cached = _CACHE_CONNECTIONS.get(cache_key)
  enc_str: str | None = cached.decode("utf-8") if cached else None

  try:
    item = _fetch_row(user_id, provider, db)
  except Exception as exc:
    logger.debug("Could not read user_integrations: %s", exc)
  else:
    if item is None and db is None:
      _CACHE_CONNECTIONS.pop(cache_key, None)
      return None
    if item and item.get("connection_metadata_json"):
      enc_str = item["connection_metadata_json"]
      _CACHE_CONNECTIONS[cache_key] = enc_str.encode("utf-8")

  return _decrypted_payload(enc_str, user_id, provider)


def delete_user_integration(
  user_id: str,
  provider: str,
  db: Optional[Any] = None,
) -> bool:
  """Delete a user integration from DB and in-memory cache."""
  if not user_id or not provider:
    return False

  existed = _CACHE_CONNECTIONS.pop(make_user_conn_cache_key(user_id, provider), None) is not None
  with _session_scope(db, "Failed deleting user integration %s/%s: %s", user_id, provider) as session:
    deleted = IntegrationRepository(session=session).delete_user_integration(user_id, provider)
  return bool(deleted or existed)


def user_integration_exists(
  user_id: str,
  provider: str,
  db: Optional[Any] = None,
) -> bool:
  """Check whether a user has an active connection configured."""
  data = load_user_integration(user_id, provider, db=db)
  return data is not None and data.get("status", "connected") == "connected"
