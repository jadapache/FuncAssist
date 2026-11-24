"""Retrieval over knowledge chunks — PostgreSQL vector, full-text and trigram search."""

from __future__ import annotations

from typing import Any

from app.context.knowledge import (
  get_chunks_for_documents,
  load_chunks,
  search_chunks_fts,
  search_chunks_trigram,
  search_chunks_vector,
)
from app.context.models import ContextChunk, SourceType


def chunks_from_documents(document_ids: list[str], *, max_chunks: int = 48) -> list[ContextChunk]:
  return [_to_chunk(item, score=None) for item in get_chunks_for_documents(document_ids, max_chunks=max_chunks)]


def search_knowledge(
  query: str,
  *,
  top_k: int = 8,
  tags: list[str] | None = None,
  query_vector: list[float] | None = None,
) -> list[ContextChunk]:
  # 1. If vector is provided, perform vector similarity search
  if query_vector:
    vector_results = search_chunks_vector(query_vector, top_k=top_k, tags=tags)
    if vector_results:
      return [_to_chunk(item, score=item.get("score")) for item in vector_results]

  # 2. Try PostgreSQL FTS (Spanish tsvector / ranking)
  fts_results = search_chunks_fts(query, top_k=top_k, tags=tags)
  if fts_results:
    return [_to_chunk(item, score=item.get("score")) for item in fts_results]

  # 3. Fall back to trigram / ILIKE search in PostgreSQL (acronyms, IDs, English terms)
  if not query.strip():
    return [_to_chunk(item, score=None) for item in _filter_by_tags(load_chunks(), tags)[:top_k]]
  trigram_results = search_chunks_trigram(query, top_k=top_k, tags=tags)
  return [_to_chunk(item, score=item.get("score")) for item in trigram_results]


def _filter_by_tags(chunks: list[dict[str, Any]], tags: list[str] | None) -> list[dict[str, Any]]:
  if not tags:
    return chunks
  tag_set = {tag.lower() for tag in tags}
  return [
    chunk
    for chunk in chunks
    if tag_set.intersection({str(tag).lower() for tag in chunk.get("tags") or []})
  ]


def _to_chunk(item: dict[str, Any], score: float | None) -> ContextChunk:
  filename = str(item.get("filename") or "document")
  return ContextChunk(
    id=str(item.get("id")),
    source_type=SourceType.KNOWLEDGE,
    source_label=filename,
    title=f"{filename}#chunk-{item.get('index', 0)}",
    text=str(item.get("text") or ""),
    metadata={
      "document_id": item.get("document_id"),
      "tags": item.get("tags") or [],
      "uploaded_at": item.get("uploaded_at"),
    },
    score=score,
  )
