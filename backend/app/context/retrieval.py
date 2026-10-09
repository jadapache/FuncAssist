"""Retrieval over knowledge chunks — FTS5 persistent index with Python BM25 fallback."""

from __future__ import annotations

from typing import Any

from app.context.knowledge import (
  get_chunks_for_documents,
  load_chunks,
  search_chunks_fts,
)
from app.context.models import ContextChunk, SourceType


def chunks_from_documents(document_ids: list[str], *, max_chunks: int = 48) -> list[ContextChunk]:
  return [_to_chunk(item, score=None) for item in get_chunks_for_documents(document_ids, max_chunks=max_chunks)]


def search_knowledge(query: str, *, top_k: int = 8, tags: list[str] | None = None) -> list[ContextChunk]:
  # 1. Try SQLite FTS5 — fast, persistent index, handles Spanish accents
  fts_results = search_chunks_fts(query, top_k=top_k, tags=tags)
  if fts_results:
    return [_to_chunk(item, score=item.get("score")) for item in fts_results]

  # 2. Fall back to Python BM25 / keyword over full corpus
  chunks = load_chunks()
  if tags:
    tag_set = {tag.lower() for tag in tags}
    chunks = [
      chunk
      for chunk in chunks
      if tag_set.intersection({str(tag).lower() for tag in chunk.get("tags") or []})
    ]

  if not chunks:
    return []

  corpus = [str(chunk.get("text") or "") for chunk in chunks]
  if not query.strip():
    return [_to_chunk(item, score=None) for item in chunks[:top_k]]

  scores = _bm25_scores(query, corpus)
  if scores is None:
    scores = _keyword_scores(query, corpus)

  ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)
  results: list[ContextChunk] = []
  for index, score in ranked[:top_k]:
    if score <= 0:
      continue
    results.append(_to_chunk(chunks[index], score=float(score)))
  return results


def _bm25_scores(query: str, corpus: list[str]) -> list[float] | None:
  try:
    from rank_bm25 import BM25Okapi
  except ImportError:
    return None

  tokenized_corpus = [_tokenize(text) for text in corpus]
  bm25 = BM25Okapi(tokenized_corpus)
  return list(bm25.get_scores(_tokenize(query)))


def _keyword_scores(query: str, corpus: list[str]) -> list[float]:
  tokens = _tokenize(query)
  if not tokens:
    return [0.0 for _ in corpus]
  scores: list[float] = []
  for text in corpus:
    hay = text.lower()
    score = 0.0
    for token in tokens:
      if token in hay:
        score += 1.0 + hay.count(token) * 0.1
    scores.append(score)
  return scores


def _tokenize(text: str) -> list[str]:
  return [token for token in text.lower().replace("\n", " ").split(" ") if token]


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
