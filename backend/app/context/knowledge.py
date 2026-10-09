"""Knowledge document storage — SQLite FTS5 backend.

Public API is identical to the JSON-based version:
  - ingest_document(filename, raw, tags) -> dict
  - delete_document(document_id) -> bool
  - list_documents() -> list[dict]
  - load_chunks() -> list[dict]
  - get_chunks_for_documents(doc_ids) -> list[dict]
  - ensure_knowledge_dirs() -> None

Database location is resolved by get_knowledge_db_path() which
honours the KNOWLEDGE_BASE_PATH setting from app.json.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Generator

from app.core.settings import LOCAL_DIR, ensure_local_dirs
from app.core.storage import load_app_settings

KNOWLEDGE_DIR = LOCAL_DIR / "knowledge"
DOCUMENTS_DIR = KNOWLEDGE_DIR / "documents"

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def get_knowledge_base_dir() -> Path:
  """Resolve the knowledge base directory.

  Precedence:
    1. knowledge_base_path key in app.json (user-configured network share/custom path)
    2. LOCAL_DIR / "knowledge" (default local path)
  """
  try:
    settings = load_app_settings()
    custom = settings.get("knowledge_base_path", "")
    if isinstance(custom, str) and custom.strip():
      p = Path(custom.strip())
      p.mkdir(parents=True, exist_ok=True)
      return p
  except Exception:
    pass
  return KNOWLEDGE_DIR


def get_knowledge_db_path() -> Path:
  return get_knowledge_base_dir() / "knowledge.db"


def get_knowledge_documents_dir() -> Path:
  """Raw uploaded files directory (local or on shared path)."""
  return get_knowledge_base_dir() / "documents"


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


def _get_connection() -> sqlite3.Connection:
  db_path = get_knowledge_db_path()
  db_path.parent.mkdir(parents=True, exist_ok=True)
  conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
  conn.row_factory = sqlite3.Row

  # WAL mode — safe concurrent access on network shares / multi-process
  conn.execute("PRAGMA journal_mode=WAL")
  conn.execute("PRAGMA synchronous=NORMAL")
  conn.execute("PRAGMA foreign_keys=ON")

  _ensure_schema(conn)
  return conn


@contextmanager
def _db() -> Generator[sqlite3.Connection, None, None]:
  conn = _get_connection()
  try:
    yield conn
    conn.commit()
  except Exception:
    conn.rollback()
    raise
  finally:
    conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
  conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id          TEXT PRIMARY KEY,
            filename    TEXT NOT NULL,
            stored_as   TEXT NOT NULL,
            tags        TEXT NOT NULL DEFAULT '[]',
            chunk_count INTEGER NOT NULL DEFAULT 0,
            char_count  INTEGER NOT NULL DEFAULT 0,
            uploaded_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
            chunk_id,
            document_id,
            filename,
            tags,
            chunk_index,
            text,
            uploaded_at,
            tokenize="unicode61 remove_diacritics 1"
        );

        CREATE TABLE IF NOT EXISTS db_meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        INSERT OR IGNORE INTO db_meta VALUES ('schema_version', '1');
    """)


# ---------------------------------------------------------------------------
# Directory setup
# ---------------------------------------------------------------------------


def ensure_knowledge_dirs() -> None:
  ensure_local_dirs()
  KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
  DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
  get_knowledge_documents_dir().mkdir(parents=True, exist_ok=True)
  with _db():
    pass


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def extract_text(filename: str, raw: bytes) -> str:
  lower = filename.lower()
  if lower.endswith(".pdf"):
    return _extract_pdf(raw)
  if lower.endswith(".docx"):
    return _extract_docx(raw)
  if lower.endswith((".html", ".htm")):
    return _extract_html(raw)
  for encoding in ("utf-8", "utf-16", "latin-1"):
    try:
      return raw.decode(encoding)
    except UnicodeDecodeError:
      continue
  return raw.decode("utf-8", errors="ignore")


