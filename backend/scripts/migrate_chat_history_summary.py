"""Add rolling conversation summary columns to chat_sessions.

The same migration runs automatically on backend startup; use this script to apply it
ahead of a deploy or in environments where the app does not run the startup hook.

Usage (from backend/):
  python -m scripts.migrate_chat_history_summary            # apply
  python -m scripts.migrate_chat_history_summary --rollback # drop the columns
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
  sys.path.insert(0, str(backend_root))

from app.core.chat_history_migration import (  # noqa: E402
  migrate_chat_history_summary_if_needed,
  rollback_chat_history_summary,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--rollback", action="store_true", help="Drop the summary columns instead of adding them.")
  args = parser.parse_args()

  if args.rollback:
    dropped = rollback_chat_history_summary()
    logger.info("Dropped columns: %s", ", ".join(dropped) or "none")
    return 0

  added = migrate_chat_history_summary_if_needed()
  logger.info("Added columns: %s", ", ".join(added) or "none (already up to date)")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
