"""Knowledge document storage — PostgreSQL RAG backend (Full-Text & Vector).

Public API:
  - ingest_document(filename, raw, tags, embedding) -> dict
  - delete_document(document_id) -> bool
  - list_documents() -> list[dict]
  - load_chunks() -> list[dict]
  - get_chunks_for_documents(doc_ids) -> list[dict]
  - search_chunks_fts(query, top_k, tags) -> list[dict]
  - search_chunks_vector(query_vector, top_k, tags) -> list[dict]
  - ensure_knowledge_dirs() -> None
  - get_db_status() -> dict

Connection parameters are managed via the DATABASE_URL environment variable.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Generator

from app.core.settings import USER_DATA_DIR, ensure_local_dirs, get_settings

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = USER_DATA_DIR / "knowledge"
KNOWLEDGE_DIR = USER_DATA_DIR / "knowledge"
DOCUMENTS_DIR = KNOWLEDGE_DIR / "documents"

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120

# ---------------------------------------------------------------------------
# Path resolution — Server-local filesystem for uploaded raw documents
# ---------------------------------------------------------------------------


def get_knowledge_base_dir() -> Path:
  return KNOWLEDGE_DIR


def get_knowledge_documents_dir() -> Path:
  return DOCUMENTS_DIR


# ---------------------------------------------------------------------------
# PostgreSQL Connection Management
# ---------------------------------------------------------------------------

_PGVECTOR_AVAILABLE: bool | None = None


def is_postgres_configured() -> bool:
  settings = get_settings()
  params = settings.get_knowledge_db_params()
  if params["host"] or params["database"]:
    return True
  url = settings.get_knowledge_db_url()
  return bool(url and url.strip())


def _get_pg_connection():
  import psycopg
  from psycopg.rows import dict_row

  settings = get_settings()
  url = settings.get_knowledge_db_url()
  if not url:
    raise ConnectionError(
      "PostgreSQL no está configurado. Defina la variable de entorno DATABASE_URL."
    )

  conn = psycopg.connect(url, row_factory=dict_row, autocommit=False)
  return conn


def _ensure_pg_schema(conn) -> None:
  global _PGVECTOR_AVAILABLE
  cur = conn.cursor()

  # 1. Try enabling pgvector and unaccent
  try:
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    conn.commit()
    _PGVECTOR_AVAILABLE = True
  except Exception as e:
    conn.rollback()
    _PGVECTOR_AVAILABLE = False
    logger.info("pgvector extension not enabled/available in PostgreSQL: %s", e)

  try:
    cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
    conn.commit()
  except Exception:
    conn.rollback()

  # 2. Register vector types in psycopg if available
  if _PGVECTOR_AVAILABLE:
    try:
      from pgvector.psycopg import register_vector
      register_vector(conn)
    except Exception as e:
      logger.warning("Could not register pgvector with psycopg: %s", e)

  # 3. Create tables
  cur.execute("""
      CREATE TABLE IF NOT EXISTS documents (
          id          VARCHAR(64) PRIMARY KEY,
          filename    TEXT NOT NULL,
          stored_as   TEXT NOT NULL,
          tags        JSONB NOT NULL DEFAULT '[]'::jsonb,
          chunk_count INTEGER NOT NULL DEFAULT 0,
          char_count  INTEGER NOT NULL DEFAULT 0,
          uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
  """)

  vector_col = "embedding vector(1536)," if _PGVECTOR_AVAILABLE else "embedding JSONB,"
  cur.execute(f"""
      CREATE TABLE IF NOT EXISTS chunks (
          chunk_id     VARCHAR(128) PRIMARY KEY,
          document_id  VARCHAR(64) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          filename     TEXT NOT NULL,
          tags         JSONB NOT NULL DEFAULT '[]'::jsonb,
          chunk_index  INTEGER NOT NULL DEFAULT 0,
          text         TEXT NOT NULL,
          tsv          tsvector GENERATED ALWAYS AS (to_tsvector('spanish', text)) STORED,
          {vector_col}
          uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
  """)

  # 4. Create Indexes
  cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin(tsv);")
  cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(document_id);")
  cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tags ON chunks USING gin(tags);")

  if _PGVECTOR_AVAILABLE:
    try:
      cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);"
      )
    except Exception:
      pass

  cur.execute("""
      CREATE TABLE IF NOT EXISTS db_meta (
          key   VARCHAR(64) PRIMARY KEY,
          value TEXT NOT NULL
      );
      INSERT INTO db_meta (key, value) VALUES ('schema_version', '2')
      ON CONFLICT (key) DO NOTHING;
  """)
  conn.commit()


@contextmanager
def _db() -> Generator[Any, None, None]:
  """PostgreSQL DB context manager."""
  conn = _get_pg_connection()
  _ensure_pg_schema(conn)
  try:
    yield conn
    conn.commit()
  except Exception:
    conn.rollback()
    raise
  finally:
    conn.close()


# ---------------------------------------------------------------------------
# Directory setup
# ---------------------------------------------------------------------------


def ensure_knowledge_dirs() -> None:
  ensure_local_dirs()
  KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
  DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
  if is_postgres_configured():
    try:
      with _db():
        pass
    except Exception as exc:
      logger.warning("Could not connect to PostgreSQL on ensure_knowledge_dirs: %s", exc)


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
# Core CRUD (PostgreSQL)
# ---------------------------------------------------------------------------


def ingest_document(
  *,
  filename: str,
  raw: bytes,
  tags: list[str] | None = None,
  embeddings: list[list[float]] | None = None,
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
  tags_clean = tags or []

  with _db() as conn:
    cur = conn.cursor()
    cur.execute(
      """INSERT INTO documents
             (id, filename, stored_as, tags, chunk_count, char_count, uploaded_at)
             VALUES (%s, %s, %s, %s, %s, %s, %s)""",
      (doc_id, filename, stored_name, json.dumps(tags_clean), len(pieces), len(text), now),
    )
    for i, piece in enumerate(pieces):
      chunk_emb = embeddings[i] if embeddings and i < len(embeddings) else None
      cur.execute(
        """INSERT INTO chunks
               (chunk_id, document_id, filename, tags, chunk_index, text, embedding, uploaded_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (
          f"{doc_id}:{i}",
          doc_id,
          filename,
          json.dumps(tags_clean),
          i,
          piece,
          chunk_emb,
          now,
        ),
      )

  return {
    "id": doc_id,
    "filename": filename,
    "stored_as": stored_name,
    "tags": tags_clean,
    "chunk_count": len(pieces),
    "uploaded_at": now,
    "char_count": len(text),
  }


def delete_document(document_id: str) -> bool:
  ensure_knowledge_dirs()
  with _db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT stored_as FROM documents WHERE id = %s", (document_id,))
    row = cur.fetchone()
    if not row:
      return False
    stored = get_knowledge_documents_dir() / row["stored_as"]
    if stored.exists():
      stored.unlink(missing_ok=True)
    cur.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM documents WHERE id = %s", (document_id,))

  return True


def list_documents() -> list[dict[str, Any]]:
  ensure_knowledge_dirs()
  with _db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents ORDER BY uploaded_at DESC")
    rows = cur.fetchall()

  result = []
  for row in rows:
    raw_tags = row["tags"]
    tags = raw_tags if isinstance(raw_tags, list) else json.loads(raw_tags or "[]")
    up_at = row["uploaded_at"]
    uploaded_at_str = up_at.isoformat() if hasattr(up_at, "isoformat") else str(up_at)
    result.append({
      "id": row["id"],
      "filename": row["filename"],
      "stored_as": row["stored_as"],
      "tags": tags,
      "chunk_count": row["chunk_count"],
      "char_count": row["char_count"],
      "uploaded_at": uploaded_at_str,
    })
  return result


def load_chunks() -> list[dict[str, Any]]:
  ensure_knowledge_dirs()
  with _db() as conn:
    cur = conn.cursor()
    cur.execute(
      "SELECT chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at FROM chunks ORDER BY document_id, chunk_index"
    )
    rows = cur.fetchall()

  result = []
  for row in rows:
    raw_tags = row["tags"]
    tags = raw_tags if isinstance(raw_tags, list) else json.loads(raw_tags or "[]")
    up_at = row["uploaded_at"]
    uploaded_at_str = up_at.isoformat() if hasattr(up_at, "isoformat") else str(up_at)
    result.append({
      "id": row["chunk_id"],
      "document_id": row["document_id"],
      "filename": row["filename"],
      "tags": tags,
      "index": row["chunk_index"],
      "text": row["text"],
      "uploaded_at": uploaded_at_str,
    })
  return result


def get_chunks_for_documents(
  document_ids: list[str],
  *,
  max_chunks: int = 48,
) -> list[dict[str, Any]]:
  if not document_ids:
    return []
  ensure_knowledge_dirs()
  with _db() as conn:
    cur = conn.cursor()
    cur.execute(
      """SELECT chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at
         FROM chunks
         WHERE document_id = ANY(%s)
         ORDER BY document_id, chunk_index
         LIMIT %s""",
      (document_ids, max_chunks),
    )
    rows = cur.fetchall()

  result = []
  for row in rows:
    raw_tags = row["tags"]
    tags = raw_tags if isinstance(raw_tags, list) else json.loads(raw_tags or "[]")
    up_at = row["uploaded_at"]
    uploaded_at_str = up_at.isoformat() if hasattr(up_at, "isoformat") else str(up_at)
    result.append({
      "id": row["chunk_id"],
      "document_id": row["document_id"],
      "filename": row["filename"],
      "tags": tags,
      "index": row["chunk_index"],
      "text": row["text"],
      "uploaded_at": uploaded_at_str,
    })
  return result


# ---------------------------------------------------------------------------
# Search: Full-Text Search (Spanish) & Vector Similarity Search
# ---------------------------------------------------------------------------


def search_chunks_fts(
  query: str,
  *,
  top_k: int = 8,
  tags: list[str] | None = None,
) -> list[dict[str, Any]]:
  """Full-Text Search with ranking and Spanish diacritics support via PostgreSQL tsvector."""
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

  with _db() as conn:
    cur = conn.cursor()
    try:
      cur.execute(
        """SELECT chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at,
                  ts_rank_cd(tsv, websearch_to_tsquery('spanish', %(query)s)) AS score
           FROM chunks
           WHERE tsv @@ websearch_to_tsquery('spanish', %(query)s)
           ORDER BY score DESC
           LIMIT %(limit)s""",
        {"query": query, "limit": top_k * 3 if tags else top_k},
      )
      rows = cur.fetchall()
      if not rows:
        cur.execute(
          """SELECT chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at,
                    ts_rank_cd(tsv, plainto_tsquery('spanish', %(query)s)) AS score
             FROM chunks
             WHERE tsv @@ plainto_tsquery('spanish', %(query)s)
             ORDER BY score DESC
             LIMIT %(limit)s""",
          {"query": query, "limit": top_k * 3 if tags else top_k},
        )
        rows = cur.fetchall()
    except Exception as err:
      logger.warning("PostgreSQL FTS error: %s", err)
      return []

    if tags:
      tag_set = {t.lower() for t in tags}
      filtered = []
      for row in rows:
        rt = row["tags"]
        row_tags = rt if isinstance(rt, list) else json.loads(rt or "[]")
        if tag_set.intersection({str(t).lower() for t in row_tags}):
          filtered.append(row)
      rows = filtered[:top_k]

    result = []
    for row in rows:
      raw_tags = row["tags"]
      tags_list = raw_tags if isinstance(raw_tags, list) else json.loads(raw_tags or "[]")
      up_at = row["uploaded_at"]
      uploaded_at_str = up_at.isoformat() if hasattr(up_at, "isoformat") else str(up_at)
      result.append({
        "id": row["chunk_id"],
        "document_id": row["document_id"],
        "filename": row["filename"],
        "tags": tags_list,
        "index": row["chunk_index"],
        "text": row["text"],
        "uploaded_at": uploaded_at_str,
        "score": float(row["score"]),
      })
    return result


def search_chunks_vector(
  query_vector: list[float],
  *,
  top_k: int = 8,
  tags: list[str] | None = None,
) -> list[dict[str, Any]]:
  """Vector similarity search (cosine distance) using PostgreSQL pgvector."""
  if not is_postgres_configured() or not query_vector:
    return []

  with _db() as conn:
    cur = conn.cursor()
    try:
      cur.execute(
        """SELECT chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at,
                  1 - (embedding <=> %(vector)s) AS score
           FROM chunks
           WHERE embedding IS NOT NULL
           ORDER BY embedding <=> %(vector)s ASC
           LIMIT %(limit)s""",
        {"vector": query_vector, "limit": top_k * 3 if tags else top_k},
      )
      rows = cur.fetchall()
    except Exception as exc:
      logger.warning("Vector search query failed: %s", exc)
      return []

    if tags:
      tag_set = {t.lower() for t in tags}
      filtered = []
      for row in rows:
        rt = row["tags"]
        row_tags = rt if isinstance(rt, list) else json.loads(rt or "[]")
        if tag_set.intersection({str(t).lower() for t in row_tags}):
          filtered.append(row)
      rows = filtered[:top_k]

    result = []
    for row in rows:
      raw_tags = row["tags"]
      tags_list = raw_tags if isinstance(raw_tags, list) else json.loads(raw_tags or "[]")
      up_at = row["uploaded_at"]
      uploaded_at_str = up_at.isoformat() if hasattr(up_at, "isoformat") else str(up_at)
      result.append({
        "id": row["chunk_id"],
        "document_id": row["document_id"],
        "filename": row["filename"],
        "tags": tags_list,
        "index": row["chunk_index"],
        "text": row["text"],
        "uploaded_at": uploaded_at_str,
        "score": float(row["score"]),
      })
    return result


# ---------------------------------------------------------------------------
# Diagnostics & Status
# ---------------------------------------------------------------------------


def get_db_status() -> dict[str, Any]:
  """Return current PostgreSQL database engine and capabilities status."""
  pg_configured = is_postgres_configured()
  params = get_settings().get_knowledge_db_params()
  status: dict[str, Any] = {
    "engine": "postgresql",
    "is_postgres": True,
    "pgvector_enabled": bool(_PGVECTOR_AVAILABLE),
    "spanish_fts_enabled": True,
    "documents_dir": str(get_knowledge_documents_dir()),
    "connected": False,
    "host": params["host"] or "remote",
    "database": params["database"] or "",
    "doc_count": 0,
    "chunk_count": 0,
  }

  if not pg_configured:
    status["error"] = "PostgreSQL no está configurado en las variables de entorno."
    return status

  try:
    with _db() as conn:
      cur = conn.cursor()
      cur.execute("SELECT COUNT(*) AS c FROM documents")
      status["doc_count"] = cur.fetchone()["c"]
      cur.execute("SELECT COUNT(*) AS c FROM chunks")
      status["chunk_count"] = cur.fetchone()["c"]
      status["host"] = params["host"] or (conn.info.host if hasattr(conn.info, "host") else "remote")
      status["database"] = params["database"] or (conn.info.dbname if hasattr(conn.info, "dbname") else "")
      status["connected"] = True
  except Exception as exc:
    logger.exception("Error al consultar el estado de la base de datos de conocimiento: %s", exc)
    status["connected"] = False
    status["error"] = "Error al conectar o consultar la base de datos de conocimiento."

  return status
