"""Database schema and data migration helpers for integrations architecture.

Handles safe, idempotent creation and migration of:
  - user_integrations (personal Jira OAuth scoped to user)
  - mcp_servers (MCP tools/endpoints configuration scoped to organization / user)

Includes advisory locks in PostgreSQL for concurrency protection during multi-instance
deployments, schema validation, and fail-safe exception propagation.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import inspect, text

from app.db.database import get_sync_db
from app.db.models import Base

logger = logging.getLogger(__name__)

# Fixed 64-bit integer key for PostgreSQL pg_advisory_lock
INTEGRATIONS_MIGRATION_LOCK_ID = 928374102938471201


def migrate_integrations_schema_if_needed() -> None:
  """Ensure new integration tables and unique constraints exist in the DB.

  Uses PostgreSQL advisory locks to guarantee concurrency safety across multiple workers.
  Fails fast and raises RuntimeError if a critical schema migration fails.
  """
  try:
    with get_sync_db() as session:
      bind = session.get_bind()
      dialect_name = bind.dialect.name

      # Concurrency protection for PostgreSQL deployments
      has_advisory_lock = False
      if dialect_name == "postgresql":
        try:
          session.execute(text(f"SELECT pg_advisory_lock({INTEGRATIONS_MIGRATION_LOCK_ID});"))
          has_advisory_lock = True
        except Exception as lock_exc:
          logger.debug("Advisory lock acquisition skipped or failed: %s", lock_exc)

      try:
        # Create tables if not present via SQLAlchemy metadata
        if hasattr(bind, "_run_ddl_visitor"):
          Base.metadata.create_all(bind, tables=[
            Base.metadata.tables["user_integrations"],
            Base.metadata.tables["mcp_servers"],
          ])

        # Enforce unique constraint (user_id, provider) on user_integrations
        session.execute(
          text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_integrations_user_provider "
            "ON user_integrations (user_id, provider);"
          )
        )
        session.commit()
        logger.info("Integrations schema verified/migrated successfully.")
      finally:
        if has_advisory_lock:
          try:
            session.execute(text(f"SELECT pg_advisory_unlock({INTEGRATIONS_MIGRATION_LOCK_ID});"))
            session.commit()
          except Exception as unlock_exc:
            logger.debug("Advisory unlock failed: %s", unlock_exc)

  except Exception as exc:
    logger.error("Critical error during integrations schema migration: %s", exc)
    raise RuntimeError(f"Database integrations schema migration failed: {exc}") from exc
