"""Idempotent schema migration: job and ownership columns on `transcriptions`.

Adds:
  - transcriptions.user_id        VARCHAR(64)  NULL  (+ index)
  - transcriptions.progress_json  TEXT         NULL
  - transcriptions.error_code     VARCHAR(40)  NULL
  - transcriptions.started_at     TIMESTAMPTZ  NULL
  - transcriptions.finished_at    TIMESTAMPTZ  NULL

Existing rows keep `user_id` NULL and are visible to nobody until assigned with
`python -m scripts.assign_transcriptions_owner --user <id>`. Runs on startup (app/main.py).
Safe to run repeatedly and concurrently (PostgreSQL advisory lock + IF NOT EXISTS).
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.db.database import get_sync_db

logger = logging.getLogger(__name__)

TRANSCRIPTION_MIGRATION_LOCK_ID = 928374102938471306
TABLE = "transcriptions"

COLUMNS: dict[str, tuple[str, str]] = {
  "user_id": ("VARCHAR(64)", "VARCHAR(64)"),
  "progress_json": ("TEXT", "TEXT"),
  "error_code": ("VARCHAR(40)", "VARCHAR(40)"),
  "started_at": ("TIMESTAMP WITH TIME ZONE", "TIMESTAMP"),
  "finished_at": ("TIMESTAMP WITH TIME ZONE", "TIMESTAMP"),
}
INDEX_NAME = "ix_transcriptions_user_id"


def _take_lock(session, dialect: str) -> bool:
  """PostgreSQL transaction advisory lock, so concurrent starts do not migrate at once."""
  if dialect != "postgresql":
    return False
  try:
    session.execute(text(f"SELECT pg_advisory_xact_lock({TRANSCRIPTION_MIGRATION_LOCK_ID});"))
    return True
  except Exception as lock_exc:
    logger.debug("Advisory lock acquisition skipped or failed: %s", lock_exc)
    return False


def _add_column(session, dialect: str, name: str, pg_type: str, generic_type: str) -> None:
  if dialect == "postgresql":
    session.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {name} {pg_type};"))
  else:
    session.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {generic_type};"))


def _add_missing(session, bind, dialect: str) -> list[str]:
  inspector = inspect(bind)
  if not inspector.has_table(TABLE):
    logger.info("Table %s does not exist yet; nothing to migrate.", TABLE)
    return []
  existing = {col["name"] for col in inspector.get_columns(TABLE)}
  added = [name for name in COLUMNS if name not in existing]
  for name in added:
    _add_column(session, dialect, name, *COLUMNS[name])
  if dialect == "postgresql":
    session.execute(text(f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON {TABLE} (user_id);"))
  session.commit()
  if added:
    logger.info("Added columns to %s: %s", TABLE, ", ".join(added))
  return added


def migrate_transcriptions_if_needed() -> list[str]:
  """Add the job/ownership columns when missing. Returns the columns that were added."""
  added: list[str] = []
  try:
    with get_sync_db() as session:
      bind = session.get_bind()
      dialect = bind.dialect.name
      has_lock = _take_lock(session, dialect)
      try:
        added = _add_missing(session, bind, dialect)
      finally:
        # The transaction lock is released by this transaction's commit/rollback. A session lock leaked
        # here: after commit, the unlock could run on another pooled connection and never release it.
        if has_lock:
          session.rollback()  # no-op after commit; releases the lock on the early-return path
  except Exception as exc:
    logger.error("Transcription schema migration failed: %s", exc)
    raise RuntimeError(f"Transcription schema migration failed: {exc}") from exc
  return added
