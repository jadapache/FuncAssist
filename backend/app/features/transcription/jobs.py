"""Job lifecycle: queueing, concurrency limit, cancellation, summaries, recovery after restarts."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.features.transcription import config, metrics, records, storage
from app.features.transcription.errors import TranscriptionJobError, classify_exception
from app.features.transcription.pipeline import JobOptions, TranscriptionPipeline
from app.features.transcription.progress import ACTIVE_STAGES, ProgressReporter, latest, publish

logger = logging.getLogger(__name__)

MAINTENANCE_INTERVAL_S = 3600


class JobManager:
  def __init__(self) -> None:
    self._tasks: dict[str, asyncio.Task[None]] = {}
    self._reporters: dict[str, ProgressReporter] = {}
    self._queue: list[str] = []
    self._semaphore: Optional[asyncio.Semaphore] = None
    self._shutting_down = False
    self._maintenance: Optional[asyncio.Task[None]] = None

  def _sem(self) -> asyncio.Semaphore:
    if self._semaphore is None:
      self._semaphore = asyncio.Semaphore(config.max_concurrent_jobs())
    return self._semaphore

  def is_running(self, job_id: str) -> bool:
    task = self._tasks.get(job_id)
    return task is not None and not task.done()

  def snapshot(self, job_id: str) -> Optional[dict[str, Any]]:
    reporter = self._reporters.get(job_id)
    return dict(reporter.snapshot) if reporter else latest(job_id)

  # --- start -----------------------------------------------------------------------------------

  async def start(
    self,
    job_id: str,
    user_id: Optional[str],
    options: JobOptions,
    *,
    title: str,
    model_info: str = "Whisper",
    previous: Optional[dict[str, Any]] = None,
  ) -> dict[str, Any]:
    if self.is_running(job_id):
      raise TranscriptionJobError("bad_request", "La transcripción ya está en curso.")
    # Keep `seq` growing across retries so clients deduplicating by seq never drop new events.
    previous = latest(job_id) or previous
    reporter = ProgressReporter(
      job_id,
      media_id=job_id,
      title=title,
      model_info=model_info,
      persist=lambda snap: records.save_progress(job_id, snap),
      initial=previous,
    )
    self._reporters[job_id] = reporter
    self._queue.append(job_id)
    snapshot = await reporter.update("queued", 0.0, "En cola…", queue_position=self._position(job_id), error=None, error_code=None, retryable=False)
    await records.save_progress(job_id, snapshot, started=True)
    task = asyncio.create_task(self._run(job_id, user_id, options, reporter), name=f"transcription:{job_id}")
    self._tasks[job_id] = task
    task.add_done_callback(lambda _t: self._tasks.pop(job_id, None))
    return snapshot

  def _position(self, job_id: str) -> Optional[int]:
    return self._queue.index(job_id) + 1 if job_id in self._queue else None

  async def _refresh_queue_positions(self) -> None:
    for queued in list(self._queue):
      reporter = self._reporters.get(queued)
      if reporter and reporter.snapshot.get("stage") == "queued":
        await reporter.update("queued", 0.0, "En cola…", queue_position=self._position(queued))

  # --- run -------------------------------------------------------------------------------------

  def _dequeue(self, job_id: str) -> None:
    if job_id in self._queue:
      self._queue.remove(job_id)

  async def _leave_queue(self, job_id: str, reporter: ProgressReporter) -> None:
    self._dequeue(job_id)
    await self._refresh_queue_positions()
    reporter.snapshot["queue_position"] = None

  async def _complete(self, job_id: str, user_id: Optional[str], options: JobOptions, reporter: ProgressReporter, record: dict[str, Any]) -> None:
    clear_error = {"error": None, "error_code": None, "retryable": False}
    done = await reporter.update("complete", 1.0, "Transcripción completada.", summary_status=record.get("summary_status"), **clear_error)
    await records.save_progress(job_id, done, finished=True)
    if options.summarize:
      await self._summarize(job_id, user_id, reporter, record)

  async def _abandon_summary(self, job_id: str, reporter: ProgressReporter) -> None:
    """Cancelled while summarising: the transcript is kept, only the summary is abandoned."""
    await records.update_record(job_id, lambda r: r.update(summary_status="skipped"))
    await reporter.update("complete", 1.0, "Transcripción completada; resumen cancelado.", summary_status="skipped")

  async def _run(self, job_id: str, user_id: Optional[str], options: JobOptions, reporter: ProgressReporter) -> None:
    started = time.monotonic()
    pipeline = TranscriptionPipeline(job_id, user_id, options, reporter)
    status = "failed"
    error: Optional[TranscriptionJobError] = None
    try:
      async with self._sem():
        await self._leave_queue(job_id, reporter)
        result = await pipeline.run()
      status = "complete"
      await self._complete(job_id, user_id, options, reporter, result.record)
    except asyncio.CancelledError:
      if status == "complete":
        await self._abandon_summary(job_id, reporter)
        return
      status = "interrupted" if self._shutting_down else "cancelled"
      error = TranscriptionJobError(status)
      await self._finish_failed(job_id, reporter, error, status)
      if status == "cancelled":
        storage.delete_chunks(job_id)
    except Exception as exc:
      error = classify_exception(exc)
      logger.error(
        "Transcription job %s failed (%s): %s", job_id, error.code, error.detail or error.user_message,
        exc_info=error.code == "internal",
      )
      await self._finish_failed(job_id, reporter, error, "failed")
    finally:
      self._dequeue(job_id)
      self._reporters.pop(job_id, None)
      pipeline.metrics["stage_ms"]["total"] = int((time.monotonic() - started) * 1000)
      await metrics.log_job({
        "transcription_id": job_id,
        "user_id": user_id,
        "status": status,
        "error_code": error.code if error else None,
        **pipeline.metrics,
      })

  async def _finish_failed(self, job_id: str, reporter: ProgressReporter, error: TranscriptionJobError, stage: str) -> None:
    try:
      snapshot = await reporter.update(
        stage,
        0.0,
        error.user_message,
        error=error.user_message,
        error_code=error.code,
        retryable=error.retryable,
        eta=None,
        eta_seconds=None,
      )

      def _mark(record: dict[str, Any]) -> None:
        record.update({
          "status": stage,
          "error": error.user_message,
          "error_code": error.code,
          "retryable": error.retryable,
          "progress": snapshot,
        })

      await records.update_record(job_id, _mark)
      await records.save_progress(job_id, snapshot, finished=True)
    except Exception as exc:
      logger.warning("Could not record failure of transcription %s: %s", job_id, exc, exc_info=True)

  async def _summarize(self, job_id: str, user_id: Optional[str], reporter: ProgressReporter, record: dict[str, Any]) -> None:
    from app.features.transcription.summarizer import summarize_transcript

    await reporter.update("complete", 1.0, "Generando resumen…", summary_status="running")
    try:
      summary = await summarize_transcript(
        record.get("segments") or [],
        title=(record.get("metadata") or {}).get("title") or "Reunión",
        user_id=user_id,
      )
      payload = summary.model_dump()
      await records.update_record(job_id, lambda r: r.update(summary=payload, summary_status="done", summary_error=None))
      await reporter.update("complete", 1.0, "Transcripción y resumen completados.", summary_status="done")
    except asyncio.CancelledError:
      raise
    except Exception as exc:
      message = getattr(exc, "detail", None) or str(exc)
      logger.warning("Automatic summary failed for %s: %s", job_id, message)
      await records.update_record(job_id, lambda r: r.update(summary_status="failed", summary_error=str(message)[:500]))
      await reporter.update("complete", 1.0, "Transcripción completada; el resumen no se pudo generar.", summary_status="failed")
    finally:
      await records.save_progress(job_id, dict(reporter.snapshot), finished=True)

  # --- cancel ----------------------------------------------------------------------------------

  async def cancel(self, job_id: str) -> bool:
    task = self._tasks.get(job_id)
    if task is not None and not task.done():
      task.cancel()
      return True
    # Not running in this process (stale state): mark it cancelled directly.
    error = TranscriptionJobError("cancelled")
    snapshot = dict(latest(job_id) or {"id": job_id, "media_id": job_id})
    snapshot["stage"] = snapshot["status"] = snapshot["error_code"] = "cancelled"
    snapshot["message"] = snapshot["error"] = error.user_message
    snapshot["retryable"] = False
    publish(job_id, snapshot)
    updated = await records.update_record(job_id, lambda r: r.update(status="cancelled", error=error.user_message, error_code="cancelled", progress=snapshot))
    return updated is not None

  # --- recovery / maintenance ------------------------------------------------------------------

  async def _mark_interrupted(self, record: dict[str, Any], error: TranscriptionJobError) -> None:
    job_id = record["id"]
    title = (record.get("metadata") or {}).get("title")
    snapshot = dict(record.get("progress") or {"id": job_id, "media_id": job_id, "title": title})
    snapshot["stage"] = snapshot["status"] = "interrupted"
    snapshot["message"] = snapshot["error"] = error.user_message
    snapshot["error_code"] = "interrupted"
    snapshot["retryable"] = True
    snapshot["eta"] = snapshot["eta_seconds"] = None
    try:
      await records.update_record(job_id, lambda r: r.update(
        status="interrupted", error=error.user_message, error_code="interrupted", retryable=True, progress=snapshot,
      ))
    except Exception as exc:
      logger.warning("Could not mark transcription %s as interrupted: %s", job_id, exc)

  async def recover_interrupted_jobs(self) -> int:
    """Jobs left in an active stage by a previous process can never finish: mark them interrupted."""
    try:
      stale = await records.list_by_status(ACTIVE_STAGES | {"pending", "processing"})
    except Exception as exc:
      logger.warning("Could not look for interrupted transcriptions: %s", exc)
      return 0
    error = TranscriptionJobError("interrupted")
    for record in stale:
      await self._mark_interrupted(record, error)
    if stale:
      logger.info("Marked %d transcription job(s) as interrupted", len(stale))
    await self._recover_open_summaries()
    return len(stale)

  async def _recover_open_summaries(self) -> None:
    """A summary that was pending/running when the process stopped will never finish."""
    try:
      completed = await records.list_by_status({"complete"})
    except Exception as exc:
      logger.warning("Could not look for interrupted summaries: %s", exc)
      return
    for record in completed:
      if record.get("summary_status") not in {"pending", "running"}:
        continue
      try:
        await records.update_record(record["id"], lambda r: r.update(
          summary_status="failed", summary_error="El resumen se interrumpió por un reinicio del servidor.",
        ))
      except Exception as exc:
        logger.warning("Could not reset summary state of %s: %s", record["id"], exc)

  def start_maintenance(self) -> None:
    if config.media_ttl_days() and self._maintenance is None:
      self._maintenance = asyncio.create_task(self._maintenance_loop(), name="transcription-media-ttl")

  async def _maintenance_loop(self) -> None:
    while True:
      try:
        await self.expire_old_media()
      except Exception as exc:
        logger.warning("Transcription media cleanup failed: %s", exc)
      await asyncio.sleep(MAINTENANCE_INTERVAL_S)

  async def expire_old_media(self) -> int:
    """Delete the audio of completed transcriptions older than TRANSCRIPTION_MEDIA_TTL_DAYS (records stay)."""
    ttl = config.media_ttl_days()
    if not ttl:
      return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl)
    candidates = [record["id"] for record in await records.list_by_status({"complete"}) if _is_older(record, cutoff)]
    expired = [job_id for job_id in candidates if storage.get_transcription_dir(job_id).exists()]
    for job_id in expired:
      storage.delete_folder(job_id)
    return len(expired)

  async def shutdown(self) -> None:
    self._shutting_down = True
    if self._maintenance:
      self._maintenance.cancel()
    tasks = [t for t in self._tasks.values() if not t.done()]
    for task in tasks:
      task.cancel()
    if tasks:
      await asyncio.gather(*tasks, return_exceptions=True)


def _is_older(record: dict[str, Any], cutoff: datetime) -> bool:
  finished = _finished_at(record)
  return finished is not None and finished < cutoff


def _finished_at(record: dict[str, Any]) -> Optional[datetime]:
  """When the job finished (else when it was created), as an aware datetime; None when unparseable."""
  finished = record.get("finished_at") or record.get("created_at")
  try:
    when = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
  except ValueError:
    return None
  return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


job_manager = JobManager()
