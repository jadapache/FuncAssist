"""SSE progress stream for transcription jobs (docs/TRANSCRIPTION_PROCESS.md §4, "SSE")."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.features.transcription import progress
from app.features.transcription.jobs import job_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transcription", tags=["transcription"], dependencies=[Depends(get_current_user)])

HEARTBEAT_S = 20.0
SSE_HEADERS = {
  "Cache-Control": "no-cache",
  "Connection": "keep-alive",
  "X-Accel-Buffering": "no",
}


def format_event(snapshot: dict[str, Any], protocol: str) -> str:
  data = json.dumps(snapshot, ensure_ascii=False, default=str)
  if protocol == "v2":
    return f"id: {snapshot.get('seq', 0)}\nevent: progress\ndata: {data}\n\n"
  return f"data: {data}\n\n"


def format_heartbeat(protocol: str) -> str:
  if protocol == "v2":
    return "event: heartbeat\ndata: {}\n\n"
  return 'data: {"event": "heartbeat", "stage": "heartbeat"}\n\n'


async def progress_events(job_id: str, initial: dict[str, Any], protocol: str = "v1") -> AsyncGenerator[str, None]:
  """Current state first, then every update until the job (and its summary) is finished."""
  queue = progress.subscribe(job_id)
  try:
    current = job_manager.snapshot(job_id) or progress.latest(job_id) or initial
    yield format_event(current, protocol)
    if progress.is_stream_finished(current):
      return
    if not job_manager.is_running(job_id):
      return  # stale persisted state: nothing will update it; the client falls back to /status
    last_seq = int(current.get("seq") or 0)
    while True:
      try:
        update = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
      except asyncio.TimeoutError:
        yield format_heartbeat(protocol)
        if not job_manager.is_running(job_id):
          final = progress.latest(job_id)
          if final and int(final.get("seq") or 0) > last_seq:
            yield format_event(final, protocol)
          return
        continue
      seq = int(update.get("seq") or 0)
      if seq and seq <= last_seq:
        continue
      last_seq = seq or last_seq
      yield format_event(update, protocol)
      if progress.is_stream_finished(update):
        return
  finally:
    progress.unsubscribe(job_id, queue)


def stream_response(job_id: str, initial: dict[str, Any], protocol: str) -> StreamingResponse:
  return StreamingResponse(
    progress_events(job_id, initial, "v2" if protocol == "v2" else "v1"),
    media_type="text/event-stream",
    headers=SSE_HEADERS,
  )


@router.get("/progress-stream/{transcription_id}")
async def get_progress_stream(
  transcription_id: str,
  protocol: Optional[str] = Query(default=None),
  last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
  current_user: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
  """Real-time progress. `?protocol=v2` sends named events with ids; otherwise data-only frames (v1)."""
  from app.api.transcription import load_owned_record
  from app.features.transcription.service import job_status

  record = await load_owned_record(transcription_id, current_user)
  if last_event_id:
    logger.debug("SSE reconnect for %s after event %s", transcription_id, last_event_id)
  return stream_response(record["id"], job_status(record), protocol or "v1")
