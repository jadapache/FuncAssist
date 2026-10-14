"""Migration, export, and integrity verification for Knowledge Base (PostgreSQL).

Includes:
  - Legacy JSON → PostgreSQL migration.
  - JSON export for backup and recovery.
  - Full-text & vector index rebuilding in PostgreSQL.
  - Integrity and health verification in PostgreSQL.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.context.knowledge import (
  KNOWLEDGE_DIR,
  _db,
  get_db_status,
  get_knowledge_base_dir,
  is_postgres_configured,
  list_documents,
  load_chunks,
)

logger = logging.getLogger(__name__)


def migrate_knowledge_if_needed() -> None:
  """Main entry point for knowledge base migrations on startup."""
  if is_postgres_configured():
    migrate_json_to_postgres_if_needed()


def migrate_json_to_postgres_if_needed() -> None:
  """Migrates legacy JSON files to PostgreSQL if present and sentinel absent."""
  chunks_path = KNOWLEDGE_DIR / "chunks.json"
  manifest_path = KNOWLEDGE_DIR / "manifest.json"

  if not chunks_path.exists() and not manifest_path.exists():
    return

  try:
    with _db() as conn:
      cur = conn.cursor()
      cur.execute("SELECT value FROM db_meta WHERE key = 'json_migration_done'")
      row = cur.fetchone()
      if row:
        return
  except Exception:
    pass

  logger.info("Starting knowledge base migration: JSON → PostgreSQL")

  manifest: list[dict[str, Any]] = []
  chunks: list[dict[str, Any]] = []

  if manifest_path.exists():
    try:
      manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
      logger.error("Could not read manifest.json: %s", e)

  if chunks_path.exists():
    try:
      chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    except Exception as e:
      logger.error("Could not read chunks.json: %s", e)

  if not manifest and not chunks:
    _mark_migration_done("json_migration_done")
    return

  chunks_by_doc: dict[str, list[dict[str, Any]]] = {}
  for chunk in chunks:
    doc_id = chunk.get("document_id", "")
    chunks_by_doc.setdefault(doc_id, []).append(chunk)

  try:
    with _db() as conn:
      cur = conn.cursor()
      for doc in manifest:
        doc_id = doc.get("id", "")
        doc_chunks = chunks_by_doc.get(doc_id, [])
        tags_json = json.dumps(doc.get("tags") or [])

        cur.execute(
          """INSERT INTO documents
                 (id, filename, stored_as, tags, chunk_count, char_count, uploaded_at)
                 VALUES (%s, %s, %s, %s, %s, %s, %s)
                 ON CONFLICT (id) DO NOTHING""",
          (
            doc_id,
            doc.get("filename", ""),
            doc.get("stored_as", ""),
            tags_json,
            doc.get("chunk_count", len(doc_chunks)),
            doc.get("char_count", 0),
            doc.get("uploaded_at", ""),
          ),
        )
        for i, chunk in enumerate(doc_chunks):
          cur.execute(
            """INSERT INTO chunks
                   (chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (chunk_id) DO NOTHING""",
            (
              chunk.get("id", f"{doc_id}:{chunk.get('index', i)}"),
              doc_id,
              chunk.get("filename", doc.get("filename", "")),
              tags_json,
              chunk.get("index", i),
              chunk.get("text", ""),
              chunk.get("uploaded_at", doc.get("uploaded_at", "")),
            ),
          )

      _mark_migration_done("json_migration_done")
      logger.info("JSON Migration complete: %d documents, %d chunks", len(manifest), len(chunks))
  except Exception as e:
    logger.error("JSON Migration failed: %s", e)
    raise

  for path in (chunks_path, manifest_path):
    try:
      if path.exists():
        path.rename(path.with_suffix(".json.migrated"))
    except Exception as e:
      logger.warning("Could not rename %s to .migrated: %s", path, e)


def _mark_migration_done(key: str) -> None:
  try:
    with _db() as conn:
      cur = conn.cursor()
      cur.execute(
        "INSERT INTO db_meta (key, value) VALUES (%s, 'true') ON CONFLICT (key) DO UPDATE SET value = 'true'",
        (key,),
      )
  except Exception as e:
    logger.warning("Could not set sentinel %s: %s", key, e)


# ---------------------------------------------------------------------------
# Export / Recovery: PostgreSQL → JSON
# ---------------------------------------------------------------------------


def export_to_json(output_dir: Path | None = None) -> tuple[Path, Path]:
  """Export all documents and chunks to manifest.export.json + chunks.export.json."""
  base = output_dir or get_knowledge_base_dir()
  base.mkdir(parents=True, exist_ok=True)

  manifest_out = base / "manifest.export.json"
  chunks_out = base / "chunks.export.json"

  docs = list_documents()
  chunks = load_chunks()

  manifest_out.write_text(json.dumps(docs, indent=2, ensure_ascii=False), encoding="utf-8")
  chunks_out.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8")

  logger.info("Exported %d documents and %d chunks to %s", len(docs), len(chunks), base)
  return manifest_out, chunks_out


def rebuild_fts_index() -> int:
  """Rebuild the full-text search and vector indexes in PostgreSQL."""
  with _db() as conn:
    cur = conn.cursor()
    cur.execute("REINDEX TABLE chunks;")
    cur.execute("SELECT COUNT(*) AS c FROM chunks")
    count = cur.fetchone()["c"]
    logger.info("PostgreSQL chunks table and indexes reindexed: %d chunks", count)
    return count


def verify_integrity() -> dict[str, Any]:
  """Runs PostgreSQL database integrity checks, validates counts and schema health."""
  status = get_db_status()
  result: dict[str, Any] = {
    "ok": status.get("connected", False),
    "details": [],
    "engine": "postgresql",
    "pgvector_enabled": status.get("pgvector_enabled"),
  }

  if not status.get("connected"):
    result["ok"] = False
    result["details"].append(f"Error de conexión a PostgreSQL: {status.get('error', 'No se pudo conectar')}")
    return result

  try:
    with _db() as conn:
      cur = conn.cursor()
      cur.execute("SELECT 1")
      result["details"].append("Conexión con PostgreSQL verificada con éxito.")

      cur.execute("SELECT id, chunk_count FROM documents")
      docs = cur.fetchall()
      for doc in docs:
        cur.execute("SELECT COUNT(*) AS c FROM chunks WHERE document_id = %s", (doc["id"],))
        actual = cur.fetchone()["c"]
        if actual != doc["chunk_count"]:
          result["ok"] = False
          result["details"].append(
            f"Discrepancia en doc {doc['id']}: esperado {doc['chunk_count']}, encontrado {actual}"
          )
  except Exception as exc:
    result["ok"] = False
    result["details"].append(f"Error en prueba de integridad: {exc}")

  if result["ok"]:
    result["details"].append("Todas las verificaciones de PostgreSQL pasaron correctamente.")

  return result
