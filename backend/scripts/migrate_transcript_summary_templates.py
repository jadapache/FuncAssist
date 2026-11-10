"""Database migration script for transcript summary templates.

Updates schema for ai_templates and ai_template_versions (VARCHAR length, tag column),
removes the obsolete 'Resumen de Transcripción y Minutas' default template, and persists
the translated Sum skills/rubrics associated with the 'transcript_summary' tag.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add backend directory to sys.path if run directly
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
  sys.path.insert(0, str(backend_root))

from sqlalchemy import select, text
from app.db.database import get_sync_db
from app.db.models import AITemplateModel
from app.ai.templates import ensure_ai_templates_seeded

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_schema_and_templates() -> None:
  """Apply database migration for transcript summary templates."""
  logger.info("Starting migration of transcript summary templates...")

  with get_sync_db() as db:
    # 1. Update columns in PostgreSQL if necessary
    for alter_sql in [
      "ALTER TABLE ai_templates ALTER COLUMN id TYPE VARCHAR(128);",
      "ALTER TABLE ai_template_versions ALTER COLUMN template_id TYPE VARCHAR(128);",
      "ALTER TABLE ai_templates ADD COLUMN IF NOT EXISTS tag VARCHAR(64);",
      "ALTER TABLE ai_template_versions ADD COLUMN IF NOT EXISTS tag VARCHAR(64);",
    ]:
      try:
        db.execute(text(alter_sql))
        db.commit()
      except Exception as exc:
        logger.debug("Schema migration skipped or not supported (e.g. SQLite): %s", exc)

    # 2. Delete legacy default templates
    legacy_ids = ["prompt:transcript_summary", "rubric:transcript_summary"]
    for legacy_id in legacy_ids:
      item = db.execute(
        select(AITemplateModel).where(AITemplateModel.id == legacy_id)
      ).scalar_one_or_none()
      if item:
        db.delete(item)
        logger.info("Removed legacy template: %s", legacy_id)
    db.commit()

  # 3. Seed new templates
  ensure_ai_templates_seeded()
  logger.info("Migration completed successfully.")


if __name__ == "__main__":
  migrate_schema_and_templates()
