"""Text extraction, chunking, the upload endpoints and the context service edges of the knowledge base."""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.api import knowledge as knowledge_api
from app.context import knowledge, service
from app.context.models import SourceType
from app.main import create_app


# --- extraction -----------------------------------------------------------------

def test_images_are_described_not_read():
  assert knowledge.extract_text("Foto.PNG", b"1234") == "[Asset Imagen: Foto.PNG (4 bytes)]"
  assert knowledge.extract_text("a.bmp", b"") == "[Asset Imagen: a.bmp (0 bytes)]"


def test_plain_text_tries_utf8_then_utf16_then_latin1():
  assert knowledge.extract_text("a.txt", "canción".encode("utf-8")) == "canción"
  assert knowledge.extract_text("a.txt", "canción".encode("utf-16")) == "canción"
  assert knowledge.extract_text("a.txt", "canción".encode("latin-1")) == "canción"


def test_html_drops_scripts_and_styles_and_breaks_lines_on_blocks():
  html = b"<html><style>p{}</style><script>alert(1)</script><h1>Titulo</h1><p>Uno &amp; dos</p>Tres</html>"
  assert knowledge.extract_text("a.HTM", html) == "Titulo Uno & dos Tres"
  assert knowledge.extract_text("a.html", "<p>caf\xe9</p>".encode("latin-1")) == "café"


def test_pdf_pages_are_joined_and_unreadable_pdfs_are_reported():
  from pypdf import PdfWriter

  writer = PdfWriter()
  writer.add_blank_page(width=72, height=72)
  writer.add_blank_page(width=72, height=72)
  buffer = BytesIO()
  writer.write(buffer)
  assert knowledge.extract_text("a.pdf", buffer.getvalue()) == "\n"
  with pytest.raises(ValueError, match="Failed to read PDF"):
    knowledge.extract_text("a.pdf", b"not a pdf")


def _docx(build):
  from docx import Document

  document = Document()
  build(document)
  buffer = BytesIO()
  document.save(buffer)
  return buffer.getvalue()


def test_docx_keeps_paragraphs_then_tables_as_markdown():
  def build(document):
    document.add_paragraph("  Intro  ")
    document.add_paragraph("   ")
    table = document.add_table(rows=3, cols=2)
    for r, row in enumerate([("Nombre", "Edad"), ("Ana", "30"), ("", "")]):
      for c, value in enumerate(row):
        table.cell(r, c).text = value
    document.add_table(rows=1, cols=1)

  text = knowledge.extract_text("a.docx", _docx(build))
  assert text == "Intro\n\n| Nombre | Edad |\n| --- | --- |\n| Ana | 30 |"


def test_docx_single_row_tables_get_no_separator_and_multiline_cells_are_flattened():
  def build(document):
    one = document.add_table(rows=1, cols=2)
    one.cell(0, 0).text, one.cell(0, 1).text = "a", "b"
    two = document.add_table(rows=2, cols=1)
    two.cell(0, 0).text, two.cell(1, 0).text = "h", "x\ny"

  text = knowledge.extract_text("a.docx", _docx(build))
  assert text == "| a | b |\n\n| h |\n| --- |\n| x y |"


def test_docx_that_is_not_a_docx_is_reported():
  with pytest.raises(ValueError, match="Failed to read DOCX"):
    knowledge.extract_text("a.docx", b"nope")


# --- chunking -------------------------------------------------------------------

def test_chunking_collapses_whitespace_and_skips_empty_text():
  assert knowledge.chunk_text("  \n\t ") == []
  assert knowledge.chunk_text("a \n b") == ["a b"]
  assert knowledge.chunk_text("x" * knowledge.CHUNK_SIZE) == ["x" * knowledge.CHUNK_SIZE]


def test_long_text_is_split_with_overlap_and_nothing_is_lost():
  size, overlap = knowledge.CHUNK_SIZE, knowledge.CHUNK_OVERLAP
  text = "".join(chr(97 + i % 26) for i in range(size * 2))
  chunks = knowledge.chunk_text(text)
  assert [len(c) for c in chunks] == [size, size, 2 * overlap]
  assert chunks[0][-overlap:] == chunks[1][:overlap]
  assert chunks[0] + chunks[1][overlap:] + chunks[2][overlap:] == text


