"""Knowledge document storage — PostgreSQL RAG backend (Full-Text & Vector).

Public API:
  - ingest_document(filename, raw, tags, embedding) -> dict
  - delete_document(document_id) -> bool
  - list_documents() -> list[dict]
  - load_chunks() -> list[dict]
  - get_chunks_for_documents(doc_ids) -> list[dict]
  - search_chunks_fts(query, top_k, tags) -> list[dict]
  - search_chunks_vector(query_vector, top_k, tags) -> list[dict]
  - search_chunks_trigram(query, top_k, tags) -> list[dict]
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

from app.ai.injection import detect_injection
from app.core.settings import KNOWLEDGE_DATA_DIR, ensure_local_dirs, get_settings

logger = logging.getLogger(__name__)
SUSPICIOUS_TAG = "posible-inyeccion"

KNOWLEDGE_DIR = KNOWLEDGE_DATA_DIR
KNOWLEDGE_RAW_UPLOADS_DIR = KNOWLEDGE_DIR
DOCUMENTS_DIR = KNOWLEDGE_RAW_UPLOADS_DIR

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120

# ---------------------------------------------------------------------------
# Path resolution — Server-local filesystem for uploaded raw documents
# ---------------------------------------------------------------------------


def get_knowledge_base_dir() -> Path:
  return KNOWLEDGE_DIR


def get_knowledge_documents_dir() -> Path:
  return KNOWLEDGE_RAW_UPLOADS_DIR


# ---------------------------------------------------------------------------
# PostgreSQL Connection Management
# ---------------------------------------------------------------------------

_PGVECTOR_AVAILABLE: bool | None = None


def is_postgres_configured() -> bool:
  url = get_settings().get_knowledge_db_url()
  return bool(url and url.strip())


_SCHEMA_INITIALIZED: bool = False


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
  if _PGVECTOR_AVAILABLE:
    _register_vector_adapter(conn)
  return conn


def _register_vector_adapter(conn) -> None:
  try:
    from pgvector.psycopg import register_vector
    register_vector(conn)
  except Exception as exc:
    logger.warning("Could not register pgvector with psycopg: %s", exc)


def _init_extensions(conn) -> None:
  global _PGVECTOR_AVAILABLE
  cur = conn.cursor()
  try:
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    conn.commit()
    _PGVECTOR_AVAILABLE = True
  except Exception as exc:
    conn.rollback()
    _PGVECTOR_AVAILABLE = False
    logger.info("pgvector extension not enabled or available in PostgreSQL: %s", exc)

  try:
    cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
    conn.commit()
  except Exception:
    conn.rollback()

  # pg_trgm is required: the trigram fallback search depends on it.
  try:
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    conn.commit()
  except Exception as exc:
    conn.rollback()
    raise RuntimeError(
      "PostgreSQL extension pg_trgm is required but could not be created. "
      "Run 'CREATE EXTENSION pg_trgm;' as a superuser on the knowledge database."
    ) from exc

  if _PGVECTOR_AVAILABLE:
    _register_vector_adapter(conn)


def _init_tables(conn) -> None:
  cur = conn.cursor()
  try:
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
    conn.commit()
  except Exception:
    conn.rollback()
    raise


def _init_vector_column(conn) -> None:
  if not _PGVECTOR_AVAILABLE:
    return
  cur = conn.cursor()
  try:
    cur.execute("""
        SELECT udt_name
        FROM information_schema.columns
        WHERE table_name = 'chunks' AND column_name = 'embedding';
    """)
    row = cur.fetchone()
    if row and row.get("udt_name") != "vector":
      cur.execute(
        "ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1536) USING NULL;"
      )
    conn.commit()
  except Exception as exc:
    conn.rollback()
    logger.warning("Could not migrate chunks embedding column to vector: %s", exc)


def _init_indexes(conn) -> None:
  cur = conn.cursor()
  try:
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin(tsv);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(document_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tags ON chunks USING gin(tags);")
    conn.commit()
  except Exception:
    conn.rollback()

  if _PGVECTOR_AVAILABLE:
    try:
      cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);"
      )
      conn.commit()
    except Exception as exc:
      conn.rollback()
      logger.warning("Could not create vector hnsw index: %s", exc)

  try:
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_text_trgm ON chunks USING gin (text gin_trgm_ops);")
    conn.commit()
  except Exception as exc:
    conn.rollback()
    logger.warning("Could not create trigram index: %s", exc)


def _init_metadata(conn) -> None:
  cur = conn.cursor()
  try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS db_meta (
            key   VARCHAR(64) PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT INTO db_meta (key, value) VALUES ('schema_version', '2')
        ON CONFLICT (key) DO NOTHING;
    """)
    conn.commit()
  except Exception:
    conn.rollback()


