"""Unit and integration tests for SQLite FTS5 Knowledge Base, migration, and recovery."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.context.knowledge import (
  delete_document,
  ensure_knowledge_dirs,
  get_chunks_for_documents,
  get_knowledge_base_dir,
  get_knowledge_db_path,
  ingest_document,
  list_documents,
  load_chunks,
  search_chunks_fts,
)
from app.context.knowledge_migration import (
  export_to_json,
  migrate_json_to_sqlite_if_needed,
  rebuild_fts_index,
  verify_integrity,
)
from app.context.retrieval import search_knowledge
from app.core.storage import save_app_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def isolated_kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
  """Isolate knowledge base storage to a temporary directory."""
  kb_dir = tmp_path / "knowledge"
  kb_dir.mkdir(parents=True, exist_ok=True)
  monkeypatch.setattr("app.context.knowledge.KNOWLEDGE_DIR", kb_dir)
  monkeypatch.setattr("app.context.knowledge.DOCUMENTS_DIR", kb_dir / "documents")

  # Reset app settings knowledge_base_path to empty (default)
  save_app_settings({"knowledge_base_path": ""})
  ensure_knowledge_dirs()
  yield kb_dir


def test_ingest_and_list_documents(isolated_kb: Path):
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


def test_fts5_search_and_spanish_diacritics(isolated_kb: Path):
  # Ingest document with Spanish accents
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

  # Query without accents ("reunion") should match "reunión" via unicode61 remove_diacritics
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


def test_search_knowledge_with_tags_and_fts5(isolated_kb: Path):
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

  # Filter by tag "transferencias"
  results = search_knowledge("pasarela", tags=["transferencias"])
  assert len(results) == 1
  assert results[0].source_label == "doc2.txt"


def test_delete_document(isolated_kb: Path):
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
  assert search_chunks_fts("temporal") == []

  # Second deletion returns False
  assert delete_document(doc_id) is False


def test_migration_json_to_sqlite(isolated_kb: Path, monkeypatch: pytest.MonkeyPatch):
  # Setup legacy chunks.json and manifest.json
  manifest_path = isolated_kb / "manifest.json"
  chunks_path = isolated_kb / "chunks.json"

  legacy_doc_id = "legacy-doc-123"
  manifest_data = [
    {
      "id": legacy_doc_id,
      "filename": "legacy_guide.md",
      "stored_as": f"{legacy_doc_id}_legacy_guide.md",
      "tags": ["legacy", "v1"],
      "chunk_count": 1,
      "char_count": 50,
      "uploaded_at": "2026-01-01T00:00:00Z",
    }
  ]
  chunks_data = [
    {
      "id": f"{legacy_doc_id}:0",
      "document_id": legacy_doc_id,
      "filename": "legacy_guide.md",
      "tags": ["legacy", "v1"],
      "index": 0,
      "text": "Informacion historica sobre arquitectura modular.",
      "uploaded_at": "2026-01-01T00:00:00Z",
    }
  ]

  manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")
  chunks_path.write_text(json.dumps(chunks_data), encoding="utf-8")

  # Remove existing SQLite knowledge.db if present to test clean migration
  db_path = get_knowledge_db_path()
  if db_path.exists():
    db_path.unlink()

  migrate_json_to_sqlite_if_needed()

  # Check SQLite now contains legacy data
  docs = list_documents()
  assert len(docs) == 1
  assert docs[0]["id"] == legacy_doc_id
  assert docs[0]["filename"] == "legacy_guide.md"

  fts_results = search_chunks_fts("arquitectura modular")
  assert len(fts_results) == 1
  assert fts_results[0]["document_id"] == legacy_doc_id

  # Check original files renamed to .migrated
  assert not manifest_path.exists()
  assert not chunks_path.exists()
  assert (isolated_kb / "manifest.json.migrated").exists()
  assert (isolated_kb / "chunks.json.migrated").exists()

  # Idempotency: Running again should not fail or duplicate
  migrate_json_to_sqlite_if_needed()
  assert len(list_documents()) == 1


def test_integrity_and_rebuild_and_export(isolated_kb: Path):
  ingest_document(
    filename="manual_calidad.txt",
    raw=b"Manual de politicas de aseguramiento de calidad QA.",
    tags=["calidad"],
  )

  # Check integrity
  integrity = verify_integrity()
  assert integrity["ok"] is True
  assert "All checks passed." in integrity["details"]

  # Rebuild FTS index
  count = rebuild_fts_index()
  assert count >= 1

  # Export to JSON
  manifest_out, chunks_out = export_to_json()
  assert manifest_out.exists()
  assert chunks_out.exists()

  manifest_content = json.loads(manifest_out.read_text(encoding="utf-8"))
  chunks_content = json.loads(chunks_out.read_text(encoding="utf-8"))
  assert len(manifest_content) == 1
  assert len(chunks_content) >= 1
  assert manifest_content[0]["filename"] == "manual_calidad.txt"


def test_api_knowledge_endpoints(isolated_kb: Path):
  app = create_app()
  client = TestClient(app)

  # 1. Upload a document
  upload_res = client.post(
    "/api/knowledge/documents",
    files={"file": ("test_doc.txt", b"Texto de prueba para busqueda en RAG", "text/plain")},
    data={"tags": "pruebas,rag"},
  )
  assert upload_res.status_code == 200
  doc_data = upload_res.json()["document"]
  doc_id = doc_data["id"]

  # 2. List documents
  list_res = client.get("/api/knowledge/documents")
  assert list_res.status_code == 200
  assert len(list_res.json()["documents"]) == 1

  # 3. Retrieve
  retrieve_res = client.post(
    "/api/knowledge/retrieve",
    json={"query": "busqueda RAG", "sources": ["knowledge"], "top_k": 5},
  )
  assert retrieve_res.status_code == 200
  assert len(retrieve_res.json()["chunks"]) >= 1

  # 4. Check path info
  path_res = client.get("/api/knowledge/path")
  assert path_res.status_code == 200
  assert "resolved_path" in path_res.json()

  # 5. Integrity check endpoint
  integrity_res = client.get("/api/knowledge/admin/integrity")
  assert integrity_res.status_code == 200
  assert integrity_res.json()["ok"] is True

  # 6. Rebuild index endpoint
  rebuild_res = client.post("/api/knowledge/admin/rebuild-index")
  assert rebuild_res.status_code == 200
  assert rebuild_res.json()["ok"] is True

  # 7. Export JSON backup endpoint
  export_res = client.post("/api/knowledge/admin/export-json")
  assert export_res.status_code == 200
  assert export_res.json()["ok"] is True

  # 8. Delete document
  del_res = client.delete(f"/api/knowledge/documents/{doc_id}")
  assert del_res.status_code == 200
  assert del_res.json()["ok"] is True
