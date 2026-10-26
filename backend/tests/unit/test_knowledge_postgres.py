"""Unit and integration tests for PostgreSQL RAG Knowledge Base (pure PostgreSQL, no SQLite)."""

import json
import re
import unicodedata
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.context.knowledge import (
  delete_document,
  ensure_knowledge_dirs,
  get_chunks_for_documents,
  get_db_status,
  get_knowledge_base_dir,
  get_knowledge_documents_dir,
  ingest_document,
  is_postgres_configured,
  list_documents,
  load_chunks,
  search_chunks_fts,
  search_chunks_vector,
)
from app.context.knowledge_migration import (
  export_to_json,
  migrate_knowledge_if_needed,
  rebuild_fts_index,
  verify_integrity,
)
from app.context.retrieval import search_knowledge
from app.core.settings import get_settings
from app.main import create_app


def _strip_accents(s: str) -> str:
  return "".join(
    c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
  ).lower()


class FakePGCursor:
  def __init__(self, storage):
    self.storage = storage
    self._last_result = []

  def execute(self, query: str, params=None):
    q = query.strip()
    p = params or ()

    # Extension / Table / Index setup
    if (
      q.startswith("CREATE EXTENSION")
      or q.startswith("CREATE TABLE")
      or q.startswith("CREATE INDEX")
      or q.startswith("REINDEX")
    ):
      self._last_result = []
      return

    if "INSERT INTO db_meta" in q:
      key = p[0] if len(p) > 0 else "k"
      val = p[1] if len(p) > 1 else "v"
      self.storage["db_meta"][key] = val
      self._last_result = []
      return

    if "SELECT value FROM db_meta" in q:
      key = p[0] if p else "json_migration_done"
      val = self.storage["db_meta"].get(key)
      self._last_result = [{"value": val}] if val else []
      return

    if "INSERT INTO documents" in q:
      doc_id, fn, stored_as, tags, chunk_count, char_count, up_at = p
      self.storage["documents"][doc_id] = {
        "id": doc_id,
        "filename": fn,
        "stored_as": stored_as,
        "tags": tags,
        "chunk_count": chunk_count,
        "char_count": char_count,
        "uploaded_at": up_at,
      }
      self._last_result = []
      return

    if "INSERT INTO chunks" in q:
      chunk_id, doc_id, fn, tags, idx, text, emb, up_at = p
      self.storage["chunks"].append({
        "chunk_id": chunk_id,
        "document_id": doc_id,
        "filename": fn,
        "tags": tags,
        "chunk_index": idx,
        "text": text,
        "embedding": emb,
        "uploaded_at": up_at,
      })
      self._last_result = []
      return

    if "SELECT COUNT(*) AS c FROM documents" in q:
      self._last_result = [{"c": len(self.storage["documents"])}]
      return

    if "SELECT COUNT(*) AS c FROM chunks" in q:
      self._last_result = [{"c": len(self.storage["chunks"])}]
      return

    if "SELECT 1" in q:
      self._last_result = [{"?column?": 1}]
      return

    if "SELECT * FROM documents" in q:
      docs = list(self.storage["documents"].values())
      self._last_result = sorted(docs, key=lambda d: str(d["uploaded_at"]), reverse=True)
      return

    if "SELECT stored_as FROM documents WHERE id =" in q:
      doc_id = p[0]
      doc = self.storage["documents"].get(doc_id)
      self._last_result = [{"stored_as": doc["stored_as"]}] if doc else []
      return

    if "DELETE FROM chunks WHERE document_id =" in q:
      doc_id = p[0]
      self.storage["chunks"] = [
        c for c in self.storage["chunks"] if c["document_id"] != doc_id
      ]
      self._last_result = []
      return

    if "DELETE FROM documents WHERE id =" in q:
      doc_id = p[0]
      if doc_id in self.storage["documents"]:
        del self.storage["documents"][doc_id]
      self._last_result = []
      return

    if "SELECT chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at" in q:
      if "tsv @@" in q:
        # Full text search with Spanish diacritics normalization
        search_term = p.get("query", "") if isinstance(p, dict) else (p[0] if p else "")
        term_clean = _strip_accents(search_term)
        matched = []
        for c in self.storage["chunks"]:
          c_clean = _strip_accents(c["text"])
          words = re.findall(r"\w+", term_clean)
          if any(w in c_clean for w in words):
            matched.append({**c, "score": 0.85})
        self._last_result = matched
        return

      if "embedding IS NOT NULL" in q:
        # Vector similarity search
        matched = []
        for c in self.storage["chunks"]:
          if c.get("embedding"):
            matched.append({**c, "score": 0.95})
        self._last_result = matched
        return

      if "document_id = ANY" in q:
        doc_ids = set(p[0])
        matched = [c for c in self.storage["chunks"] if c["document_id"] in doc_ids]
        self._last_result = matched
        return

      # General load chunks
      self._last_result = list(self.storage["chunks"])
      return

    if "SELECT id, chunk_count FROM documents" in q:
      self._last_result = [
        {"id": d["id"], "chunk_count": d["chunk_count"]}
        for d in self.storage["documents"].values()
      ]
      return

    self._last_result = []

  def fetchone(self):
    return self._last_result[0] if self._last_result else None

  def fetchall(self):
    return list(self._last_result)


