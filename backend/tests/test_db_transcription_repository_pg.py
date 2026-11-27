"""TranscriptionRepository against a real PostgreSQL (skipped when TEST_DATABASE_URL is not set)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from app.db.models import TranscriptionModel
from app.db.repositories.transcription_repository import TranscriptionRepository, _parse_dt


def _id():
  return str(uuid.uuid4())


@pytest.fixture
def repo(pg_async_session):
  return TranscriptionRepository(pg_async_session)


async def _row(repo, tid):
  return await repo._row(tid)


# --- dates --------------------------------------------------------------------------


def test_dates_are_parsed_from_text_and_passed_through():
  moment = datetime(2024, 1, 2, tzinfo=timezone.utc)
  assert _parse_dt(moment) is moment
  assert _parse_dt("2024-01-02T00:00:00Z") == moment
  assert _parse_dt("2024-01-02T00:00:00+00:00") == moment
  assert _parse_dt("not a date") is None
  assert _parse_dt("") is None and _parse_dt(None) is None and _parse_dt(5) is None


# --- upsert -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_record_needs_an_id(repo):
  with pytest.raises(ValueError, match="must have an 'id'"):
    await repo.upsert({"title": "x"})
  with pytest.raises(ValueError):
    await repo.upsert({"id": ""})


@pytest.mark.asyncio
async def test_a_minimal_record_gets_the_defaults(repo):
  tid = _id()
  saved = await repo.upsert({"id": tid})
  assert (saved["title"], saved["description"], saved["language"], saved["status"], saved["model_info"]) == ("Reunión", "", "es", "complete", "Whisper")
  assert (saved["duration_seconds"], saved["text"], saved["segments"], saved["summary"], saved["user_id"]) == (0.0, "", [], None, None)
  assert (saved["original_filename"], saved["stored_filename"], saved["path"], saved["progress"], saved["error_code"]) == ("", "", "", None, None)
  assert (saved["started_at"], saved["finished_at"], saved["saved_to_knowledge"], saved["document_id"]) == (None, None, False, None)
  assert saved["metadata"] == {"title": "Reunión", "description": ""}


@pytest.mark.asyncio
async def test_title_and_description_come_from_the_metadata_first(repo):
  a = await repo.upsert({"id": _id(), "metadata": {"title": "Meta", "description": "md"}, "title": "Top", "description": "td"})
  b = await repo.upsert({"id": _id(), "title": "Top", "description": "td"})
  c = await repo.upsert({"id": _id(), "metadata": {"title": "", "description": ""}, "title": "Top"})
  assert (a["title"], a["description"]) == ("Meta", "md")
  assert (b["title"], b["description"]) == ("Top", "td")
  assert (c["title"], c["description"]) == ("Top", "")


@pytest.mark.asyncio
async def test_file_names_and_path_fall_back_to_the_media_entry(repo):
  media = {"original_filename": "m.mp3", "stored_filename": "media.mp3", "path": "/m/media.mp3", "id": "x", "transcription_id": "y", "size_bytes": 9}
  a = await repo.upsert({"id": _id(), "media": media})
  assert (a["original_filename"], a["stored_filename"], a["path"]) == ("m.mp3", "media.mp3", "/m/media.mp3")
  assert a["media"]["size_bytes"] == 9
  b = await repo.upsert({"id": _id(), "original_filename": "o.mp3", "stored_filename": "s.mp3", "path": "/p", "media": media})
  assert (b["original_filename"], b["stored_filename"], b["path"]) == ("o.mp3", "s.mp3", "/p")
  c = await repo.upsert({"id": _id(), "filename": "f.mp3", "media": media})
  assert c["original_filename"] == "f.mp3"
  d = await repo.upsert({"id": _id(), "media": "not a dict"})
  assert d["original_filename"] == ""


@pytest.mark.asyncio
async def test_the_stored_media_entry_drops_its_ids_and_survives_a_round_trip(repo, pg_async_session):
  tid = _id()
  await repo.upsert({"id": tid, "media": {"id": "x", "transcription_id": "y", "size_bytes": 5, "hash": "h"}})
  stored = json.loads((await _row(repo, tid)).metadata_json)
  assert stored["media"] == {"size_bytes": 5, "hash": "h"}
  assert (await repo.get(tid))["media"]["hash"] == "h"


@pytest.mark.asyncio
async def test_record_fields_live_in_the_metadata_and_other_metadata_is_kept(repo):
  tid = _id()
  record = {
    "id": tid, "metadata": {"title": "T", "description": "d", "custom": 1, "speakers": ["old"]},
    "speakers": ["Ana"], "provider": "groq", "error": "boom", "consent": {"ok": True}, "retryable": True,
  }
  saved = await repo.upsert(record)
  assert saved["speakers"] == ["Ana"] and saved["provider"] == "groq" and saved["error"] == "boom"
  assert saved["consent"] == {"ok": True} and saved["retryable"] is True
  assert saved["metadata"] == {"title": "T", "description": "d", "custom": 1}
  stored = json.loads((await _row(repo, tid)).metadata_json)
  assert stored["speakers"] == ["Ana"] and stored["custom"] == 1 and "title" not in stored and "description" not in stored


@pytest.mark.asyncio
async def test_knowledge_flags_are_stored_only_when_present(repo):
  a = await repo.upsert({"id": _id()})
  b = await repo.upsert({"id": _id(), "saved_to_knowledge": 1, "document_id": "doc-1"})
  c = await repo.upsert({"id": _id(), "saved_to_knowledge": 0, "document_id": None})
  assert (a["saved_to_knowledge"], a["document_id"]) == (False, None)
  assert (b["saved_to_knowledge"], b["document_id"]) == (True, "doc-1")
  assert (c["saved_to_knowledge"], c["document_id"]) == (False, None)


@pytest.mark.asyncio
async def test_scalar_fields_are_stored_with_unicode_intact(repo):
  tid = _id()
  saved = await repo.upsert({
    "id": tid, "duration_seconds": "12.5", "language": "en", "status": "pending", "model_info": "Groq", "text": "canción",
    "segments": [{"text_raw": "canción"}], "summary": {"overview": "ñandú"}, "user_id": 42,
  })
  assert (saved["duration_seconds"], saved["language"], saved["status"], saved["model_info"], saved["user_id"]) == (12.5, "en", "pending", "Groq", "42")
  row = await _row(repo, tid)
  assert "canción" in row.segments_json and "ñandú" in row.summary_json
  assert (await repo.upsert({"id": _id(), "duration_seconds": None}))["duration_seconds"] == 0.0
  assert (await repo.upsert({"id": _id(), "summary": {}}))["summary"] == {}


@pytest.mark.asyncio
async def test_progress_error_code_and_dates_are_stored_when_given(repo):
  tid = _id()
  saved = await repo.upsert({
    "id": tid, "progress": {"stage": "queued", "n": 1}, "error_code": "timeout",
    "started_at": "2024-01-02T03:04:05Z", "finished_at": datetime(2024, 1, 3, tzinfo=timezone.utc),
  })
  assert saved["progress"] == {"stage": "queued", "n": 1} and saved["error_code"] == "timeout"
  assert saved["started_at"].startswith("2024-01-02T03:04:05") and saved["finished_at"].startswith("2024-01-03")
  cleared = await repo.upsert({"id": tid, "progress": None, "error_code": None, "finished_at": None})
  assert cleared["progress"] is None and cleared["error_code"] is None and cleared["finished_at"] is None
  assert cleared["started_at"].startswith("2024-01-02")


@pytest.mark.asyncio
async def test_updating_keeps_what_the_new_record_does_not_mention(repo):
  tid = _id()
  await repo.upsert({
    "id": tid, "original_filename": "o.mp3", "stored_filename": "s.mp3", "path": "/p", "user_id": "u1",
    "progress": {"stage": "queued"}, "error_code": "timeout", "started_at": "2024-01-02T00:00:00Z", "finished_at": "2024-01-03T00:00:00Z",
  })
  saved = await repo.upsert({"id": tid, "title": "Nuevo", "text": "hola"})
  assert (saved["original_filename"], saved["stored_filename"], saved["path"], saved["user_id"]) == ("o.mp3", "s.mp3", "/p", "u1")
  assert saved["progress"] == {"stage": "queued"} and saved["error_code"] == "timeout"
  assert saved["started_at"].startswith("2024-01-02") and saved["finished_at"].startswith("2024-01-03")
  assert (saved["title"], saved["text"]) == ("Nuevo", "hola")
  assert (await repo.upsert({"id": tid, "started_at": ""}))["started_at"].startswith("2024-01-02")


@pytest.mark.asyncio
async def test_invalid_dates_clear_the_value(repo):
  tid = _id()
  await repo.upsert({"id": tid, "started_at": "2024-01-02T00:00:00Z", "finished_at": "2024-01-03T00:00:00Z"})
  saved = await repo.upsert({"id": tid, "started_at": "garbage", "finished_at": "garbage"})
  assert saved["started_at"] is None and saved["finished_at"] is None


# --- queries ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_finds_a_record_by_id_or_by_its_slug(repo):
  tid = "1a2b3c4d-0000-4000-8000-000000000001"
  saved = await repo.upsert({"id": tid, "title": "Reunión semanal"})
  assert (await repo.get(tid))["id"] == tid
  assert (await repo.get(saved["slug"]))["id"] == tid
  assert await repo.get("otro-titulo-1a2b3c4d") is not None
  assert await repo.get("otro-titulo-ffffffff") is None
  assert await repo.get("short-1234567") is None
  assert await repo.get("nohyphenatall") is None


@pytest.mark.asyncio
async def test_list_returns_the_newest_first_optionally_for_one_owner(repo):
  a, b, c = _id(), _id(), _id()
  await repo.upsert({"id": a, "user_id": "u1"})
  await repo.upsert({"id": b, "user_id": "u2"})
  await repo.upsert({"id": c, "user_id": "u1"})
  mine = [r["id"] for r in await repo.list("u1")]
  assert set(mine) == {a, c} and len(await repo.list()) >= 3


@pytest.mark.asyncio
async def test_list_by_status_filters_by_status_and_owner(repo):
  a, b, c = _id(), _id(), _id()
  await repo.upsert({"id": a, "status": "complete", "user_id": "u1"})
  await repo.upsert({"id": b, "status": "failed", "user_id": "u1"})
  await repo.upsert({"id": c, "status": "complete", "user_id": "u2"})
  assert {r["id"] for r in await repo.list_by_status({"complete"})} >= {a, c}
  assert b not in {r["id"] for r in await repo.list_by_status(["complete"])}
  assert {r["id"] for r in await repo.list_by_status({"complete", "failed"}, user_id="u1")} == {a, b}
  assert [r["id"] for r in await repo.list_by_status({"failed"}, user_id="u1")] == [b]
  assert await repo.list_by_status(set(), user_id="u1") == []


@pytest.mark.asyncio
async def test_progress_updates_touch_only_the_job_columns(repo):
  tid = _id()
  await repo.upsert({"id": tid, "text": "hola", "status": "pending"})
  started = datetime(2024, 1, 2, tzinfo=timezone.utc)
  finished = datetime(2024, 1, 3, tzinfo=timezone.utc)
  assert await repo.update_progress(tid, {"stage": "transcribing", "error_code": None}, started_at=started) is True
  row = await repo.get(tid)
  assert (row["status"], row["text"], row["progress"]["stage"], row["error_code"]) == ("transcribing", "hola", "transcribing", None)
  assert row["started_at"].startswith("2024-01-02") and row["finished_at"] is None
  other = datetime(2025, 5, 5, tzinfo=timezone.utc)
  await repo.update_progress(tid, {"stage": "failed", "error_code": "timeout"}, started_at=other, finished_at=finished)
  row = await repo.get(tid)
  assert (row["status"], row["error_code"]) == ("failed", "timeout")
  assert row["started_at"].startswith("2024-01-02") and row["finished_at"].startswith("2024-01-03")
  await repo.update_progress(tid, {"message": "no stage"})
  assert (await repo.get(tid))["status"] == "failed"


@pytest.mark.asyncio
async def test_progress_of_an_unknown_record_is_refused(repo):
  assert await repo.update_progress(_id(), {"stage": "x"}) is False


@pytest.mark.asyncio
async def test_unowned_records_can_be_assigned_to_a_user(repo):
  a, b = _id(), _id()
  await repo.upsert({"id": a})
  await repo.upsert({"id": b, "user_id": "u1"})
  assigned = await repo.assign_owner("u9")
  assert assigned >= 1
  assert (await repo.get(a))["user_id"] == "u9" and (await repo.get(b))["user_id"] == "u1"
  assert await repo.assign_owner("u2", only_unowned=False) >= 2
  assert (await repo.get(b))["user_id"] == "u2"


@pytest.mark.asyncio
async def test_a_record_can_be_deleted_once(repo):
  tid = _id()
  await repo.upsert({"id": tid})
  assert await repo.delete(tid) is True
  assert await repo.get(tid) is None
  assert await repo.delete(tid) is False


# --- round 2: slug lookup limits and unicode progress ---------------------------------


@pytest.mark.asyncio
async def test_slug_lookup_needs_a_hyphen_and_a_long_enough_suffix(repo):
  await repo.upsert({"id": "abcdefgh-0000-4000-8000-000000000001", "title": "Reunión"})
  await repo.upsert({"id": "abc12345-0000-4000-8000-000000000002", "title": "Otra"})
  assert await repo.get("abcdefgh") is None
  assert await repo.get("x-abc") is None
  assert (await repo.get("reunion-abcdefgh"))["title"] == "Reunión"
  assert (await repo.get("lo-que-sea-abc12345"))["title"] == "Otra"


@pytest.mark.asyncio
async def test_progress_keeps_accents_readable(repo):
  tid = _id()
  await repo.upsert({"id": tid})
  await repo.update_progress(tid, {"stage": "queued", "message": "canción"})
  assert "canción" in (await _row(repo, tid)).progress_json
