"""AI audit log: JSONL writes, reverse reading, legacy files and metric aggregation."""

import json
import os
from datetime import datetime, timezone

import pytest

from app.ai import logging as ai_logging


@pytest.fixture
def logs_dir(tmp_path, monkeypatch):
  d = tmp_path / "logs"
  monkeypatch.setattr(ai_logging, "LOGS_DIR", d)
  monkeypatch.setattr(ai_logging, "ensure_local_dirs", lambda: None)
  return d


def test_sync_write_and_list(logs_dir):
  e1 = ai_logging.log_ai_call({"route": "chat", "n": 1})
  e2 = ai_logging.log_ai_call({"route": "chat", "n": 2})
  assert e1["id"] != e2["id"] and "created_at" in e1
  logs = ai_logging.list_logs(limit=10)
  assert [l["n"] for l in logs] == [2, 1]
  assert ai_logging.list_logs(limit=1)[0]["n"] == 2


def test_daily_path_uses_date(logs_dir):
  p = ai_logging._get_daily_log_path(datetime(2025, 1, 2, tzinfo=timezone.utc))
  assert p.name == "2025-01-02.jsonl" and logs_dir.exists()


@pytest.mark.asyncio
async def test_async_write_is_flushed(logs_dir):
  ai_logging.log_ai_call({"route": "async"})
  await ai_logging.flush_pending_logs()
  assert ai_logging.list_logs()[0]["route"] == "async"
  await ai_logging.flush_pending_logs()  # no pending: no-op


def test_write_failure_is_swallowed(monkeypatch, caplog):
  def boom(dt=None):
    raise OSError("disk full")
  monkeypatch.setattr(ai_logging, "_get_daily_log_path", boom)
  ai_logging._write_log_entry({"id": "x"})
  assert "Could not write AI log entry" in caplog.text


def test_reverse_reader_small_blocks(tmp_path):
  p = tmp_path / "f.jsonl"
  p.write_bytes(b"first line\n\nsecond line\nthird")
  assert list(ai_logging._iter_lines_reversed(p, block_size=4)) == ["third", "second line", "first line"]


def test_list_logs_skips_bad_lines_and_reads_legacy(logs_dir):
  logs_dir.mkdir(parents=True)
  (logs_dir / "2024-01-01.jsonl").write_text('{"a": 1}\nnot json\n', encoding="utf-8")
  (logs_dir / "old1.json").write_text('{"legacy": 1}', encoding="utf-8")
  (logs_dir / "old2.json").write_text("broken", encoding="utf-8")
  (logs_dir / "old3.json").write_text('{"legacy": 3}', encoding="utf-8")
  os.utime(logs_dir / "old3.json", (1, 1))
  logs = ai_logging.list_logs(limit=10)
  assert logs[0] == {"a": 1} and {"legacy": 1} in logs and {"legacy": 3} in logs and len(logs) == 3
  assert len(ai_logging.list_logs(limit=2)) == 2


def test_list_logs_unreadable_file(logs_dir, monkeypatch):
  logs_dir.mkdir(parents=True)
  (logs_dir / "2024-01-01.jsonl").write_text('{"a": 1}\n', encoding="utf-8")

  def boom(path, block_size=0):
    raise OSError("locked")
    yield  # pragma: no cover

  monkeypatch.setattr(ai_logging, "_iter_lines_reversed", boom)
  assert ai_logging.list_logs() == []


def test_percentile():
  assert ai_logging.percentile([], 50) is None
  assert ai_logging.percentile([5, "x"], 95) == 5.0
  assert ai_logging.percentile([1, 2, 3, 4], 50) == 2.5
  assert ai_logging.percentile([10, 20], 100) == 20.0


def test_summarize_logs():
  logs = [
    {"prompt_tokens": 100, "completion_tokens": 10, "cached_tokens": 50, "cost_usd": 0.01, "duration_ms": 100,
     "ttft_ms": 10, "route": "chat", "protocol": "v2", "intent_source": "rules", "fallback_used": True},
    {"prompt_tokens": 100, "completion_tokens": 20, "duration_ms": 300, "ttft_ms": 30, "route": "chat",
     "finish_reason": "length", "error_code": "x"},
    {"refused": True, "prompt_tokens": True, "route": "doc"},
  ]
  s = ai_logging.summarize_logs(logs)
  assert s["total_calls"] == 3 and s["total_prompt_tokens"] == 200 and s["total_completion_tokens"] == 30
  assert s["total_cost_usd"] == 0.01 and s["avg_duration_ms"] == 200.0 and s["p50_duration_ms"] == 200.0
  assert s["fallback_rate"] == 0.5 and s["cache_hit_rate"] == 0.25
  assert s["error_rate"] == round(1 / 3, 4) and s["truncation_rate"] == round(1 / 3, 4)
  assert s["routes"] == {"chat": 2, "doc": 1} and s["protocols"] == {"v2": 1} and s["intent_sources"] == {"rules": 1}
  empty = ai_logging.summarize_logs([])
  assert empty["avg_duration_ms"] == 0.0 and empty["p50_duration_ms"] is None and empty["fallback_rate"] == 0.0
  assert json.dumps(empty)
