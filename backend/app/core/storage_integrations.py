"""Organization integrations persistence (Jira, GitHub, GitLab, etc.).

Handles organization-level OAuth configuration and access secrets with AES-256-GCM encryption.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from cryptography.exceptions import InvalidTag

from app.core.secrets import decrypt_bytes, encrypt_bytes
from app.core.storage_cache import _CACHE_CONNECTIONS, make_conn_cache_key

logger = logging.getLogger(__name__)


def save_connection(integration_id: str, payload: dict[str, Any], org_id: str = "default") -> None:
  """Save encrypted connection payload to organization_integrations table."""
  raw = json.dumps(payload, indent=2).encode("utf-8")
  encrypted = encrypt_bytes(raw)
  cache_key = make_conn_cache_key(org_id, integration_id)
  _CACHE_CONNECTIONS[cache_key] = encrypted

  try:
    from app.db.unit_of_work import SyncUnitOfWork
    with SyncUnitOfWork() as uow:
      enc_str = encrypted
      uow.integrations.save_organization_integration(
        organization_id=org_id,
        provider=integration_id,
        client_id=payload.get("client_id"),
        client_secret_ref=enc_str,
        status="active",
        settings_payload=None,
      )
      uow.commit()
  except Exception as exc:
    logger.error("Failed to persist organization integration to DB: %s", exc)
    raise


def load_connection(integration_id: str, org_id: str = "default") -> dict[str, Any] | None:
  """Load encrypted connection payload from organization_integrations table."""
  cache_key = make_conn_cache_key(org_id, integration_id)
  encrypted: str | None = _CACHE_CONNECTIONS.get(cache_key)

  try:
    from app.db.unit_of_work import SyncUnitOfWork
    with SyncUnitOfWork() as uow:
      item = uow.integrations.get_organization_integration(org_id, integration_id)
      if item and item.get("client_secret_ref"):
        encrypted = item["client_secret_ref"]
        _CACHE_CONNECTIONS[cache_key] = encrypted
      elif item is None:
        # If DB explicitly has no record, invalidate cache
        _CACHE_CONNECTIONS.pop(cache_key, None)
        return None
  except Exception as exc:
    logger.debug("Could not read connection from organization_integrations: %s", exc)

  if not encrypted:
    return None

  try:
    decrypted = decrypt_bytes(encrypted)
    return json.loads(decrypted.decode("utf-8"))
  except (InvalidTag, ValueError, json.JSONDecodeError) as exc:
    logger.warning("Decryption failed for integration %s: %s", integration_id, exc)
    return None


def delete_connection(integration_id: str, org_id: str = "default") -> bool:
  """Delete connection from organization_integrations table and cache."""
  cache_key = make_conn_cache_key(org_id, integration_id)
  existed = cache_key in _CACHE_CONNECTIONS
  _CACHE_CONNECTIONS.pop(cache_key, None)

  try:
    from app.db.unit_of_work import SyncUnitOfWork
    with SyncUnitOfWork() as uow:
      deleted = uow.integrations.delete_organization_integration(org_id, integration_id)
      uow.commit()
      return bool(deleted or existed)
  except Exception as exc:
    logger.error("Could not delete connection from DB: %s", exc)
    raise


def connection_exists(integration_id: str, org_id: str = "default") -> bool:
  """Check if connection exists in organization_integrations table or memory."""
  cache_key = make_conn_cache_key(org_id, integration_id)
  if cache_key in _CACHE_CONNECTIONS:
    return True

  try:
    from app.db.unit_of_work import SyncUnitOfWork
    with SyncUnitOfWork() as uow:
      return uow.integrations.organization_integration_exists(org_id, integration_id)
  except Exception:
    return False

