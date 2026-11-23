"""Job progress: stage contract, monotonic percentage, measured ETA and the in-process SSE hub.

The hub is per process (one uvicorn worker is assumed, see docs/TRANSCRIPTION_PROCESS.md §7). The
persistent copy of the latest snapshot lives in `transcriptions.progress_json`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# stage -> (start %, end %) of the global progress bar.
STAGE_RANGES: dict[str, tuple[int, int]] = {
  "uploading": (0, 10),
  "queued": (10, 10),
  "preprocessing": (10, 20),
  "transcribing": (20, 80),
  "cleaning": (80, 85),
  "diarizing": (85, 95),
  "saving": (95, 99),
  "complete": (100, 100),
}
TERMINAL_STAGES = {"complete", "failed", "cancelled", "interrupted"}
ACTIVE_STAGES = {"queued", "preprocessing", "transcribing", "cleaning", "diarizing", "saving"}
SUMMARY_OPEN = {"pending", "running"}
# Rough fixed cost of the stages after transcription, added to the ETA.
POST_TRANSCRIPTION_S = 8.0


def format_eta(seconds: Optional[float]) -> Optional[str]:
  if seconds is None:
    return None
  if seconds <= 5:
    return "unos segundos"
  mins, secs = int(seconds // 60), int(seconds % 60)
  return f"~{mins} min {secs} s" if mins else f"~{secs} s"


def stage_to_percent(stage: str, stage_progress: float) -> int:
  start, end = STAGE_RANGES.get(stage, (0, 0))
  return int(round(start + (end - start) * max(0.0, min(1.0, stage_progress))))


def is_stream_finished(snapshot: dict[str, Any]) -> bool:
  stage = snapshot.get("stage")
  if stage not in TERMINAL_STAGES:
    return False
  return not (stage == "complete" and snapshot.get("summary_status") in SUMMARY_OPEN)


# --- hub ---------------------------------------------------------------------------------------

_SUBSCRIBERS: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
_LATEST: dict[str, dict[str, Any]] = {}
_RETENTION_S = 300.0


def subscribe(job_id: str) -> asyncio.Queue[dict[str, Any]]:
  queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
  _SUBSCRIBERS.setdefault(job_id, set()).add(queue)
  return queue


def unsubscribe(job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
  subs = _SUBSCRIBERS.get(job_id)
  if subs is not None:
    subs.discard(queue)
    if not subs:
      _SUBSCRIBERS.pop(job_id, None)


def latest(job_id: str) -> Optional[dict[str, Any]]:
  return _LATEST.get(job_id)


def forget(job_id: str) -> None:
  _LATEST.pop(job_id, None)


def publish(job_id: str, snapshot: dict[str, Any]) -> None:
  """Store the snapshot and fan it out to every SSE subscriber (drops the oldest when full)."""
  _LATEST[job_id] = snapshot
  for queue in list(_SUBSCRIBERS.get(job_id, ())):
    if queue.full():
      try:
        queue.get_nowait()
      except asyncio.QueueEmpty:
        pass
    queue.put_nowait(snapshot)
  if is_stream_finished(snapshot):
    try:
      loop = asyncio.get_running_loop()
    except RuntimeError:
      return
    seq = snapshot.get("seq")

    def _expire() -> None:
      current = _LATEST.get(job_id)
      if current is not None and current.get("seq") == seq and job_id not in _SUBSCRIBERS:
        _LATEST.pop(job_id, None)

    loop.call_later(_RETENTION_S, _expire)


# --- reporter ----------------------------------------------------------------------------------

Persist = Callable[[dict[str, Any]], Awaitable[None]]


class ProgressReporter:
  """Builds contract snapshots for one job, keeps `progress` monotonic and estimates the ETA."""

  PERSIST_EVERY_S = 5.0

  def __init__(
    self,
    job_id: str,
    *,
    media_id: str,
    title: str,
    model_info: str,
    persist: Optional[Persist] = None,
    initial: Optional[dict[str, Any]] = None,
  ) -> None:
    self.job_id = job_id
    self._persist = persist
    self._last_persist = 0.0
    self._last_stage: Optional[str] = None
    base = dict(initial or {})
    self.seq = int(base.get("seq") or 0)
    self.snapshot: dict[str, Any] = {
      "id": job_id,
      "media_id": media_id,
      "title": title,
      "status": "queued",
      "stage": "queued",
      "stage_progress": 0.0,
      "progress": 0,
      "message": "",
      "eta": None,
      "eta_seconds": None,
      "chunks_done": 0,
      "chunks_total": 0,
      "queue_position": None,
      "error": None,
      "error_code": None,
      "retryable": False,
      "summary_status": "pending",
      "model_info": model_info,
      "seq": self.seq,
      "timestamp": None,
      "live_segments": [],
      "preview": None,
    }
    self._audio_total = 0.0
    self._audio_done = 0.0
    self._baseline_done = 0.0
    self._work_started: Optional[float] = None

  # ETA: throughput of the transcription stage (audio seconds per wall second).
  def set_audio_work(self, total_audio_s: float, already_done_s: float = 0.0) -> None:
    self._audio_total = max(0.0, total_audio_s)
    self._audio_done = max(0.0, already_done_s)
    self._baseline_done = self._audio_done
    self._work_started = time.monotonic()

  def add_audio_done(self, audio_s: float) -> None:
    self._audio_done = min(self._audio_total, self._audio_done + audio_s)

  @property
  def audio_fraction(self) -> float:
    return self._audio_done / self._audio_total if self._audio_total else 0.0

  def _eta_seconds(self, stage: str) -> Optional[float]:
    if stage in TERMINAL_STAGES:
      return 0.0
    if stage in {"cleaning", "diarizing", "saving"}:
      return POST_TRANSCRIPTION_S
    if stage != "transcribing" or self._work_started is None:
      return None
    measured = self._audio_done - self._baseline_done
    elapsed = time.monotonic() - self._work_started
    if measured <= 0 or elapsed <= 0:
      return None
    rate = measured / elapsed
    return (self._audio_total - self._audio_done) / rate + POST_TRANSCRIPTION_S

  async def update(self, stage: str, stage_progress: float = 0.0, message: Optional[str] = None, **fields: Any) -> dict[str, Any]:
    snap = self.snapshot
    if stage in STAGE_RANGES:
      snap["progress"] = max(int(snap.get("progress") or 0), stage_to_percent(stage, stage_progress))
    snap["stage"] = stage
    snap["status"] = stage
    snap["stage_progress"] = round(max(0.0, min(1.0, stage_progress)), 3)
    if message is not None:
      snap["message"] = message
    snap.update(fields)
    eta = self._eta_seconds(stage)
    snap["eta_seconds"] = None if eta is None else round(eta)
    snap["eta"] = format_eta(eta)
    self.seq += 1
    snap["seq"] = self.seq
    snap["timestamp"] = datetime.now(timezone.utc).isoformat()
    frozen = dict(snap)
    publish(self.job_id, frozen)
    await self._maybe_persist(frozen, force=stage != self._last_stage or stage in TERMINAL_STAGES)
    self._last_stage = stage
    return frozen

  async def _maybe_persist(self, snapshot: dict[str, Any], force: bool) -> None:
    if not self._persist:
      return
    now = time.monotonic()
    if not force and now - self._last_persist < self.PERSIST_EVERY_S:
      return
    self._last_persist = now
    try:
      await self._persist(snapshot)
    except Exception as exc:  # progress persistence must never break the job
      logger.warning("Could not persist progress for %s: %s", self.job_id, exc, exc_info=True)
