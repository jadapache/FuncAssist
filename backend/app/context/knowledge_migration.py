"""One-time migration from chunks.json + manifest.json → knowledge.db (SQLite FTS5).

Safe to call multiple times — checks a sentinel key in db_meta before proceeding.
Also provides export (SQLite → JSON) for backup and recovery.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def migrate_json_to_sqlite_if_needed() -> None:
  """Runs the migration once if legacy JSON files exist and the sentinel is absent.

  Leaves the original JSON files in place as backup (with .migrated suffix).
  """
  from app.context.knowledge import (
    KNOWLEDGE_DIR,
    _get_connection,
  )

  chunks_path = KNOWLEDGE_DIR / "chunks.json"
  manifest_path = KNOWLEDGE_DIR / "manifest.json"

  # Nothing to migrate
  if not chunks_path.exists() and not manifest_path.exists():
    return

  # Check sentinel
  try:
    conn = _get_connection()
    row = conn.execute(
      "SELECT value FROM db_meta WHERE key = 'json_migration_done'"
    ).fetchone()
    conn.close()
    if row:
      return  # Already migrated
  except Exception:
    pass  # db doesn't exist yet — proceed with migration

  logger.info("Starting knowledge base migration: JSON → SQLite FTS5")

  # Load legacy data
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
    # Mark as done even if files were empty
    _mark_migration_done()
    return

  # Group chunks by document_id
  chunks_by_doc: dict[str, list[dict[str, Any]]] = {}
  for chunk in chunks:
    doc_id = chunk.get("document_id", "")
    chunks_by_doc.setdefault(doc_id, []).append(chunk)

  # Insert into SQLite
  conn = _get_connection()
  try:
    for doc in manifest:
      doc_id = doc.get("id", "")
      doc_chunks = chunks_by_doc.get(doc_id, [])
      tags_json = json.dumps(doc.get("tags") or [])

      conn.execute(
        """INSERT OR IGNORE INTO documents
               (id, filename, stored_as, tags, chunk_count, char_count, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
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
      conn.executemany(
        """INSERT INTO chunks
               (chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
          (
            chunk.get("id", f"{doc_id}:{chunk.get('index', i)}"),
            doc_id,
            chunk.get("filename", doc.get("filename", "")),
            tags_json,
            chunk.get("index", i),
            chunk.get("text", ""),
            chunk.get("uploaded_at", doc.get("uploaded_at", "")),
          )
          for i, chunk in enumerate(doc_chunks)
        ],
      )

    conn.execute(
      "INSERT OR REPLACE INTO db_meta VALUES ('json_migration_done', 'true')"
    )
    conn.commit()
    logger.info(
      "Migration complete: %d documents, %d chunks", len(manifest), len(chunks)
    )
  except Exception as e:
    conn.rollback()
    logger.error("Migration failed: %s", e)
    raise
  finally:
    conn.close()

  # Rename originals to .migrated (keep as backup, don't delete)
  for path in (chunks_path, manifest_path):
    try:
      if path.exists():
        path.rename(path.with_suffix(".json.migrated"))
    except Exception as e:
      logger.warning("Could not rename %s to .migrated: %s", path, e)


def _mark_migration_done() -> None:
  from app.context.knowledge import _get_connection

  conn = _get_connection()
  try:
    conn.execute(
      "INSERT OR REPLACE INTO db_meta VALUES ('json_migration_done', 'true')"
    )
    conn.commit()
  finally:
    conn.close()


# ---------------------------------------------------------------------------
# Export / Recovery: SQLite → JSON
# ---------------------------------------------------------------------------


def export_to_json(output_dir: Path | None = None) -> tuple[Path, Path]:
  """Export knowledge.db back to chunks.json + manifest.json.

  Use for backup, debugging, or rollback to JSON-based system.
  Returns (manifest_path, chunks_path) of written files.
  """
  from app.context.knowledge import _get_connection, get_knowledge_base_dir

  base = output_dir or get_knowledge_base_dir()
  base.mkdir(parents=True, exist_ok=True)

  manifest_out = base / "manifest.export.json"
  chunks_out = base / "chunks.export.json"

  conn = _get_connection()
  try:
    docs = conn.execute("SELECT * FROM documents ORDER BY uploaded_at").fetchall()
    chunks = conn.execute(
      "SELECT * FROM chunks ORDER BY document_id, chunk_index"
    ).fetchall()

    manifest_list = [
      {
        "id": row["id"],
        "filename": row["filename"],
        "stored_as": row["stored_as"],
        "tags": json.loads(row["tags"] or "[]"),
        "chunk_count": row["chunk_count"],
        "char_count": row["char_count"],
        "uploaded_at": row["uploaded_at"],
      }
      for row in docs
    ]

    chunks_list = [
      {
        "id": row["chunk_id"],
        "document_id": row["document_id"],
        "filename": row["filename"],
        "tags": json.loads(row["tags"] or "[]"),
        "index": row["chunk_index"],
        "text": row["text"],
        "uploaded_at": row["uploaded_at"],
      }
      for row in chunks
    ]
  finally:
    conn.close()

  manifest_out.write_text(
    json.dumps(manifest_list, indent=2, ensure_ascii=False), encoding="utf-8"
  )
  chunks_out.write_text(
    json.dumps(chunks_list, indent=2, ensure_ascii=False), encoding="utf-8"
  )

  logger.info(
    "Exported %d documents and %d chunks to %s", len(manifest_list), len(chunks_list), base
  )
  return manifest_out, chunks_out


def rebuild_fts_index() -> int:
  """Rebuilds the FTS5 index in-place from existing document data.

  Use when the FTS index becomes corrupt or after a failed partial write.
  Returns the number of chunks re-indexed.
  """
  from app.context.knowledge import _get_connection

  conn = _get_connection()
  try:
    conn.execute("INSERT INTO chunks(chunks) VALUES('rebuild')")
    row = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
    count = row[0] if row else 0
    conn.commit()
    logger.info("FTS5 index rebuilt: %d chunks", count)
    return count
  except Exception as e:
    conn.rollback()
    logger.error("FTS5 rebuild failed: %s", e)
    raise
  finally:
    conn.close()


def verify_integrity() -> dict[str, Any]:
  """Runs SQLite integrity check + FTS5 integrity check.

  Returns a dict with 'ok' bool, 'details' list, and 'db_path'.
  """
  from app.context.knowledge import _get_connection, get_knowledge_db_path

  result: dict[str, Any] = {"ok": True, "details": [], "db_path": str(get_knowledge_db_path())}
  conn = _get_connection()
  try:
    # SQLite page-level integrity
    rows = conn.execute("PRAGMA integrity_check").fetchall()
    for row in rows:
      msg = row[0]
      if msg != "ok":
        result["ok"] = False
        result["details"].append(f"integrity_check: {msg}")

    # FTS5 index integrity
    try:
      conn.execute(
        "INSERT INTO chunks(chunks, rank) VALUES('integrity-check', NULL)"
      ).fetchall()
    except sqlite3.OperationalError as e:
      err_str = str(e)
      if "integrity-check" in err_str.lower() or "ok" in err_str.lower():
        pass
      else:
        result["ok"] = False
        result["details"].append(f"fts5_integrity: {e}")

    # Check document/chunk count consistency
    docs = conn.execute("SELECT id, chunk_count FROM documents").fetchall()
    for doc in docs:
      actual = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
        (doc["id"],),
      ).fetchone()[0]
      if actual != doc["chunk_count"]:
        result["ok"] = False
        result["details"].append(
          f"chunk_count mismatch for doc {doc['id']}: expected {doc['chunk_count']}, found {actual}"
        )
  finally:
    conn.close()

  if result["ok"]:
    result["details"].append("All checks passed.")
  return result
