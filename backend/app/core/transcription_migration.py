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


def migrate_transcriptions_if_needed() -> list[str]:
  """Add the job/ownership columns when missing. Returns the columns that were added."""
  added: list[str] = []
  try:
    with get_sync_db() as session:
      bind = session.get_bind()
      dialect = bind.dialect.name
      has_lock = False
      if dialect == "postgresql":
        try:
          session.execute(text(f"SELECT pg_advisory_lock({TRANSCRIPTION_MIGRATION_LOCK_ID});"))
          has_lock = True
        except Exception as lock_exc:
          logger.debug("Advisory lock acquisition skipped or failed: %s", lock_exc)
      try:
        inspector = inspect(bind)
        if not inspector.has_table(TABLE):
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
        if dialect == "postgresql":
          session.execute(text(f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON {TABLE} (user_id);"))
        session.commit()
        if added:
          logger.info("Added columns to %s: %s", TABLE, ", ".join(added))
      finally:
        if has_lock:
          try:
            session.execute(text(f"SELECT pg_advisory_unlock({TRANSCRIPTION_MIGRATION_LOCK_ID});"))
            session.commit()
          except Exception as unlock_exc:
            logger.debug("Advisory unlock failed: %s", unlock_exc)
  except Exception as exc:
    logger.error("Transcription schema migration failed: %s", exc)
    raise RuntimeError(f"Transcription schema migration failed: {exc}") from exc
  return added
