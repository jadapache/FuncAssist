"""HTTP tests for app/api/transcription.py with the records/service/storage layer faked."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import transcription as tr
from app.core.exceptions import FFmpegError
from app.features.transcription.errors import TranscriptionJobError

USER_ID = "test-user-id"


class FakeRecords:
  def __init__(self):
    self.db: dict[str, dict[str, Any]] = {}
    self.raise_edit: Exception | None = None
    self.update_returns_none = False

  async def get_record(self, tid):
    rec = self.db.get(tid)
    return dict(rec) if rec else None

  def can_access(self, record, user):
    return record.get("user_id") == user.get("id")

  async def save_record(self, record):
    self.db[record["id"]] = dict(record)

  async def list_records(self, user):
    return [dict(r) for r in self.db.values() if r.get("user_id") == user["id"]]

  async def update_record(self, tid, mutate):
    if self.raise_edit:
      raise self.raise_edit
    if self.update_returns_none or tid not in self.db:
      return None
    rec = dict(self.db[tid])
    mutate(rec)
    self.db[tid] = rec
    return dict(rec)


@pytest.fixture
def recs(monkeypatch):
  fr = FakeRecords()
  for name in ("get_record", "can_access", "save_record", "list_records", "update_record"):
    monkeypatch.setattr(tr.records, name, getattr(fr, name))
  return fr


@pytest.fixture
def client(recs):
  app = FastAPI()
  app.include_router(tr.router, prefix="/api")
  return TestClient(app, base_url="https://testserver")


def _own(recs, tid="tid-12345678", **extra):
  recs.db[tid] = {"id": tid, "user_id": USER_ID, "title": "t", "segments": [], **extra}
  return tid


def _job_err(code="bad_request"):
  return TranscriptionJobError(code, f"msg-{code}")


# --- helpers ---


def test_new_id_and_http_error():
  assert tr._new_id("abcd_1234") == "abcd_1234"
  assert tr._new_id("bad id!") != "bad id!"
  assert len(tr._new_id(None)) == 36
  assert tr._http_error(_job_err("file_too_large")).status_code == 413
  assert tr._http_error(_job_err("weird")).status_code == 422


def test_consent_required_and_record():
  with pytest.raises(HTTPException) as ei:
    tr._require_consent(False)
  assert ei.value.status_code == 400
  rec = tr._consent_record({"username": "u"})
  assert rec["confirmed"] is True and rec["confirmed_by"] == "u"


# --- upload ---


def _patch_upload(monkeypatch, exc=None):
  async def save_upload(file, tid, title, description):
    if exc:
      raise exc
    return {"id": tid, "title": title, "size_bytes": 3}

  monkeypatch.setattr(tr.storage, "save_upload", save_upload)
  monkeypatch.setattr(
    tr.service, "media_entry_for_upload",
    lambda entry, user: {"id": entry["id"], "user_id": user["id"], "title": entry["title"]},
  )




def test_upload_ok_stores_consent(client, recs, monkeypatch):
  _patch_upload(monkeypatch)
  r = client.post(
    "/api/transcription/upload",
    files={"file": ("a.wav", b"abc")},
    data={"consent_confirmed": "true", "transcription_id": "myid_12345"},
  )
  assert r.status_code == 200, r.text
  body = r.json()
  assert body["transcription_id"] == "myid_12345" and body["size"] == 3
  assert body["entry"]["title"] == "a.wav"
  assert recs.db["myid_12345"]["consent"]["confirmed"] is True


def test_upload_conflicting_id_409(client, recs, monkeypatch):
  _patch_upload(monkeypatch)
  recs.db["foreign_123"] = {"id": "foreign_123", "user_id": "someone-else"}
  r = client.post("/api/transcription/upload", files={"file": ("a.wav", b"abc")},
                  data={"consent_confirmed": "true", "transcription_id": "foreign_123"})
  assert r.status_code == 409


def test_upload_existing_own_id_and_storage_error(client, recs, monkeypatch):
  _own(recs, "mine_1234")
  _patch_upload(monkeypatch, exc=_job_err("unsupported_format"))
  r = client.post("/api/transcription/upload", files={"file": ("a.xyz", b"abc")},
                  data={"consent_confirmed": "true", "transcription_id": "mine_1234"})
  assert r.status_code == 415 and r.json()["detail"] == "msg-unsupported_format"


# --- jobs ---


def test_transcribe_retry_and_errors(client, recs, monkeypatch):
  tid = _own(recs)
  seen = {}

  async def start_job(record, user, opts):
    seen["opts"] = opts

  monkeypatch.setattr(tr.service, "start_job", start_job)
  r = client.post(f"/api/transcription/transcribe/{tid}", json={"language": "en", "num_speakers": 2})
  assert r.status_code == 200 and r.json()["status"] == "queued"
  assert seen["opts"].language == "en" and seen["opts"].num_speakers == 2

  assert client.post(f"/api/transcription/transcribe/{tid}").status_code == 200
  assert client.post(f"/api/transcription/transcribe/{tid}", json={"num_speakers": 0}).status_code == 422

  async def fail(*a, **k):
    raise _job_err("no_credentials")

  monkeypatch.setattr(tr.service, "start_job", fail)
  assert client.post(f"/api/transcription/transcribe/{tid}").status_code == 400
  assert client.post("/api/transcription/transcribe/missing").status_code == 404

  async def ok(*a, **k):
    return None

  monkeypatch.setattr(tr.service, "retry_job", ok)
  r = client.post(f"/api/transcription/retry/{tid}")
  assert r.status_code == 200 and r.json()["transcription_id"] == tid
  monkeypatch.setattr(tr.service, "retry_job", fail)
  assert client.post(f"/api/transcription/retry/{tid}").status_code == 400


def test_cancel_active_status_result_list(client, recs, monkeypatch):
  tid = _own(recs)
  from app.features.transcription.jobs import job_manager

  async def cancel(job_id):
    return job_id == tid

  monkeypatch.setattr(job_manager, "cancel", cancel)
  assert client.post(f"/api/transcription/cancel/{tid}").json()["ok"] is True

  async def active(user):
    return [{"id": tid}]

  monkeypatch.setattr(tr.service, "active_jobs", active)
  assert client.get("/api/transcription/jobs/active").json() == {"jobs": [{"id": tid}]}

  monkeypatch.setattr(tr.service, "job_status", lambda rec: {"id": rec["id"], "stage": "queued"})
  assert client.get(f"/api/transcription/status/{tid}").json()["stage"] == "queued"

  res = client.get(f"/api/transcription/result/{tid}").json()
  assert res["id"] == tid and "user_id" not in res

  lst = client.get("/api/transcription/list").json()["transcriptions"]
  assert [i["id"] for i in lst] == [tid] and "user_id" not in lst[0]


def test_other_user_gets_404(client, recs):
  recs.db["x_12345678"] = {"id": "x_12345678", "user_id": "other"}
  assert client.get("/api/transcription/result/x_12345678").status_code == 404


def test_delete(client, recs, monkeypatch):
  tid = _own(recs)
  result = {"v": True}

  async def delete(record):
    return result["v"]

  monkeypatch.setattr(tr.service, "delete_transcription", delete)
  assert client.delete(f"/api/transcription/{tid}").json()["ok"] is True
  result["v"] = False
  assert client.delete(f"/api/transcription/{tid}").status_code == 404


def test_submit_client_transcription(client, monkeypatch):
  captured = {}

  async def submit(payload, user):
    captured.update(payload)
    return {"id": payload["id"], "user_id": user["id"]}, {"summary_text": "s"}

  monkeypatch.setattr(tr.service, "submit_client_transcription", submit)
  body = {"id": "c1", "text": "hola"}
  assert client.post("/api/transcription/submit-client-transcription", json=body).status_code == 400
  r = client.post("/api/transcription/submit-client-transcription", json={**body, "consent_confirmed": True})
  assert r.status_code == 200
  data = r.json()
  assert data["transcription"] == {"id": "c1"} and data["summary"] == {"summary_text": "s"}
  assert "consent_confirmed" not in captured and captured["consent"]["confirmed"] is True

  async def fail(*a):
    raise _job_err("bad_request")

  monkeypatch.setattr(tr.service, "submit_client_transcription", fail)
  r = client.post("/api/transcription/submit-client-transcription", json={**body, "consent_confirmed": True})
  assert r.status_code == 400
  assert client.post("/api/transcription/submit-client-transcription", json={}).status_code == 422


def test_models_and_stats(client, monkeypatch):
  monkeypatch.setattr(tr.service, "get_available_models_info", lambda user_id: {"user": user_id})
  assert client.get("/api/transcription/available-models").json() == {"user": USER_ID}

  calls = {}

  def read_entries(limit):
    calls["limit"] = limit
    return [{"user_id": USER_ID, "x": 1}, {"user_id": "other"}]

  monkeypatch.setattr(tr.metrics, "read_entries", read_entries)
  monkeypatch.setattr(tr.metrics, "summarize", lambda e: {"n": len(e)})
  assert client.get("/api/transcription/stats?limit=999999").json() == {"count": 1, "n": 1}
  assert calls["limit"] == 5000


# --- summaries ---


def test_summary_templates(client, monkeypatch):
  async def list_prompts(tag):
    assert tag == "transcript_summary"
    return [{"feature": "f1", "title": "T"}, {"feature": "f2", "description": "d", "tag": "x"}]

  monkeypatch.setattr(tr, "list_prompts", list_prompts)
  t = client.get("/api/transcription/summary-templates?tag=").json()["templates"]
  assert t[0] == {"id": "f1", "title": "T", "description": "", "tag": "transcript_summary"}
  assert t[1]["title"] == "f2" and t[1]["tag"] == "x"


def test_generate_and_update_summary(client, recs, monkeypatch):
  tid = _own(recs)
  seen = {}

  async def gen(record, user, feature):
    seen["feature"] = feature
    return {"summary_text": "ok"}, {**record}

  monkeypatch.setattr(tr.service, "generate_summary", gen)
  r = client.post(f"/api/transcription/generate-summary/{tid}", json={"rubric_id": "r1"})
  assert r.json()["summary"] == {"summary_text": "ok"} and "user_id" not in r.json()["transcription"]
  assert seen["feature"] == "r1"
  client.post(f"/api/transcription/generate-summary/{tid}")
  assert seen["feature"] is None

  r = client.put(f"/api/transcription/summary/{tid}", json={"summary": {"summary_text": "new"}})
  assert r.status_code == 200
  assert recs.db[tid]["summary"]["summary_text"] == "new" and recs.db[tid]["summary_status"] == "done"
  assert client.put(f"/api/transcription/summary/{tid}", json={}).status_code == 422
  recs.update_returns_none = True
  assert client.put(f"/api/transcription/summary/{tid}", json={"summary": {}}).status_code == 404


# --- speakers/segments ---


def test_speaker_and_segment_edits(client, recs, monkeypatch):
  tid = _own(recs)
  monkeypatch.setattr(tr.seg_ops, "apply_speaker_edits", lambda r, rename, merge: r.update(rename=rename, merge=merge))
  monkeypatch.setattr(tr.seg_ops, "rename_by_name", lambda r, m: r.update(map=m))
  monkeypatch.setattr(tr.seg_ops, "edit_segment", lambda r, sid, **kw: r.update(seg=sid, kw=kw))
  monkeypatch.setattr(tr.seg_ops, "split_segment", lambda r, sid, at: r.update(split=[sid, at]))

  r = client.patch(f"/api/transcription/{tid}/speakers",
                   json={"rename": {"S1": "Ana"}, "merge": [{"from": "S2", "into": "S1"}]})
  assert r.status_code == 200
  assert r.json()["transcription"]["merge"] == [{"from": "S2", "into": "S1"}]
  assert client.patch(f"/api/transcription/{tid}/speakers", json={}).json()["transcription"]["merge"] == []

  r = client.put(f"/api/transcription/speakers/{tid}", json={"speaker_map": {"A": "B"}})
  assert r.json()["transcription"]["map"] == {"A": "B"}

  r = client.patch(f"/api/transcription/{tid}/segments/s1", json={"text": "x", "marked": True})
  assert r.json()["transcription"]["kw"]["text"] == "x"
  r = client.patch(f"/api/transcription/{tid}/segments/s1", json={"speaker_id": "a", "new_speaker_name": "b"})
  assert r.status_code == 422

  r = client.post(f"/api/transcription/{tid}/segments/s1/split", json={"at": 3})
  assert r.json()["transcription"]["split"] == ["s1", 3]
  assert client.post(f"/api/transcription/{tid}/segments/s1/split", json={"at": 0}).status_code == 422

  recs.raise_edit = tr.seg_ops.EditError("bad segment")
  r = client.post(f"/api/transcription/{tid}/segments/s1/split", json={"at": 3})
  assert r.status_code == 400 and r.json()["detail"] == "bad segment"
  recs.raise_edit = None
  recs.update_returns_none = True
  assert client.put(f"/api/transcription/speakers/{tid}", json={"speaker_map": {}}).status_code == 404


def test_save_to_knowledge(client, recs, monkeypatch):
  tid = _own(recs)
  seen = {}

  async def save(record, custom_tags):
    seen["tags"] = custom_tags
    return {"ok": True, "document_id": "d1"}

  monkeypatch.setattr(tr.service, "save_to_knowledge_base", save)
  r = client.post(f"/api/transcription/save-to-knowledge/{tid}", json={"custom_tags": ["a"]})
  assert r.json()["document_id"] == "d1" and seen["tags"] == ["a"]
  client.post(f"/api/transcription/save-to-knowledge/{tid}")
  assert seen["tags"] == []

  async def boom(record, custom_tags):
    raise RuntimeError("disk")

  monkeypatch.setattr(tr.service, "save_to_knowledge_base", boom)
  r = client.post(f"/api/transcription/save-to-knowledge/{tid}")
  assert r.status_code == 500 and "disk" in r.json()["detail"]


# --- audio utilities ---


def test_process_audio_extraction(monkeypatch, tmp_path):
  import app.features.transcription.ffmpeg_utils as fu

  monkeypatch.setattr(fu, "extract_audio_track", lambda i, o, validate: (o, 1.0))
  assert tr._process_audio_extraction(tmp_path / "i", tmp_path / "o") == tmp_path / "o"
  monkeypatch.setattr(fu, "extract_audio_track", lambda i, o, validate: o)
  assert tr._process_audio_extraction(tmp_path / "i", tmp_path / "o") == tmp_path / "o"


def test_extract_audio_paths(client, monkeypatch):
  assert client.post("/api/transcription/extract-audio", files={"file": ("a.exe", b"x")}).status_code == 415

  def ok(inp: Path, out: Path):
    out.write_bytes(b"RIFFwav")
    return out

  monkeypatch.setattr(tr, "_process_audio_extraction", ok)
  r = client.post("/api/transcription/extract-audio", files={"file": ("a.mp4", b"data")})
  assert r.status_code == 200 and r.content == b"RIFFwav"
  assert r.headers["content-type"] == "audio/wav"

  monkeypatch.setattr(tr, "_process_audio_extraction", lambda i, o: i)
  r = client.post("/api/transcription/extract-audio", files={"file": ("a.mp4", b"data")})
  assert r.status_code == 422 and "FFmpeg" in r.json()["detail"]

  def ffmpeg_fail(i, o):
    raise FFmpegError("broken stream")

  monkeypatch.setattr(tr, "_process_audio_extraction", ffmpeg_fail)
  r = client.post("/api/transcription/extract-audio", files={"file": ("a.mp4", b"data")})
  assert r.status_code == 422 and "Error de FFmpeg" in r.json()["detail"]

  for msg, code in (("audio codec missing", 422), ("unexpected", 500)):
    def generic(i, o, msg=msg):
      raise RuntimeError(msg)

    monkeypatch.setattr(tr, "_process_audio_extraction", generic)
    assert client.post("/api/transcription/extract-audio", files={"file": ("a.mp4", b"data")}).status_code == code

  monkeypatch.setattr(tr.config, "max_upload_bytes", lambda: 2)
  r = client.post("/api/transcription/extract-audio", files={"file": ("a.mp4", b"toolong")})
  assert r.status_code == 413


def test_dictate(client, monkeypatch, tmp_path):
  import app.core.settings as cs
  import app.features.transcription.whisper_cloud as wc

  monkeypatch.setattr(cs, "USER_DATA_DIR", tmp_path)
  behaviour = {"mode": "ok"}

  async def transcribe(path, user_id, language):
    assert path.exists()
    if behaviour["mode"] == "job":
      raise _job_err("no_credentials")
    if behaviour["mode"] == "boom":
      raise RuntimeError("x")
    return "hola mundo"

  monkeypatch.setattr(wc, "transcribe_short_audio", transcribe)
  r = client.post("/api/transcription/dictate", files={"file": ("v.webm", b"abc")})
  assert r.json() == {"text": "hola mundo", "filename": "v.webm"}
  assert list((tmp_path / "temp_voice").iterdir()) == []

  assert client.post("/api/transcription/dictate", files={"file": ("v.webm", b"")}).status_code == 400
  behaviour["mode"] = "job"
  r = client.post("/api/transcription/dictate", files={"file": ("v.webm", b"a")})
  assert r.json()["error"] == "msg-no_credentials"
  behaviour["mode"] = "boom"
  assert client.post("/api/transcription/dictate", files={"file": ("v.webm", b"a")}).json()["text"] == ""
  monkeypatch.setattr(tr, "DICTATION_MAX_BYTES", 1)
  assert client.post("/api/transcription/dictate", files={"file": ("v.webm", b"ab")}).status_code == 413


# --- exports ---


def test_exports(client, monkeypatch):
  monkeypatch.setattr(tr, "create_inventario_xlsx", lambda markdown_content, title: b"XLSX")
  monkeypatch.setattr(tr, "create_levantamiento_docx", lambda content, title: b"DOCX")
  r = client.post("/api/transcription/export/inventario", json={"content": "x", "title": "Mi doc"})
  assert r.content == b"XLSX" and "Inventario_Mi_doc.xlsx" in r.headers["content-disposition"]
  r = client.post("/api/transcription/export/levantamiento", json={"title": ""})
  assert r.content == b"DOCX"
  assert "Levantamiento_Levantamiento_Requerimientos.docx" in r.headers["content-disposition"]

  def boom(*a, **k):
    raise ValueError("bad md")

  monkeypatch.setattr(tr, "create_inventario_xlsx", boom)
  monkeypatch.setattr(tr, "create_levantamiento_docx", boom)
  assert client.post("/api/transcription/export/inventario", json={}).status_code == 500
  r = client.post("/api/transcription/export/levantamiento", json={})
  assert r.status_code == 500 and "bad md" in r.json()["detail"]
