"""Idempotent schema migration: rolling conversation summary columns on chat_sessions.

Adds:
  - chat_sessions.history_summary            TEXT         NULL
  - chat_sessions.history_summary_key        VARCHAR(80)  NULL
  - chat_sessions.history_summary_updated_at TIMESTAMPTZ  NULL

`Base.metadata.create_all` only creates missing tables; it never adds columns to existing
ones, so environments created before this change need this migration. It runs on startup
(see app/main.py) and can be run manually: `python -m scripts.migrate_chat_history_summary`.

Safe to run repeatedly and concurrently (PostgreSQL advisory lock + IF NOT EXISTS).
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.db.database import get_sync_db

logger = logging.getLogger(__name__)

CHAT_HISTORY_MIGRATION_LOCK_ID = 928374102938471305
TABLE = "chat_sessions"

# column name -> (PostgreSQL type, generic SQL type for other dialects)
COLUMNS: dict[str, tuple[str, str]] = {
  "history_summary": ("TEXT", "TEXT"),
  "history_summary_key": ("VARCHAR(80)", "VARCHAR(80)"),
  "history_summary_updated_at": ("TIMESTAMP WITH TIME ZONE", "TIMESTAMP"),
}


def migrate_chat_history_summary_if_needed() -> list[str]:
  """Add the summary columns when missing. Returns the columns that were added.

  Raises RuntimeError on failure so a broken schema is not silently served.
  """
  added: list[str] = []
  try:
    with get_sync_db() as session:
      bind = session.get_bind()
      dialect = bind.dialect.name

      has_lock = False
      if dialect == "postgresql":
        try:
          session.execute(text(f"SELECT pg_advisory_xact_lock({CHAT_HISTORY_MIGRATION_LOCK_ID});"))
          has_lock = True
        except Exception as lock_exc:
          logger.debug("Advisory lock acquisition skipped or failed: %s", lock_exc)

      try:
        inspector = inspect(bind)
        if not inspector.has_table(TABLE):
          # Fresh database: create_all will create the table with the new columns.
          logger.info("Table %s does not exist yet; nothing to migrate.", TABLE)
          return added

        existing = {col["name"] for col in inspector.get_columns(TABLE)}
        for name, (pg_type, generic_type) in COLUMNS.items():
          if name in existing:
            continue
          if dialect == "postgresql":
            session.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {name} {pg_type};"))
          else:
            session.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {generic_type};"))
          added.append(name)

        session.commit()
        if added:
          logger.info("Added columns to %s: %s", TABLE, ", ".join(added))
        else:
          logger.info("Chat history summary schema already up to date.")
      finally:
        # The transaction lock is released by this transaction's commit/rollback. A session lock leaked
        # here: after commit, the unlock could run on another pooled connection and never release it.
        if has_lock:
          session.rollback()  # no-op after commit; releases the lock on early-exit paths
  except Exception as exc:
    logger.error("Chat history summary migration failed: %s", exc)
    raise RuntimeError(f"Chat history summary migration failed: {exc}") from exc

  return added


def rollback_chat_history_summary() -> list[str]:
  """Drop the summary columns (manual rollback only; summaries are regenerable caches)."""
  dropped: list[str] = []
  with get_sync_db() as session:
    bind = session.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(TABLE):
      return dropped
    existing = {col["name"] for col in inspector.get_columns(TABLE)}
    for name in COLUMNS:
      if name in existing:
        session.execute(text(f"ALTER TABLE {TABLE} DROP COLUMN {name};"))
        dropped.append(name)
    session.commit()
  return dropped
