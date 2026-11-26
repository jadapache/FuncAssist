"""Edge cases of artifact parsing and streaming, conversation history and the AI audit log."""

import asyncio
import json
import logging
import os

import pytest

from app.ai import artifacts, history
from app.ai import logging as ai_logging
from app.ai.providers.base import AIMessage


# --- artifacts: truncation heuristics -------------------------------------

def _long(last_line, filler_lines=20):
  return "\n".join(["Línea de relleno con texto suficiente para pasar el umbral."] * filler_lines + [last_line])


def test_truncation_heuristic_needs_more_than_500_chars():
  at_limit = "x" * (500 - len("\n## Seccion")) + "\n## Seccion"
  assert len(at_limit) == 500 and artifacts.is_artifact_truncated(at_limit) is False
  assert artifacts.is_artifact_truncated("x" * (501 - len("\n## Seccion")) + "\n## Seccion") is True


def test_only_the_last_line_decides_whether_a_long_text_is_cut():
  assert artifacts.is_artifact_truncated(_long("-")) is True
  assert artifacts.is_artifact_truncated("## Titulo\n" + _long("Cierre completo.")) is False
  assert artifacts.is_artifact_truncated(_long("Cierre completo.") + "\n") is False


def test_whitespace_and_empty_text_are_not_truncated():
  assert artifacts.is_artifact_truncated("") is False
  assert artifacts.is_artifact_truncated("   \n ") is False
  assert artifacts.has_unclosed_artifact("") is False
  assert artifacts.has_unclosed_artifact("sin etiquetas") is False


# --- artifacts: extraction ------------------------------------------------

def test_artifact_with_empty_body_followed_by_a_cut_off_one():
  raw = '<artifact title="A" extension="md"></artifact><artifact title="B" extension="docx">cuerpo'
  found, _ = artifacts.extract_artifacts(raw)
  assert [(a.title, a.extension, a.content, a.index) for a in found] == [("A", "md", "", 0), ("B", "docx", "cuerpo", 1)]


def test_closing_tag_in_other_case_still_closes_the_artifact():
  found, clean = artifacts.extract_artifacts('<artifact title="A" extension="MD">x</ARTIFACT>')
  assert [(a.title, a.extension, a.content) for a in found] == [("A", "md", "x")]
  assert clean == "x"


def test_both_attribute_orders_are_extracted():
  main, _ = artifacts.extract_artifacts('<artifact title="T1" extension="DOCX"> uno </artifact>')
  alt, _ = artifacts.extract_artifacts('<artifact extension="XLSX" title="T2"> dos </artifact>')
  assert (main[0].title, main[0].extension, main[0].content, main[0].index) == ("T1", "docx", "uno", 0)
  assert (alt[0].title, alt[0].extension, alt[0].content, alt[0].index) == ("T2", "xlsx", "dos", 0)


def test_fallback_artifact_is_the_first_one():
  fallback = artifacts.build_fallback_artifact("# Mi plan\ncuerpo")
  assert (fallback.title, fallback.extension, fallback.index) == ("Mi plan", "docx", 0)


@pytest.mark.parametrize("text,expected", [
  ("hola <", 1), ("<art", 4), ("<artifac", 8), ("<artifact", 0), ("abc", 0), ("", 0), ("ok </chat", 6),
])
def test_partial_suffix_len(text, expected):
  assert artifacts._partial_suffix_len(text, artifacts._HELD_PREFIXES_OUTSIDE) == expected


# --- artifacts: streaming splitter ----------------------------------------

def test_single_feed_with_a_whole_artifact_and_trailing_text():
  events = artifacts.ArtifactStreamSplitter().feed('antes <artifact title="A" extension="md">cuerpo</artifact> despues')
  assert [e[0] for e in events] == ["delta", "artifact_start", "artifact_delta", "artifact_end", "delta"]
  assert events[2][1] == {"index": 0, "text": "cuerpo"}
  assert events[3][1]["truncated"] is False
  assert events[4][1] == {"text": " despues"}


def test_artifacts_are_numbered_in_order():
  events = artifacts.ArtifactStreamSplitter().feed(
    '<artifact title="A" extension="md">1</artifact><artifact title="B" extension="md">2</artifact>'
  )
  assert [e[1]["index"] for e in events if e[0] == "artifact_start"] == [0, 1]
  assert [e[1]["index"] for e in events if e[0] == "artifact_end"] == [0, 1]


def test_empty_and_one_character_bodies():
  empty = artifacts.ArtifactStreamSplitter().feed('<artifact title="A" extension="md"></artifact>')
  assert [e[0] for e in empty] == ["artifact_start", "artifact_end"]
  one = artifacts.ArtifactStreamSplitter().feed('<artifact title="A" extension="md">x</artifact>')
  assert [e[0] for e in one] == ["artifact_start", "artifact_delta", "artifact_end"]