def _extract_pdf(raw: bytes) -> str:
  try:
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(raw))
    return "\n".join(page.extract_text() or "" for page in reader.pages)
  except Exception as exc:
    raise ValueError(f"Failed to read PDF: {exc}") from exc


def _extract_docx(raw: bytes) -> str:
  try:
    from io import BytesIO

    from docx import Document

    document = Document(BytesIO(raw))
    return "\n".join(p.text for p in document.paragraphs if p.text)
  except Exception as exc:
    raise ValueError(f"Failed to read DOCX: {exc}") from exc


def _extract_html(raw: bytes) -> str:
  for encoding in ("utf-8", "utf-16", "latin-1"):
    try:
      html = raw.decode(encoding)
      break
    except UnicodeDecodeError:
      continue
  else:
    html = raw.decode("utf-8", errors="ignore")
  html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
  html = re.sub(r"(?is)<(br|p|div|li|h[1-6]|tr)[^>]*>", "\n", html)
  text = re.sub(r"(?s)<[^>]+>", " ", html)
  return unescape(re.sub(r"\s+", " ", text)).strip()


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_text(text: str) -> list[str]:
  cleaned = re.sub(r"\s+", " ", text).strip()
  if not cleaned:
    return []
  if len(cleaned) <= CHUNK_SIZE:
    return [cleaned]
  chunks: list[str] = []
  start = 0
  while start < len(cleaned):
    end = min(start + CHUNK_SIZE, len(cleaned))
    chunks.append(cleaned[start:end])
    if end >= len(cleaned):
      break
    start = max(0, end - CHUNK_OVERLAP)
  return chunks


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------


def ingest_document(
  *,
  filename: str,
  raw: bytes,
  tags: list[str] | None = None,
) -> dict[str, Any]:
  ensure_knowledge_dirs()
  text = extract_text(filename, raw)
  if not text.strip():
    raise ValueError("No extractable text found in document.")

  doc_id = str(uuid.uuid4())
  safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename)
  stored_name = f"{doc_id}_{safe_name}"

  docs_dir = get_knowledge_documents_dir()
  (docs_dir / stored_name).write_bytes(raw)

  pieces = chunk_text(text)
  now = datetime.now(timezone.utc).isoformat()
  tags_json = json.dumps(tags or [])

  with _db() as conn:
    conn.execute(
      """INSERT INTO documents
             (id, filename, stored_as, tags, chunk_count, char_count, uploaded_at)
             VALUES (?, ?, ?, ?, ?, ?, ?)""",
      (doc_id, filename, stored_name, tags_json, len(pieces), len(text), now),
    )
    conn.executemany(
      """INSERT INTO chunks
             (chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at)
             VALUES (?, ?, ?, ?, ?, ?, ?)""",
      [
        (f"{doc_id}:{i}", doc_id, filename, tags_json, i, piece, now)
        for i, piece in enumerate(pieces)
      ],
    )

  return {
    "id": doc_id,
    "filename": filename,
    "stored_as": stored_name,
    "tags": tags or [],
    "chunk_count": len(pieces),
    "uploaded_at": now,
    "char_count": len(text),
  }


def delete_document(document_id: str) -> bool:
  ensure_knowledge_dirs()
  with _db() as conn:
    row = conn.execute(
      "SELECT stored_as FROM documents WHERE id = ?", (document_id,)
    ).fetchone()
    if not row:
      return False

    stored = get_knowledge_documents_dir() / row["stored_as"]
    if stored.exists():
      stored.unlink(missing_ok=True)

    conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

  return True


def list_documents() -> list[dict[str, Any]]:
  ensure_knowledge_dirs()
  with _db() as conn:
    rows = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
  return [
    {
      "id": row["id"],
      "filename": row["filename"],
      "stored_as": row["stored_as"],
      "tags": json.loads(row["tags"] or "[]"),
      "chunk_count": row["chunk_count"],
      "char_count": row["char_count"],
      "uploaded_at": row["uploaded_at"],
    }
    for row in rows
  ]


