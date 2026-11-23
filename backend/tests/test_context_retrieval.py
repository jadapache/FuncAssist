"""search_knowledge fallback chain: vector -> FTS -> trigram / tag-filtered listing."""

from __future__ import annotations

import pytest

from app.context import retrieval


def row(cid="1", **extra):
  return {"id": cid, "filename": "spec.pdf", "index": 3, "text": "hola", "document_id": "d1", "tags": ["A"], "score": 0.5, **extra}


class _Calls(list):
  install = None


@pytest.fixture
def calls(monkeypatch):
  log = _Calls()

  def make(name, result):
    def fn(*args, **kwargs):
      log.append((name, args, kwargs))
      return result() if callable(result) else result
    return fn

  def install(vector=(), fts=(), trigram=(), loaded=()):
    monkeypatch.setattr(retrieval, "search_chunks_vector", make("vector", list(vector)))
    monkeypatch.setattr(retrieval, "search_chunks_fts", make("fts", list(fts)))
    monkeypatch.setattr(retrieval, "search_chunks_trigram", make("trigram", list(trigram)))
    monkeypatch.setattr(retrieval, "load_chunks", make("load", list(loaded)))

  install()
  log.install = install
  return log


def test_vector_hit_short_circuits(calls):
  calls.install(vector=[row("v")], fts=[row("f")])
  out = retrieval.search_knowledge("q", query_vector=[0.1, 0.2], top_k=3, tags=["A"])
  assert [c.id for c in out] == ["v"] and [c[0] for c in calls] == ["vector"]
  assert calls[0][2] == {"top_k": 3, "tags": ["A"]}
  assert out[0].title == "spec.pdf#chunk-3" and out[0].score == 0.5 and out[0].metadata["document_id"] == "d1"


def test_vector_miss_falls_to_fts(calls):
  calls.install(fts=[row("f")])
  out = retrieval.search_knowledge("q", query_vector=[0.1])
  assert [c.id for c in out] == ["f"] and [c[0] for c in calls] == ["vector", "fts"]


def test_fts_miss_falls_to_trigram(calls):
  calls.install(trigram=[row("t")])
  out = retrieval.search_knowledge("ABC-123")
  assert [c.id for c in out] == ["t"] and [c[0] for c in calls] == ["fts", "trigram"]


def test_blank_query_lists_chunks_filtered_by_tags(calls):
  calls.install(loaded=[row("1", tags=["A"]), row("2", tags=["b"]), row("3", tags=[])])
  assert [c.id for c in retrieval.search_knowledge("  ")] == ["1", "2", "3"]
  assert [c.id for c in retrieval.search_knowledge("  ", tags=["B"])] == ["2"]
  assert [c.id for c in retrieval.search_knowledge("  ", top_k=1)] == ["1"]
  assert all(c[0] != "trigram" for c in calls)
  assert retrieval.search_knowledge("  ")[0].score is None


