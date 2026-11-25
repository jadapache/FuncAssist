"""Corporate and AI template repositories against a real PostgreSQL (skipped without TEST_DATABASE_URL)."""

from __future__ import annotations

import json

import pytest

from app.db.models import AITemplateModel, AITemplateVersionModel, CorporateTemplateModel
from app.db.repositories.corporate_template_repository import CorporateTemplateRepository, _template_columns
from app.db.repositories.template_repository import AITemplateRepository, _payload_json


# -- corporate templates ----------------------------------------------------------------------------

@pytest.fixture
def corporate(pg_async_session):
  return CorporateTemplateRepository(pg_async_session)


@pytest.mark.asyncio
async def test_upsert_fills_every_default(corporate):
  saved = await corporate.upsert({"id": "t1"})
  assert (saved["id"], saved["title"], saved["filename"], saved["stored_filename"]) == (
    "t1", "Plantilla Corporativa", "t1.docx", "t1.docx")
  assert (saved["file_type"], saved["file_size"], saved["module"], saved["tags"]) == ("docx", 0, "general", [])
  assert saved["created_at"]


@pytest.mark.asyncio
async def test_upsert_stores_the_given_fields_and_keeps_accents_readable(corporate, pg_async_session):
  saved = await corporate.upsert({
    "id": "t1", "title": "Formato ñandú", "filename": "f.docx", "stored_filename": "abc.docx", "file_type": "xlsx",
    "file_size": "42", "module": "ventas", "tags": ["ñandú"], "custom_content": "texto",
  })
  assert (saved["title"], saved["stored_filename"], saved["file_type"], saved["file_size"]) == (
    "Formato ñandú", "abc.docx", "xlsx", 42)
  assert (saved["module"], saved["tags"], saved["custom_content"]) == ("ventas", ["ñandú"], "texto")
  row = await pg_async_session.get(CorporateTemplateModel, "t1")
  assert row.tags_json == '["ñandú"]'


@pytest.mark.asyncio
async def test_the_stored_filename_defaults_to_the_filename(corporate):
  assert (await corporate.upsert({"id": "t1", "filename": "a.docx"}))["stored_filename"] == "a.docx"


@pytest.mark.asyncio
async def test_upsert_requires_an_id(corporate):
  with pytest.raises(ValueError, match="id"):
    await corporate.upsert({"title": "sin id"})


@pytest.mark.asyncio
async def test_upserting_again_updates_the_row_and_returns_it_refreshed(corporate):
  await corporate.upsert({"id": "t1", "title": "Viejo", "module": "a", "tags": ["x"], "custom_content": "contenido"})
  updated = await corporate.upsert({"id": "t1", "title": "Nuevo", "module": "b", "tags": ["y"]})
  assert (updated["title"], updated["module"], updated["tags"]) == ("Nuevo", "b", ["y"])
  assert updated["custom_content"] == "contenido"  # not touched when the item brings none
  assert len(await corporate.list()) == 1
  assert (await corporate.upsert({"id": "t1", "custom_content": "otro"}))["custom_content"] == "otro"


@pytest.mark.asyncio
async def test_get_finds_only_the_requested_template(corporate):
  await corporate.upsert({"id": "t1", "title": "Uno"})
  await corporate.upsert({"id": "t2", "title": "Dos"})
  assert (await corporate.get("t2"))["title"] == "Dos"
  assert await corporate.get("missing") is None


@pytest.mark.asyncio
async def test_list_is_sorted_by_title(corporate):
  for tid, title in (("a", "Zeta"), ("b", "Alfa"), ("c", "Medio")):
    await corporate.upsert({"id": tid, "title": title})
  assert [t["title"] for t in await corporate.list()] == ["Alfa", "Medio", "Zeta"]


@pytest.mark.asyncio
async def test_delete_removes_only_that_template(corporate):
  await corporate.upsert({"id": "t1"})
  await corporate.upsert({"id": "t2"})
  assert await corporate.delete("t1") is True
  assert [t["id"] for t in await corporate.list()] == ["t2"]
  assert await corporate.delete("t1") is False


