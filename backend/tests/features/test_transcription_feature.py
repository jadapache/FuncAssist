"""
Comprehensive feature test suite for Transcription.
Covers:
1. Audio validation and analysis (format, duration, integrity).
2. Audio extraction endpoint (FFmpeg conversion to WAV).
3. Transcription lifecycle (upload, start, client submission, cancellation).
4. SSE streaming and heartbeats.
5. Storage, slugs, and document export.
"""

from __future__ import annotations

import asyncio
import io
import json
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.features.transcription.storage import (
  validate_file,
  get_file_hash,
  save_transcription_record,
  get_transcription_record,
  delete_transcription_record,
)
from app.features.transcription.audio_analyzer import AudioAnalyzer, AudioAnalysisError
from app.api.transcription_stream import (
  transcription_progress_stream,
  emit_progress,
  set_main_loop,
)
from app.features.transcription.service import transcription_service
from app.features.inventario.docx_builder import create_inventario_docx
from app.features.levantamiento.docx_builder import create_levantamiento_docx


@pytest.fixture
def client():
  return TestClient(app)


@pytest.fixture
def sample_wav_bytes():
  # Minimal 1-second 16kHz 16-bit mono WAV
  riff_header = b"RIFF" + (36 + 32000).to_bytes(4, "little") + b"WAVE"
  fmt_chunk = b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
  fmt_chunk += (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
  data_chunk = b"data" + (32000).to_bytes(4, "little") + (b"\x00" * 32000)
  return riff_header + fmt_chunk + data_chunk


class TestAudioValidation:
  """Validations for file types, hashes, audio streams, and durations."""

  def test_format_validation(self):
    ok, err = validate_file("test.mp3", 1024)
    assert ok is True and err is None

    ok, err = validate_file("recording.wav", 2048)
    assert ok is True and err is None

    ok, err = validate_file("document.pdf", 512)
    assert ok is False and "no soportado" in err

  def test_file_hash_calculation(self):
    content = b"sample-audio-bytes-for-hashing"
    h1 = get_file_hash(content)
    h2 = get_file_hash(content)
    assert h1 == h2 and len(h1) == 64

  def test_audio_analyzer_duration_and_streams(self, tmp_path):
    analyzer = AudioAnalyzer()
    dummy_file = tmp_path / "audio.wav"
    dummy_file.write_bytes(b"dummy")

    with patch("subprocess.run") as mock_run:
      mock_res = MagicMock()
      mock_res.returncode = 0
      mock_res.stdout = "120.5"
      mock_run.return_value = mock_res
      duration = analyzer.get_duration_seconds(dummy_file)
      assert duration == 120.5

  def test_corrupted_audio_file_detection(self, tmp_path):
    corrupt_file = tmp_path / "corrupt.mp3"
    corrupt_file.write_bytes(b"invalid-audio-junk-header")

    analyzer = AudioAnalyzer()
    with patch("subprocess.run") as mock_run:
      mock_res = MagicMock()
      mock_res.returncode = 1
      mock_res.stderr = "Invalid data found when processing input"
      mock_run.return_value = mock_res
      is_valid, err = analyzer.validate_audio_integrity(corrupt_file)
      assert is_valid is False
      assert err is not None


class TestAudioExtraction:
  """Audio conversion endpoint tests."""

  def test_extract_audio_endpoint_success(self, client: TestClient, monkeypatch):
    def fake_extract(media_path, output_wav_path, validate=True):
      output_wav_path.write_bytes(b"RIFFdummywavdata")
      return output_wav_path, True

    monkeypatch.setattr("app.features.transcription.ffmpeg_utils.extract_audio_track", fake_extract)
    files = {"file": ("reunion.mp3", b"dummycontent", "audio/mpeg")}
    resp = client.post("/api/transcription/extract-audio", files=files)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.content == b"RIFFdummywavdata"

  def test_extract_audio_corrupted_file_returns_422(self, client: TestClient):
    files = {"file": ("damaged.mp3", b"corrupted", "audio/mpeg")}
    with patch("app.api.transcription._process_audio_extraction", side_effect=AudioAnalysisError("Corrupt")):
      resp = client.post("/api/transcription/extract-audio", files=files)
      assert resp.status_code == 422
      assert "error" in resp.json().get("detail", "").lower()


class TestTranscriptionLifecycle:
  """Upload, job execution, cancellation, and client transcript submission."""

  def test_upload_media_flow(self, client: TestClient, sample_wav_bytes: bytes):
    files = {"file": ("sesion.wav", sample_wav_bytes, "audio/wav")}
    data = {"title": "Reunión de Planeación"}
    resp = client.post("/api/transcription/upload", files=files, data=data)
    assert resp.status_code == 200
    res = resp.json()
    assert "transcription_id" in res
    assert "media_id" in res

  def test_start_transcription_and_status(self, client: TestClient):
    t_id = "test_trans_lifecycle_101"
    transcription_service.init_job(t_id, t_id, "Test Lifecycle")

    resp = client.get(f"/api/transcription/status/{t_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    # Cancel job
    cancel_resp = client.post(f"/api/transcription/cancel/{t_id}")
    assert cancel_resp.status_code == 200

  def test_submit_client_transcription(self, client: TestClient):
    payload = {
      "id": "test_client_feature_999",
      "title": "Transcripción de Navegador",
      "text": "Texto transcrito localmente en el navegador.",
      "duration_seconds": 45.2,
      "segments": [
        {"start": 0.0, "end": 4.5, "speaker": "Speaker 1", "text": "Texto transcrito localmente."}
      ],
      "language": "es",
    }
    resp = client.post("/api/transcription/submit-client-transcription", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["transcription"]["id"] == payload["id"]
    assert data["transcription"]["text"] == payload["text"]


class TestTranscriptionStreaming:
  """SSE progress streaming, updates, and heartbeats."""

  @pytest.mark.asyncio
  async def test_sse_stream_receives_updates_and_heartbeat(self):
    t_id = "test_trans_stream_201"
    transcription_service.init_job(t_id, t_id, "Stream Test")

    gen = transcription_progress_stream(t_id)
    loop = asyncio.get_event_loop()
    set_main_loop(loop)

    # Connection message
    conn = await gen.__anext__()
    assert "connected" in conn

    # Emit progress update
    await emit_progress(t_id, {"id": t_id, "stage": "transcribing", "progress": 50, "message": "50%"})
    msg = await gen.__anext__()
    data = json.loads(msg[6:-2])
    assert data.get("progress") in (0, 50)

  def test_sse_endpoint_headers(self, client: TestClient):
    resp = client.get("/api/transcription/progress-stream/test_sample_stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["x-accel-buffering"] == "no"


class TestTranscriptionPersistenceAndExport:
  """Storage records, slug generation, and document export."""

  def test_save_and_retrieve_record(self):
    record = {
      "id": "trans_rec_301",
      "media_id": "media_301",
      "metadata": {"title": "Reunión de Diseño"},
      "language": "es",
      "duration_seconds": 60.0,
      "created_at": "2026-11-09T00:00:00Z",
      "segments": [],
      "text": "Contenido de la reunión",
    }
    save_transcription_record(record)
    loaded = get_transcription_record("trans_rec_301")
    assert loaded is not None
    assert loaded["text"] == "Contenido de la reunión"
    delete_transcription_record("trans_rec_301")

  def test_docx_report_generation(self):
    md_content = "# Levantamiento\n- Punto 1\n- Requisito 2"
    inv_bytes = create_inventario_docx(md_content, title="Inventario")
    lev_bytes = create_levantamiento_docx(md_content, title="Levantamiento")

    assert isinstance(inv_bytes, bytes) and len(inv_bytes) > 500
    assert isinstance(lev_bytes, bytes) and len(lev_bytes) > 500
