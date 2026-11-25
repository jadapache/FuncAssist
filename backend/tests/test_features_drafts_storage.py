"""Draft storage on disk: what is written for a session and how the drafts are found again."""

from __future__ import annotations

import json
import logging

import pytest

import app.features.drafts.storage as ds


@pytest.fixture
def drafts_dir(tmp_path, monkeypatch):
  drafts = tmp_path / "Borradores"
  monkeypatch.setattr(ds, "USER_DRAFTS_DIR", drafts)
  monkeypatch.setattr(ds, "GENERATED_DIR", tmp_path / "generated")
  monkeypatch.setattr(ds, "ensure_local_dirs", lambda: None)
  return drafts


def read(path):
  return json.loads(path.read_text(encoding="utf-8"))


def test_the_draft_folders_exist_after_ensuring_them(drafts_dir, tmp_path):
  ds.ensure_draft_dirs()
  assert (tmp_path / "generated").is_dir() and all((drafts_dir / spec).is_dir() for spec in ds.VALID_SPECS)


def test_a_session_is_saved_under_its_specification_with_a_short_id_in_the_folder_name(drafts_dir):
  meta = ds.save_draft_session({"id": "abcdef123456", "name": "Mi sesión", "specification": "inventario"})
  folder = drafts_dir / "Inventario" / "Mi_sesión_abcdef12"
  assert meta["folder_path"] == str(folder) and folder.is_dir()


def test_the_title_comes_from_the_name_then_the_title_then_a_default(drafts_dir):
  titles = [ds.save_draft_session(s)["title"] for s in (
    {"name": "Nombre", "title": "Título"}, {"title": "Título"}, {})]
  assert titles == ["Nombre", "Título", "Borrador"]


def test_the_specification_comes_from_the_specification_then_the_feature_slug(drafts_dir):
  specs = [ds.save_draft_session(s)["specification"] for s in (
    {"specification": "mejoras", "feature_slug": "inventario"}, {"feature_slug": "inventario"}, {})]
  assert specs == ["Mejoras", "Inventario", "Levantamiento"]


def test_the_last_interaction_comes_from_either_spelling_or_is_now(drafts_dir):
  def last(session):
    return ds.save_draft_session(session)["last_interaction"]

  assert last({"lastInteraction": "A", "last_interaction": "B"}) == "A"
  assert last({"last_interaction": "B"}) == "B"
  assert last({}).startswith("20")


def test_the_chat_is_written_as_json_and_as_markdown(drafts_dir):
  messages = [{"role": "user", "content": " Hola ñ ", "timestamp": "t1"}, {"role": "assistant", "content": "ok"}]
  meta = ds.save_draft_session({"id": "i" * 10, "name": "Chat", "specification": "mejoras", "messages": messages,
                                "documentContent": "texto", "lastInteraction": "L"})
  folder = drafts_dir / "Mejoras" / "Chat_iiiiiiii"
  assert read(folder / "chat.json") == {
    "id": "i" * 10, "title": "Chat", "specification": "Mejoras", "last_interaction": "L", "messages": messages,
    "documentContent": "texto"}
  assert "ñ" in (folder / "chat.json").read_text(encoding="utf-8")
  markdown = (folder / "chat.md").read_text(encoding="utf-8").splitlines()
  assert markdown[:2] == ["# Historial de Sesión - Chat", "**Especificación:** Mejoras"]
  assert markdown[2].startswith("**Fecha:** 20") and markdown[2].endswith(" UTC")
  assert markdown[3:] == ["", "---", "", "### Usuario (t1)", "Hola ñ", "", "### Asistente QA ()", "ok"]
  assert meta["message_count"] == 2


def test_each_artifact_is_saved_as_markdown_and_binary_files_where_they_apply(drafts_dir):
  meta = ds.save_draft_session({"id": "i" * 10, "name": "S", "artifacts": [
    {"id": "a1", "title": "Doc", "extension": "DOCX", "content": "# T", "createdAt": "c", "updatedAt": "u"},
    {"title": "Hoja", "extension": "xlsx", "content": "| A |\n|---|\n| 1 |"},
    {"title": "Nota", "extension": "md", "content": "solo md"},
    {"content": "sin título ni extensión"},
  ]})
  folder = drafts_dir / "Levantamiento" / "S_iiiiiiii"
  doc, sheet, note, bare = meta["artifacts"]
  assert doc == {"id": "a1", "title": "Doc", "extension": "docx", "path": str(folder / "Doc.docx"),
                 "md_path": str(folder / "Doc.md"), "created_at": "c", "updated_at": "u"}
  assert (sheet["path"], sheet["md_path"], sheet["created_at"], sheet["updated_at"]) == (
    str(folder / "Hoja.xlsx"), str(folder / "Hoja.md"), "", "")
  assert len(sheet["id"]) == 36
  assert (note["extension"], note["path"]) == ("md", str(folder / "Nota.md"))
  assert (bare["title"], bare["extension"], bare["path"]) == ("Documento", "docx", str(folder / "Documento.docx"))
  assert (folder / "Doc.md").read_text(encoding="utf-8") == "# T"
  assert (folder / "Doc.docx").stat().st_size > 0 and (folder / "Hoja.xlsx").stat().st_size > 0
  assert not (folder / "Nota.docx").exists() and not (folder / "Nota.xlsx").exists()