class FakePGConnection:
  def __init__(self, storage):
    self.storage = storage
    self.info = type("Info", (), {"host": "pg.internal.test", "dbname": "test_knowledge_db"})()

  def cursor(self):
    return FakePGCursor(self.storage)

  def commit(self):
    pass

  def rollback(self):
    pass

  def close(self):
    pass


@pytest.fixture(autouse=True)
def mock_postgres_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
  """Configure PostgreSQL environment and fake connection with in-memory storage."""
  kb_dir = tmp_path / "knowledge"
  kb_dir.mkdir(parents=True, exist_ok=True)
  monkeypatch.setattr("app.context.knowledge.KNOWLEDGE_DIR", kb_dir)
  monkeypatch.setattr("app.context.knowledge.DOCUMENTS_DIR", kb_dir / "documents")

  monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:secret@pg.internal.test:5432/test_knowledge_db")

  shared_storage = {"documents": {}, "chunks": [], "db_meta": {}}

  def _fake_conn():
    return FakePGConnection(shared_storage)

  monkeypatch.setattr("app.context.knowledge._get_pg_connection", _fake_conn)
  monkeypatch.setattr("app.context.knowledge._PGVECTOR_AVAILABLE", True)
  get_settings.cache_clear()

  ensure_knowledge_dirs()
  yield shared_storage
  get_settings.cache_clear()


def test_ingest_and_list_documents(mock_postgres_db):
  doc = ingest_document(
    filename="spec_requisitos.md",
    raw=b"# Requisitos del Sistema\nEl usuario debe poder iniciar sesion de forma segura con 2FA.",
    tags=["seguridad", "auth"],
  )

  assert doc["id"]
  assert doc["filename"] == "spec_requisitos.md"
  assert doc["chunk_count"] >= 1
  assert "seguridad" in doc["tags"]

  docs = list_documents()
  assert len(docs) == 1
  assert docs[0]["id"] == doc["id"]
  assert docs[0]["filename"] == "spec_requisitos.md"

  chunks = load_chunks()
  assert len(chunks) >= 1
  assert chunks[0]["document_id"] == doc["id"]
  assert "2FA" in chunks[0]["text"]


def test_fts_search_and_spanish_diacritics(mock_postgres_db):
  ingest_document(
    filename="acta_reunion.txt",
    raw="En la reunión de planeación se discutió la optimización del módulo de autenticación.".encode(
      "utf-8"
    ),
    tags=["reunion", "qa"],
  )

  ingest_document(
    filename="guia_pruebas.txt",
    raw="Guía de pruebas automatizadas para regresión en pipelines CI/CD.".encode(
      "utf-8"
    ),
    tags=["testing"],
  )

  # Query without accents ("reunion") should match "reunión"
  results_no_accent = search_chunks_fts("reunion")
  assert len(results_no_accent) >= 1
  assert results_no_accent[0]["filename"] == "acta_reunion.txt"

  # Query with accents
  results_with_accent = search_chunks_fts("reunión")
  assert len(results_with_accent) >= 1
  assert results_with_accent[0]["filename"] == "acta_reunion.txt"

  # Query for second doc
  results_ci = search_chunks_fts("automatizadas")
  assert len(results_ci) >= 1
  assert results_ci[0]["filename"] == "guia_pruebas.txt"


def test_search_knowledge_with_tags_and_ranking(mock_postgres_db):
  ingest_document(
    filename="doc1.txt",
    raw=b"Contenido sobre pasarela de pagos con tarjeta de credito.",
    tags=["pagos"],
  )
  ingest_document(
    filename="doc2.txt",
    raw=b"Contenido sobre pasarela de pagos con transferencias bancarias.",
    tags=["transferencias"],
  )

  results = search_knowledge("pasarela", tags=["transferencias"])
  assert len(results) == 1
  assert results[0].source_label == "doc2.txt"


def test_vector_similarity_search(mock_postgres_db):
  ingest_document(
    filename="vector_manual.txt",
    raw=b"Analisis semantico con representacion vectorial de documentos tecnicos.",
    tags=["ia", "vectorial"],
    embeddings=[[0.05] * 1536],
  )

  hits = search_chunks_vector([0.05] * 1536, top_k=5)
  assert len(hits) >= 1
  assert hits[0]["filename"] == "vector_manual.txt"
  assert hits[0]["score"] == 0.95


