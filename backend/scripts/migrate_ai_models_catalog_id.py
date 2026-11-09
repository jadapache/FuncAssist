"""Database migration script for ai_models_catalog schema.

Enforces VARCHAR(128) column length for ai_models_catalog id field.
Run once: python -m scripts.migrate_ai_models_catalog_id
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add backend directory to sys.path if run directly
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
  sys.path.insert(0, str(backend_root))

from sqlalchemy import text
from app.db.database import get_sync_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_ai_models_catalog() -> None:
  """Apply database migration for ai_models_catalog table."""
  logger.info("Starting migration for ai_models_catalog id column...")
  with get_sync_db() as db:
    try:
      db.execute(text("ALTER TABLE ai_models_catalog ALTER COLUMN id TYPE VARCHAR(128);"))
      db.commit()
      logger.info("Successfully altered ai_models_catalog id column to VARCHAR(128).")
    except Exception as exc:
      logger.debug("Migration skipped or not supported (e.g. SQLite): %s", exc)
  logger.info("Migration completed.")


if __name__ == "__main__":
  migrate_ai_models_catalog()
