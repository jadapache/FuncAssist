"""Tests for drafts storage (filesystem) and the thin run_grounded_feature wrappers."""

from __future__ import annotations

import json

import openpyxl
import pytest
from docx import Document

import app.features.drafts.storage as ds


@pytest.fixture
def drafts_dir(tmp_path, monkeypatch):
  drafts = tmp_path / "Borradores"
  monkeypatch.setattr(ds, "USER_DRAFTS_DIR", drafts)
  monkeypatch.setattr(ds, "GENERATED_DIR", tmp_path / "generated")
  monkeypatch.setattr(ds, "ensure_local_dirs", lambda: None)
  return drafts


@pytest.mark.parametrize("raw,expected", [
  (None, "Levantamiento"), ("", "Levantamiento"), ("chat", "Mejoras"),
  ("  QA_Analysis ", "Mejoras"), ("inventario_requerimientos", "Inventario"),
  ("unknown", "Levantamiento"),
])
def test_normalize_specification(raw, expected):
  assert ds.normalize_specification(raw) == expected




def test_sanitize_folder_name():
  assert ds.sanitize_folder_name('a/b:c*  d') == "a_b_c__d"
  assert ds.sanitize_folder_name("   ") == "Borrador"
  assert len(ds.sanitize_folder_name("x" * 100)) == 60


def test_ensure_draft_dirs_creates_spec_folders(drafts_dir):
  ds.ensure_draft_dirs()
  assert sorted(p.name for p in drafts_dir.iterdir()) == sorted(ds.VALID_SPECS)


def test_save_with_docx_and_xlsx_artifacts(drafts_dir):
  meta = ds.save_draft_session({
    "id": "abcdef1234567890",
    "name": "Sesión: Pagos",
    "feature_slug": "requerimientos",
    "user_id": "u1",
    "messages": [
      {"role": "user", "content": " Hola ", "timestamp": "t1"},
      {"role": "assistant", "content": "Respuesta"},
    ],
    "artifacts": [
      {"id": "a1", "title": "Doc Final", "extension": "DOCX", "content": "# Titulo\nTexto"},
      {"title": "Hoja", "extension": "xlsx", "content": "| ID | X |\n|---|---|\n| 1 | 2 |"},
      {"title": "Notas", "extension": "md", "content": "solo md"},
    ],
  })
  folder = drafts_dir / "Levantamiento" / "Sesión__Pagos_abcdef12"
  assert meta["folder_path"] == str(folder)
  assert meta["specification"] == "Levantamiento"
  assert meta["message_count"] == 2 and meta["artifact_count"] == 3

  chat = json.loads((folder / "chat.json").read_text(encoding="utf-8"))
  assert chat["id"] == "abcdef1234567890" and len(chat["messages"]) == 2
  md = (folder / "chat.md").read_text(encoding="utf-8")
  assert "# Historial de Sesión - Sesión: Pagos" in md
  assert "### Usuario (t1)" in md and "### Asistente QA ()" in md and "\nHola\n" in md

  arts = {a["title"]: a for a in meta["artifacts"]}
  assert arts["Doc Final"]["path"].endswith("Doc_Final.docx")
  assert arts["Doc Final"]["extension"] == "docx"
  doc = Document(str(folder / "Doc_Final.docx"))
  assert "Titulo" in [p.text for p in doc.paragraphs]
  wb = openpyxl.load_workbook(folder / "Hoja.xlsx")
  assert wb.active["A2"].value == "1"
  assert arts["Notas"]["path"].endswith("Notas.md")
  assert (folder / "Notas.md").read_text(encoding="utf-8") == "solo md"

  on_disk = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
  assert on_disk["id"] == "abcdef1234567890"


def test_save_builder_failures_fall_back_to_md(drafts_dir, monkeypatch):
  import app.features.inventario.xlsx_builder as xb
  import app.features.levantamiento.docx_builder as db

  def boom(*a, **k):
    raise RuntimeError("fail")

  monkeypatch.setattr(db, "create_levantamiento_docx", boom)
  monkeypatch.setattr(xb, "create_inventario_xlsx", boom)
  meta = ds.save_draft_session({
    "title": "T", "specification": "mejoras",
    "artifacts": [{"title": "D", "content": "x"}, {"title": "S", "extension": "xlsx", "content": "y"}],
  })
  assert all(a["path"].endswith(".md") for a in meta["artifacts"])
  assert meta["specification"] == "Mejoras"