def test_delete_document(mock_postgres_db):
  doc = ingest_document(
    filename="borrador.txt",
    raw=b"Documento temporal para ser eliminado.",
    tags=["temp"],
  )
  doc_id = doc["id"]
  assert len(list_documents()) == 1

  deleted = delete_document(doc_id)
  assert deleted is True
  assert len(list_documents()) == 0
  assert len(load_chunks()) == 0


def test_db_status_diagnostics(mock_postgres_db):
  status = get_db_status()
  assert status["engine"] == "postgresql"
  assert status["is_postgres"] is True
  assert status["connected"] is True
  assert status["spanish_fts_enabled"] is True
  assert status["host"] == "pg.internal.test"


def test_separated_postgres_environment_variables(monkeypatch: pytest.MonkeyPatch):
  get_settings.cache_clear()
  monkeypatch.setenv("DATABASE_URL", "postgresql://admin_user:secret_pass123@db.cluster.internal:5433/qa_vector_db")

  settings = get_settings()
  params = settings.get_knowledge_db_params()
  assert params["host"] == "db.cluster.internal"
  assert params["port"] == 5433
  assert params["user"] == "admin_user"
  assert params["password"] == "secret_pass123"
  assert params["database"] == "qa_vector_db"

  url = settings.get_knowledge_db_url()
  assert url is not None
  assert "admin_user" in url
  assert "db.cluster.internal:5433" in url
  assert "qa_vector_db" in url
  assert is_postgres_configured() is True
  get_settings.cache_clear()


def test_integrity_and_rebuild_and_export(mock_postgres_db, tmp_path: Path):
  ingest_document(
    filename="manual_calidad.txt",
    raw=b"Manual de politicas de aseguramiento de calidad QA.",
    tags=["calidad"],
  )

  integrity = verify_integrity()
  assert integrity["ok"] is True
  assert integrity["engine"] == "postgresql"

  reindexed = rebuild_fts_index()
  assert reindexed >= 1

  export_dir = tmp_path / "export"
  manifest_out, chunks_out = export_to_json(export_dir)
  assert manifest_out.exists()
  assert chunks_out.exists()

  manifest_content = json.loads(manifest_out.read_text(encoding="utf-8"))
  chunks_content = json.loads(chunks_out.read_text(encoding="utf-8"))
  assert len(manifest_content) == 1
  assert len(chunks_content) >= 1
  assert manifest_content[0]["filename"] == "manual_calidad.txt"


def test_api_knowledge_endpoints(mock_postgres_db):
  app = create_app()
  client = TestClient(app)

  # 1. Upload
  upload_res = client.post(
    "/api/knowledge/documents",
    files={"file": ("test_doc.txt", b"Texto de prueba para busqueda en RAG", "text/plain")},
    data={"tags": "pruebas,rag"},
  )
  assert upload_res.status_code == 200
  doc_id = upload_res.json()["document"]["id"]

  # 2. List
  list_res = client.get("/api/knowledge/documents")
  assert list_res.status_code == 200
  assert len(list_res.json()["documents"]) == 1

  # 3. Retrieve
  retrieve_res = client.post(
    "/api/knowledge/retrieve",
    json={"query": "busqueda RAG", "sources": ["knowledge"], "top_k": 5},
  )
  assert retrieve_res.status_code == 200

  # 4. DB Status
  status_res = client.get("/api/knowledge/db-status")
  assert status_res.status_code == 200
  assert status_res.json()["engine"] == "postgresql"

  # 5. Admin Integrity & Rebuild & Export
  integrity_res = client.get("/api/knowledge/admin/integrity")
  assert integrity_res.status_code == 200
  assert integrity_res.json()["ok"] is True

  rebuild_res = client.post("/api/knowledge/admin/rebuild-index")
  assert rebuild_res.status_code == 200
  assert rebuild_res.json()["ok"] is True

  export_res = client.post("/api/knowledge/admin/export-json")
  assert export_res.status_code == 200
  assert export_res.json()["ok"] is True

  # 6. Delete
  del_res = client.delete(f"/api/knowledge/documents/{doc_id}")
  assert del_res.status_code == 200
  assert del_res.json()["ok"] is True


def test_db_status_exception_does_not_leak_stack_trace():
  from unittest.mock import patch
  with patch("app.context.knowledge._db", side_effect=RuntimeError("psycopg.OperationalError: password authentication failed for user 'sensitive_admin'")):
    status = get_db_status()
    assert status["connected"] is False
    assert "sensitive_admin" not in status.get("error", "")
    assert status["error"] == "Error al conectar o consultar la base de datos de conocimiento."


def test_api_db_status_exception_sanitized(mock_postgres_db):
  from unittest.mock import patch
  app = create_app()
  client = TestClient(app)
  with patch("app.api.knowledge.get_db_status", side_effect=RuntimeError("psycopg connection failed with credentials")):
    res = client.get("/api/knowledge/db-status")
    assert res.status_code == 500
    assert "credentials" not in res.text
    assert res.json()["detail"] == "Error interno al obtener el estado de la base de datos de conocimiento."