def test_text_just_over_the_limit_makes_two_chunks():
  chunks = knowledge.chunk_text("y" * (knowledge.CHUNK_SIZE + 1))
  assert [len(c) for c in chunks] == [knowledge.CHUNK_SIZE, knowledge.CHUNK_OVERLAP + 1]


# --- upload endpoints -----------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
  calls = []

  def fake_ingest(*, filename, raw, tags):
    calls.append((filename, raw, tags))
    if raw == b"bad":
      raise ValueError("No extractable text found in document.")
    return {"id": filename}

  monkeypatch.setattr(knowledge_api, "ingest_document", fake_ingest)
  test_client = TestClient(create_app())
  test_client.calls = calls
  return test_client


def test_single_upload_splits_the_tags(client):
  response = client.post("/api/knowledge/documents", files={"file": ("a.txt", b"hola")}, data={"tags": " a, ,b "})
  assert response.status_code == 200
  assert client.calls == [("a.txt", b"hola", ["a", "b"])]


def test_single_upload_rejects_empty_files_and_unreadable_ones(client):
  empty = client.post("/api/knowledge/documents", files={"file": ("a.txt", b"")})
  assert (empty.status_code, empty.json()["detail"]) == (400, "Empty file")
  bad = client.post("/api/knowledge/documents", files={"file": ("a.txt", b"bad")})
  assert (bad.status_code, bad.json()["detail"]) == (400, "No extractable text found in document.")


def test_batch_upload_keeps_the_good_files_and_lists_the_errors(client):
  files = [("files", ("a.txt", b"ok")), ("files", ("b.txt", b"")), ("files", ("c.txt", b"bad"))]
  body = client.post("/api/knowledge/documents/batch", files=files, data={"tags": "x"}).json()
  assert [d["id"] for d in body["documents"]] == ["a.txt"]
  assert body["errors"] == ["b.txt: empty", "c.txt: No extractable text found in document."]
  assert client.calls[0] == ("a.txt", b"ok", ["x"])


def test_batch_upload_fails_when_nothing_was_ingested(client):
  response = client.post("/api/knowledge/documents/batch", files=[("files", ("b.txt", b"")), ("files", ("c.txt", b"bad"))])
  assert response.status_code == 400
  assert response.json()["detail"] == "b.txt: empty; c.txt: No extractable text found in document."


# --- context service: shared GitHub and GitLab flow -----------------------------

class _Repos:
  def __init__(self, selected=True, authed=True):
    self.selected, self.authed, self.calls = selected, authed, []

  async def authenticate(self):
    return self.authed

  def selected_repos(self):
    return ["r"] if self.selected else []

  async def get_pull_requests(self, max_results):
    self.calls.append(("prs", max_results))
    return [{"number": 7, "repo": "o/r", "title": "T", "state": "open", "user": "u", "updated_at": "U", "merged_at": None}]

  get_merge_requests = get_pull_requests

  async def get_commits(self, max_results):
    self.calls.append(("commits", max_results))
    return [{"sha": "s1", "repo": "o/r", "message": "m", "author": "a", "date": "d"}]

  async def get_issues(self, max_results):
    self.calls.append(("issues", max_results))
    return [{"number": 3, "repo": "o/r", "title": "I", "state": "open", "user": "u", "updated_at": "U"}]


@pytest.fixture
def registry(monkeypatch):
  items = {}
  monkeypatch.setattr(service.registry, "get", lambda name: items[name])
  monkeypatch.setattr(service, "search_knowledge", lambda q, top_k=8: [])
  return items


@pytest.mark.asyncio
async def test_github_chunks_carry_their_text_title_and_label(registry):
  registry["github"] = _Repos()
  bundle = await service.assemble_context(query="q", sources=["github"])
  pr, commit = bundle.chunks
  assert pr.title == "PR #7: T" and pr.source_label == "o/r" and pr.source_type == SourceType.GITHUB
  assert pr.text == "PR #7 in o/r\nTitle: T\nState: open\nAuthor: u\nUpdated: U\nMerged: None"
  assert commit.title == "s1 m" and commit.text == "Commit s1 in o/r\nAuthor: a\nDate: d\nMessage: m"
  assert registry["github"].calls == [("prs", 20), ("commits", 20)]