def test_template_columns_keep_accents_readable():
  assert _template_columns({"tags": ["ñ"]}, "t")["tags_json"] == '["ñ"]'


# -- AI templates -----------------------------------------------------------------------------------

@pytest.fixture
def ai(pg_async_session):
  return AITemplateRepository(pg_async_session)


def test_the_payload_keeps_accents_readable_and_leaves_out_the_column_fields():
  data = {"id": "x", "template_type": "t", "feature": "f", "version": 3, "updated_by": "u", "created_at": "c",
          "updated_at": "d", "texto": "canción", "tag": "T"}
  assert json.loads(_payload_json(data)) == {"texto": "canción", "tag": "T"}
  assert "canción" in _payload_json(data)


@pytest.mark.asyncio
async def test_a_new_template_starts_at_version_one_with_its_first_history_entry(ai, pg_async_session):
  saved = await ai.save_template_update("prompt", "chat", {"texto": "hola ñ", "tag": "T1", "id": "ignored"})
  assert (saved["id"], saved["template_type"], saved["feature"], saved["version"]) == ("prompt:chat", "prompt", "chat", 1)
  assert (saved["updated_by"], saved["tag"], saved["texto"]) == ("user", "T1", "hola ñ")
  (entry,) = await ai.get_version_history("prompt", "chat")
  assert (entry["version"], entry["change_summary"], entry["created_by"], entry["tag"]) == (
    1, "Created prompt for chat", "user", "T1")
  row = await pg_async_session.get(AITemplateModel, "prompt:chat")
  assert "ñ" in row.payload_json and "ignored" not in row.payload_json


@pytest.mark.asyncio
async def test_a_new_template_can_bring_its_version_author_and_summary(ai):
  saved = await ai.save_template_update(
    "rubric", "doc", {"version": 3}, updated_by="ana", change_summary="Importada")
  assert (saved["version"], saved["updated_by"]) == (3, "ana")
  (entry,) = await ai.get_version_history("rubric", "doc")
  assert (entry["version"], entry["change_summary"], entry["created_by"]) == (3, "Importada", "ana")


@pytest.mark.asyncio
async def test_updating_merges_the_data_and_adds_a_version(ai):
  await ai.save_template_update("prompt", "chat", {"texto": "uno", "extra": "se queda", "tag": "T1"})
  updated = await ai.save_template_update("prompt", "chat", {"texto": "dos"}, updated_by="ana")
  assert (updated["version"], updated["texto"], updated["extra"], updated["updated_by"]) == (2, "dos", "se queda", "ana")
  assert updated["tag"] == "T1"
  history = await ai.get_version_history("prompt", "chat")
  assert [h["version"] for h in history] == [2, 1]
  assert (history[0]["change_summary"], history[0]["created_by"], history[0]["tag"]) == (
    "Updated prompt for chat", "ana", "T1")


@pytest.mark.asyncio
async def test_updating_can_change_the_tag_and_the_summary(ai):
  await ai.save_template_update("prompt", "chat", {"tag": "T1"})
  updated = await ai.save_template_update("prompt", "chat", {"tag": "T2"}, change_summary="Cambio de etiqueta")
  assert updated["tag"] == "T2"
  newest = (await ai.get_version_history("prompt", "chat"))[0]
  assert (newest["tag"], newest["change_summary"]) == ("T2", "Cambio de etiqueta")


@pytest.mark.asyncio
async def test_a_template_stored_with_version_zero_moves_to_version_two(ai, pg_async_session):
  pg_async_session.add(AITemplateModel(
    id="prompt:old", template_type="prompt", feature="old", version=0, payload_json="{}"))
  await pg_async_session.flush()
  assert (await ai.save_template_update("prompt", "old", {"a": 1}))["version"] == 2


@pytest.mark.asyncio
async def test_get_template_finds_only_the_requested_one(ai):
  await ai.save_template_update("prompt", "a", {"texto": "A"})
  await ai.save_template_update("prompt", "b", {"texto": "B"})
  await ai.save_template_update("rubric", "a", {"texto": "R"})
  assert (await ai.get_template("prompt", "b"))["texto"] == "B"
  assert (await ai.get_template("rubric", "a"))["texto"] == "R"
  assert await ai.get_template("prompt", "missing") is None