def load_chunks() -> list[dict[str, Any]]:
  """Return all chunks as a list of dicts.

  Used by retrieval.py for fallback scoring or full listing.
  For normal queries, search_chunks_fts() is preferred.
  """
  ensure_knowledge_dirs()
  with _db() as conn:
    rows = conn.execute(
      "SELECT chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at FROM chunks"
    ).fetchall()
  return [
    {
      "id": row["chunk_id"],
      "document_id": row["document_id"],
      "filename": row["filename"],
      "tags": json.loads(row["tags"] or "[]"),
      "index": row["chunk_index"],
      "text": row["text"],
      "uploaded_at": row["uploaded_at"],
    }
    for row in rows
  ]


def get_chunks_for_documents(
  document_ids: list[str],
  *,
  max_chunks: int = 48,
) -> list[dict[str, Any]]:
  if not document_ids:
    return []
  ensure_knowledge_dirs()
  placeholders = ",".join("?" * len(document_ids))
  with _db() as conn:
    rows = conn.execute(
      f"""SELECT chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at
          FROM chunks
          WHERE document_id IN ({placeholders})
          ORDER BY document_id, chunk_index
          LIMIT ?""",
      (*document_ids, max_chunks),
    ).fetchall()
  return [
    {
      "id": row["chunk_id"],
      "document_id": row["document_id"],
      "filename": row["filename"],
      "tags": json.loads(row["tags"] or "[]"),
      "index": row["chunk_index"],
      "text": row["text"],
      "uploaded_at": row["uploaded_at"],
    }
    for row in rows
  ]


# ---------------------------------------------------------------------------
# FTS5 search
# ---------------------------------------------------------------------------


def _sanitize_fts5_query(query: str) -> str:
  """Sanitize user query for SQLite FTS5 MATCH syntax."""
  terms = re.findall(r"[\w\u00C0-\u017F]+", query)
  if not terms:
    return ""
  # Enclose each term in double quotes to prevent syntax errors with FTS5 operators
  return " ".join(f'"{term}"' for term in terms)


def search_chunks_fts(
  query: str,
  *,
  top_k: int = 8,
  tags: list[str] | None = None,
) -> list[dict[str, Any]]:
  """FTS5 MATCH search with BM25 ranking and Spanish diacritics support.

  Returns up to top_k chunks.
  """
  ensure_knowledge_dirs()
  if not query.strip():
    all_chunks = load_chunks()
    if tags:
      tag_set = {t.lower() for t in tags}
      all_chunks = [
        c
        for c in all_chunks
        if tag_set.intersection({str(t).lower() for t in c.get("tags") or []})
      ]
    return all_chunks[:top_k]

  safe_query = _sanitize_fts5_query(query)
  if not safe_query:
    return []

  try:
    with _db() as conn:
      if tags:
        rows = conn.execute(
          """SELECT chunk_id, document_id, filename, tags,
                    chunk_index, text, uploaded_at,
                    bm25(chunks) AS score
             FROM chunks
             WHERE chunks MATCH ?
             ORDER BY score
             LIMIT ?""",
          (safe_query, top_k * 3),
        ).fetchall()
        tag_set = {t.lower() for t in tags}
        filtered = [
          row
          for row in rows
          if tag_set.intersection({t.lower() for t in json.loads(row["tags"] or "[]")})
        ]
        rows = filtered[:top_k]
      else:
        rows = conn.execute(
          """SELECT chunk_id, document_id, filename, tags,
                    chunk_index, text, uploaded_at,
                    bm25(chunks) AS score
             FROM chunks
             WHERE chunks MATCH ?
             ORDER BY score
             LIMIT ?""",
          (safe_query, top_k),
        ).fetchall()

    return [
      {
        "id": row["chunk_id"],
        "document_id": row["document_id"],
        "filename": row["filename"],
        "tags": json.loads(row["tags"] or "[]"),
        "index": row["chunk_index"],
        "text": row["text"],
        "uploaded_at": row["uploaded_at"],
        "score": abs(float(row["score"])),
      }
      for row in rows
    ]
  except sqlite3.OperationalError:
    return []
