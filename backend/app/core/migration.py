"""One-time path migration from repo-local/ to OS user data directory.

Safe to call multiple times checks a sentinel file before proceeding.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.core.settings import ROOT_DIR, SETTINGS_DIR, USER_DATA_DIR

logger = logging.getLogger(__name__)

SENTINEL_FILE = SETTINGS_DIR / ".migrated_v2"
OLD_LOCAL_DIR = ROOT_DIR / "local"


def migrate_paths_if_needed() -> None:
  if SENTINEL_FILE.exists():
    return
  if not OLD_LOCAL_DIR.exists():
    SENTINEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    SENTINEL_FILE.write_text("done", encoding="utf-8")
    return

  dirs_to_migrate = [
    "settings",
    "transcriptions",
    "templates",
    "ai",
    "knowledge",
    "connections",
    "history",
  ]
  for d in dirs_to_migrate:
    src = OLD_LOCAL_DIR / d
    dst = USER_DATA_DIR / d
    if src.exists() and not dst.exists():
      try:
        shutil.copytree(src, dst)
      except Exception as exc:
        logger.warning(f"Error copying {src} to {dst}: {exc}")
    elif src.exists() and dst.exists():
      for item in src.glob("**/*"):
        if item.is_file():
          rel = item.relative_to(src)
          target = dst / rel
          if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
              shutil.copy2(item, target)
            except Exception as exc:
              logger.warning(f"Error copying {item} to {target}: {exc}")

  SENTINEL_FILE.parent.mkdir(parents=True, exist_ok=True)
  SENTINEL_FILE.write_text("done", encoding="utf-8")
  logger.info(f"Path migration complete. Data is now at: {USER_DATA_DIR}")
