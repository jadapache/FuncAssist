"""Corporate template storage: index file, content extraction, tag detection and CRUD."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import docx
import pytest

from app.core import template_storage as ts


class _FailingUoW:
  async def __aenter__(self):
    raise RuntimeError("no db")

  async def __aexit__(self, *exc):
    return False


class _FakeTemplates:
  def __init__(self, items=None, item=None):
    self.items, self.item = items, item
    self.upserted, self.deleted = [], []

  async def list(self):
    return self.items

  async def get(self, tid):
    return self.item

  async def upsert(self, item):
    self.upserted.append(item)

  async def delete(self, tid):
    self.deleted.append(tid)


def _uow_with(templates):
  class UoW:
    corporate_templates = templates

    async def __aenter__(self):
      return self

    async def __aexit__(self, *exc):
      return False

    async def commit(self):
      pass

  return UoW


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
  monkeypatch.setattr(ts, "TEMPLATES_DIR", tmp_path / "templates")
  monkeypatch.setattr(ts, "INDEX_FILE", tmp_path / "templates" / "templates_index.json")
  monkeypatch.setattr(ts, "LEGACY_INDEX_FILE", tmp_path / "legacy_index.json")
  monkeypatch.setattr(ts, "ensure_local_dirs", lambda: None)
  monkeypatch.setattr("app.db.unit_of_work.AsyncUnitOfWork", _FailingUoW)
  return tmp_path


# ------------------------------------------------------------------ index


def test_load_index_variants(sandbox):
  assert ts._load_index() == []
  ts._save_index([{"id": "a"}])
  assert ts._load_index() == [{"id": "a"}]
  ts.INDEX_FILE.write_text("{not json", encoding="utf-8")
  assert ts._load_index() == []


def test_legacy_index_is_migrated(sandbox):
  ts.LEGACY_INDEX_FILE.write_text(json.dumps([{"id": "old"}]), encoding="utf-8")
  assert ts._load_index() == [{"id": "old"}]
  assert not ts.LEGACY_INDEX_FILE.exists() and json.loads(ts.INDEX_FILE.read_text()) == [{"id": "old"}]


def test_legacy_index_corrupt_returns_empty(sandbox):
  ts.LEGACY_INDEX_FILE.write_text("garbage", encoding="utf-8")
  assert ts._load_index() == []


# ------------------------------------------------------------------ tags / extraction


def test_detect_tags():
  text = "Hola {{ necesidad }} y [[ req_funcional ]] y {{necesidad}} {{ no valid! }}"
  assert ts.detect_tags(text) == ["NECESIDAD", "REQ_FUNCIONAL"]
  assert ts.detect_tags("") == []


def _make_docx(path: Path):
  d = docx.Document()
  d.add_heading("Titulo", 1)
  d.add_heading("Sub", 2)
  d.add_heading("Sub3", 3)
  d.add_paragraph("Texto normal {{NECESIDAD}}")
  d.add_paragraph("   ")
  table = d.add_table(rows=2, cols=2)
  table.cell(0, 0).text = "A"
  table.cell(0, 1).text = "B"
  table.cell(1, 0).text = "1"
  table.cell(1, 1).text = "2"
  d.sections[0].header.paragraphs[0].text = "Encabezado {{PAGINA}}"
  d.sections[0].footer.paragraphs[0].text = "Pie"
  d.save(path)


def test_extract_docx_structure(tmp_path):
  p = tmp_path / "t.docx"
  _make_docx(p)
  res = ts.extract_docx_structure(p)
  assert "# Titulo" in res["content"] and "## Sub" in res["content"] and "### Sub3" in res["content"]
  assert "| A | B |" in res["content"] and "| --- | --- |" in res["content"] and "| 1 | 2 |" in res["content"]
  assert "Texto normal" in res["content"]
  assert res["header"] == "Encabezado {{PAGINA}}" and res["footer"] == "Pie"


def test_extract_docx_header_footer_tables_and_defaults(tmp_path):
  d = docx.Document()
  d.add_paragraph("cuerpo")
  ht = d.sections[0].header.add_table(1, 2, width=docx.shared.Inches(4))
  ht.cell(0, 0).text = "Logo"
  ht.cell(0, 1).text = "Formato"
  ft = d.sections[0].footer.add_table(1, 1, width=docx.shared.Inches(4))
  ft.cell(0, 0).text = "Pie tabla"
  p = tmp_path / "t.docx"
  d.save(p)
  res = ts.extract_docx_structure(p)
  assert "| Logo | Formato |" in res["header"] and "| Pie tabla |" in res["footer"]

  empty = docx.Document()
  q = tmp_path / "empty.docx"
  empty.save(q)
  res = ts.extract_docx_structure(q)
  assert res["content"] == "" and "{{PAGINA}}" in res["header"] and "{{TOTAL_PAGINAS}}" in res["footer"]


def test_extract_docx_errors(tmp_path, monkeypatch):
  bad = tmp_path / "bad.docx"
  bad.write_text("not a zip", encoding="utf-8")
  assert ts.extract_docx_structure(bad)["content"].startswith("Error al extraer estructura .docx")
  monkeypatch.setattr(ts, "docx", None)
  assert "no disponible" in ts.extract_docx_structure(bad)["content"]


def _put(name: str, data: bytes) -> str:
  ts.ensure_template_dirs()
  (ts.TEMPLATES_DIR / name).write_bytes(data)
  return name


def test_extract_template_content_formats(sandbox):
  assert "no se encuentra" in ts.extract_template_content("missing.md")
  assert ts.extract_template_content(_put("a.md", "# Hola ñ".encode())) == "# Hola ñ"
  assert ts.extract_template_content(_put("l.txt", "caf\xe9".encode("latin-1"))) == "café"

  _make_docx(ts.TEMPLATES_DIR / "d.docx")
  assert "# Titulo" in ts.extract_template_content("d.docx")

  xlsx = ts.TEMPLATES_DIR / "x.xlsx"
  with zipfile.ZipFile(xlsx, "w") as z:
    z.writestr("xl/sharedStrings.xml", "<sst><si><t>Uno</t></si><si><t> </t></si><si><t>Dos</t></si></sst>")
  assert ts.extract_template_content("x.xlsx") == "Uno\nDos"
  empty = ts.TEMPLATES_DIR / "e.xlsx"
  with zipfile.ZipFile(empty, "w") as z:
    z.writestr("other.xml", "<a/>")
  assert "cargado exitosamente" in ts.extract_template_content("e.xlsx")
  _put("broken.xlsx", b"not a zip")
  assert "listo para estructurar" in ts.extract_template_content("broken.xlsx")

  assert "texto legible" in ts.extract_template_content(_put("old.doc", b"\x00\x01texto legible aqui\x00\x02"))
  assert ts.extract_template_content(_put("bin.dat", b"\x00\x01\x02")) == "Plantilla binaria (.dat) almacenada correctamente."


def test_extract_text_read_error(sandbox, monkeypatch):
  _put("bad.md", b"\xff\xfe")
  real = Path.read_text

  def fake(self, *a, **kw):
    if kw.get("encoding") == "latin-1":
      raise OSError("disk")
    return real(self, *a, **kw)

  monkeypatch.setattr(Path, "read_text", fake)
  assert "Error al leer el archivo de texto" in ts.extract_template_content("bad.md")


# ------------------------------------------------------------------ CRUD


@pytest.mark.asyncio
async def test_save_list_get_and_file_path(sandbox):
  item = await ts.save_template_file("Plan.md", b"Hola {{ custom_tag }}", title="  ", module="")
  assert item["title"] == "Plan" and item["module"] == "general" and item["file_type"] == "md"
  assert "CUSTOM_TAG" in item["tags"] and "NECESIDAD" in item["tags"] and item["file_size"] == 21

  listed = await ts.list_templates()
  assert [t["id"] for t in listed] == [item["id"]]
  assert (await ts.get_template(item["id"]))["id"] == item["id"]
  assert await ts.get_template("nope") is None
  assert ts.get_template_file_path(item["id"]).name == item["stored_filename"]
  assert ts.get_template_file_path("nope") is None


@pytest.mark.asyncio
async def test_missing_tags_are_defaulted(sandbox):
  ts._save_index([{"id": "x", "stored_filename": "x.md"}])
  assert "NECESIDAD" in (await ts.list_templates())[0]["tags"]
  assert "NECESIDAD" in (await ts.get_template("x"))["tags"]
  assert ts.get_template_file_path("x") is None  # stored file does not exist


@pytest.mark.asyncio
async def test_db_backed_list_get_and_writes(sandbox, monkeypatch):
  tpl = _FakeTemplates(items=[{"id": "db1"}], item={"id": "db1"})
  monkeypatch.setattr("app.db.unit_of_work.AsyncUnitOfWork", _uow_with(tpl))
  listed = await ts.list_templates()
  assert listed[0]["id"] == "db1" and "tags" in listed[0]
  assert (await ts.get_template("db1"))["tags"]

  item = await ts.save_template_file("a.txt", b"x")
  assert tpl.upserted[-1]["id"] == item["id"]
  await ts.update_template_metadata(item["id"], title="Nuevo")
  assert tpl.upserted[-1]["title"] == "Nuevo"
  assert await ts.delete_template(item["id"]) is True and tpl.deleted == [item["id"]]


@pytest.mark.asyncio
async def test_update_template_metadata(sandbox):
  md = await ts.save_template_file("a.md", b"viejo")
  upd = await ts.update_template_metadata(md["id"], title=" Titulo ", module=" qa ", tags=["b", "a", "b"], content="nuevo {{X}}")
  assert upd["title"] == "Titulo" and upd["module"] == "qa" and upd["tags"] == ["a", "b"]
  assert (ts.TEMPLATES_DIR / md["stored_filename"]).read_text(encoding="utf-8") == "nuevo {{X}}"
  assert upd["file_size"] == len("nuevo {{X}}")

  blank = await ts.update_template_metadata(md["id"], title="  ", module="")
  assert blank["title"] == "Titulo" and blank["module"] == "qa"

  d = ts.TEMPLATES_DIR / "z.docx"
  _make_docx(d)
  ts._save_index(ts._load_index() + [{"id": "dx", "stored_filename": "z.docx", "title": "D"}])
  await ts.update_template_metadata("dx", content="sidecar")
  assert (ts.TEMPLATES_DIR / "z.docx.content.md").read_text(encoding="utf-8") == "sidecar"

  assert await ts.update_template_metadata("missing", title="x") is None


@pytest.mark.asyncio
async def test_get_template_detail_sources(sandbox):
  assert await ts.get_template_detail("missing") is None

  md = await ts.save_template_file("a.md", b"Hola {{NECESIDAD}}")
  detail = await ts.get_template_detail(md["id"])
  assert detail["content"] == "Hola {{NECESIDAD}}" and detail["detected_tags"] == ["NECESIDAD"]
  assert detail["header_content"] == "" and detail["system_tags"] is ts.DEFAULT_SYSTEM_TAGS

  await ts.update_template_metadata(md["id"], content="editado {{AREA}}")
  assert (await ts.get_template_detail(md["id"]))["detected_tags"] == ["AREA"]

  d = ts.TEMPLATES_DIR / "w.docx"
  _make_docx(d)
  ts._save_index(ts._load_index() + [{"id": "dx", "stored_filename": "w.docx"}])
  detail = await ts.get_template_detail("dx")
  assert "# Titulo" in detail["content"] and detail["header_content"] == "Encabezado {{PAGINA}}"
  assert set(detail["detected_tags"]) == {"NECESIDAD", "PAGINA"}

  (ts.TEMPLATES_DIR / "w.docx.content.md").write_text("de sidecar", encoding="utf-8")
  detail = await ts.get_template_detail("dx")
  assert detail["content"] == "de sidecar" and detail["footer_content"] == "Pie"


@pytest.mark.asyncio
async def test_delete_template(sandbox):
  item = await ts.save_template_file("a.md", b"x")
  path = ts.TEMPLATES_DIR / item["stored_filename"]
  assert path.exists()
  assert await ts.delete_template(item["id"]) is True
  assert not path.exists() and ts._load_index() == []
  assert await ts.delete_template(item["id"]) is False


# ------------------------------------------------------------------ behaviours pinned by mutation testing


def test_template_dirs_are_created_with_their_parents_and_can_be_ensured_twice(sandbox, monkeypatch):
  nested = sandbox / "deep" / "nested" / "templates"
  monkeypatch.setattr(ts, "TEMPLATES_DIR", nested)
  ts.ensure_template_dirs()
  ts.ensure_template_dirs()
  assert nested.is_dir()


def test_a_table_gets_its_separator_only_after_the_first_row(tmp_path):
  d = docx.Document()
  table = d.add_table(rows=3, cols=2)
  for r, values in enumerate([("A", "B"), ("1", "2"), ("3", "4")]):
    for c, value in enumerate(values):
      table.cell(r, c).text = value
  path = tmp_path / "t.docx"
  d.save(path)
  assert "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |" in ts.extract_docx_structure(path)["content"]


def test_a_table_whose_first_row_is_empty_has_no_separator(tmp_path):
  d = docx.Document()
  table = d.add_table(rows=3, cols=2)
  for r, values in enumerate([("", ""), ("x", "y"), ("p", "q")]):
    for c, value in enumerate(values):
      table.cell(r, c).text = value
  path = tmp_path / "t.docx"
  d.save(path)
  content = ts.extract_docx_structure(path)["content"]
  assert "| x | y |\n| p | q |" in content and "---" not in content


@pytest.mark.parametrize("raw,expected", [
  (b"\x00\x01 abc \x02\x03", "Plantilla binaria (.doc) almacenada correctamente."),  # three characters are not enough
  (b"\x00\x01 abcd \x02\x03", " abcd "),
])
def test_binary_templates_show_only_strings_of_more_than_three_characters(sandbox, raw, expected):
  assert ts.extract_template_content(_put("b.doc", raw)) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("filename,title,module,expected_title,expected_module", [
  ("Mi Formato.docx", "", "", "Mi Formato", "general"),
  ("Mi Formato.docx", "  Título propio  ", "ventas", "Título propio", "ventas"),
  ("otro.md", "   ", "general", "otro", "general"),
])
async def test_saved_templates_get_a_default_title_and_module(sandbox, filename, title, module, expected_title, expected_module):
  item = await ts.save_template_file(filename, b"x", title=title, module=module)
  assert (item["title"], item["module"]) == (expected_title, expected_module)
  assert (await ts.get_template(item["id"]))["title"] == expected_title


@pytest.mark.asyncio
async def test_edited_content_does_not_hide_the_header_and_footer_of_a_word_template(sandbox):
  d = ts.TEMPLATES_DIR / "w.docx"
  ts.ensure_template_dirs()
  _make_docx(d)
  ts._save_index([{"id": "dx", "stored_filename": "w.docx", "custom_content": "editado {{AREA}}"}])
  detail = await ts.get_template_detail("dx")
  assert detail["content"] == "editado {{AREA}}"
  assert (detail["header_content"], detail["footer_content"]) == ("Encabezado {{PAGINA}}", "Pie")
  assert set(detail["detected_tags"]) == {"AREA", "PAGINA"}


@pytest.mark.asyncio
async def test_only_word_templates_have_a_header_and_footer(sandbox):
  item = await ts.save_template_file("a.md", b"texto")
  detail = await ts.get_template_detail(item["id"])
  assert (detail["header_content"], detail["footer_content"]) == ("", "")
