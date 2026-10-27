"""Organization integrations persistence (Jira, GitHub, GitLab, etc.).

Handles organization-level OAuth configuration and access secrets with Fernet encryption.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import uuid
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.core.settings import get_settings
from app.core.storage_cache import _CACHE_CONNECTIONS, make_conn_cache_key
from app.db.models import OrganizationIntegrationModel

logger = logging.getLogger(__name__)


def _derive_fernet_key(secret: str) -> bytes:
  digest = hashlib.sha256(secret.encode("utf-8")).digest()
  return base64.urlsafe_b64encode(digest)


def _resolve_secret() -> str:
  settings = get_settings()
  secret = settings.secret_key or os.getenv("SECRET_KEY")
  if secret and secret.strip():
    return secret.strip()

  raise RuntimeError(
    "SECRET_KEY environment variable is required for application storage and encryption. "
    "Please define SECRET_KEY in your .env or container environment."
  )


def _fernet() -> Fernet:
  return Fernet(_derive_fernet_key(_resolve_secret()))


def save_connection(integration_id: str, payload: dict[str, Any], org_id: str = "default") -> None:
  """Save encrypted connection payload to organization_integrations table."""
  raw = json.dumps(payload, indent=2).encode("utf-8")
  encrypted = _fernet().encrypt(raw)
  cache_key = make_conn_cache_key(org_id, integration_id)
  _CACHE_CONNECTIONS[cache_key] = encrypted

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as db:
      item = db.scalar(
        select(OrganizationIntegrationModel).where(
          OrganizationIntegrationModel.organization_id == org_id,
          OrganizationIntegrationModel.provider == integration_id,
        )
      )
      enc_str = encrypted.decode("ascii")
      if item:
        item.client_secret_ref = enc_str
        item.client_id = payload.get("client_id")
        item.status = "active"
      else:
        new_item = OrganizationIntegrationModel(
          id=str(uuid.uuid4()),
          organization_id=org_id,
          provider=integration_id,
          client_id=payload.get("client_id"),
          client_secret_ref=enc_str,
          status="active",
        )
        db.add(new_item)
      db.commit()
  except Exception as exc:
    logger.error("Failed to persist organization integration to DB: %s", exc)
    raise


def load_connection(integration_id: str, org_id: str = "default") -> dict[str, Any] | None:
  """Load encrypted connection payload from organization_integrations table."""
  cache_key = make_conn_cache_key(org_id, integration_id)
  encrypted: bytes | None = _CACHE_CONNECTIONS.get(cache_key)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as db:
      item = db.scalar(
        select(OrganizationIntegrationModel).where(
          OrganizationIntegrationModel.organization_id == org_id,
          OrganizationIntegrationModel.provider == integration_id,
        )
      )
      if item and item.client_secret_ref:
        encrypted = item.client_secret_ref.encode("ascii")
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
    decrypted = _fernet().decrypt(encrypted)
    return json.loads(decrypted.decode("utf-8"))
  except (InvalidToken, json.JSONDecodeError, OSError) as exc:
    logger.warning("Decryption failed for integration %s: %s", integration_id, exc)
    return None


def delete_connection(integration_id: str, org_id: str = "default") -> bool:
  """Delete connection from organization_integrations table and cache."""
  cache_key = make_conn_cache_key(org_id, integration_id)
  existed = cache_key in _CACHE_CONNECTIONS
  _CACHE_CONNECTIONS.pop(cache_key, None)

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as db:
      item = db.scalar(
        select(OrganizationIntegrationModel).where(
          OrganizationIntegrationModel.organization_id == org_id,
          OrganizationIntegrationModel.provider == integration_id,
        )
      )
      if item:
        db.delete(item)
        db.commit()
        return True
      return existed
  except Exception as exc:
    logger.error("Could not delete connection from DB: %s", exc)
    raise


def connection_exists(integration_id: str, org_id: str = "default") -> bool:
  """Check if connection exists in organization_integrations table or memory."""
  cache_key = make_conn_cache_key(org_id, integration_id)
  if cache_key in _CACHE_CONNECTIONS:
    return True

  try:
    from app.db.database import get_sync_db
    with get_sync_db() as db:
      item = db.scalar(
        select(OrganizationIntegrationModel.id).where(
          OrganizationIntegrationModel.organization_id == org_id,
          OrganizationIntegrationModel.provider == integration_id,
        )
      )
      return item is not None
  except Exception:
    return False