def _ensure_pg_schema(conn) -> None:
  _init_extensions(conn)
  _init_tables(conn)
  _init_vector_column(conn)
  _init_indexes(conn)
  _init_metadata(conn)


@contextmanager
def _db() -> Generator[Any, None, None]:
  """PostgreSQL DB context manager."""
  global _SCHEMA_INITIALIZED
  conn = _get_pg_connection()
  if not _SCHEMA_INITIALIZED:
    _ensure_pg_schema(conn)
    _SCHEMA_INITIALIZED = True
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
  if is_postgres_configured():
    try:
      with _db():
        pass
    except Exception as exc:
      logger.warning("Could not connect to PostgreSQL on ensure_knowledge_dirs: %s", exc)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
_HTML_SUFFIXES = (".html", ".htm")


def _decode_text(raw: bytes) -> str:
  for encoding in ("utf-8", "utf-16"):
    try:
      return raw.decode(encoding)
    except UnicodeDecodeError:
      continue
  return raw.decode("latin-1")


def extract_text(filename: str, raw: bytes) -> str:
  lower = filename.lower()
  if lower.endswith(_IMAGE_SUFFIXES):
    return f"[Asset Imagen: {filename} ({len(raw)} bytes)]"
  if lower.endswith(".pdf"):
    return _extract_pdf(raw)
  if lower.endswith(".docx"):
    return _extract_docx(raw)
  if lower.endswith(_HTML_SUFFIXES):
    return _extract_html(raw)
  return _decode_text(raw)


def _extract_pdf(raw: bytes) -> str:
  try:
    from io import BytesIO
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(raw))
    return "\n".join(page.extract_text() or "" for page in reader.pages)
  except Exception as exc:
    raise ValueError(f"Failed to read PDF: {exc}") from exc


def _table_as_markdown(table) -> str:
  """A Word table as a Markdown table, with a separator under the header when it is missing."""
  lines = []
  for row in table.rows:
    cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
    if any(cells):
      lines.append("| " + " | ".join(cells) + " |")
  if len(lines) > 1 and "---" not in lines[1]:
    lines.insert(1, "| " + " | ".join(["---"] * len(table.columns)) + " |")
  return "\n".join(lines)


def _extract_docx(raw: bytes) -> str:
  try:
    from io import BytesIO
    from docx import Document

    document = Document(BytesIO(raw))
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    tables = [markdown for markdown in map(_table_as_markdown, document.tables) if markdown]
    return "\n\n".join(paragraphs + tables)
  except Exception as exc:
    raise ValueError(f"Failed to read DOCX: {exc}") from exc


def _extract_html(raw: bytes) -> str:
  html = _decode_text(raw)
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
  chunks: list[str] = []
  start = 0
  while True:
    end = min(start + CHUNK_SIZE, len(cleaned))
    chunks.append(cleaned[start:end])
    if end >= len(cleaned):
      return chunks
    start = end - CHUNK_OVERLAP


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

  tags = list(tags or [])
  suspicious = detect_injection(text)
  if suspicious:
    # Kept and searchable, but flagged: the prompt-side check decides what the model gets to see.
    logger.warning("injection_detected_on_ingest filename=%s rules=%s", filename, ",".join(suspicious))
    if SUSPICIOUS_TAG not in tags:
      tags.append(SUSPICIOUS_TAG)

  doc_id = str(uuid.uuid4())
  safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename)
  stored_name = f"{doc_id}_{safe_name}"

  docs_dir = get_knowledge_documents_dir()
  docs_dir.mkdir(parents=True, exist_ok=True)
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
    (get_knowledge_documents_dir() / row["stored_as"]).unlink(missing_ok=True)
    cur.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM documents WHERE id = %s", (document_id,))

  return True


