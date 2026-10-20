"""Background worker for periodic model catalog integrity and synchronization.

Template indexing and filesystem scans have been eliminated as templates,
transcriptions, and AI model catalogs are managed and persisted directly
in PostgreSQL entities.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 60
FRONTIER_SYNC_INTERVAL_SECONDS = 3600  # 1 hour
_last_frontier_sync_ts: float = 0.0


async def _refresh_builtin_model_catalog() -> None:
  """Verify that builtin models catalog reflects actual files on disk."""
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


async def _refresh_frontier_models_catalog(force: bool = False) -> None:
  """Sync frontier model specs and pricing from LiteLLM into PostgreSQL."""
  global _last_frontier_sync_ts
  import time

  now = time.monotonic()
  if not force and (now - _last_frontier_sync_ts) < FRONTIER_SYNC_INTERVAL_SECONDS:
    return

  try:
    from app.ai.frontier_sync import sync_frontier_models_catalog

    _last_frontier_sync_ts = now
    res = await sync_frontier_models_catalog(force_remote=force)
    logger.debug(
      f"Frontier models catalog background sync completed: {res.get('status')} ({res.get('models_count')} models)"
    )
  except Exception as e:
    logger.debug(f"frontier model catalog background sync skipped: {e}")


async def run_index_refresher() -> None:
  """Infinite background loop. Start with asyncio.create_task() in lifespan."""
  logger.info(f"Background catalog refresher started (interval: {REFRESH_INTERVAL_SECONDS}s)")

  # Initial non-blocking frontier sync shortly after server boot
  async def _initial_frontier_boot_sync():
    await asyncio.sleep(3)
    await _refresh_frontier_models_catalog(force=False)

  asyncio.create_task(_initial_frontier_boot_sync())

  while True:
    try:
      await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
      await _refresh_builtin_model_catalog()
      await _refresh_frontier_models_catalog(force=False)
    except asyncio.CancelledError:
      break
    except Exception as exc:
      logger.debug(f"Index refresher iteration error: {exc}")