def test_malformed_tag_is_passed_through_and_parsing_continues():
  events = artifacts.ArtifactStreamSplitter().feed('<artifact foo> y <artifact title="A" extension="md">z</artifact>')
  assert events[0] == ("delta", {"text": "<artifact foo>"})
  assert [e[0] for e in events][1:] == ["delta", "artifact_start", "artifact_delta", "artifact_end"]


def test_incomplete_opening_tag_waits_for_more_text():
  splitter = artifacts.ArtifactStreamSplitter()
  assert splitter.feed('<artifact title="A"') == []
  events = splitter.feed(' extension="md">ok</artifact>')
  assert [e[0] for e in events] == ["artifact_start", "artifact_delta", "artifact_end"]


# --- history --------------------------------------------------------------

def test_continuation_lines_extend_the_latest_turn():
  assert history._parse_prefixed_lines(["user: a\nassistant: b\ncontinua"]) == [
    {"role": "user", "content": "a"}, {"role": "assistant", "content": "b\ncontinua"},
  ]


def test_consecutive_turns_of_one_role_are_merged_into_the_latest():
  messages = history.format_history_as_messages([
    {"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "assistant", "content": "c"},
  ])
  assert [(m.role, m.content) for m in messages] == [("user", "a"), ("assistant", "b\n\nc")]


def test_summary_cache_evicts_the_oldest_entry(monkeypatch):
  monkeypatch.setattr(history, "_SUMMARY_CACHE_MAX", 3)
  monkeypatch.setattr(history, "_summary_cache", history.OrderedDict())
  for key in "abcd":
    history._cache_put(key, key.upper())
  assert list(history._summary_cache) == ["b", "c", "d"]
  assert history._cache_get("b") == "B"
  history._cache_put("e", "E")
  assert list(history._summary_cache) == ["d", "b", "e"]


class _Store:
  def __init__(self, record=None, load_error=None, save_error=None):
    self.record, self.load_error, self.save_error, self.saved = record, load_error, save_error, []

  async def load(self):
    if self.load_error:
      raise self.load_error
    return self.record

  async def save(self, key, summary):
    if self.save_error:
      raise self.save_error
    self.saved.append((key, summary))


def _turns(n):
  return [AIMessage(role="user" if i % 2 == 0 else "assistant", content=f"m{i}") for i in range(n)]


@pytest.mark.asyncio
async def test_persisted_summary_lookup():
  older = _turns(4)
  assert await history._load_persisted_summary(None, "s", older) == (0, None)

  def key(count):
    return history._encode_store_key(count, history._summary_key("s", older[:count]))

  assert await history._load_persisted_summary(_Store((key(4), "S4")), "s", older) == (4, "S4")
  assert await history._load_persisted_summary(_Store((key(1), "S1")), "s", older) == (1, "S1")
  assert await history._load_persisted_summary(_Store((key(0), "S0")), "s", older) == (0, None)
  assert await history._load_persisted_summary(_Store((history._encode_store_key(5, "x"), "S")), "s", older) == (0, None)
  assert await history._load_persisted_summary(_Store((history._encode_store_key(2, "wrong"), "S")), "s", older) == (0, None)
  assert await history._load_persisted_summary(_Store(None), "s", older) == (0, None)


@pytest.mark.asyncio
async def test_failed_store_load_is_logged_with_traceback(caplog):
  with caplog.at_level(logging.WARNING):
    assert await history._load_persisted_summary(_Store(load_error=RuntimeError("x")), "s", _turns(2)) == (0, None)
  assert any("Could not load" in r.getMessage() and r.exc_info for r in caplog.records)


@pytest.mark.asyncio
async def test_failed_store_save_and_summary_are_logged_with_traceback(caplog):
  class _Failing:
    default_model = "m-1"

    async def complete(self, messages, max_tokens=None):
      raise RuntimeError("down")

  with caplog.at_level(logging.WARNING):
    await history._persist_summary(_Store(save_error=RuntimeError("x")), "k", "s")
    await history._persist_summary(None, "k", "s")
    assert await history._request_summary(_Failing(), None, _turns(2)) == ""
  assert any("Could not persist" in r.getMessage() and r.exc_info for r in caplog.records)
  assert any("summarization failed" in r.getMessage() and "m-1" in r.getMessage() and r.exc_info for r in caplog.records)


def test_recent_window_starts_on_a_user_turn_and_keeps_a_pair(monkeypatch):
  messages = [AIMessage(role="assistant", content="a0")] + _turns(5)
  window = history._recent_window(messages, 10_000, "m")
  assert [m.content for m in window] == ["m0", "m1", "m2", "m3", "m4"]
  monkeypatch.setattr(history, "count_tokens", lambda model, msgs: 10_000)
  assert len(history._recent_window(_turns(6), 1, "m")) == 2


@pytest.mark.asyncio
async def test_prune_leaves_short_or_within_budget_conversations_untouched(monkeypatch):
  monkeypatch.setattr(history, "count_tokens", lambda model, msgs: 100)
  two = _turns(2)
  assert await history.prune_or_summarize_history(two, 1, "m") is two
  three = _turns(3)
  assert await history.prune_or_summarize_history(three, 100, "m") is three
  assert await history.prune_or_summarize_history([], 1, "m") == []
  assert len(await history.prune_or_summarize_history(_turns(8), 1, "m")) < 8


# --- audit log ------------------------------------------------------------

@pytest.fixture
def nested_logs(tmp_path, monkeypatch):
  monkeypatch.setattr(ai_logging, "LOGS_DIR", tmp_path / "a" / "b" / "logs")
  monkeypatch.setattr(ai_logging, "SECURITY_DIR", tmp_path / "a" / "b" / "security")
  monkeypatch.setattr(ai_logging, "ensure_local_dirs", lambda: None)
  return tmp_path


def test_log_directories_are_created_with_parents_and_reused(nested_logs):
  ai_logging._get_daily_log_path()
  ai_logging._get_daily_log_path()
  ai_logging.list_logs()
  ai_logging.list_logs()
  ai_logging._write_security_entry({"id": "1"})
  ai_logging._write_security_entry({"id": "2"})
  assert [e["id"] for e in ai_logging.list_security_events()] == ["2", "1"]


def test_entries_keep_non_ascii_characters_readable(nested_logs):
  ai_logging._write_log_entry({"id": "1", "text": "ñandú"})
  ai_logging._write_security_entry({"id": "2", "text": "acción"})
  assert "ñandú" in next(ai_logging.LOGS_DIR.glob("*.jsonl")).read_text(encoding="utf-8")
  assert "acción" in next(ai_logging.SECURITY_DIR.glob("*.jsonl")).read_text(encoding="utf-8")


def test_write_failures_are_logged_with_traceback(nested_logs, monkeypatch, caplog):
  def boom(*args, **kwargs):
    raise OSError("disk full")
  monkeypatch.setattr(ai_logging, "_get_daily_log_path", boom)
  monkeypatch.setattr(ai_logging, "ensure_local_dirs", boom)
  with caplog.at_level(logging.WARNING):
    ai_logging._write_log_entry({"id": "x"})
    ai_logging._write_security_entry({"id": "y"})
  assert sum(1 for r in caplog.records if "Could not write" in r.getMessage() and r.exc_info) == 2


@pytest.mark.asyncio
async def test_flush_does_not_raise_when_a_write_failed():
  async def fail():
    raise RuntimeError("x")
  task = asyncio.ensure_future(fail())
  ai_logging._PENDING_WRITES.add(task)
  try:
    await ai_logging.flush_pending_logs()
  finally:
    ai_logging._PENDING_WRITES.discard(task)


def test_newest_daily_file_and_newest_legacy_file_come_first(nested_logs):
  ai_logging.LOGS_DIR.mkdir(parents=True)
  (ai_logging.LOGS_DIR / "2025-01-01.jsonl").write_text(json.dumps({"n": "old-day"}) + "\n")
  (ai_logging.LOGS_DIR / "2025-01-02.jsonl").write_text(json.dumps({"n": "new-day"}) + "\n")
  for name, mtime in (("a.json", 100), ("b.json", 200)):
    path = ai_logging.LOGS_DIR / name
    path.write_text(json.dumps({"n": name}))
    os.utime(path, (mtime, mtime))
  assert [e["n"] for e in ai_logging.list_logs(limit=10)] == ["new-day", "old-day", "b.json", "a.json"]
  assert [e["n"] for e in ai_logging.list_logs(limit=3)] == ["new-day", "old-day", "b.json"]


def test_reverse_reader_returns_every_line_of_a_multi_block_file(tmp_path):
  path = tmp_path / "f.jsonl"
  lines = [f"linea-{i}" for i in range(20)]
  path.write_text("\n".join(lines) + "\n")
  assert list(ai_logging._iter_lines_reversed(path, block_size=7)) == lines[::-1]


def test_percentile_of_one_value():
  assert ai_logging.percentile([5], 95) == 5.0
  assert ai_logging.percentile([], 50) is None
  assert ai_logging.percentile([1, 3], 50) == 2.0


# --- round 3: remaining boundary cases -------------------------------------

def test_each_cut_off_artifact_ends_where_the_next_one_begins():
  raw = (
    '<artifact title="A" extension="md">a</artifact>'
    '<artifact title="B" extension="md">b</artifact>'
    '<artifact title="C" extension="md">c-parcial'
  )
  found, _ = artifacts.extract_artifacts(raw)
  assert [(a.title, a.content, a.index) for a in found] == [("A", "a", 0), ("B", "b", 1), ("C", "c-parcial", 2)]


def test_directories_are_created_with_their_parents_on_first_use(tmp_path, monkeypatch):
  monkeypatch.setattr(ai_logging, "LOGS_DIR", tmp_path / "x" / "y" / "logs")
  monkeypatch.setattr(ai_logging, "SECURITY_DIR", tmp_path / "p" / "q" / "security")
  monkeypatch.setattr(ai_logging, "ensure_local_dirs", lambda: None)
  assert ai_logging.list_logs() == []
  ai_logging._write_security_entry({"id": "1"})
  assert [e["id"] for e in ai_logging.list_security_events()] == ["1"]