def _tags_of(raw: Any) -> list[Any]:
  return raw if isinstance(raw, list) else json.loads(raw or "[]")


def _timestamp(value: Any) -> str:
  return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _chunk_dict(row: dict[str, Any], *, scored: bool = False) -> dict[str, Any]:
  chunk = {
    "id": row["chunk_id"],
    "document_id": row["document_id"],
    "filename": row["filename"],
    "tags": _tags_of(row["tags"]),
    "index": row["chunk_index"],
    "text": row["text"],
    "uploaded_at": _timestamp(row["uploaded_at"]),
  }
  if scored:
    chunk["score"] = float(row["score"])
  return chunk


def _document_dict(row: dict[str, Any]) -> dict[str, Any]:
  return {
    "id": row["id"],
    "filename": row["filename"],
    "stored_as": row["stored_as"],
    "tags": _tags_of(row["tags"]),
    "chunk_count": row["chunk_count"],
    "char_count": row["char_count"],
    "uploaded_at": _timestamp(row["uploaded_at"]),
  }


def list_documents() -> list[dict[str, Any]]:
  ensure_knowledge_dirs()
  with _db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents ORDER BY uploaded_at DESC")
    rows = cur.fetchall()
  return [_document_dict(row) for row in rows]


_CHUNK_COLUMNS = "chunk_id, document_id, filename, tags, chunk_index, text, uploaded_at"


def load_chunks() -> list[dict[str, Any]]:
  ensure_knowledge_dirs()
  with _db() as conn:
    cur = conn.cursor()
    cur.execute(f"SELECT {_CHUNK_COLUMNS} FROM chunks ORDER BY document_id, chunk_index")
    rows = cur.fetchall()
  return [_chunk_dict(row) for row in rows]


