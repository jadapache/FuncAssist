"""Boundary cases of the transcription jobs, metrics, storage, SSE stream, service and schema migration."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.api import transcription_stream as stream
from app.core import transcription_migration as migration
from app.features.transcription import jobs, metrics, progress, service, storage
from app.features.transcription import whisper_cloud as wc
from app.features.transcription.errors import TranscriptionJobError
from app.features.transcription.jobs import JobManager
from app.features.transcription.pipeline import JobOptions
from tests.test_transcription_jobs import FakeRecords, FakeReporter  # noqa: F401  (shared fakes)
from tests.test_transcription_jobs import records  # noqa: F401  (fixture)

# --- metrics --------------------------------------------------------------------------


@pytest.fixture
def logs(tmp_path, monkeypatch):
  target = tmp_path / "deep" / "er" / "logs"
  monkeypatch.setattr(metrics, "LOG_DIR", target)
  return target


async def _logged(logs, entry):
  await metrics.log_job(entry)
  return json.loads(next(logs.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()[0])


@pytest.mark.asyncio
async def test_job_metrics_are_written_with_accents_and_the_real_time_factor(logs):
  entry = await _logged(logs, {"transcription_id": "t", "note": "canción", "stage_ms": {"a": 500, "b": 500}, "audio_s": 2.0})
  assert entry["rtf"] == 0.5 and entry["note"] == "canción" and entry["timestamp"]
  assert "canción" in next(logs.glob("*.jsonl")).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_the_time_factor_needs_audio_and_time(logs):
  assert "rtf" not in await _logged(logs, {"stage_ms": {"a": 500}, "audio_s": 0})
  for path in logs.glob("*.jsonl"):
    path.unlink()
  assert "rtf" not in await _logged(logs, {"stage_ms": {"a": 0}, "audio_s": 5})
  for path in logs.glob("*.jsonl"):
    path.unlink()
  assert "rtf" not in await _logged(logs, {"audio_s": 5})
  for path in logs.glob("*.jsonl"):
    path.unlink()
  assert (await _logged(logs, {"stage_ms": {"a": 500}, "audio_s": 0.5}))["rtf"] == 1.0


@pytest.mark.asyncio
async def test_a_second_entry_is_appended_to_the_same_day(logs):
  await metrics.log_job({"n": 1})
  await metrics.log_job({"n": 2})
  assert [e["n"] for e in reversed(metrics.read_entries())] == [1, 2]


# --- whisper backoff ------------------------------------------------------------------


def test_backoff_doubles_each_attempt_adds_jitter_and_stops_at_a_minute(monkeypatch):
  monkeypatch.setattr(wc.random, "uniform", lambda low, high: (low + high) / 2)
  assert [wc._backoff_delay(Exception(), n) for n in range(3)] == [2.5, 4.5, 8.5]
  assert wc._backoff_delay(Exception(), 10) == 60.0
  assert wc._backoff_delay(SimpleNamespace(retry_after=7.0), 3) == 7.0
  assert wc._backoff_delay(SimpleNamespace(retry_after=0), 0) == 2.5
  assert wc._backoff_delay(SimpleNamespace(retry_after=900.0), 0) == 60.0


# --- storage --------------------------------------------------------------------------


@pytest.fixture
def transcriptions(tmp_path, monkeypatch):
  monkeypatch.setattr(storage, "TRANSCRIPTIONS_DIR", tmp_path / "transcriptions")
  monkeypatch.setattr(storage, "ensure_local_dirs", lambda: None)
  monkeypatch.setattr(storage, "APP_TRANSCRIPTIONS_DIR", tmp_path / "app")
  return tmp_path / "transcriptions"


class _Upload:
  filename = "a.mp3"

  async def read(self, size):
    return b""


@pytest.mark.asyncio
async def test_a_failure_before_the_temporary_file_exists_is_not_masked(transcriptions, monkeypatch):
  async def boom(upload, tmp, limit):
    raise RuntimeError("disk gone")

  monkeypatch.setattr(storage, "_stream_to_file", boom)
  with pytest.raises(RuntimeError, match="disk gone"):
    await storage.save_upload(_Upload(), "t1", "T")
  assert not (transcriptions / "t1").exists()


def test_local_media_creates_its_folder_with_parents_and_tolerates_an_existing_one(tmp_path, monkeypatch):
  root = tmp_path / "media"
  root.mkdir()
  (root / "a.mp3").write_bytes(b"x")
  monkeypatch.setenv("TRANSCRIPTION_DESKTOP_MODE", "1")
  monkeypatch.setenv("TRANSCRIPTION_LOCAL_ROOTS", str(root))
  monkeypatch.setattr(storage, "TRANSCRIPTIONS_DIR", tmp_path / "x" / "y" / "transcriptions")
  storage.local_media_entry("t1", str(root / "a.mp3"), "T")
  storage.local_media_entry("t1", str(root / "a.mp3"), "T")
  assert (tmp_path / "x" / "y" / "transcriptions" / "t1").is_dir()


# --- jobs -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_started_job_is_queued_with_a_clean_state_and_a_growing_sequence(records, monkeypatch):
  async def idle(self, *args):
    return None

  monkeypatch.setattr(JobManager, "_run", idle)
  monkeypatch.setattr(jobs, "latest", lambda job_id: None)
  manager = JobManager()
  previous = {"seq": 5, "stage": "failed", "error": "old", "error_code": "timeout", "retryable": True}
  snapshot = await manager.start("j", "u", JobOptions(), title="T", previous=previous)
  assert snapshot["stage"] == "queued" and snapshot["seq"] > 5 and snapshot["queue_position"] == 1
  assert (snapshot["error"], snapshot["error_code"], snapshot["retryable"]) == (None, None, False)
  assert records.progress[-1][2] == {"started": True} and records.progress[-1][0] == "j"
  await manager._tasks["j"]
  await asyncio.sleep(0)
  assert manager._tasks == {}


@pytest.mark.asyncio
async def test_the_live_state_wins_over_the_stored_one_when_restarting(records, monkeypatch):
  async def idle(self, *args):
    return None

  monkeypatch.setattr(JobManager, "_run", idle)
  monkeypatch.setattr(jobs, "latest", lambda job_id: {"seq": 20})
  snapshot = await JobManager().start("j", "u", JobOptions(), title="T", previous={"seq": 5})
  assert snapshot["seq"] > 20


@pytest.mark.asyncio
async def test_a_job_that_is_already_running_cannot_be_started_again(records):
  manager = JobManager()
  manager._tasks["j"] = asyncio.create_task(asyncio.sleep(30))
  with pytest.raises(TranscriptionJobError) as raised:
    await manager.start("j", "u", JobOptions(), title="T")
  assert raised.value.code == "bad_request" and raised.value.user_message == "La transcripción ya está en curso."
  manager._tasks["j"].cancel()


@pytest.mark.asyncio
async def test_only_queued_jobs_get_their_position_refreshed():
  manager = JobManager()
  manager._queue.extend(["a", "b", "c"])
  queued, busy = FakeReporter(), FakeReporter()
  queued.snapshot, busy.snapshot = {"stage": "queued"}, {"stage": "transcribing"}
  manager._reporters.update({"a": queued, "b": busy})
  await manager._refresh_queue_positions()
  assert queued.updates == [("queued", 0.0, "En cola…", {"queue_position": 1})] and busy.updates == []


@pytest.mark.asyncio
async def test_the_total_time_of_a_run_is_measured_in_milliseconds(records, monkeypatch):
  from tests.test_transcription_jobs import FakePipeline

  async def ok():
    return SimpleNamespace(record={})

  logged = []

  async def log_job(entry):
    logged.append(entry)

  FakePipeline.behaviour = ok
  ticks = iter([1.0, 3.5])
  monkeypatch.setattr(jobs, "TranscriptionPipeline", FakePipeline)
  monkeypatch.setattr(jobs.metrics, "log_job", log_job)
  monkeypatch.setattr(jobs, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
  await JobManager()._run("j", "u", JobOptions(summarize=False), FakeReporter())
  assert logged[0]["stage_ms"]["total"] == 2500


@pytest.mark.asyncio
async def test_a_recorded_failure_is_saved_as_finished_and_a_failed_recording_logs_its_traceback(records, caplog):
  records.store = {"j": {"id": "j"}}
  manager = JobManager()
  await manager._finish_failed("j", FakeReporter(), TranscriptionJobError("timeout"), "failed")
  assert records.progress[-1][2] == {"finished": True}
  records.fail_update = {"j"}
  with caplog.at_level(logging.WARNING):
    await manager._finish_failed("j", FakeReporter(), TranscriptionJobError("timeout"), "failed")
  assert next(r for r in caplog.records if "Could not record failure" in r.getMessage()).exc_info


def test_a_record_is_older_only_when_it_finished_before_the_cutoff():
  cutoff = datetime(2024, 6, 1, tzinfo=timezone.utc)
  older = lambda when: jobs._is_older({"finished_at": when}, cutoff)  # noqa: E731
  assert older((cutoff - timedelta(seconds=1)).isoformat()) is True
  assert older(cutoff.isoformat()) is False
  assert older((cutoff + timedelta(seconds=1)).isoformat()) is False
  assert older("not a date") is False and jobs._is_older({}, cutoff) is False
  assert jobs._is_older({"created_at": "2024-01-01T00:00:00"}, cutoff) is True


@pytest.mark.asyncio
async def test_a_stale_cancellation_keeps_the_known_state_and_marks_it_not_retryable(records, monkeypatch):
  published = []
  monkeypatch.setattr(jobs, "publish", lambda job_id, snap: published.append(snap))
  monkeypatch.setattr(jobs, "latest", lambda job_id: {"id": job_id, "retryable": True, "eta": 5})
  records.store = {"j": {"id": "j"}}
  await JobManager().cancel("j")
  snapshot = published[0]
  assert snapshot["retryable"] is False and snapshot["eta"] == 5 and snapshot["stage"] == "cancelled"


# --- SSE stream -----------------------------------------------------------------------


def test_events_carry_their_sequence_number_in_the_v2_protocol():
  assert stream.format_event({"seq": 7, "stage": "x"}, "v2").startswith("id: 7\nevent: progress\n")
  assert stream.format_event({"stage": "x"}, "v2").startswith("id: 0\n")
  assert stream.format_event({"stage": "ñ"}, "v1") == 'data: {"stage": "ñ"}\n\n'
  assert stream.format_heartbeat("v2") == "event: heartbeat\ndata: {}\n\n"
  assert '"heartbeat"' in stream.format_heartbeat("v1")


def test_the_closing_event_is_sent_only_when_it_is_newer():
  progress._LATEST["k1"] = {"seq": 5, "stage": "complete"}
  assert stream._closing_event("k1", 5, "v1") is None
  assert stream._closing_event("k1", 4, "v1") is not None
  assert stream._closing_event("nobody", 0, "v1") is None
  progress._LATEST.pop("k1")


async def _collect(queue, job_id="k2", last_seq=0, running=True, monkeypatch=None):
  return [event async for event in stream._follow_updates(queue, job_id, last_seq, "v2")]


@pytest.mark.asyncio
async def test_updates_at_or_below_the_last_sequence_are_skipped(monkeypatch):
  queue = asyncio.Queue()
  for update in ({"seq": 3, "stage": "transcribing"}, {"seq": 4, "stage": "transcribing"}, {"seq": 5, "stage": "failed"}):
    queue.put_nowait(update)
  events = await _collect(queue, last_seq=3)
  assert [e.split("\n")[0] for e in events] == ["id: 4", "id: 5"]


@pytest.mark.asyncio
async def test_an_update_without_a_sequence_does_not_reset_the_last_one():
  queue = asyncio.Queue()
  for update in ({"stage": "transcribing", "n": "no seq"}, {"seq": 2, "stage": "transcribing"}, {"seq": 6, "stage": "failed"}):
    queue.put_nowait(update)
  events = await _collect(queue, last_seq=4)
  assert len(events) == 2 and "no seq" in events[0] and events[1].startswith("id: 6")


@pytest.mark.asyncio
async def test_silence_sends_a_heartbeat_and_a_finished_job_sends_its_last_state(monkeypatch):
  monkeypatch.setattr(stream, "HEARTBEAT_S", 0.01)
  monkeypatch.setattr(stream.job_manager, "is_running", lambda job_id: False)
  progress._LATEST["k3"] = {"seq": 9, "stage": "complete", "summary_status": "done"}
  events = await _collect(asyncio.Queue(), job_id="k3", last_seq=4)
  progress._LATEST.pop("k3")
  assert events[0].startswith("event: heartbeat") and events[1].startswith("id: 9") and len(events) == 2


@pytest.mark.asyncio
async def test_silence_while_the_job_still_runs_keeps_waiting(monkeypatch):
  monkeypatch.setattr(stream, "HEARTBEAT_S", 0.01)
  runs = iter([True, False])
  monkeypatch.setattr(stream.job_manager, "is_running", lambda job_id: next(runs))
  events = await _collect(asyncio.Queue(), job_id="k4", last_seq=0)
  assert [e.split("\n")[0] for e in events] == ["event: heartbeat", "event: heartbeat"]


# --- service --------------------------------------------------------------------------


@pytest.mark.parametrize("provider, model, keys, label", [
  ("groq", "whisper-large-v3-turbo", {"groq": False, "openai": False}, "Groq Whisper (whisper-large-v3-turbo)"),
  ("groq", "onnx-community/whisper-base", {"groq": False, "openai": False}, "Groq Whisper (whisper-large-v3)"),
  ("groq", "foo", {"groq": False, "openai": False}, "Groq Whisper (whisper-large-v3)"),
  ("auto", "whisper-x", {"groq": True, "openai": False}, "Groq Whisper (whisper-x)"),
  ("cloud", "whisper-x", {"groq": True, "openai": True}, "Groq Whisper (whisper-x)"),
  ("browser_asr", "m", {"groq": True, "openai": True}, "Transformers.js Navegador (m)"),
  ("auto", "m", {"groq": False, "openai": False}, "Transformers.js Navegador (m)"),
  ("openai", "m", {"groq": False, "openai": False}, "OpenAI Whisper (whisper-1)"),
  ("auto", "m", {"groq": False, "openai": True}, "OpenAI Whisper (whisper-1)"),
  ("cloud", "m", {"groq": False, "openai": True}, "OpenAI Whisper (whisper-1)"),
])
def test_the_active_engine_label_follows_the_provider_and_the_available_keys(provider, model, keys, label):
  assert service._active_model_label(provider, model, keys) == label


def test_a_record_without_progress_gets_a_derived_status():
  done = service._derived_status({"id": "r1", "status": "uploaded", "segments": [{"text": "x"}], "metadata": {"title": "T"}, "summary_status": "done", "model_info": "M"})
  assert done == {
    "id": "r1", "media_id": "r1", "title": "T", "status": "complete", "stage": "complete", "stage_progress": 1.0, "progress": 100,
    "message": "Transcripción completada.", "eta": None, "eta_seconds": None, "chunks_done": 0, "chunks_total": 0, "queue_position": None,
    "error": None, "error_code": None, "retryable": False, "summary_status": "done", "model_info": "M", "seq": 0, "timestamp": None, "live_segments": [],
  }
  failed = service._derived_status({"id": "r2", "status": "failed", "error": "boom", "error_code": "timeout", "retryable": 1, "segments": [{"x": 1}]})
  assert (failed["stage"], failed["progress"], failed["stage_progress"], failed["message"]) == ("failed", 0, 0.0, "boom")
  assert (failed["error_code"], failed["retryable"], failed["title"]) == ("timeout", True, None)
  waiting = service._derived_status({"id": "r3", "status": "uploaded"})
  assert (waiting["stage"], waiting["message"]) == ("uploaded", "")
  assert service._derived_status({"id": "r4"})["stage"] == "complete"


def test_job_status_prefers_the_live_then_the_stored_then_the_derived_snapshot(monkeypatch):
  monkeypatch.setattr(service.job_manager, "snapshot", lambda job_id: None)
  stored = {"id": "r", "progress": {"stage": "failed", "summary_status": "old"}, "summary_status": "done"}
  assert service.job_status(stored) == {"stage": "failed", "summary_status": "done"}
  assert service.job_status({"id": "r", "progress": {"stage": "failed", "summary_status": "old"}})["summary_status"] == "old"
  assert service.job_status({"id": "r", "progress": {"message": "no stage"}, "status": "failed"})["stage"] == "failed"
  assert service.job_status({"id": "r", "progress": "text", "status": "failed"})["stage"] == "failed"
  monkeypatch.setattr(service.job_manager, "snapshot", lambda job_id: {"live": True})
  assert service.job_status(stored) == {"live": True}


@pytest.fixture
def client_service(monkeypatch):
  state = SimpleNamespace(saved=[], updates=[], rules=[], update_result="keep", summaries=[], summary_error=None)

  async def get_record(tid):
    return None

  async def save_record(record):
    state.saved.append(record)
    return record

  async def update_record(tid, mutate):
    state.updates.append(tid)
    record = {"id": tid}
    mutate(record)
    state.last_update = record
    return None if state.update_result is None else record

  async def summarize(segments, title, user_id, feature=None):
    state.summaries.append((segments, title, user_id))
    if state.summary_error:
      raise state.summary_error
    return SimpleNamespace(model_dump=lambda: {"overview": "ok"})

  real_rules = service.apply_rules

  def spy_rules(segments, **kwargs):
    state.rules.append(kwargs)
    return real_rules(segments, **kwargs)

  monkeypatch.setattr(service.records, "get_record", get_record)
  monkeypatch.setattr(service.records, "save_record", save_record)
  monkeypatch.setattr(service.records, "update_record", update_record)
  monkeypatch.setattr(service, "summarize_transcript", summarize)
  monkeypatch.setattr(service, "apply_rules", spy_rules)
  import app.ai.providers.factory as factory

  monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: {})
  return state


USER = {"id": "u1"}


@pytest.mark.asyncio
async def test_browser_segments_get_numeric_times_a_default_speaker_and_ids(client_service):
  payload = {"id": "t1", "segments": [{"start": "1.5", "end": "2", "text": "hola"}, {"text_raw": "", "text": "ignorado"}, {"id": "mine", "text_raw": "adiós", "speaker_id": "S2"}]}
  saved, summary = await service.submit_client_transcription(payload, USER)
  assert summary is None and [s["text_raw"] for s in saved["segments"]] == ["hola", "adiós"]
  assert (saved["segments"][0]["start"], saved["segments"][0]["end"]) == (1.5, 2.0)
  assert [s["speaker_id"] for s in saved["segments"]] == ["S1", "S1"] and saved["segments"][1]["id"] == "mine"


@pytest.mark.asyncio
async def test_browser_diarization_keeps_the_speakers_the_browser_found(client_service):
  payload = {"id": "t1", "diarization": "browser", "segments": [{"text": "a", "speaker_id": "S1"}, {"text": "b", "speaker_id": "S2"}]}
  saved, _ = await service.submit_client_transcription(payload, USER)
  assert [s["speaker_id"] for s in saved["segments"]] == ["S1", "S2"] and saved["diarization"] == "browser"


@pytest.mark.asyncio
async def test_a_browser_transcript_without_segments_uses_the_text_and_the_defaults(client_service):
  saved, _ = await service.submit_client_transcription({"id": "t1", "segments": None, "text": "texto suelto"}, USER)
  assert saved["segments"] == [] and saved["text"] == "texto suelto"
  assert saved["metadata"] == {"title": "Reunión", "description": "", "engine": "Transformers.js (Client-side)"}
  assert (saved["language"], saved["duration_seconds"], saved["diarization"], saved["summary_status"]) == ("es", 0.0, "none", "skipped")
  assert (saved["saved_to_knowledge"], saved["document_id"], saved["error"], saved["error_code"], saved["summary"]) == (False, None, None, None, None)
  assert (saved["model_info"], saved["status"], saved["source"], saved["user_id"]) == ("Whisper Web (Client)", "complete", "browser", "u1")
  assert client_service.rules[0]["language"] == "es" and client_service.rules[0]["extra_fillers"] == []


@pytest.mark.asyncio
async def test_browser_metadata_comes_from_the_payload(client_service):
  payload = {"id": "t1", "title": "Mi reunión", "description": "d", "language": "en", "duration_seconds": "12.5", "consent": {"ok": True}, "generate_summary_now": False}
  saved, _ = await service.submit_client_transcription(payload, USER)
  assert (saved["metadata"]["title"], saved["metadata"]["description"], saved["language"], saved["duration_seconds"]) == ("Mi reunión", "d", "en", 12.5)
  assert saved["consent"] == {"ok": True} and client_service.rules[0]["language"] == "en"


@pytest.mark.asyncio
async def test_a_requested_summary_is_stored_and_a_failing_one_is_recorded(client_service):
  payload = {"id": "t1", "segments": [{"text": "hola"}], "generate_summary_now": True}
  saved, summary = await service.submit_client_transcription(payload, USER)
  assert summary == {"overview": "ok"} and client_service.last_update["summary_status"] == "done" and saved["id"] == "t1"
  assert client_service.summaries[0][1:] == ("Reunión", "u1")
  client_service.summary_error = SimpleNamespace(detail="d" * 600)
  client_service.summary_error = type("E", (Exception,), {"detail": "d" * 600})("x")
  saved, summary = await service.submit_client_transcription(payload, USER)
  assert summary is None and client_service.last_update["summary_status"] == "failed" and client_service.last_update["summary_error"] == "d" * 500


@pytest.mark.asyncio
async def test_a_summary_whose_update_returns_nothing_keeps_the_saved_record(client_service):
  client_service.update_result = None
  payload = {"id": "t1", "segments": [{"text": "hola"}], "generate_summary_now": True}
  saved, summary = await service.submit_client_transcription(payload, USER)
  assert summary == {"overview": "ok"} and saved["summary_status"] == "pending"
  client_service.summary_error = RuntimeError("boom")
  saved, summary = await service.submit_client_transcription(payload, USER)
  assert summary is None and saved["summary_status"] == "pending"


@pytest.mark.asyncio
async def test_summaries_are_only_requested_for_transcripts_that_have_segments(client_service):
  saved, summary = await service.submit_client_transcription({"id": "t1", "segments": [], "generate_summary_now": True}, USER)
  assert summary is None and client_service.summaries == []


@pytest.mark.asyncio
async def test_an_id_owned_by_someone_else_is_refused(client_service, monkeypatch):
  async def foreign(tid):
    return {"id": tid, "user_id": "other"}

  monkeypatch.setattr(service.records, "get_record", foreign)
  with pytest.raises(TranscriptionJobError) as raised:
    await service.submit_client_transcription({"id": "t1"}, USER)
  assert raised.value.user_message == "Identificador de transcripción en uso."

  async def mine(tid):
    return {"id": tid, "user_id": "u1"}

  monkeypatch.setattr(service.records, "get_record", mine)
  await service.submit_client_transcription({"id": "t1"}, USER)


@pytest.mark.asyncio
async def test_a_summary_for_a_record_without_segments_is_requested_with_an_empty_list(client_service):
  summary, updated = await service.generate_summary({"id": "t1"}, USER, None)
  assert client_service.summaries[0][0] == []
  assert updated == {"id": "t1", "summary": {"overview": "ok"}, "summary_status": "done", "summary_error": None}


@pytest.mark.asyncio
async def test_saving_to_the_knowledge_base_tags_the_document(monkeypatch):
  import app.context.knowledge as knowledge

  seen = {}

  def ingest(**kwargs):
    seen.update(kwargs)
    return {"id": "doc-1"}

  async def update(tid, mutate):
    return None

  monkeypatch.setattr(knowledge, "ingest_document", ingest)
  monkeypatch.setattr(service.records, "update_record", update)
  record = {"id": "t1", "metadata": {"title": "Acta"}, "segments": []}
  assert (await service.save_to_knowledge_base(record, ["extra"]))["document_id"] == "doc-1"
  assert set(seen["tags"]) == {"reunion", "transcripcion", "extra"} and seen["filename"] == "Acta.txt"
  await service.save_to_knowledge_base({**record, "metadata": {"title": "acta.TXT"}}, None)
  assert set(seen["tags"]) == {"reunion", "transcripcion"} and seen["filename"] == "acta.TXT"


# --- schema migration -----------------------------------------------------------------


class _Session:
  def __init__(self, fail=False):
    self.statements, self.fail = [], fail

  def execute(self, statement):
    if self.fail:
      raise RuntimeError("no lock")
    self.statements.append(str(statement))


def test_the_advisory_lock_is_only_taken_on_postgresql_and_only_when_available():
  assert migration._take_lock(_Session(), "sqlite") is False
  session = _Session()
  assert migration._take_lock(session, "postgresql") is True and "pg_advisory_xact_lock" in session.statements[0]
  assert migration._take_lock(_Session(fail=True), "postgresql") is False


def test_columns_are_added_with_the_syntax_of_the_dialect():
  pg, generic = _Session(), _Session()
  migration._add_column(pg, "postgresql", "user_id", "VARCHAR(64)", "VARCHAR(64)")
  migration._add_column(generic, "sqlite", "started_at", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP")
  assert pg.statements == ["ALTER TABLE transcriptions ADD COLUMN IF NOT EXISTS user_id VARCHAR(64);"]
  assert generic.statements == ["ALTER TABLE transcriptions ADD COLUMN started_at TIMESTAMP;"]
