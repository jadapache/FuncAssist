"""Job lifecycle: cancellation, recovery after restarts, summaries, media expiry and the run loop."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.features.transcription import jobs
from app.features.transcription.errors import TranscriptionJobError
from app.features.transcription.jobs import JobManager
from app.features.transcription.pipeline import JobOptions
from app.features.transcription.progress import ACTIVE_STAGES


class FakeRecords:
  """In-memory stand-in for the records module."""

  def __init__(self):
    self.store, self.progress, self.fail_update, self.fail_list = {}, [], set(), set()
    self.listed = []

  async def list_by_status(self, statuses):
    self.listed.append(set(statuses))
    key = frozenset(statuses)
    if any(f <= key or f == key for f in self.fail_list):
      raise RuntimeError("db down")
    return [dict(r) for r in self.store.values() if r.get("status") in statuses]

  async def update_record(self, job_id, mutate):
    if job_id in self.fail_update:
      raise RuntimeError("cannot write")
    record = self.store.get(job_id)
    if record is None:
      return None
    mutate(record)
    return record

  async def save_progress(self, job_id, snapshot, **flags):
    self.progress.append((job_id, dict(snapshot), flags))


@pytest.fixture
def records(monkeypatch):
  fake = FakeRecords()
  for name in ("list_by_status", "update_record", "save_progress"):
    monkeypatch.setattr(jobs.records, name, getattr(fake, name))
  return fake


# --- recovery -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interrupted_jobs_are_marked_with_their_previous_progress(records):
  records.store = {
    "a": {"id": "a", "status": "transcribing", "progress": {"id": "a", "title": "Uno", "percent": 40}},
    "b": {"id": "b", "status": "pending", "metadata": {"title": "Dos"}},
    "c": {"id": "c", "status": "complete", "summary_status": "done"},
  }
  assert await JobManager().recover_interrupted_jobs() == 2
  assert records.listed[0] == ACTIVE_STAGES | {"pending", "processing"}
  a, b = records.store["a"], records.store["b"]
  assert (a["status"], a["error_code"], a["retryable"]) == ("interrupted", "interrupted", True)
  assert a["error"] == TranscriptionJobError("interrupted").user_message
  assert a["progress"]["title"] == "Uno" and a["progress"]["percent"] == 40
  assert a["progress"]["stage"] == a["progress"]["status"] == "interrupted" and a["progress"]["eta"] is None
  assert a["progress"]["retryable"] is True and a["progress"]["error_code"] == "interrupted"
  assert b["progress"]["title"] == "Dos" and b["progress"]["media_id"] == "b" and b["progress"]["id"] == "b"


@pytest.mark.asyncio
async def test_recovery_logs_the_count_and_survives_a_failing_record(records, caplog):
  records.store = {"a": {"id": "a", "status": "pending"}, "b": {"id": "b", "status": "pending"}}
  records.fail_update = {"a"}
  with caplog.at_level(logging.INFO):
    assert await JobManager().recover_interrupted_jobs() == 2
  messages = [r.getMessage() for r in caplog.records]
  assert "Could not mark transcription a as interrupted: cannot write" in messages
  assert "Marked 2 transcription job(s) as interrupted" in messages
  assert records.store["b"]["status"] == "interrupted"


@pytest.mark.asyncio
async def test_recovery_without_stale_jobs_does_not_log_a_count(records, caplog):
  with caplog.at_level(logging.INFO):
    assert await JobManager().recover_interrupted_jobs() == 0
  assert not any("Marked" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_recovery_gives_up_quietly_when_the_listing_fails(monkeypatch, caplog):
  async def boom(statuses):
    raise RuntimeError("db down")

  monkeypatch.setattr(jobs.records, "list_by_status", boom)
  with caplog.at_level(logging.WARNING):
    assert await JobManager().recover_interrupted_jobs() == 0
  assert any("Could not look for interrupted transcriptions: db down" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_open_summaries_of_finished_jobs_are_failed(records):
  records.store = {
    "p": {"id": "p", "status": "complete", "summary_status": "pending"},
    "r": {"id": "r", "status": "complete", "summary_status": "running"},
    "d": {"id": "d", "status": "complete", "summary_status": "done"},
    "n": {"id": "n", "status": "complete"},
  }
  await JobManager()._recover_open_summaries()
  assert records.listed == [{"complete"}]
  for job in ("p", "r"):
    assert records.store[job]["summary_status"] == "failed"
    assert records.store[job]["summary_error"] == "El resumen se interrumpió por un reinicio del servidor."
  assert records.store["d"]["summary_status"] == "done" and "summary_error" not in records.store["n"]


@pytest.mark.asyncio
async def test_open_summary_recovery_logs_failures_and_keeps_going(records, caplog):
  records.store = {
    "p": {"id": "p", "status": "complete", "summary_status": "pending"},
    "r": {"id": "r", "status": "complete", "summary_status": "running"},
  }
  records.fail_update = {"p"}
  with caplog.at_level(logging.WARNING):
    await JobManager()._recover_open_summaries()
  assert any("Could not reset summary state of p: cannot write" in r.getMessage() for r in caplog.records)
  assert records.store["r"]["summary_status"] == "failed"


@pytest.mark.asyncio
async def test_open_summary_recovery_survives_a_failing_listing(monkeypatch, caplog):
  async def boom(statuses):
    raise RuntimeError("db down")

  monkeypatch.setattr(jobs.records, "list_by_status", boom)
  with caplog.at_level(logging.WARNING):
    await JobManager()._recover_open_summaries()
  assert any("Could not look for interrupted summaries: db down" in r.getMessage() for r in caplog.records)


# --- cancellation ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_running_job_is_cancelled_through_its_task():
  manager = JobManager()
  task = asyncio.create_task(asyncio.sleep(30))
  manager._tasks["j"] = task
  assert await manager.cancel("j") is True
  with pytest.raises(asyncio.CancelledError):
    await task


@pytest.mark.asyncio
async def test_a_job_that_is_not_running_here_is_marked_cancelled_directly(records, monkeypatch):
  published = []
  monkeypatch.setattr(jobs, "publish", lambda job_id, snap: published.append((job_id, snap)))
  monkeypatch.setattr(jobs, "latest", lambda job_id: {"id": job_id, "stage": "transcribing", "title": "T"})
  records.store = {"j": {"id": "j", "status": "transcribing"}}
  assert await JobManager().cancel("j") is True
  message = TranscriptionJobError("cancelled").user_message
  job_id, snapshot = published[0]
  assert job_id == "j" and snapshot["title"] == "T"
  assert (snapshot["stage"], snapshot["status"], snapshot["error_code"], snapshot["retryable"]) == ("cancelled", "cancelled", "cancelled", False)
  assert snapshot["error"] == snapshot["message"] == message
  assert records.store["j"]["status"] == "cancelled" and records.store["j"]["progress"] is snapshot
  assert records.store["j"]["error"] == message and records.store["j"]["error_code"] == "cancelled"


@pytest.mark.asyncio
async def test_cancelling_an_unknown_job_reports_nothing_to_cancel(records, monkeypatch):
  published = []
  monkeypatch.setattr(jobs, "publish", lambda job_id, snap: published.append(snap))
  monkeypatch.setattr(jobs, "latest", lambda job_id: None)
  assert await JobManager().cancel("ghost") is False
  assert published[0]["id"] == published[0]["media_id"] == "ghost"


@pytest.mark.asyncio
async def test_a_finished_task_is_not_cancelled_again(records, monkeypatch):
  monkeypatch.setattr(jobs, "publish", lambda *a: None)
  monkeypatch.setattr(jobs, "latest", lambda job_id: None)
  task = asyncio.create_task(asyncio.sleep(0))
  await task
  manager = JobManager()
  manager._tasks["j"] = task
  assert await manager.cancel("j") is False


# --- summaries ------------------------------------------------------------------------


class FakeReporter:
  def __init__(self):
    self.snapshot, self.updates = {"stage": "queued"}, []

  async def update(self, stage, percent, message, **fields):
    self.updates.append((stage, percent, message, fields))
    self.snapshot = {"stage": stage, **fields}
    return self.snapshot


@pytest.fixture
def summarizer(monkeypatch):
  import app.features.transcription.summarizer as module

  calls = []
  state = {"error": None}

  async def fake(segments, *, title, user_id):
    calls.append((segments, title, user_id))
    if state["error"]:
      raise state["error"]
    return SimpleNamespace(model_dump=lambda: {"overview": "ok"})

  monkeypatch.setattr(module, "summarize_transcript", fake)
  return SimpleNamespace(calls=calls, state=state)


@pytest.mark.asyncio
async def test_a_summary_is_stored_and_reported(records, summarizer):
  records.store = {"j": {"id": "j", "status": "complete"}}
  reporter = FakeReporter()
  record = {"segments": [{"text": "hola"}], "metadata": {"title": "Reunión semanal"}}
  await JobManager()._summarize("j", "u1", reporter, record)
  assert summarizer.calls == [([{"text": "hola"}], "Reunión semanal", "u1")]
  stored = records.store["j"]
  assert (stored["summary"], stored["summary_status"], stored["summary_error"]) == ({"overview": "ok"}, "done", None)
  assert [u[2] for u in reporter.updates] == ["Generando resumen…", "Transcripción y resumen completados."]
  assert reporter.updates[0][3] == {"summary_status": "running"} and reporter.updates[1][3] == {"summary_status": "done"}
  assert records.progress[-1][2] == {"finished": True}


@pytest.mark.asyncio
async def test_a_summary_without_segments_or_title_uses_the_defaults(records, summarizer):
  records.store = {"j": {"id": "j"}}
  await JobManager()._summarize("j", None, FakeReporter(), {})
  assert summarizer.calls == [([], "Reunión", None)]


@pytest.mark.asyncio
async def test_a_failing_summary_is_recorded_without_failing_the_job(records, summarizer, caplog):
  records.store = {"j": {"id": "j"}}
  summarizer.state["error"] = SimpleNamespace(detail="x" * 600)
  summarizer.state["error"] = type("E", (Exception,), {"detail": "d" * 600})("boom")
  reporter = FakeReporter()
  with caplog.at_level(logging.WARNING):
    await JobManager()._summarize("j", "u", reporter, {})
  stored = records.store["j"]
  assert stored["summary_status"] == "failed" and stored["summary_error"] == "d" * 500
  assert reporter.updates[-1][2] == "Transcripción completada; el resumen no se pudo generar."
  assert reporter.updates[-1][3] == {"summary_status": "failed"}
  assert any("Automatic summary failed for j: " + "d" * 600 in r.getMessage() for r in caplog.records)
  assert records.progress[-1][2] == {"finished": True}


@pytest.mark.asyncio
async def test_a_failing_summary_without_detail_reports_the_exception_text(records, summarizer):
  records.store = {"j": {"id": "j"}}
  summarizer.state["error"] = RuntimeError("plain failure")
  await JobManager()._summarize("j", "u", FakeReporter(), {})
  assert records.store["j"]["summary_error"] == "plain failure"


@pytest.mark.asyncio
async def test_a_cancelled_summary_propagates_but_still_saves_progress(records, summarizer):
  summarizer.state["error"] = asyncio.CancelledError()
  with pytest.raises(asyncio.CancelledError):
    await JobManager()._summarize("j", "u", FakeReporter(), {})
  assert records.progress[-1][2] == {"finished": True}


# --- media expiry and maintenance -----------------------------------------------------


def _iso(days_ago, suffix="+00:00", naive=False):
  moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
  return moment.replace(tzinfo=None).isoformat() if naive else moment.isoformat().replace("+00:00", suffix)


@pytest.fixture
def media(monkeypatch, records):
  existing, removed = set(), []
  monkeypatch.setattr(jobs.storage, "get_transcription_dir", lambda job_id: SimpleNamespace(exists=lambda: job_id in existing))
  monkeypatch.setattr(jobs.storage, "delete_folder", lambda job_id: removed.append(job_id))
  return SimpleNamespace(existing=existing, removed=removed)


@pytest.mark.asyncio
async def test_expiry_does_nothing_without_a_ttl(records, media, monkeypatch):
  monkeypatch.delenv("TRANSCRIPTION_MEDIA_TTL_DAYS", raising=False)
  assert await JobManager().expire_old_media() == 0
  assert records.listed == []


@pytest.mark.asyncio
async def test_only_old_completed_media_that_still_exists_is_removed(records, media, monkeypatch):
  monkeypatch.setenv("TRANSCRIPTION_MEDIA_TTL_DAYS", "10")
  records.store = {
    "old": {"id": "old", "status": "complete", "finished_at": _iso(11)},
    "z": {"id": "z", "status": "complete", "finished_at": _iso(11, suffix="Z")},
    "naive": {"id": "naive", "status": "complete", "finished_at": _iso(11, naive=True)},
    "created": {"id": "created", "status": "complete", "created_at": _iso(11)},
    "fresh": {"id": "fresh", "status": "complete", "finished_at": _iso(9)},
    "gone": {"id": "gone", "status": "complete", "finished_at": _iso(30)},
    "bad": {"id": "bad", "status": "complete", "finished_at": "yesterday"},
    "none": {"id": "none", "status": "complete"},
    "other": {"id": "other", "status": "failed", "finished_at": _iso(99)},
  }
  media.existing.update({"old", "z", "naive", "created", "fresh", "bad", "none", "other"})
  assert await JobManager().expire_old_media() == 4
  assert sorted(media.removed) == ["created", "naive", "old", "z"]
  assert records.listed == [{"complete"}]


@pytest.mark.asyncio
async def test_maintenance_starts_once_and_only_with_a_ttl(monkeypatch):
  manager = JobManager()
  started = []

  async def fake_loop():
    started.append(1)

  monkeypatch.setattr(manager, "_maintenance_loop", fake_loop)
  monkeypatch.delenv("TRANSCRIPTION_MEDIA_TTL_DAYS", raising=False)
  manager.start_maintenance()
  assert manager._maintenance is None
  monkeypatch.setenv("TRANSCRIPTION_MEDIA_TTL_DAYS", "5")
  manager.start_maintenance()
  first = manager._maintenance
  manager.start_maintenance()
  await first
  assert manager._maintenance is first and started == [1] and first.get_name() == "transcription-media-ttl"


@pytest.mark.asyncio
async def test_the_maintenance_loop_logs_failures_and_sleeps_an_hour(monkeypatch, caplog):
  manager = JobManager()
  sleeps = []

  async def failing():
    raise RuntimeError("disk")

  async def fake_sleep(seconds):
    sleeps.append(seconds)
    raise asyncio.CancelledError

  monkeypatch.setattr(manager, "expire_old_media", failing)
  monkeypatch.setattr(jobs.asyncio, "sleep", fake_sleep)
  with caplog.at_level(logging.WARNING), pytest.raises(asyncio.CancelledError):
    await manager._maintenance_loop()
  assert sleeps == [3600]
  assert any("Transcription media cleanup failed: disk" in r.getMessage() for r in caplog.records)


# --- shutdown -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_cancels_the_maintenance_and_every_running_job():
  manager = JobManager()
  running = asyncio.create_task(asyncio.sleep(30))
  done = asyncio.create_task(asyncio.sleep(0))
  await done
  manager._tasks = {"a": running, "b": done}
  manager._maintenance = asyncio.create_task(asyncio.sleep(30))
  await manager.shutdown()
  assert manager._shutting_down is True and running.cancelled() and manager._maintenance.cancelled()


@pytest.mark.asyncio
async def test_shutdown_with_nothing_running_is_a_no_op():
  manager = JobManager()
  await manager.shutdown()
  assert manager._shutting_down is True


# --- the run loop ---------------------------------------------------------------------


class FakePipeline:
  behaviour = None

  def __init__(self, job_id, user_id, options, reporter):
    self.metrics = {"stage_ms": {}, "provider": "fake"}

  async def run(self):
    return await FakePipeline.behaviour()


@pytest.fixture
def run_env(monkeypatch, records):
  logged, deleted = [], []

  async def log_job(entry):
    logged.append(entry)

  monkeypatch.setattr(jobs, "TranscriptionPipeline", FakePipeline)
  monkeypatch.setattr(jobs.metrics, "log_job", log_job)
  monkeypatch.setattr(jobs.storage, "delete_chunks", lambda job_id: deleted.append(job_id))
  return SimpleNamespace(logged=logged, deleted=deleted, records=records)


async def _run(manager, options=None, reporter=None, user="u"):
  reporter = reporter or FakeReporter()
  await manager._run("j", user, options or JobOptions(summarize=False), reporter)
  return reporter


def _result(**record):
  return SimpleNamespace(record=record)


@pytest.mark.asyncio
async def test_a_successful_run_completes_and_logs_its_metrics(run_env):
  async def ok():
    return _result(summary_status="skipped")

  FakePipeline.behaviour = ok
  manager = JobManager()
  manager._queue.append("j")
  reporter = await _run(manager)
  assert reporter.updates[-1][0] == "complete" and reporter.updates[-1][3]["summary_status"] == "skipped"
  assert reporter.snapshot["stage"] == "complete" and reporter.updates[-1][3]["retryable"] is False
  assert run_env.records.progress[-1][2] == {"finished": True}
  entry = run_env.logged[0]
  assert (entry["transcription_id"], entry["user_id"], entry["status"], entry["error_code"]) == ("j", "u", "complete", None)
  assert entry["provider"] == "fake" and isinstance(entry["stage_ms"]["total"], int)
  assert manager._queue == [] and manager._reporters == {}


@pytest.mark.asyncio
async def test_a_run_waits_for_its_turn_and_clears_the_queue_position(run_env):
  async def ok():
    return _result()

  FakePipeline.behaviour = ok
  manager = JobManager()
  manager._queue.extend(["other", "j"])
  other = FakeReporter()
  other.snapshot = {"stage": "queued"}
  manager._reporters["other"] = other
  reporter = FakeReporter()
  reporter.snapshot = {"stage": "queued", "queue_position": 2}
  await _run(manager, reporter=reporter)
  assert other.updates == [("queued", 0.0, "En cola…", {"queue_position": 1})]
  assert reporter.updates[-1][0] == "complete"


@pytest.mark.asyncio
async def test_a_run_with_summary_requested_summarizes(run_env, monkeypatch):
  async def ok():
    return _result(segments=[1])

  FakePipeline.behaviour = ok
  seen = []

  async def fake_summarize(self, job_id, user_id, reporter, record):
    seen.append((job_id, user_id, record))

  monkeypatch.setattr(JobManager, "_summarize", fake_summarize)
  await _run(JobManager(), options=JobOptions(summarize=True))
  assert seen == [("j", "u", {"segments": [1]})]
  seen.clear()
  await _run(JobManager(), options=JobOptions(summarize=False))
  assert seen == []


@pytest.mark.asyncio
async def test_a_failure_is_classified_logged_and_recorded(run_env, caplog):
  async def bad():
    raise TranscriptionJobError("auth_error", detail="bad key")

  FakePipeline.behaviour = bad
  run_env.records.store = {"j": {"id": "j"}}
  with caplog.at_level(logging.ERROR):
    reporter = await _run(JobManager())
  record = run_env.records.store["j"]
  assert (record["status"], record["error_code"], record["retryable"]) == ("failed", "auth_error", False)
  assert run_env.logged[0]["status"] == "failed" and run_env.logged[0]["error_code"] == "auth_error"
  assert reporter.updates[-1][3]["error_code"] == "auth_error" and reporter.updates[-1][3]["eta"] is None
  message = next(r for r in caplog.records if "failed (auth_error)" in r.getMessage())
  assert "bad key" in message.getMessage() and not message.exc_info


@pytest.mark.asyncio
async def test_an_unexpected_failure_logs_its_traceback(run_env, caplog):
  async def bad():
    raise ValueError("oops")

  FakePipeline.behaviour = bad
  with caplog.at_level(logging.ERROR):
    await _run(JobManager())
  record = next(r for r in caplog.records if "failed (internal)" in r.getMessage())
  assert "ValueError: oops" in record.getMessage() and record.exc_info


@pytest.mark.asyncio
async def test_a_cancelled_run_is_recorded_and_its_chunks_are_deleted(run_env):
  async def cancelled():
    raise asyncio.CancelledError

  FakePipeline.behaviour = cancelled
  run_env.records.store = {"j": {"id": "j"}}
  await _run(JobManager())
  assert run_env.records.store["j"]["status"] == "cancelled" and run_env.deleted == ["j"]
  assert run_env.logged[0]["status"] == "cancelled" and run_env.logged[0]["error_code"] == "cancelled"


@pytest.mark.asyncio
async def test_a_run_stopped_by_shutdown_is_interrupted_and_keeps_its_chunks(run_env):
  async def cancelled():
    raise asyncio.CancelledError

  FakePipeline.behaviour = cancelled
  run_env.records.store = {"j": {"id": "j"}}
  manager = JobManager()
  manager._shutting_down = True
  await _run(manager)
  assert run_env.records.store["j"]["status"] == "interrupted" and run_env.deleted == []
  assert run_env.logged[0]["error_code"] == "interrupted"


@pytest.mark.asyncio
async def test_cancelling_while_summarizing_keeps_the_transcript(run_env, monkeypatch):
  async def ok():
    return _result()

  async def cancelled_summary(self, *args):
    raise asyncio.CancelledError

  FakePipeline.behaviour = ok
  monkeypatch.setattr(JobManager, "_summarize", cancelled_summary)
  run_env.records.store = {"j": {"id": "j", "status": "complete"}}
  reporter = await _run(JobManager(), options=JobOptions(summarize=True))
  assert run_env.records.store["j"]["summary_status"] == "skipped"
  assert reporter.updates[-1][2] == "Transcripción completada; resumen cancelado." and reporter.updates[-1][3] == {"summary_status": "skipped"}
  assert run_env.logged[0]["status"] == "complete" and run_env.deleted == []


@pytest.mark.asyncio
async def test_a_failure_to_record_the_failure_is_only_logged(run_env, caplog):
  async def bad():
    raise TranscriptionJobError("timeout")

  FakePipeline.behaviour = bad
  run_env.records.fail_update = {"j"}
  run_env.records.store = {"j": {"id": "j"}}
  with caplog.at_level(logging.WARNING):
    await _run(JobManager())
  assert any("Could not record failure of transcription j: cannot write" in r.getMessage() for r in caplog.records)
  assert run_env.logged[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_the_concurrency_limit_comes_from_the_configuration(monkeypatch):
  monkeypatch.setenv("TRANSCRIPTION_MAX_CONCURRENT_JOBS", "3")
  manager = JobManager()
  semaphore = manager._sem()
  assert semaphore is manager._sem() and semaphore._value == 3


def test_a_job_is_running_only_while_its_task_is_not_done():
  manager = JobManager()
  assert manager.is_running("j") is False
  manager._tasks["j"] = SimpleNamespace(done=lambda: False)
  assert manager.is_running("j") is True
  manager._tasks["j"] = SimpleNamespace(done=lambda: True)
  assert manager.is_running("j") is False