def get_chunks_for_documents(document_ids: list[str], *, max_chunks: int = 48) -> list[dict[str, Any]]:
  if not document_ids:
    return []
  ensure_knowledge_dirs()
  with _db() as conn:
    cur = conn.cursor()
    cur.execute(
      f"SELECT {_CHUNK_COLUMNS} FROM chunks WHERE document_id = ANY(%s) ORDER BY document_id, chunk_index LIMIT %s",
      (document_ids, max_chunks),
    )
    rows = cur.fetchall()
  return [_chunk_dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Search: Full-Text Search (Spanish), vector similarity and trigram similarity
# ---------------------------------------------------------------------------


def _search_limit(top_k: int, tags: list[str] | None) -> int:
  """Over-fetch when tags will filter the rows afterwards, so top_k survivors remain likely."""
  return top_k * 3 if tags else top_k


def _with_any_tag(rows: list[dict[str, Any]], tags: list[str] | None, top_k: int) -> list[dict[str, Any]]:
  if not tags:
    return rows[:top_k]
  wanted = {tag.lower() for tag in tags}
  return [row for row in rows if wanted & {str(tag).lower() for tag in _tags_of(row["tags"])}][:top_k]


def _search_chunks(fetch, *, top_k: int, tags: list[str] | None, failure: str, needs_vector: bool = False) -> list[dict[str, Any]]:
  """Run `fetch(cursor)` and return the chunks carrying one of the tags; a failing query yields no results."""
  with _db() as conn:
    if needs_vector and not _PGVECTOR_AVAILABLE:
      return []
    try:
      rows = fetch(conn.cursor())
    except Exception as exc:
      logger.warning(failure, exc)
      return []
  return [_chunk_dict(row, scored=True) for row in _with_any_tag(rows, tags, top_k)]


_FTS_SQL = """SELECT {columns}, ts_rank_cd(tsv, {tsquery}('spanish', %(query)s)) AS score
  FROM chunks
  WHERE tsv @@ {tsquery}('spanish', %(query)s)
  ORDER BY score DESC
  LIMIT %(limit)s"""


def _fts_rows(cur, query: str, limit: int) -> list[dict[str, Any]]:
  """Web-style syntax first; a plain query when that matches nothing (e.g. a lone negated term)."""
  for tsquery in ("websearch_to_tsquery", "plainto_tsquery"):
    cur.execute(_FTS_SQL.format(columns=_CHUNK_COLUMNS, tsquery=tsquery), {"query": query, "limit": limit})
    rows = cur.fetchall()
    if rows:
      return rows
  return []


def search_chunks_fts(query: str, *, top_k: int = 8, tags: list[str] | None = None) -> list[dict[str, Any]]:
  """Full-Text Search with ranking and Spanish diacritics support via PostgreSQL tsvector."""
  ensure_knowledge_dirs()
  if not query.strip():
    return _with_any_tag(load_chunks(), tags, top_k)
  limit = _search_limit(top_k, tags)
  return _search_chunks(lambda cur: _fts_rows(cur, query, limit), top_k=top_k, tags=tags, failure="PostgreSQL FTS error: %s")


_VECTOR_SQL = f"""SELECT {_CHUNK_COLUMNS}, 1 - (embedding <=> %(vector)s::vector) AS score
  FROM chunks
  WHERE embedding IS NOT NULL
  ORDER BY embedding <=> %(vector)s::vector ASC
  LIMIT %(limit)s"""


def _query_rows(cur, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
  cur.execute(sql, params)
  return cur.fetchall()


def search_chunks_vector(query_vector: list[float], *, top_k: int = 8, tags: list[str] | None = None) -> list[dict[str, Any]]:
  """Vector similarity search (cosine distance) using PostgreSQL pgvector."""
  if not is_postgres_configured() or not query_vector:
    return []
  params = {"vector": query_vector, "limit": _search_limit(top_k, tags)}
  return _search_chunks(
    lambda cur: _query_rows(cur, _VECTOR_SQL, params),
    top_k=top_k, tags=tags, failure="Vector search query failed: %s", needs_vector=True,
  )


_TRIGRAM_SQL = f"""SELECT {_CHUNK_COLUMNS}, word_similarity(%(query)s, text) AS score
  FROM chunks
  WHERE %(query)s <%% text
  ORDER BY score DESC
  LIMIT %(limit)s"""


def search_chunks_trigram(query: str, *, top_k: int = 8, tags: list[str] | None = None) -> list[dict[str, Any]]:
  """Fuzzy lexical search via pg_trgm word similarity.

  Catches terms the Spanish tsvector misses, such as acronyms, IDs and English words.
  """
  if not is_postgres_configured() or not query.strip():
    return []
  params = {"query": query, "limit": _search_limit(top_k, tags)}
  return _search_chunks(
    lambda cur: _query_rows(cur, _TRIGRAM_SQL, params),
    top_k=top_k, tags=tags, failure="Trigram search query failed: %s",
  )


# ---------------------------------------------------------------------------
# Diagnostics & Status
# ---------------------------------------------------------------------------


def _empty_status(params: dict[str, Any]) -> dict[str, Any]:
  return {
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


def _count(cur, table: str) -> int:
  cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
  return cur.fetchone()["c"]


def _fill_live_status(status: dict[str, Any], params: dict[str, Any]) -> None:
  with _db() as conn:
    cur = conn.cursor()
    status["doc_count"] = _count(cur, "documents")
    status["chunk_count"] = _count(cur, "chunks")
    status["host"] = params["host"] or conn.info.host
    status["database"] = params["database"] or conn.info.dbname
    status["pgvector_enabled"] = bool(_PGVECTOR_AVAILABLE)
    status["connected"] = True


def get_db_status() -> dict[str, Any]:
  """Return current PostgreSQL database engine and capabilities status."""
  params = get_settings().get_knowledge_db_params()
  status = _empty_status(params)
  if not is_postgres_configured():
    status["error"] = "PostgreSQL no está configurado en las variables de entorno."
    return status
  try:
    _fill_live_status(status, params)
  except Exception as exc:
    logger.exception("Error al consultar el estado de la base de datos de conocimiento: %s", exc)
    status["connected"] = False
    status["error"] = "Error al conectar o consultar la base de datos de conocimiento."
  return status