def test_save_document_content_only_and_defaults(drafts_dir):
  meta = ds.save_draft_session({"documentContent": "# Doc"})
  assert meta["title"] == "Borrador"
  assert meta["specification"] == "Levantamiento"
  assert len(meta["id"]) == 36
  assert meta["artifacts"][0]["extension"] == "md"
  assert open(meta["artifacts"][0]["path"], encoding="utf-8").read() == "# Doc"


def test_save_without_content_has_no_artifacts(drafts_dir):
  meta = ds.save_draft_session({"id": "z" * 10, "name": "Vacío", "lastInteraction": "2020"})
  assert meta["artifacts"] == [] and meta["last_interaction"] == "2020"


def test_list_get_delete_roundtrip(drafts_dir):
  a = ds.save_draft_session({"id": "id-a-00000", "name": "A", "specification": "inventario",
                              "user_id": "u1", "last_interaction": "2024-01-01"})
  b = ds.save_draft_session({"id": "id-b-00000", "name": "B", "specification": "mejoras",
                              "user_id": "u2", "last_interaction": "2025-01-01"})
  ds.save_draft_session({"id": "id-c-00000", "name": "C", "last_interaction": "2023-01-01"})

  # noise that the scanner must skip
  (drafts_dir / "stray.txt").write_text("x")
  (drafts_dir / "Mejoras" / "file.txt").write_text("x")
  bad = drafts_dir / "Mejoras" / "bad"
  bad.mkdir()
  (bad / "metadata.json").write_text("{not json")
  noid = drafts_dir / "Mejoras" / "noid"
  noid.mkdir()
  (noid / "metadata.json").write_text(json.dumps({"x": 1}))
  (drafts_dir / "Mejoras" / "nometa").mkdir()

  all_ids = [i["id"] for i in ds.list_generated_drafts()]
  assert all_ids == ["id-b-00000", "id-a-00000", "id-c-00000"]  # sorted desc
  assert [i["id"] for i in ds.list_generated_drafts(user_id="u1")] == ["id-a-00000", "id-c-00000"]
  assert [i["id"] for i in ds.list_generated_drafts(specification="qa_analysis")] == ["id-b-00000"]

  got = ds.get_generated_draft("id-a-00000")
  assert got["details"]["title"] == "A"
  assert ds.get_generated_draft("missing") is None

  # corrupted chat.json -> no details but item returned
  (drafts_dir / "Mejoras" / "B_id-b-000" / "chat.json").write_text("{bad")
  assert "details" not in ds.get_generated_draft("id-b-00000")

  assert ds.delete_generated_draft("id-a-00000") is True
  assert ds.get_generated_draft("id-a-00000") is None
  assert ds.delete_generated_draft("id-a-00000") is False
  assert a["id"] and b["id"]




# --- thin service wrappers -------------------------------------------------

SERVICE_CASES = [
  ("app.features.inventario.service", "generate_inventario_report", {"query": "q"},
   {"feature": "inventario_doc", "sources": ["knowledge", "jira", "github"]}),
  ("app.features.levantamiento.service", "generate_levantamiento_report", {"query": "q", "sources": ["jira"]},
   {"feature": "levantamiento_doc", "sources": ["jira"]}),
  ("app.features.mejoras.service", "generate_mejoras_report", {"query": "q"},
   {"feature": "mejoras_doc", "sources": ["jira", "github", "gitlab", "knowledge"]}),
  ("app.features.change_impact.service", "analyze_change_impact", {"query": "q", "user_id": "u"},
   {"feature": "change_impact", "sources": ["jira", "github", "knowledge"], "user_id": "u"}),
  ("app.features.prd_checker.service", "review_prd", {"query": "q", "document_ids": ["d1"]},
   {"feature": "prd_checker", "sources": ["knowledge"], "document_ids": ["d1"]}),
  ("app.features.standup.service", "generate_standup", {},
   {"feature": "standup", "sources": ["jira", "github"]}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("module,func,kwargs,expected", SERVICE_CASES)
async def test_service_wrappers_delegate(monkeypatch, module, func, kwargs, expected):
  import importlib

  mod = importlib.import_module(module)
  calls = []

  async def fake_run(**kw):
    calls.append(kw)
    return {"ok": True}

  monkeypatch.setattr(mod, "run_grounded_feature", fake_run)
  assert await getattr(mod, func)(**kwargs) == {"ok": True}
  assert len(calls) == 1
  for k, v in expected.items():
    assert calls[0][k] == v
  if func == "generate_standup":
    assert "standup" in calls[0]["query"].lower()