@pytest.mark.asyncio
async def test_list_templates_filters_by_type_and_tag_and_sorts_by_feature(ai):
  await ai.save_template_update("prompt", "zeta", {"tag": "X"})
  await ai.save_template_update("prompt", "alfa", {"tag": "Y"})
  await ai.save_template_update("prompt", "medio", {"tag": "X"})
  await ai.save_template_update("rubric", "otro", {"tag": "X"})
  assert [t["feature"] for t in await ai.list_templates("prompt")] == ["alfa", "medio", "zeta"]
  assert [t["feature"] for t in await ai.list_templates("prompt", tag="X")] == ["medio", "zeta"]
  assert [t["feature"] for t in await ai.list_templates("rubric")] == ["otro"]
  assert await ai.list_templates("prompt", tag="none") == []


@pytest.mark.asyncio
async def test_the_version_history_belongs_to_one_template_newest_first_and_can_be_limited(ai):
  for _ in range(3):
    await ai.save_template_update("prompt", "chat", {"a": 1})
  await ai.save_template_update("prompt", "other", {"a": 1})
  assert [h["version"] for h in await ai.get_version_history("prompt", "chat")] == [3, 2, 1]
  assert [h["version"] for h in await ai.get_version_history("prompt", "chat", limit=2)] == [3, 2]
  assert [h["version"] for h in await ai.get_version_history("prompt", "chat", limit=0)] == [3, 2, 1]
  assert [h["template_id"] for h in await ai.get_version_history("prompt", "other")] == ["prompt:other"]


@pytest.mark.asyncio
async def test_seeding_adds_the_missing_defaults_with_their_first_history_entry(ai, pg_async_session):
  await ai.seed_defaults(
    {"chat": {"texto": "hola", "tag": "T", "version": 4}, "plain": {"texto": "p"}},
    {"doc": {"criterio": "c"}},
  )
  chat, plain, doc = (await ai.get_template("prompt", "chat"), await ai.get_template("prompt", "plain"),
                      await ai.get_template("rubric", "doc"))
  assert (chat["version"], chat["tag"], chat["updated_by"], chat["texto"]) == (4, "T", "system", "hola")
  assert plain["version"] == 1 and (doc["version"], doc["criterio"]) == (1, "c")
  (entry,) = await ai.get_version_history("prompt", "chat")
  assert (entry["version"], entry["change_summary"], entry["created_by"], entry["tag"]) == (
    4, "Initial system seed", "system", "T")
  assert (await ai.get_version_history("rubric", "doc"))[0]["template_type"] == "rubric"


@pytest.mark.asyncio
async def test_seeding_never_overwrites_what_is_stored_and_can_be_repeated(ai):
  await ai.save_template_update("prompt", "chat", {"texto": "editado"})
  defaults = ({"chat": {"texto": "original"}}, {"doc": {"criterio": "c"}})
  await ai.seed_defaults(*defaults)
  await ai.seed_defaults(*defaults)
  assert (await ai.get_template("prompt", "chat"))["texto"] == "editado"
  assert len(await ai.get_version_history("prompt", "chat")) == 1
  assert len(await ai.get_version_history("rubric", "doc")) == 1


@pytest.mark.asyncio
async def test_seeding_removes_the_obsolete_transcript_summary_templates(ai, pg_async_session):
  await ai.save_template_update("prompt", "transcript_summary", {"a": 1})
  await ai.save_template_update("rubric", "transcript_summary", {"a": 1})
  await ai.save_template_update("prompt", "keep", {"a": 1})
  await ai.seed_defaults({}, {})
  assert await ai.get_template("prompt", "transcript_summary") is None
  assert await ai.get_template("rubric", "transcript_summary") is None
  assert (await ai.get_template("prompt", "keep"))["a"] == 1
  assert await ai.get_version_history("prompt", "transcript_summary") == []
