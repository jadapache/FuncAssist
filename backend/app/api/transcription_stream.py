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

# Global store: transcription_id -> asyncio.Queue of progress updates
_PROGRESS_QUEUES: Dict[str, asyncio.Queue] = {}
_ACTIVE_STREAMS: Dict[str, int] = {}
_LATEST_PROGRESS: Dict[str, dict[str, Any]] = {}


def get_or_create_progress_queue(transcription_id: str) -> asyncio.Queue:
  """Get or create progress queue for a transcription (max 50 pending updates)."""
  if transcription_id not in _PROGRESS_QUEUES:
    _PROGRESS_QUEUES[transcription_id] = asyncio.Queue(maxsize=50)
  return _PROGRESS_QUEUES[transcription_id]


async def emit_progress(transcription_id: str, update: Dict[str, Any]) -> None:
  """
  Emit a progress update to all listening clients via SSE.
  """
  try:
    queue = get_or_create_progress_queue(transcription_id)
    if "timestamp" not in update:
      update["timestamp"] = datetime.now(timezone.utc).isoformat()
    _LATEST_PROGRESS[transcription_id] = update

    # If queue is full, drain one old item to make room for latest update
    if queue.full():
      try:
        queue.get_nowait()
      except asyncio.QueueEmpty:
        pass

    queue.put_nowait(update)
    logger.debug(f"Progress emitted: {transcription_id} - {update.get('stage')} {update.get('progress')}%")
  except Exception as e:
    logger.warning(f"Failed to emit progress for {transcription_id}: {e}")


def emit_progress_sync(transcription_id: str, update: Dict[str, Any]) -> None:
  """Synchronous helper that schedules emit_progress in the running event loop if available."""
  try:
    loop = asyncio.get_running_loop()
    loop.create_task(emit_progress(transcription_id, update))
  except RuntimeError:
    pass


async def _cleanup_queue_after_delay(transcription_id: str, delay_seconds: int = 300) -> None:
  """Remove queue after delay if no clients are connected."""
  await asyncio.sleep(delay_seconds)
  if _ACTIVE_STREAMS.get(transcription_id, 0) == 0:
    if transcription_id in _PROGRESS_QUEUES:
      del _PROGRESS_QUEUES[transcription_id]
      logger.info(f"Cleaned up progress queue: {transcription_id}")


async def transcription_progress_stream(transcription_id: str) -> AsyncGenerator[str, None]:
  """
  SSE stream generator for transcription progress.
  Pushes updates in real time and sends a heartbeat every 20 seconds.
  """
  queue = get_or_create_progress_queue(transcription_id)
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
