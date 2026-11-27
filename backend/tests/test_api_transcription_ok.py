"""Response contracts and limits of the transcription endpoints: success flags, limits, cleanup and defaults."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.api import transcription as tr
from app.features.transcription.errors import TranscriptionJobError
from tests.test_api_transcription import USER_ID, _job_err, _own, _patch_upload, client, recs  # noqa: F401

# --- upload ---------------------------------------------------------------------------


def test_an_upload_without_the_consent_field_is_refused_and_one_with_it_succeeds(client, recs, monkeypatch):
  _patch_upload(monkeypatch)
  refused = client.post("/api/transcription/upload", files={"file": ("a.wav", b"abc")})
  assert refused.status_code == 400 and "Ley 1581" in refused.json()["detail"]
  accepted = client.post("/api/transcription/upload", files={"file": ("a.wav", b"abc")}, data={"consent_confirmed": "true"})
  assert accepted.json()["ok"] is True and accepted.json()["message"] == "Archivo multimedia subido con éxito."


# --- success flags --------------------------------------------------------------------


def test_starting_and_retrying_a_job_report_success(client, recs, monkeypatch):
  tid = _own(recs)

  async def start(record, user, options=None):
    return None

  monkeypatch.setattr(tr.service, "start_job", start)
  monkeypatch.setattr(tr.service, "retry_job", start)
  for url in (f"/api/transcription/transcribe/{tid}", f"/api/transcription/retry/{tid}"):
    body = client.post(url).json()
    assert body == {"ok": True, "status": "queued", "transcription_id": tid, "media_id": tid}


def test_a_client_transcription_reports_success(client, monkeypatch):
  async def submit(payload, user):
    return {"id": payload["id"]}, None

  monkeypatch.setattr(tr.service, "submit_client_transcription", submit)
  body = client.post("/api/transcription/submit-client-transcription", json={"id": "c1", "consent_confirmed": True}).json()
  assert body["ok"] is True and body["summary"] is None and body["message"] == "Transcripción del cliente registrada exitosamente."


def test_summaries_and_edits_report_success(client, recs, monkeypatch):
  tid = _own(recs)

  async def generate(record, user, feature):
    return {"summary_text": "ok"}, {**record}

  monkeypatch.setattr(tr.service, "generate_summary", generate)
  assert client.post(f"/api/transcription/generate-summary/{tid}").json()["ok"] is True
  assert client.put(f"/api/transcription/summary/{tid}", json={"summary": {"summary_text": "x"}}).json()["ok"] is True
  monkeypatch.setattr(tr.seg_ops, "edit_segment", lambda r, sid, **kw: r.update(seg=sid))
  assert client.patch(f"/api/transcription/{tid}/segments/seg_1", json={"text": "hola"}).json()["ok"] is True


# --- stats ----------------------------------------------------------------------------


def test_stats_read_between_one_and_five_thousand_entries_of_the_caller_only(client, monkeypatch):
  calls = []

  def read_entries(limit):
    calls.append(limit)
    return [{"user_id": USER_ID}, {"user_id": "other"}, {"user_id": "other"}]

  monkeypatch.setattr(tr.metrics, "read_entries", read_entries)
  monkeypatch.setattr(tr.metrics, "summarize", lambda entries: {"users": [e["user_id"] for e in entries]})
  body = client.get("/api/transcription/stats?limit=0").json()
  assert body == {"count": 1, "users": [USER_ID]}
  client.get("/api/transcription/stats?limit=-5")
  client.get("/api/transcription/stats?limit=3")
  client.get("/api/transcription/stats?limit=5000")
  client.get("/api/transcription/stats?limit=5001")
  assert calls == [1, 1, 3, 5000, 5000]


# --- extraction limits and cleanup ----------------------------------------------------


def _ok_extraction(monkeypatch):
  def ok(source: Path, output: Path):
    output.write_bytes(b"RIFFwav")
    return output

  monkeypatch.setattr(tr, "_process_audio_extraction", ok)


def test_an_upload_exactly_at_the_limit_is_accepted_and_one_byte_more_is_not(client, monkeypatch):
  _ok_extraction(monkeypatch)
  monkeypatch.setattr(tr.config, "max_upload_bytes", lambda: 4)
  assert client.post("/api/transcription/extract-audio", files={"file": ("a.mp4", b"1234")}).status_code == 200
  assert client.post("/api/transcription/extract-audio", files={"file": ("a.mp4", b"12345")}).status_code == 413


def test_the_size_limit_is_reported_in_megabytes(client, monkeypatch):
  monkeypatch.setattr(tr.config, "max_upload_bytes", lambda: 3 * 1024 * 1024)
  response = client.post("/api/transcription/extract-audio", files={"file": ("a.mp4", b"x" * (3 * 1024 * 1024 + 1))})
  assert response.status_code == 413 and response.json()["detail"] == "El archivo supera el máximo de 3 MB."


def test_temporary_folders_are_removed_quietly_after_failures_and_after_the_response(client, monkeypatch):
  removed = []

  def record_removal(path, ignore_errors=False):
    removed.append((Path(path).name.startswith("funcassist_audio_"), ignore_errors))

  monkeypatch.setattr(tr.shutil, "rmtree", record_removal)

  def fail(source, output):
    raise RuntimeError("boom")

  monkeypatch.setattr(tr, "_process_audio_extraction", fail)
  client.post("/api/transcription/extract-audio", files={"file": ("a.mp4", b"x")})
  monkeypatch.setattr(tr, "_process_audio_extraction", lambda source, output: source)
  client.post("/api/transcription/extract-audio", files={"file": ("a.mp4", b"x")})
  _ok_extraction(monkeypatch)
  client.post("/api/transcription/extract-audio", files={"file": ("a.mp4", b"x")})
  assert removed == [(True, True)] * 3


def test_the_converter_is_asked_to_validate_its_output(tmp_path, monkeypatch):
  import app.features.transcription.ffmpeg_utils as ffmpeg_utils

  seen = {}

  def extract(source, output, validate):
    seen["validate"] = validate
    return output

  monkeypatch.setattr(ffmpeg_utils, "extract_audio_track", extract)
  tr._process_audio_extraction(tmp_path / "a.mp4", tmp_path / "o.wav")
  assert seen == {"validate": True}


# --- dictation ------------------------------------------------------------------------


@pytest.fixture
def dictation(client, monkeypatch, tmp_path):
  import app.core.settings as core_settings
  import app.features.transcription.whisper_cloud as whisper

  state = {"paths": [], "action": None, "error": None}
  monkeypatch.setattr(core_settings, "USER_DATA_DIR", tmp_path / "fresh")

  async def transcribe(path, user_id, language):
    state["paths"].append(path)
    if state["action"]:
      state["action"](path)
    if state["error"]:
      raise state["error"]
    return "hola"

  monkeypatch.setattr(whisper, "transcribe_short_audio", transcribe)
  state["client"] = client
  return state


def test_dictation_keeps_the_extension_or_defaults_to_webm(dictation, tmp_path):
  client = dictation["client"]
  client.post("/api/transcription/dictate", files={"file": ("voz.ogg", b"a")})
  client.post("/api/transcription/dictate", files={"file": ("voz", b"a")})
  assert [p.suffix for p in dictation["paths"]] == [".ogg", ".webm"]
  assert all(p.name.startswith("voice_") and p.parent == tmp_path / "fresh" / "temp_voice" for p in dictation["paths"])


def test_dictation_tolerates_a_file_that_is_already_gone(dictation):
  dictation["action"] = lambda path: path.unlink()
  assert dictation["client"].post("/api/transcription/dictate", files={"file": ("v.webm", b"a")}).json()["text"] == "hola"


def test_a_failed_dictation_logs_the_detail_or_the_user_message(dictation, caplog):
  client = dictation["client"]
  dictation["error"] = TranscriptionJobError("no_credentials", detail="sin llave")
  with caplog.at_level(logging.WARNING):
    client.post("/api/transcription/dictate", files={"file": ("v.webm", b"a")})
    dictation["error"] = TranscriptionJobError("no_credentials", detail="")
    client.post("/api/transcription/dictate", files={"file": ("v.webm", b"a")})
  messages = [r.getMessage() for r in caplog.records if "Voice dictation failed" in r.getMessage()]
  assert messages[0] == "Voice dictation failed (no_credentials): sin llave"
  assert messages[1].startswith("Voice dictation failed (no_credentials): La transcripción en servidor requiere")


