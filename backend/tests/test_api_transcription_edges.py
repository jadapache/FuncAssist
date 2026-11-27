"""Audio extraction endpoint failures and the desktop-mode file endpoints."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import transcription as api
from app.core.exceptions import FFmpegError
from app.features.transcription.errors import TranscriptionJobError
from app.main import create_app


@pytest.fixture
def client():
  return TestClient(create_app())


@pytest.fixture
def temp_dirs(monkeypatch):
  created = []
  real = api.tempfile.mkdtemp

  def tracking(**kwargs):
    path = real(**kwargs)
    created.append(Path(path))
    return path

  monkeypatch.setattr(api.tempfile, "mkdtemp", tracking)
  return created


def _post(client, name="clip.mp4", data=b"media"):
  return client.post("/api/transcription/extract-audio", files={"file": (name, data)})


# --- extract-audio ------------------------------------------------------------------


def test_unsupported_containers_are_refused(client, temp_dirs):
  response = _post(client, "notes.txt")
  assert response.status_code == 415 and response.json()["detail"] == "Formato '.txt' no soportado."
  assert temp_dirs == []


def test_a_successful_extraction_returns_the_wav_and_cleans_up_afterwards(client, temp_dirs, monkeypatch):
  def fake(source, output):
    assert source.name == "input.mp4" and source.read_bytes() == b"media"
    output.write_bytes(b"RIFFwav")
    return output

  monkeypatch.setattr(api, "_process_audio_extraction", fake)
  response = _post(client)
  assert response.status_code == 200 and response.content == b"RIFFwav"
  assert response.headers["content-type"] == "audio/wav" and "audio_16k.wav" in response.headers["content-disposition"]
  assert not temp_dirs[0].exists()


def test_ffmpeg_failures_are_unprocessable_and_clean_up(client, temp_dirs, monkeypatch):
  def fake(source, output):
    raise FFmpegError("conversion failed")

  monkeypatch.setattr(api, "_process_audio_extraction", fake)
  response = _post(client)
  assert response.status_code == 422 and response.json()["detail"].startswith("Error de FFmpeg al extraer audio: ")
  assert not temp_dirs[0].exists()


def test_an_oversized_upload_keeps_its_own_error_and_cleans_up(client, temp_dirs, monkeypatch):
  monkeypatch.setattr(api.config, "max_upload_bytes", lambda: 1)
  response = _post(client, data=b"too big")
  assert response.status_code == 413 and "0 MB" in response.json()["detail"]
  assert not temp_dirs[0].exists()


@pytest.mark.parametrize("message, status", [("FFmpeg exploded", 422), ("bad AUDIO stream", 422), ("disk on fire", 500)])
def test_other_failures_are_classified_by_their_message(client, temp_dirs, monkeypatch, message, status):
  def fake(source, output):
    raise RuntimeError(message)

  monkeypatch.setattr(api, "_process_audio_extraction", fake)
  response = _post(client)
  assert response.status_code == status and response.json()["detail"] == f"Error al procesar archivo: {message}"
  assert not temp_dirs[0].exists()


def test_a_missing_or_unchanged_result_is_unprocessable(client, temp_dirs, monkeypatch):
  monkeypatch.setattr(api, "_process_audio_extraction", lambda source, output: output)
  assert _post(client).status_code == 422
  assert not temp_dirs[0].exists()
  monkeypatch.setattr(api, "_process_audio_extraction", lambda source, output: source)
  response = _post(client)
  assert response.status_code == 422 and "No se pudo extraer la pista de audio" in response.json()["detail"]
  assert not temp_dirs[1].exists()


def test_the_audio_failure_mapping_keeps_http_errors_as_they_are():
  passthrough = HTTPException(status_code=409, detail="x")
  assert api._audio_failure(passthrough) is passthrough
  assert api._audio_failure(FFmpegError("boom")).status_code == 422


def test_extraction_unwraps_the_tuple_the_converter_returns(tmp_path, monkeypatch):
  import app.features.transcription.ffmpeg_utils as ffmpeg_utils

  monkeypatch.setattr(ffmpeg_utils, "extract_audio_track", lambda i, o, validate: (o, True))
  assert api._process_audio_extraction(tmp_path / "a.mp4", tmp_path / "o.wav") == tmp_path / "o.wav"
  monkeypatch.setattr(ffmpeg_utils, "extract_audio_track", lambda i, o, validate: o)
  assert api._process_audio_extraction(tmp_path / "a.mp4", tmp_path / "o.wav") == tmp_path / "o.wav"


# --- desktop endpoints --------------------------------------------------------------


@pytest.mark.asyncio
async def test_picking_a_file_reports_a_cancelled_dialog(monkeypatch):
  monkeypatch.setattr(api, "open_native_file_dialog_sync", lambda: None)
  assert await api.pick_local_file() == {"ok": False, "cancelled": True, "message": "No se seleccionó ningún archivo."}


@pytest.mark.asyncio
async def test_picking_a_file_outside_the_allowed_roots_is_forbidden(monkeypatch):
  monkeypatch.setattr(api, "open_native_file_dialog_sync", lambda: "/etc/passwd")
  monkeypatch.setattr(api.storage, "is_allowed_local_path", lambda path: False)
  with pytest.raises(HTTPException) as raised:
    await api.pick_local_file()
  assert raised.value.status_code == 403 and raised.value.detail == "Ruta local no permitida."


@pytest.mark.asyncio
async def test_a_picked_file_is_described(monkeypatch):
  monkeypatch.setattr(api, "open_native_file_dialog_sync", lambda: "/media/a.mp3")
  monkeypatch.setattr(api.storage, "is_allowed_local_path", lambda path: path == Path("/media/a.mp3"))
  monkeypatch.setattr(api, "inspect_local_file", lambda path: {"name": "a.mp3", "path": path})
  assert await api.pick_local_file() == {"ok": True, "selected": True, "name": "a.mp3", "path": "/media/a.mp3"}


@pytest.mark.asyncio
async def test_inspecting_a_file_needs_an_allowed_path(monkeypatch):
  monkeypatch.setattr(api.storage, "is_allowed_local_path", lambda path: str(path).startswith("/media"))
  monkeypatch.setattr(api, "inspect_local_file", lambda path: {"name": path})
  assert await api.inspect_file(SimpleNamespace(file_path="/media/a.mp3")) == {"name": "/media/a.mp3"}
  with pytest.raises(HTTPException) as raised:
    await api.inspect_file(SimpleNamespace(file_path="/etc/passwd"))
  assert raised.value.status_code == 403


@pytest.mark.asyncio
async def test_a_local_path_is_registered_as_a_transcription(monkeypatch):
  saved = []
  entry = {"size_bytes": 7}

  async def save(record):
    saved.append(record)

  monkeypatch.setattr(api.storage, "local_media_entry", lambda tid, path, title, description: {**entry, "id": tid, "path": path})
  monkeypatch.setattr(api.service, "media_entry_for_upload", lambda e, user: {"entry": e, "user": user["id"]})
  monkeypatch.setattr(api.records, "save_record", save)
  req = SimpleNamespace(transcription_id="custom-id-123", local_path="/media/a.mp3", title="T", description="d")
  body = await api.register_local_path(req, {"id": "u1"})
  assert body["ok"] is True and body["media_id"] == body["transcription_id"] == "custom-id-123" and body["size"] == 7
  assert body["message"] == "Archivo local vinculado con éxito." and saved == [{"entry": body["entry"], "user": "u1"}]


@pytest.mark.asyncio
async def test_registering_a_forbidden_path_is_an_http_error(monkeypatch):
  def refuse(*args):
    raise TranscriptionJobError("bad_request", "Ruta local no permitida.")

  monkeypatch.setattr(api.storage, "local_media_entry", refuse)
  req = SimpleNamespace(transcription_id=None, local_path="/x", title="T", description="")
  with pytest.raises(HTTPException) as raised:
    await api.register_local_path(req, {"id": "u1"})
  assert raised.value.status_code == 400
