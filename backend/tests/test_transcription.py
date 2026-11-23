"""Transcription feature tests: API ownership, browser submissions, speaker edits, SSE and jobs.

Jobs run the real pipeline with ffmpeg and the speech provider replaced by fakes.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user
from app.features.transcription import config, media, metrics, pipeline, records, storage
from app.features.transcription.errors import TranscriptionJobError
from app.features.transcription.jobs import JobManager
from app.features.transcription.pipeline import JobOptions
from app.features.transcription.whisper_cloud import SpeechTarget

OTHER_USER = {"id": "other-user", "username": "otro", "role": "user", "status": "approved"}
OWNER_ID = "test-user-id"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
  monkeypatch.setattr(storage, "TRANSCRIPTIONS_DIR", tmp_path / "transcriptions")
  monkeypatch.setattr(metrics, "LOG_DIR", tmp_path / "logs")
  return tmp_path


@pytest.fixture
def client():
  return TestClient(main_module.app)


@pytest.fixture
def sample_wav_bytes():
  riff_header = b"RIFF" + (36 + 32000).to_bytes(4, "little") + b"WAVE"
  fmt_chunk = b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
  fmt_chunk += (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
  return riff_header + fmt_chunk + b"data" + (32000).to_bytes(4, "little") + (b"\x00" * 32000)


class TestOwnership:
  def test_other_user_cannot_see_or_touch_it(self, client, sample_wav_bytes):
    resp = client.post(
      "/api/transcription/upload",
      files={"file": ("sesion.wav", sample_wav_bytes, "audio/wav")},
      data={"title": "Reunión de Planeación", "consent_confirmed": "true"},
    )
    assert resp.status_code == 200, resp.text
    tid = resp.json()["transcription_id"]

    main_module.app.dependency_overrides[get_current_user] = lambda: OTHER_USER
    for method, url in [
      ("get", f"/api/transcription/result/{tid}"),
      ("get", f"/api/transcription/status/{tid}"),
      ("get", f"/api/transcription/progress-stream/{tid}"),
      ("post", f"/api/transcription/cancel/{tid}"),
      ("delete", f"/api/transcription/{tid}"),
    ]:
      assert getattr(client, method)(url).status_code == 404, url
    assert all(t["id"] != tid for t in client.get("/api/transcription/list").json()["transcriptions"])




















# --- jobs with the real pipeline and fake ffmpeg / provider ------------------------------------


class FakeSpeechClient:
  calls: list[str] = []
  fail_on: dict[str, TranscriptionJobError] = {}
  block: asyncio.Event | None = None

  def __init__(self, target: SpeechTarget) -> None:
    self.target = target
    self.retries = 0

  async def __aenter__(self) -> "FakeSpeechClient":
    return self

  async def __aexit__(self, *exc: object) -> None:
    return None

  async def transcribe(self, path, *, language=None, prompt=""):
    FakeSpeechClient.calls.append(path.stem)
    if FakeSpeechClient.block is not None:
      await FakeSpeechClient.block.wait()
    error = FakeSpeechClient.fail_on.pop(path.stem, None)
    if error:
      raise error
    return {
      "language": "es",
      "segments": [
        {"start": 0.5, "end": 3.0, "text_raw": "Eh, bueno, revisemos el inventario.", "_metrics": {}},
        {"start": 3.0, "end": 5.0, "text_raw": "Subtítulos realizados por la comunidad de Amara.org", "_metrics": {}},
      ],
    }


@pytest.fixture
def fake_pipeline(monkeypatch, isolated_dirs):
  FakeSpeechClient.calls = []
  FakeSpeechClient.fail_on = {}
  FakeSpeechClient.block = None
  state = {"duration": 150.0, "silences": [(100.0, 110.0)]}

  async def probe(path):
    return state["duration"]

  async def extract(source, dest, duration, on_progress=None):
    if on_progress:
      on_progress(0.5)
    dest.write_bytes(b"RIFF")
    return dest

  async def noise(wav):
    return -60.0

  async def silences(wav, threshold, min_silence, duration):
    return state["silences"]

  async def export(wav, regions, dest):
    dest.write_bytes(b"ID3")
    return dest

  monkeypatch.setattr(media, "probe_duration", probe)
  monkeypatch.setattr(media, "extract_audio", extract)
  monkeypatch.setattr(media, "measure_noise_floor", noise)
  monkeypatch.setattr(media, "detect_silences", silences)
  monkeypatch.setattr(media, "export_regions", export)
  monkeypatch.setattr(pipeline, "SpeechClient", FakeSpeechClient)
  monkeypatch.setattr(pipeline, "resolve_speech_target", lambda user_id: SpeechTarget("groq", "k", "whisper-large-v3"))
  monkeypatch.setattr(pipeline, "resolve_diarization_target", lambda user_id, requested: None)
  monkeypatch.setattr(pipeline, "_user_settings", lambda user_id: {})
  return state


async def _create_uploaded_record(tid: str) -> None:
  folder = storage.get_transcription_dir(tid)
  folder.mkdir(parents=True, exist_ok=True)
  path = folder / "media.mp3"
  path.write_bytes(b"ID3media")
  entry = {
    "id": tid, "transcription_id": tid, "original_filename": "reunion.mp3", "filename": "reunion.mp3",
    "stored_filename": "media.mp3", "path": str(path), "size_bytes": 8, "file_size_formatted": "8 B",
    "hash": "", "is_video": False, "title": "Reunión", "description": "", "created_at": "2026-11-21T00:00:00+00:00",
  }
  await records.save_record(storage.initial_record(entry, OWNER_ID))


async def _run_job(manager: JobManager, tid: str, **options: Any) -> dict[str, Any]:
  await manager.start(tid, OWNER_ID, JobOptions(summarize=False, **options), title="Reunión")
  task = manager._tasks[tid]
  await task
  record = await records.get_record(tid)
  assert record is not None
  return record


class TestJobs:
  @pytest.mark.asyncio
  async def test_job_completes_with_clean_text_and_real_progress(self, fake_pipeline):
    await _create_uploaded_record("job-complete-0001")
    record = await _run_job(JobManager(), "job-complete-0001")
    assert record["status"] == "complete"
    assert record["progress"]["stage"] == "complete" and record["progress"]["progress"] == 100
    assert record["silence_trimmed_s"] > 0
    assert record["diarization"] == "none" and set(record["speakers"]) == {"S1"}
    texts = [s["text"] for s in record["segments"]]
    assert "Revisemos el inventario." in texts
    assert not any("Amara" in (s["text_raw"] or "") for s in record["segments"])
    assert record["cleanup"]["hallucinations_removed"] >= 1
    assert not storage.chunks_dir("job-complete-0001").exists()

  @pytest.mark.asyncio
  async def test_provider_error_marks_job_failed_with_code(self, fake_pipeline):
    await _create_uploaded_record("job-failed-0001")
    FakeSpeechClient.fail_on["chunk_000"] = TranscriptionJobError("auth_error")
    record = await _run_job(JobManager(), "job-failed-0001")
    assert record["status"] == "failed"
    assert record["error_code"] == "auth_error"
    assert record["progress"]["stage"] == "failed" and record["progress"]["retryable"] is False

  @pytest.mark.asyncio
  async def test_retry_reuses_finished_chunks_and_stops_after_failure(self, fake_pipeline, monkeypatch):
    monkeypatch.setattr(config, "chunk_seconds", lambda: 60.0)
    monkeypatch.setattr(config, "chunk_concurrency", lambda provider: 1)
    fake_pipeline["silences"] = []
    await _create_uploaded_record("job-retry-0001")
    FakeSpeechClient.fail_on["chunk_001"] = TranscriptionJobError("rate_limit")
    manager = JobManager()
    failed = await _run_job(manager, "job-retry-0001")
    assert failed["status"] == "failed" and failed["retryable"] is True
    # No request reaches the provider after a chunk fails.
    assert FakeSpeechClient.calls == ["chunk_000", "chunk_001"]

    FakeSpeechClient.calls = []
    done = await _run_job(manager, "job-retry-0001")
    assert done["status"] == "complete"
    assert "chunk_000" not in FakeSpeechClient.calls
    assert FakeSpeechClient.calls[0] == "chunk_001"


def test_upload_requires_recording_consent(client, sample_wav_bytes):
  resp = client.post(
    "/api/transcription/upload",
    files={"file": ("sesion.wav", sample_wav_bytes, "audio/wav")},
    data={"title": "Sin consentimiento"},
  )
  assert resp.status_code == 400
  assert "1581" in resp.json()["detail"]
