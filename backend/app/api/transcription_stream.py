from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transcription", tags=["transcription-streaming"])

# Global store: transcription_id -> Set of subscriber asyncio.Queue
_PROGRESS_SUBSCRIBERS: Dict[str, set[asyncio.Queue]] = {}
_ACTIVE_STREAMS: Dict[str, int] = {}
_LATEST_PROGRESS: Dict[str, dict[str, Any]] = {}


def register_subscriber(transcription_id: str) -> asyncio.Queue:
  """Create and register a dedicated progress queue for an SSE subscriber."""
  if transcription_id not in _PROGRESS_SUBSCRIBERS:
    _PROGRESS_SUBSCRIBERS[transcription_id] = set()
  q: asyncio.Queue = asyncio.Queue(maxsize=50)
  _PROGRESS_SUBSCRIBERS[transcription_id].add(q)
  return q


def unregister_subscriber(transcription_id: str, q: asyncio.Queue) -> None:
  """Unregister a subscriber queue."""
  if transcription_id in _PROGRESS_SUBSCRIBERS:
    _PROGRESS_SUBSCRIBERS[transcription_id].discard(q)
    if not _PROGRESS_SUBSCRIBERS[transcription_id]:
      del _PROGRESS_SUBSCRIBERS[transcription_id]


def get_or_create_progress_queue(transcription_id: str) -> asyncio.Queue:
  """Get or create progress queue for a transcription (for test compatibility)."""
  return register_subscriber(transcription_id)


async def emit_progress(transcription_id: str, update: Dict[str, Any]) -> None:
  """
  Emit a progress update to all listening clients via SSE.
  Broadcasts the message to all registered subscriber queues.
  """
  try:
    if "timestamp" not in update:
      update["timestamp"] = datetime.now(timezone.utc).isoformat()
    _LATEST_PROGRESS[transcription_id] = update

    subscribers = _PROGRESS_SUBSCRIBERS.get(transcription_id, set()).copy()
    for q in subscribers:
      if q.full():
        try:
          q.get_nowait()
        except asyncio.QueueEmpty:
          pass
      try:
        q.put_nowait(update)
      except Exception:
        pass
    logger.debug(f"Progress emitted: {transcription_id} - {update.get('stage')} {update.get('progress')}% to {len(subscribers)} subscribers")
  except Exception as e:
    logger.warning(f"Failed to emit progress for {transcription_id}: {e}")


_MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
  """Store reference to the main asyncio event loop."""
  global _MAIN_LOOP
  _MAIN_LOOP = loop


def get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
  """Retrieve the active main asyncio event loop."""
  global _MAIN_LOOP
  if _MAIN_LOOP is not None and not _MAIN_LOOP.is_closed():
    return _MAIN_LOOP
  try:
    loop = asyncio.get_running_loop()
    _MAIN_LOOP = loop
    return loop
  except RuntimeError:
    return _MAIN_LOOP


def emit_progress_sync(transcription_id: str, update: Dict[str, Any]) -> None:
  """Synchronous helper that schedules emit_progress in the running event loop if available."""
  if "timestamp" not in update:
    update["timestamp"] = datetime.now(timezone.utc).isoformat()
  _LATEST_PROGRESS[transcription_id] = update

  # If called on a thread with a running loop:
  try:
    loop = asyncio.get_running_loop()
    set_main_loop(loop)
    loop.create_task(emit_progress(transcription_id, update))
    return
  except RuntimeError:
    pass

  # If called from a worker thread (e.g. ThreadPoolExecutor / asyncio.to_thread):
  loop = get_main_loop()
  if loop is not None and not loop.is_closed():
    try:
      asyncio.run_coroutine_threadsafe(emit_progress(transcription_id, update), loop)
      return
    except Exception as exc:
      logger.warning(f"Failed to dispatch emit_progress to main loop: {exc}")


async def _cleanup_queue_after_delay(transcription_id: str, delay_seconds: int = 300) -> None:
  """Clean up cached progress status after delay."""
  await asyncio.sleep(delay_seconds)
  if _ACTIVE_STREAMS.get(transcription_id, 0) == 0:
    if transcription_id in _LATEST_PROGRESS:
      stage = str(_LATEST_PROGRESS[transcription_id].get("stage") or "")
      if stage in {"complete", "failed", "cancelled"}:
        del _LATEST_PROGRESS[transcription_id]
        logger.info(f"Cleaned up progress status cache: {transcription_id}")


async def transcription_progress_stream(transcription_id: str) -> AsyncGenerator[str, None]:
  """
  SSE stream generator for transcription progress.
  Pushes updates in real time and sends a heartbeat every 20 seconds.
  """
  set_main_loop(asyncio.get_running_loop())
  queue = register_subscriber(transcription_id)
  _ACTIVE_STREAMS[transcription_id] = _ACTIVE_STREAMS.get(transcription_id, 0) + 1
  logger.info(f"SSE client connected for {transcription_id} (active: {_ACTIVE_STREAMS[transcription_id]})")

  try:
    # Send initial connection event
    initial_event = {
      "event": "connected",
      "transcription_id": transcription_id,
      "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    yield f"data: {json.dumps(initial_event)}\n\n"

    # If we already have a latest progress status, send it immediately
    if transcription_id in _LATEST_PROGRESS:
      latest = _LATEST_PROGRESS[transcription_id]
      yield f"data: {json.dumps(latest)}\n\n"
      latest_stage = str(latest.get("stage") or latest.get("status") or "")
      if latest_stage in {"complete", "failed", "cancelled"} or latest.get("progress") == 100:
        return

    while True:
      try:
        update = await asyncio.wait_for(queue.get(), timeout=20.0)
        yield f"data: {json.dumps(update)}\n\n"

        # If job has reached a terminal state, close stream gracefully after final message
        stage = str(update.get("stage") or update.get("status") or "")
        if stage in {"complete", "failed", "cancelled"} or update.get("progress") == 100:
          await asyncio.sleep(0.5)
          break
      except asyncio.TimeoutError:
        # Heartbeat ping
        heartbeat = {
          "event": "heartbeat",
          "stage": "heartbeat",
          "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        yield f"data: {json.dumps(heartbeat)}\n\n"

  except asyncio.CancelledError:
    logger.info(f"SSE stream cancelled by client: {transcription_id}")
  except Exception as e:
    logger.error(f"SSE stream error for {transcription_id}: {e}", exc_info=True)
    error_event = {
      "event": "error",
      "stage": "failed",
      "message": str(e),
      "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    yield f"data: {json.dumps(error_event)}\n\n"
  finally:
    unregister_subscriber(transcription_id, queue)
    _ACTIVE_STREAMS[transcription_id] = max(0, _ACTIVE_STREAMS.get(transcription_id, 1) - 1)
    logger.info(f"SSE client disconnected: {transcription_id} (active: {_ACTIVE_STREAMS[transcription_id]})")
    asyncio.create_task(_cleanup_queue_after_delay(transcription_id, delay_seconds=180))


@router.get("/progress-stream/{transcription_id}")
async def get_progress_stream(transcription_id: str):
  """
  Subscribe to real-time progress updates via Server-Sent Events (SSE).
  """
  return StreamingResponse(
    transcription_progress_stream(transcription_id),
    media_type="text/event-stream",
    headers={
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  )
