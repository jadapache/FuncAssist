"""Transcription feature tests: API ownership, browser submissions, speaker edits, SSE and jobs.

Jobs run the real pipeline with ffmpeg and the speech provider replaced by fakes.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user
from app.api.transcription_stream import progress_events
from app.core.exceptions import FFmpegError
from app.features.inventario.docx_builder import create_inventario_docx
from app.features.levantamiento.docx_builder import create_levantamiento_docx
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


def _as_other_user():
  main_module.app.dependency_overrides[get_current_user] = lambda: OTHER_USER


def _upload(client: TestClient, wav: bytes, title: str = "Reunión de Planeación") -> str:
  resp = client.post("/api/transcription/upload", files={"file": ("sesion.wav", wav, "audio/wav")}, data={"title": title})
  assert resp.status_code == 200, resp.text
  return resp.json()["transcription_id"]


def _submit(client: TestClient, tid: str = "client-transcription-001", segments: list[dict] | None = None) -> dict:
  payload = {
    "id": tid,
    "title": "Transcripción de Navegador",
    "text": "",
    "duration_seconds": 12.0,
    "language": "es",
    "generate_summary_now": False,
    "segments": segments or [
      {"start": 0.0, "end": 4.0, "speaker": "Participante 1", "text": "Eh, bueno, revisemos el el inventario, ¿no?"},
      {"start": 4.0, "end": 8.0, "speaker": "Participante 1", "text": "[música] Este documento define el alcance."},
    ],
  }
  resp = client.post("/api/transcription/submit-client-transcription", json=payload)
  assert resp.status_code == 200, resp.text
  return resp.json()["transcription"]


class TestUploadAndOwnership:
  def test_upload_creates_owned_record(self, client, sample_wav_bytes):
    tid = _upload(client, sample_wav_bytes)
    result = client.get(f"/api/transcription/result/{tid}").json()
    assert result["metadata"]["title"] == "Reunión de Planeación"
    assert result["has_media"] is True
    assert "user_id" not in result

  def test_other_user_cannot_see_or_touch_it(self, client, sample_wav_bytes):
    tid = _upload(client, sample_wav_bytes)
    _as_other_user()
    for method, url in [
      ("get", f"/api/transcription/result/{tid}"),
      ("get", f"/api/transcription/status/{tid}"),
      ("get", f"/api/transcription/progress-stream/{tid}"),
      ("post", f"/api/transcription/cancel/{tid}"),
      ("delete", f"/api/transcription/{tid}"),
    ]:
      assert getattr(client, method)(url).status_code == 404, url
    assert all(t["id"] != tid for t in client.get("/api/transcription/list").json()["transcriptions"])

  def test_unsupported_format_is_rejected(self, client):
    resp = client.post("/api/transcription/upload", files={"file": ("notes.pdf", b"%PDF", "application/pdf")})
    assert resp.status_code == 415

  def test_upload_size_limit(self, client, sample_wav_bytes, monkeypatch):
    monkeypatch.setattr(config, "max_upload_bytes", lambda: 1000)
    resp = client.post("/api/transcription/upload", files={"file": ("big.wav", sample_wav_bytes, "audio/wav")})
    assert resp.status_code == 413


class TestClientSubmission:
  def test_cleanup_keeps_literal_text(self, client):
    record = _submit(client)
    first, second = record["segments"]
    assert first["text_raw"] == "Eh, bueno, revisemos el el inventario, ¿no?"
    assert first["text"] == "Revisemos el inventario."
    assert second["text"] == "Este documento define el alcance."
    assert record["source"] == "browser"
    assert record["diarization"] == "none"
    assert record["cleanup"]["fillers_removed"] >= 3
    assert record["summary_status"] == "skipped"

  def test_browser_diarization_keeps_speaker_ids(self, client):
    payload = {
      "id": "client-diarized-0001",
      "title": "Reunión diarizada",
      "duration_seconds": 8.0,
      "generate_summary_now": False,
      "diarization": "browser",
      "segments": [
        {"start": 0.0, "end": 3.0, "speaker_id": "S1", "text": "Buenos días."},
        {"start": 3.0, "end": 6.0, "speaker_id": "S2", "text": "Hola, empecemos."},
      ],
    }
    record = client.post("/api/transcription/submit-client-transcription", json=payload).json()["transcription"]
    assert record["diarization"] == "browser"
    assert [s["speaker_id"] for s in record["segments"]] == ["S1", "S2"]
    assert record["speakers"]["S2"]["name"] == "Participante 2"

  def test_speaker_ids_are_ignored_without_browser_diarization(self, client):
    payload = {
      "id": "client-undiarized-0001",
      "title": "Sin diarización",
      "generate_summary_now": False,
      "segments": [{"start": 0.0, "end": 3.0, "speaker_id": "S7", "text": "Hola."}],
    }
    record = client.post("/api/transcription/submit-client-transcription", json=payload).json()["transcription"]
    assert record["diarization"] == "none" and set(record["speakers"]) == {"S1"}


class TestSpeakerEditing:
  def test_rename_assign_split_and_mark(self, client):
    tid = _submit(client)["id"]
    renamed = client.patch(f"/api/transcription/{tid}/speakers", json={"rename": {"S1": "Ana"}}).json()["transcription"]
    assert {s["speaker"] for s in renamed["segments"]} == {"Ana"}

    seg_id = renamed["segments"][1]["id"]
    assigned = client.patch(
      f"/api/transcription/{tid}/segments/{seg_id}", json={"new_speaker_name": "Luis", "marked": True}
    ).json()["transcription"]
    assert assigned["segments"][1]["speaker"] == "Luis" and assigned["segments"][1]["marked"] is True
    assert assigned["diarization"] == "manual"

    split = client.post(f"/api/transcription/{tid}/segments/{seg_id}/split", json={"at": 5}).json()["transcription"]
    assert len(split["segments"]) == 3

    merged = client.patch(
      f"/api/transcription/{tid}/speakers", json={"merge": [{"from": "S2", "into": "S1"}]}
    ).json()["transcription"]
    assert set(merged["speakers"]) == {"S1"}

  def test_invalid_edit_is_400(self, client):
    tid = _submit(client)["id"]
    resp = client.patch(f"/api/transcription/{tid}/speakers", json={"rename": {"S9": "Nadie"}})
    assert resp.status_code == 400


class TestStatusAndStream:
  def test_cancel_stale_job_keeps_record(self, client, sample_wav_bytes):
    tid = _upload(client, sample_wav_bytes)
    assert client.post(f"/api/transcription/cancel/{tid}").json()["ok"] is True
    status = client.get(f"/api/transcription/status/{tid}").json()
    assert status["stage"] == "cancelled" and status["error_code"] == "cancelled"

  @pytest.mark.asyncio
  async def test_sse_v2_frames(self):
    snapshot = {"id": "j1", "stage": "complete", "status": "complete", "progress": 100, "seq": 7, "summary_status": "done"}
    frames = [frame async for frame in progress_events("j1", snapshot, "v2")]
    assert frames == [frames[0]]
    assert frames[0].startswith("id: 7\nevent: progress\ndata: ")

  @pytest.mark.asyncio
  async def test_sse_v1_frames_are_data_only(self):
    snapshot = {"id": "j2", "stage": "failed", "seq": 3}
    frames = [frame async for frame in progress_events("j2", snapshot, "v1")]
    assert frames[0].startswith("data: {")


class TestExtraction:
  def test_extract_audio_endpoint_success(self, client, monkeypatch):
    def fake_extract(media_path, output_wav_path, validate=True):
      output_wav_path.write_bytes(b"RIFFdummywavdata")
      return output_wav_path, True

    monkeypatch.setattr("app.features.transcription.ffmpeg_utils.extract_audio_track", fake_extract)
    resp = client.post("/api/transcription/extract-audio", files={"file": ("reunion.mp3", b"dummy", "audio/mpeg")})
    assert resp.status_code == 200
    assert resp.content == b"RIFFdummywavdata"

  def test_extract_audio_ffmpeg_failure_is_422(self, client):
    with patch("app.api.transcription._process_audio_extraction", side_effect=FFmpegError("corrupt")):
      resp = client.post("/api/transcription/extract-audio", files={"file": ("damaged.mp3", b"x", "audio/mpeg")})
    assert resp.status_code == 422


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
  async def test_retry_reuses_finished_chunks(self, fake_pipeline, monkeypatch):
    monkeypatch.setattr(config, "chunk_seconds", lambda: 60.0)
    monkeypatch.setattr(config, "chunk_concurrency", lambda provider: 1)
    fake_pipeline["silences"] = []
    await _create_uploaded_record("job-retry-0001")
    FakeSpeechClient.fail_on["chunk_001"] = TranscriptionJobError("rate_limit")
    manager = JobManager()
    failed = await _run_job(manager, "job-retry-0001")
    assert failed["status"] == "failed" and failed["retryable"] is True
    assert FakeSpeechClient.calls == ["chunk_000", "chunk_001"]

    FakeSpeechClient.calls = []
    done = await _run_job(manager, "job-retry-0001")
    assert done["status"] == "complete"
    assert "chunk_000" not in FakeSpeechClient.calls
    assert FakeSpeechClient.calls[0] == "chunk_001"

  @pytest.mark.asyncio
  async def test_cancel_running_job(self, fake_pipeline):
    await _create_uploaded_record("job-cancel-0001")
    FakeSpeechClient.block = asyncio.Event()
    manager = JobManager()
    await manager.start("job-cancel-0001", OWNER_ID, JobOptions(summarize=False), title="Reunión")
    task = manager._tasks["job-cancel-0001"]
    for _ in range(200):
      if FakeSpeechClient.calls:
        break
      await asyncio.sleep(0.01)
    assert await manager.cancel("job-cancel-0001") is True
    await task
    record = await records.get_record("job-cancel-0001")
    assert record is not None and record["status"] == "cancelled"
    assert record["progress"]["error_code"] == "cancelled"


class TestDocuments:
  def test_docx_report_generation(self):
    md_content = "# Levantamiento\n- Punto 1\n- Requisito 2"
    assert len(create_inventario_docx(md_content, title="Inventario")) > 500
    assert len(create_levantamiento_docx(md_content, title="Levantamiento")) > 500