def test_a_binary_file_that_cannot_be_built_leaves_only_the_markdown_and_logs_it(drafts_dir, monkeypatch, caplog):
  def boom(content, title):
    raise RuntimeError("sin memoria")

  monkeypatch.setitem(ds._BINARY_BUILDERS, "docx", boom)
  with caplog.at_level(logging.WARNING, logger=ds.logger.name):
    meta = ds.save_draft_session({"name": "S", "artifacts": [{"title": "Doc", "extension": "docx", "content": "x"}]})
  (artifact,) = meta["artifacts"]
  assert artifact["path"] == artifact["md_path"] and artifact["path"].endswith("Doc.md")
  assert not list(drafts_dir.glob("*/*/Doc.docx"))
  assert "Could not build DOCX for Doc: sin memoria" in caplog.text


def test_the_artifacts_win_over_the_document_content(drafts_dir):
  meta = ds.save_draft_session({"documentContent": "suelto", "artifacts": [{"title": "A", "extension": "md", "content": "x"}]})
  assert [a["title"] for a in meta["artifacts"]] == ["A"]


def test_the_document_content_is_saved_as_one_markdown_artifact_when_there_are_no_artifacts(drafts_dir):
  meta = ds.save_draft_session({"id": "i" * 10, "name": "Sesión", "documentContent": "# Doc"})
  folder = drafts_dir / "Levantamiento" / "Sesión_iiiiiiii"
  (artifact,) = meta["artifacts"]
  assert (folder / "Sesión.md").read_text(encoding="utf-8") == "# Doc"
  assert artifact["title"] == "Sesión" and artifact["extension"] == "md" and len(artifact["id"]) == 36
  assert artifact["path"] == artifact["md_path"] == str(folder / "Sesión.md")
  assert "created_at" not in artifact


def test_a_session_without_content_has_no_artifacts(drafts_dir):
  meta = ds.save_draft_session({"name": "Vacío"})
  assert meta["artifacts"] == [] and meta["artifact_count"] == 0


def test_the_metadata_is_saved_in_the_draft_folder_and_returned(drafts_dir):
  meta = ds.save_draft_session({"id": "i" * 10, "name": "M", "user_id": "u1", "lastInteraction": "L"})
  folder = drafts_dir / "Levantamiento" / "M_iiiiiiii"
  stored = read(folder / "metadata.json")
  assert stored == meta
  assert {k: meta[k] for k in ("id", "user_id", "title", "specification", "last_interaction", "folder_path")} == {
    "id": "i" * 10, "user_id": "u1", "title": "M", "specification": "Levantamiento", "last_interaction": "L",
    "folder_path": str(folder)}
  assert meta["updated_at"].startswith("20")


def test_saving_the_same_session_again_updates_the_same_draft(drafts_dir):
  ds.save_draft_session({"id": "i" * 10, "name": "S", "messages": [{"content": "uno"}]})
  again = ds.save_draft_session({"id": "i" * 10, "name": "S", "messages": [{"content": "uno"}, {"content": "dos"}]})
  assert again["message_count"] == 2 and len(ds.list_generated_drafts()) == 1


def test_scanning_skips_loose_files_and_folders_without_usable_metadata(drafts_dir):
  good = ds.save_draft_session({"id": "good-0000", "name": "G"})
  (drafts_dir / "stray.txt").write_text("x")
  (drafts_dir / "Mejoras" / "file.txt").write_text("x")
  for name, content in (("broken", "{no json"), ("noid", '{"x": 1}'), ("list", "[1]")):
    folder = drafts_dir / "Mejoras" / name
    folder.mkdir()
    (folder / "metadata.json").write_text(content)
  (drafts_dir / "Mejoras" / "nometa").mkdir()
  assert [d["id"] for d in ds.list_generated_drafts()] == [good["id"]]


def test_scanning_adds_the_folder_path_it_found_the_draft_in(drafts_dir):
  ds.ensure_draft_dirs()
  folder = drafts_dir / "Mejoras" / "manual"
  folder.mkdir()
  (folder / "metadata.json").write_text(json.dumps({"id": "m", "folder_path": "wrong"}))
  assert ds.list_generated_drafts() == [{"id": "m", "folder_path": str(folder)}]


def test_drafts_are_listed_newest_interaction_first_falling_back_to_the_update_time(drafts_dir):
  for draft_id, last in (("a" * 10, "2024"), ("b" * 10, "2025"), ("c" * 10, "2023")):
    ds.save_draft_session({"id": draft_id, "name": draft_id, "lastInteraction": last})
  manual = drafts_dir / "Mejoras" / "manual"
  manual.mkdir()
  (manual / "metadata.json").write_text(json.dumps({"id": "m", "updated_at": "2024-06"}))
  assert [d["id"] for d in ds.list_generated_drafts()] == ["b" * 10, "m", "a" * 10, "c" * 10]


