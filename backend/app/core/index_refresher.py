"""
Background task that periodically regenerates index JSON files from the filesystem
to guard against stale state after crashes, external edits, or model downloads.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 60


async def _refresh_templates_index() -> None:
  """Rebuild templates_index.json by scanning templates/ directory."""
  try:
    from app.core.template_storage import (
      INDEX_FILE,
      TEMPLATES_DIR,
      _load_index,
      _save_index,
    )

    if not TEMPLATES_DIR.exists():
      return

    disk_files = {
      f.stem: f
      for f in TEMPLATES_DIR.iterdir()
      if f.is_file() and not f.name.endswith(".content.md")
    }
    current_index = {item["id"]: item for item in _load_index()}

    changed = False
    for file_id, file_path in disk_files.items():
      if file_id not in current_index:
        logger.warning(f"Found unregistered template file on disk: {file_path}")
        changed = True

    # Remove index entries whose files no longer exist
    to_remove = [fid for fid in current_index if fid not in disk_files]
    if to_remove:
      for fid in to_remove:
        logger.info(f"Removing stale template index entry: {fid}")
      new_index = [v for k, v in current_index.items() if k not in to_remove]
      _save_index(new_index)
      changed = True

    if changed:
      logger.info("templates_index.json refreshed")
  except Exception as e:
    logger.debug(f"templates index refresh skipped: {e}")


async def _refresh_builtin_model_catalog() -> None:
  """Verify that builtin_models_catalog.json reflects actual files on disk."""
  try:
    from app.ai.builtin_local import get_builtin_cache_dir, load_builtin_catalog

    catalog = load_builtin_catalog(task_type=None)
    cache_dir = get_builtin_cache_dir()

    for model_id, meta in catalog.items():
      filename = meta.get("filename")
      if not filename:
        continue
      target = cache_dir / filename
      if not target.exists():
        logger.debug(f"Builtin model not on disk: {model_id}")
  except Exception as e:
    logger.debug(f"builtin model catalog check skipped: {e}")


async def _refresh_transcription_index() -> None:
  """
  Scan transcriptions/ directory in Documents and rebuild transcriptions_index.json
  in the OS user data path.
  """
  try:
    from app.features.transcription.storage import (
      TRANSCRIPTIONS_DIR,
      list_transcriptions,
    )

    if not TRANSCRIPTIONS_DIR.exists():
      return
    list_transcriptions()
  except Exception as e:
    logger.debug(f"transcription index refresh skipped: {e}")


FRONTIER_SYNC_INTERVAL_SECONDS = 3600  # 1 hour
_last_frontier_sync_ts: float = 0.0


async def _refresh_frontier_models_catalog(force: bool = False) -> None:
  """Sync frontier model specs and pricing from LiteLLM in the background."""
  global _last_frontier_sync_ts
  import time

  now = time.monotonic()
  if not force and (now - _last_frontier_sync_ts) < FRONTIER_SYNC_INTERVAL_SECONDS:
    return

  try:
    from app.ai.frontier_sync import sync_frontier_models_catalog

    _last_frontier_sync_ts = now
    res = await sync_frontier_models_catalog(force_remote=force)
    logger.debug(f"Frontier models catalog background sync completed: {res.get('status')} ({res.get('models_count')} models)")
  except Exception as e:
    logger.debug(f"frontier model catalog background sync skipped: {e}")


async def run_index_refresher() -> None:
  """Infinite background loop. Start with asyncio.create_task() in lifespan."""
  logger.info(f"Index refresher started (interval: {REFRESH_INTERVAL_SECONDS}s)")
  
  # Initial non-blocking frontier sync shortly after server boot
  async def _initial_frontier_boot_sync():
    await asyncio.sleep(3)
    await _refresh_frontier_models_catalog(force=False)

  asyncio.create_task(_initial_frontier_boot_sync())

  while True:
    try:
      await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
      await _refresh_templates_index()
      await _refresh_builtin_model_catalog()
      await _refresh_transcription_index()
      await _refresh_frontier_models_catalog(force=False)
    except asyncio.CancelledError:
      break
    except Exception as exc:
      logger.debug(f"Index refresher iteration error: {exc}")