@pytest.mark.asyncio
async def test_gitlab_chunks_carry_their_text_title_and_label(registry):
  registry["gitlab"] = _Repos()
  bundle = await service.assemble_context(query="q", sources=["gitlab"])
  mr, commit, issue = bundle.chunks
  assert mr.title == "MR !7: T" and mr.text.startswith("MR !7 in o/r\n") and mr.source_type == SourceType.GITLAB
  assert commit.id == "gitlab:commit:o/r:s1"
  assert issue.title == "Issue #3: I" and issue.text == "Issue #3 in o/r\nTitle: I\nState: open\nAuthor: u\nUpdated: U"
  assert registry["gitlab"].calls == [("prs", 20), ("commits", 20), ("issues", 15)]


@pytest.mark.asyncio
async def test_a_source_that_fails_half_way_is_both_used_and_missing(registry):
  class Failing(_Repos):
    async def get_commits(self, max_results):
      raise RuntimeError("boom")

  registry["github"] = Failing()
  bundle = await service.assemble_context(query="q", sources=["github"])
  assert (bundle.used_sources, bundle.missing_sources, bundle.chunks) == (["github"], ["github"], [])


# --- round 2 --------------------------------------------------------------------

def test_a_pdf_page_without_text_counts_as_empty(monkeypatch):
  import pypdf

  class Page:
    def __init__(self, text):
      self.text = text

    def extract_text(self):
      return self.text

  class Reader:
    def __init__(self, stream):
      self.pages = [Page("uno"), Page(None), Page("tres")]

  monkeypatch.setattr(pypdf, "PdfReader", Reader)
  assert knowledge.extract_text("a.pdf", b"x") == "uno\n\ntres"


def test_a_table_that_already_has_a_separator_row_is_left_alone():
  def build(document):
    table = document.add_table(rows=2, cols=2)
    for r, row in enumerate([("a", "b"), ("---", "---")]):
      for c, value in enumerate(row):
        table.cell(r, c).text = value

  assert knowledge.extract_text("a.docx", _docx(build)) == "| a | b |\n| --- | --- |"


@pytest.mark.asyncio
async def test_an_issue_without_a_summary_is_titled_by_its_key(registry):
  class Jira:
    async def authenticate(self, user_id=None):
      return True

    async def get_issues(self, max_results, user_id=None):
      return [{"key": "AAA-9"}]

  registry["jira"] = Jira()
  bundle = await service.assemble_context(query="", sources=["jira"])
  assert bundle.chunks[0].title == "AAA-9"


def test_rough_match_ignores_words_of_up_to_two_letters():
  assert service._rough_match("de la", "nada") is True
  assert service._rough_match("abc", "nada") is False
  assert service._rough_match("abc", "xx ABC xx") is True
  assert service._rough_match("ab", "nada") is True


def test_knowledge_paths_report_defaults_when_the_status_is_empty(client, monkeypatch):
  monkeypatch.setattr(knowledge_api, "get_db_status", lambda: {})
  got = client.get("/api/knowledge/path").json()
  assert (got["is_custom"], got["is_accessible"], got["pgvector_enabled"], got["doc_count"], got["chunk_count"], got["engine"]) == (False, True, False, 0, 0, "postgresql")
  put = client.put("/api/knowledge/path", json={"path": ""}).json()
  assert (put["ok"], put["is_custom"], put["is_accessible"], put["engine"]) == (True, False, True, "postgresql")


def test_export_endpoint_reports_success(client, monkeypatch, tmp_path):
  monkeypatch.setattr(knowledge_api, "export_to_json", lambda: (tmp_path / "m.json", tmp_path / "c.json"))
  body = client.post("/api/knowledge/admin/export-json").json()
  assert body["ok"] is True and body["manifest_path"].endswith("m.json")
