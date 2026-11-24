"""Service-layer tests: model info, job lifecycle helpers, browser submissions, summaries and knowledge."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.ai.providers import factory
from app.features.transcription import service
from app.features.transcription.errors import TranscriptionJobError
from app.features.transcription.pipeline import JobOptions

USER = {"id": "u1"}


# --- doubles ------------------------------------------------------------------------------------


@pytest.fixture
def store(monkeypatch) -> dict[str, dict[str, Any]]:
  """In-memory replacement of the records module functions used by the service."""
  data: dict[str, dict[str, Any]] = {}

  async def get_record(tid):
    return data.get(tid)

  async def save_record(record):
    data[record["id"]] = record
    return record

  async def update_record(tid, mutate):
    rec = data.get(tid)
    if rec is None:
      return None
    mutate(rec)
    return rec

  async def list_by_status(statuses, user_id=None):
    return [r for r in data.values() if r.get("status") in statuses and r.get("user_id") == user_id]

  async def delete_record(tid):
    return data.pop(tid, None) is not None

  monkeypatch.setattr(service.records, "get_record", get_record)
  monkeypatch.setattr(service.records, "save_record", save_record)
  monkeypatch.setattr(service.records, "update_record", update_record)
  monkeypatch.setattr(service.records, "list_by_status", list_by_status)
  monkeypatch.setattr(service.records, "delete_record", delete_record)
  return data


@pytest.fixture
def ai_settings(monkeypatch):
  cfg: dict[str, Any] = {}
  monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: cfg)
  return cfg


@pytest.fixture
def keys(monkeypatch):
  state = {"groq": False, "openai": False}
  monkeypatch.setattr(service, "available_providers", lambda user_id: dict(state))
  return state


class FakeJobs:
  def __init__(self):
    self.live: dict[str, dict] = {}
    self.running: set[str] = set()
    self.started: list[tuple] = []
    self.cancelled: list[str] = []

  async def start(self, tid, user_id, options, *, title, previous):
    self.started.append((tid, user_id, options, title, previous))
    return {"id": tid, "stage": "queued"}

  def snapshot(self, tid):
    return self.live.get(tid)

  def is_running(self, tid):
    return tid in self.running

  async def cancel(self, tid):
    self.cancelled.append(tid)


@pytest.fixture
def jobs(monkeypatch):
  fake = FakeJobs()
  monkeypatch.setattr(service, "job_manager", fake)
  return fake


# --- get_available_models_info ------------------------------------------------------------------


def test_models_info_default_is_browser(ai_settings, keys):
  info = service.get_available_models_info("u1")
  assert info["configured_provider"] == "browser_asr"
  assert info["available_providers"] == ["browser_asr"]
  assert info["active_model_label"] == "Transformers.js Navegador (onnx-community/whisper-base)"
  assert info["diarization_available"] is False
  assert info["browser_diarization"] is False
  assert info["local_available"] is True


def test_models_info_groq_label_and_providers(ai_settings, keys):
  keys.update(groq=True, openai=True)
  ai_settings.update(transcription_provider="groq", transcription_model="whisper-large-v3-turbo")
  info = service.get_available_models_info()
  assert info["active_model_label"] == "Groq Whisper (whisper-large-v3-turbo)"
  assert info["available_providers"] == ["browser_asr", "groq", "openai"]
  assert info["groq_configured"] and info["openai_configured"]
  assert info["diarization_available"] is True


def test_models_info_groq_non_whisper_model_uses_default_label(ai_settings, keys):
  keys["groq"] = True
  ai_settings.update(transcription_provider="cloud", transcription_model="org/other")
  assert service.get_available_models_info()["active_model_label"] == "Groq Whisper (whisper-large-v3)"


def test_models_info_openai_when_only_openai_key(ai_settings, keys):
  keys["openai"] = True
  ai_settings["transcription_provider"] = "auto"
  assert service.get_available_models_info()["active_model_label"] == "OpenAI Whisper (whisper-1)"


def test_models_info_diarization_off_and_browser_diarization_on(ai_settings, keys):
  keys["openai"] = True
  ai_settings.update(transcription_diarization="OFF", transcription_browser_diarization="On")
  info = service.get_available_models_info()
  assert info["diarization_available"] is False
  assert info["browser_diarization"] is True


# --- jobs ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_job_requires_media(jobs):
  with pytest.raises(TranscriptionJobError) as exc:
    await service.start_job({"id": "t1", "has_media": False}, USER, JobOptions())
  assert exc.value.code == "bad_request"
  assert jobs.started == []


@pytest.mark.asyncio
async def test_start_job_passes_title_and_previous_progress(jobs):
  record = {"id": "t1", "has_media": True, "metadata": {"title": "Kickoff"}, "progress": {"stage": "error"}}
  opts = JobOptions(language="es")
  result = await service.start_job(record, USER, opts)
  assert result == {"id": "t1", "stage": "queued"}
  assert jobs.started == [("t1", "u1", opts, "Kickoff", {"stage": "error"})]


@pytest.mark.asyncio
async def test_start_job_default_title(jobs):
  await service.start_job({"id": "t1", "has_media": True}, USER, JobOptions())
  assert jobs.started[0][3] == "Transcripción"


@pytest.mark.asyncio
async def test_retry_job_rebuilds_options(jobs):
  record = {"id": "t1", "has_media": True, "job_options": {"language": "en", "diarize": False, "bogus": 1}}
  await service.retry_job(record, USER)
  opts = jobs.started[0][2]
  assert opts.language == "en" and opts.diarize is False


def test_job_status_prefers_live_snapshot(jobs):
  jobs.live["t1"] = {"stage": "transcribing"}
  assert service.job_status({"id": "t1"}) == {"stage": "transcribing"}


def test_job_status_uses_persisted_progress(jobs):
  record = {"id": "t1", "progress": {"stage": "cleaning", "summary_status": "old"}, "summary_status": "running"}
  snap = service.job_status(record)
  assert snap["stage"] == "cleaning" and snap["summary_status"] == "running"
  assert record["progress"]["summary_status"] == "old"  # stored snapshot is not mutated


def test_job_status_persisted_progress_keeps_own_summary_status(jobs):
  snap = service.job_status({"id": "t1", "progress": {"stage": "saving", "summary_status": "done"}})
  assert snap["summary_status"] == "done"


@pytest.mark.parametrize("status", ["completed", "complete", "uploaded"])
def test_job_status_derived_complete(jobs, status):
  snap = service.job_status({"id": "t1", "status": status, "segments": [{"text": "x"}], "metadata": {"title": "T"}})
  assert snap["stage"] == "complete" and snap["progress"] == 100 and snap["stage_progress"] == 1.0
  assert snap["title"] == "T" and snap["message"] == "Transcripción completada."


def test_job_status_uploaded_without_segments_is_not_complete(jobs):
  snap = service.job_status({"id": "t1", "status": "uploaded"})
  assert snap["stage"] == "uploaded" and snap["progress"] == 0


def test_job_status_failed_record(jobs):
  snap = service.job_status(
    {"id": "t1", "status": "error", "error": "boom", "error_code": "timeout", "retryable": 1}
  )
  assert snap["stage"] == "error" and snap["message"] == "boom"
  assert snap["error_code"] == "timeout" and snap["retryable"] is True


def test_job_status_defaults_to_complete_when_status_missing(jobs):
  assert service.job_status({"id": "t1", "segments": [{"text": "x"}]})["stage"] == "complete"


@pytest.mark.asyncio
async def test_active_jobs_lists_only_user_active(store, jobs):
  store["a"] = {"id": "a", "user_id": "u1", "status": "transcribing", "progress": {"stage": "transcribing"}}
  store["b"] = {"id": "b", "user_id": "u1", "status": "complete"}
  store["c"] = {"id": "c", "user_id": "other", "status": "queued"}
  result = await service.active_jobs(USER)
  assert [r["stage"] for r in result] == ["transcribing"]


@pytest.mark.asyncio
async def test_delete_transcription_cancels_running_job(store, jobs):
  store["t1"] = {"id": "t1"}
  jobs.running.add("t1")
  assert await service.delete_transcription({"id": "t1"}) is True
  assert jobs.cancelled == ["t1"] and "t1" not in store


@pytest.mark.asyncio
async def test_delete_transcription_idle(store, jobs):
  assert await service.delete_transcription({"id": "nope"}) is False
  assert jobs.cancelled == []


def test_media_entry_for_upload(monkeypatch):
  monkeypatch.setattr(service.storage, "initial_record", lambda entry, uid: {"entry": entry, "uid": uid})
  assert service.media_entry_for_upload({"title": "T"}, {"id": 7}) == {"entry": {"title": "T"}, "uid": "7"}


# --- submit_client_transcription ----------------------------------------------------------------


def _payload(**over):
  base = {
    "id": "t1",
    "title": "Daily",
    "language": "es",
    "duration_seconds": 12,
    "segments": [
      {"start": 0, "end": 2, "text": "hola equipo", "speaker_id": "S2"},
      {"start": 2, "end": 3, "text_raw": "   "},
      {"start": 3, "end": 5, "text": "empecemos", "speaker_id": "S3"},
    ],
  }
  base.update(over)
  return base


@pytest.mark.asyncio
async def test_submit_rejects_foreign_id(store, ai_settings):
  store["t1"] = {"id": "t1", "user_id": "someone-else"}
  with pytest.raises(TranscriptionJobError) as exc:
    await service.submit_client_transcription(_payload(), USER)
  assert exc.value.code == "bad_request"


@pytest.mark.asyncio
async def test_submit_saves_record_without_browser_diarization(store, ai_settings):
  saved, summary = await service.submit_client_transcription(_payload(), USER)
  assert summary is None
  assert saved is store["t1"]
  assert saved["user_id"] == "u1" and saved["source"] == "browser" and saved["status"] == "complete"
  assert saved["summary_status"] == "skipped"
  assert saved["diarization"] == "none"
  assert len(saved["segments"]) == 2  # blank segment dropped
  assert {s["speaker_id"] for s in saved["segments"]} == {"S1"}  # speaker ids flattened
  assert saved["metadata"]["title"] == "Daily"
  assert saved["duration_seconds"] == 12.0
  assert "hola equipo" in saved["text"].lower()


@pytest.mark.asyncio
async def test_submit_keeps_browser_diarization(store, ai_settings):
  saved, _ = await service.submit_client_transcription(_payload(diarization="browser"), USER)
  assert saved["diarization"] == "browser"
  assert {s["speaker_id"] for s in saved["segments"]} == {"S2", "S3"}


@pytest.mark.asyncio
async def test_submit_llm_cleanup_mode_downgraded_to_rules(store, ai_settings, monkeypatch):
  ai_settings["transcription_cleanup"] = "LLM"
  seen = {}
  real = service.apply_rules

  def spy(segments, mode, language, extra_fillers):
    seen.update(mode=mode, fillers=extra_fillers)
    return real(segments, mode=mode, language=language, extra_fillers=extra_fillers)

  monkeypatch.setattr(service, "apply_rules", spy)
  ai_settings["transcription_fillers"] = ["eh"]
  await service.submit_client_transcription(_payload(), USER)
  assert seen == {"mode": "rules", "fillers": ["eh"]}


@pytest.mark.asyncio
async def test_submit_defaults_when_optional_fields_missing(store, ai_settings):
  saved, _ = await service.submit_client_transcription({"id": "t2", "segments": [], "text": "fallback"}, USER)
  assert saved["metadata"]["title"] == "Reunión"
  assert saved["language"] == "es"
  assert saved["segments"] == []
  assert saved["text"] == "fallback"


@pytest.fixture
def summarizer_stub(monkeypatch):
  state = SimpleNamespace(error=None, calls=[])

  async def fake(segments, title, user_id):
    state.calls.append((title, user_id))
    if state.error:
      raise state.error
    return SimpleNamespace(model_dump=lambda: {"summary_text": "resumen"})

  monkeypatch.setattr(service, "summarize_transcript", fake)
  return state


@pytest.mark.asyncio
async def test_submit_generates_summary(store, ai_settings, summarizer_stub):
  saved, summary = await service.submit_client_transcription(_payload(generate_summary_now=True), USER)
  assert summary == {"summary_text": "resumen"}
  assert saved["summary_status"] == "done" and saved["summary"] == summary
  assert summarizer_stub.calls == [("Daily", "u1")]


@pytest.mark.asyncio
async def test_submit_summary_not_attempted_without_segments(store, ai_settings, summarizer_stub):
  saved, summary = await service.submit_client_transcription(
    _payload(generate_summary_now=True, segments=[]), USER
  )
  assert summary is None and summarizer_stub.calls == []
  assert saved["summary_status"] == "pending"


@pytest.mark.parametrize(
  "error,message",
  [(RuntimeError("fallo LLM"), "fallo LLM"), (SimpleNamespace(), None)],
)
@pytest.mark.asyncio
async def test_submit_summary_failure_is_recorded(store, ai_settings, summarizer_stub, error, message):
  class WithDetail(Exception):
    detail = "detalle HTTP"

  summarizer_stub.error = WithDetail() if message is None else error
  saved, summary = await service.submit_client_transcription(_payload(generate_summary_now=True), USER)
  assert summary is None
  assert saved["summary_status"] == "failed"
  assert saved["summary_error"] == (message or "detalle HTTP")


@pytest.mark.asyncio
async def test_submit_summary_cancellation_propagates(store, ai_settings, summarizer_stub):
  summarizer_stub.error = asyncio.CancelledError()
  with pytest.raises(asyncio.CancelledError):
    await service.submit_client_transcription(_payload(generate_summary_now=True), USER)


# --- generate_summary ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_summary_success(store, summarizer_stub, monkeypatch):
  store["t1"] = {"id": "t1", "summary_status": "failed", "summary_error": "old"}
  captured = {}

  async def fake(segments, title, feature, user_id):
    captured.update(segments=segments, title=title, feature=feature, user_id=user_id)
    return SimpleNamespace(model_dump=lambda: {"summary_text": "ok"})

  monkeypatch.setattr(service, "summarize_transcript", fake)
  record = {"id": "t1", "segments": [{"text": "x"}], "metadata": {"title": "Kickoff"}}
  summary, updated = await service.generate_summary(record, USER, None)
  assert summary.model_dump() == {"summary_text": "ok"}
  assert captured["feature"] == "transcript_summary_standard_meeting" and captured["title"] == "Kickoff"
  assert updated["summary_status"] == "done" and updated["summary_error"] is None
  assert updated["summary"] == {"summary_text": "ok"}


@pytest.mark.asyncio
async def test_generate_summary_returns_input_record_when_missing_from_store(store, monkeypatch):
  async def fake(segments, title, feature, user_id):
    return SimpleNamespace(model_dump=lambda: {})

  monkeypatch.setattr(service, "summarize_transcript", fake)
  record = {"id": "ghost"}
  _, updated = await service.generate_summary(record, USER, "custom")
  assert updated is record


@pytest.mark.parametrize("error", [RuntimeError("x"), asyncio.CancelledError()])
@pytest.mark.asyncio
async def test_generate_summary_failure_marks_failed_and_reraises(store, monkeypatch, error):
  store["t1"] = {"id": "t1"}

  async def fake(segments, title, feature, user_id):
    raise error

  monkeypatch.setattr(service, "summarize_transcript", fake)
  with pytest.raises(type(error)):
    await service.generate_summary({"id": "t1", "segments": []}, USER, None)
  assert store["t1"]["summary_status"] == "failed"


# --- save_to_knowledge_base ---------------------------------------------------------------------


@pytest.fixture
def ingest(monkeypatch):
  calls: list[dict] = []

  def fake_ingest(**kwargs):
    calls.append(kwargs)
    return {"id": "doc-9"}

  import app.context.knowledge as knowledge

  monkeypatch.setattr(knowledge, "ingest_document", fake_ingest)
  return calls


@pytest.mark.asyncio
async def test_save_to_knowledge_with_summary(store, ingest):
  store["t1"] = {"id": "t1"}
  record = {
    "id": "t1",
    "metadata": {"title": "Kickoff"},
    "summary": {"summary_text": "Todo bien", "participants": ["Ana", "Luis"], "decisions": ["Usar X"], "topics": []},
    "segments": [{"start": 0, "end": 2, "speaker": "Ana", "speaker_id": "S1", "text": "hola", "text_raw": "hola"}],
  }
  result = await service.save_to_knowledge_base(record, custom_tags=["proyecto", "reunion"])
  assert result["ok"] is True and result["document_id"] == "doc-9"
  call = ingest[0]
  assert call["filename"] == "Kickoff.txt"
  assert sorted(call["tags"]) == ["proyecto", "reunion", "transcripcion"]
  text = call["raw"].decode("utf-8")
  assert "Resumen Ejecutivo" in text and "Todo bien" in text
  assert "Participantes: Ana, Luis" in text and "Decisiones: Usar X" in text
  assert "Temas:" not in text
  assert "Diálogo Completo Transcrito" in text and "[00:00]" in text and "hola" in text
  assert store["t1"]["saved_to_knowledge"] is True and store["t1"]["document_id"] == "doc-9"


@pytest.mark.asyncio
async def test_save_to_knowledge_without_summary_keeps_txt_name(store, ingest):
  store["t1"] = {"id": "t1"}
  record = {"id": "t1", "metadata": {"title": "notas.TXT"}, "segments": [], "turn_gap_s": 3}
  await service.save_to_knowledge_base(record)
  assert ingest[0]["filename"] == "notas.TXT"
  assert sorted(ingest[0]["tags"]) == ["reunion", "transcripcion"]
  assert "Resumen Ejecutivo" not in ingest[0]["raw"].decode("utf-8")