def test_listing_keeps_the_drafts_of_the_user_and_those_without_owner(drafts_dir):
  ds.save_draft_session({"id": "mine-0000", "name": "1", "user_id": "u1"})
  ds.save_draft_session({"id": "theirs-000", "name": "2", "user_id": "u2"})
  ds.save_draft_session({"id": "nobody-000", "name": "3"})
  assert sorted(d["id"] for d in ds.list_generated_drafts(user_id="u1")) == ["mine-0000", "nobody-000"]
  assert len(ds.list_generated_drafts()) == 3


def test_listing_filters_by_the_normalized_specification(drafts_dir):
  ds.save_draft_session({"id": "inv-00000", "name": "1", "specification": "inventario"})
  ds.save_draft_session({"id": "mej-00000", "name": "2", "specification": "mejoras"})
  assert [d["id"] for d in ds.list_generated_drafts(specification="INVENTARIO_requerimientos")] == ["inv-00000"]
  assert [d["id"] for d in ds.list_generated_drafts(specification="qa_analysis")] == ["mej-00000"]


def test_a_draft_is_returned_with_its_chat_details(drafts_dir):
  ds.save_draft_session({"id": "i" * 10, "name": "D", "messages": [{"content": "hola"}]})
  draft = ds.get_generated_draft("i" * 10)
  assert draft["details"]["messages"] == [{"content": "hola"}] and draft["title"] == "D"
  assert ds.get_generated_draft("missing") is None


def test_a_draft_without_a_readable_chat_is_returned_without_details(drafts_dir):
  meta = ds.save_draft_session({"id": "i" * 10, "name": "D"})
  chat = drafts_dir / "Levantamiento" / "D_iiiiiiii" / "chat.json"
  chat.write_text("{broken")
  assert "details" not in ds.get_generated_draft(meta["id"])
  chat.unlink()
  assert "details" not in ds.get_generated_draft(meta["id"])


def test_deleting_removes_the_folder_and_says_whether_the_draft_existed(drafts_dir):
  meta = ds.save_draft_session({"id": "i" * 10, "name": "D"})
  other = ds.save_draft_session({"id": "o" * 10, "name": "O"})
  assert ds.delete_generated_draft(meta["id"]) is True
  assert not (drafts_dir / "Levantamiento" / "D_iiiiiiii").exists()
  assert [d["id"] for d in ds.list_generated_drafts()] == [other["id"]]
  assert ds.delete_generated_draft(meta["id"]) is False


def test_a_draft_written_by_hand_can_be_deleted_too(drafts_dir):
  ds.ensure_draft_dirs()
  folder = drafts_dir / "Mejoras" / "manual"
  folder.mkdir()
  (folder / "metadata.json").write_text(json.dumps({"id": "m"}))
  assert ds.delete_generated_draft("m") is True and not folder.exists()


def test_the_folders_are_created_with_their_parents_and_ensuring_them_twice_is_fine(tmp_path, monkeypatch):
  monkeypatch.setattr(ds, "USER_DRAFTS_DIR", tmp_path / "a" / "b" / "Borradores")
  monkeypatch.setattr(ds, "GENERATED_DIR", tmp_path / "c" / "d")
  monkeypatch.setattr(ds, "ensure_local_dirs", lambda: None)
  ds.ensure_draft_dirs()
  ds.ensure_draft_dirs()
  assert (tmp_path / "c" / "d").is_dir()
  assert all((tmp_path / "a" / "b" / "Borradores" / spec).is_dir() for spec in ds.VALID_SPECS)


def test_a_session_can_be_saved_into_a_folder_that_has_no_specification_parent_yet(tmp_path, monkeypatch):
  monkeypatch.setattr(ds, "USER_DRAFTS_DIR", tmp_path / "Borradores")
  monkeypatch.setattr(ds, "GENERATED_DIR", tmp_path / "generated")
  monkeypatch.setattr(ds, "ensure_local_dirs", lambda: None)
  monkeypatch.setattr(ds, "ensure_draft_dirs", lambda: None)
  meta = ds.save_draft_session({"id": "i" * 10, "name": "S"})
  assert (tmp_path / "Borradores" / "Levantamiento" / "S_iiiiiiii" / "metadata.json").exists() and meta["id"]


def test_the_metadata_keeps_accents_readable(drafts_dir):
  ds.save_draft_session({"id": "i" * 10, "name": "Sesión ñandú"})
  text = (drafts_dir / "Levantamiento" / "Sesión_ñandú_iiiiiiii" / "metadata.json").read_text(encoding="utf-8")
  assert "Sesión ñandú" in text


def test_deleting_does_not_fail_when_the_folder_cannot_be_removed(drafts_dir, monkeypatch):
  meta = ds.save_draft_session({"id": "i" * 10, "name": "D"})

  def rmtree(path, ignore_errors=False):
    if not ignore_errors:
      raise OSError("locked")

  monkeypatch.setattr(ds.shutil, "rmtree", rmtree)
  assert ds.delete_generated_draft(meta["id"]) is True
