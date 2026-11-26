"""Local AI call audit log supporting high-performance daily JSONL and metric tracking."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from itertools import chain, islice
from pathlib import Path
from typing import Any, Iterator

from app.core.settings import USER_DATA_DIR, ensure_local_dirs

LOGS_DIR = USER_DATA_DIR / "ai" / "logs"
_READ_BLOCK_BYTES = 64 * 1024

logger = logging.getLogger(__name__)

# Strong references to in-flight writes: the event loop only keeps weak references to tasks,
# so an unreferenced write task can be garbage-collected before it runs and the entry is lost.
_PENDING_WRITES: set[asyncio.Task[Any]] = set()


def _get_daily_log_path(dt: datetime | None = None) -> Path:
  ensure_local_dirs()
  LOGS_DIR.mkdir(parents=True, exist_ok=True)
  date_str = (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
  return LOGS_DIR / f"{date_str}.jsonl"


def _write_log_entry(payload: dict[str, Any]) -> None:
  try:
    path = _get_daily_log_path()
    with open(path, "a", encoding="utf-8") as f:
      f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
  except Exception as exc:  # the audit log must never break a request
    logger.warning("Could not write AI log entry %s: %s", payload.get("id"), exc, exc_info=True)


def log_ai_call(entry: dict[str, Any]) -> dict[str, Any]:
  """Audit log entry append to daily JSONL."""
  payload = {
    "id": str(uuid.uuid4()),
    "created_at": datetime.now(timezone.utc).isoformat(),
    **entry,
  }
  try:
    loop = asyncio.get_running_loop()
  except RuntimeError:
    _write_log_entry(payload)
    return payload
  task = loop.create_task(asyncio.to_thread(_write_log_entry, payload))
  _PENDING_WRITES.add(task)
  task.add_done_callback(_PENDING_WRITES.discard)
  return payload


async def flush_pending_logs() -> None:
  """Wait for queued log writes (used on shutdown and in tests)."""
  if _PENDING_WRITES:
    await asyncio.gather(*list(_PENDING_WRITES), return_exceptions=True)


def _iter_lines_reversed(path: Path, block_size: int = _READ_BLOCK_BYTES) -> Iterator[str]:
  """Yield the lines of a file from last to first, reading fixed-size blocks from the end."""
  with open(path, "rb") as f:
    position = path.stat().st_size
    remainder = b""
    while position > 0:
      read_size = min(block_size, position)
      position -= read_size
      f.seek(position)
      block = f.read(read_size) + remainder
      lines = block.split(b"\n")
      # The first piece may be the tail of a line that starts in an earlier block.
      remainder = lines.pop(0)
      for raw in reversed(lines):
        if raw.strip():
          yield raw.decode("utf-8", errors="replace")
    if remainder.strip():
      yield remainder.decode("utf-8", errors="replace")


def _iter_jsonl_records(directory: Path) -> Iterator[Any]:
  """Parsed records of every daily JSONL file in `directory`, newest file and newest line first.

  Unparseable lines and unreadable files are skipped.
  """
  for jf in sorted(directory.glob("*.jsonl"), reverse=True):
    try:
      for line in _iter_lines_reversed(jf):
        try:
          yield json.loads(line)
        except json.JSONDecodeError:
          continue
    except OSError:
      continue


def _iter_legacy_logs() -> Iterator[Any]:
  """Backward compatibility: legacy individual JSON files, newest first."""
  json_files = sorted(LOGS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
  for path in json_files:
    try:
      yield json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
      continue


def list_logs(limit: int = 20) -> list[dict[str, Any]]:
  """Latest log entries, newest first, reading each daily file from its end."""
  ensure_local_dirs()
  LOGS_DIR.mkdir(parents=True, exist_ok=True)
  return list(islice(chain(_iter_jsonl_records(LOGS_DIR), _iter_legacy_logs()), limit))


SECURITY_DIR = USER_DATA_DIR / "ai" / "security"
# Writes run in worker threads; serializing them keeps concurrent events from colliding on the file.
_SECURITY_WRITE_LOCK = threading.Lock()


def _write_security_entry(payload: dict[str, Any]) -> None:
  try:
    ensure_local_dirs()
    SECURITY_DIR.mkdir(parents=True, exist_ok=True)
    path = SECURITY_DIR / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    with _SECURITY_WRITE_LOCK, open(path, "a", encoding="utf-8") as f:
      f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
  except Exception as exc:  # the audit log must never break a request
    logger.warning("Could not write security log entry %s: %s", payload.get("id"), exc, exc_info=True)


def log_security_event(kind: str, **fields: Any) -> dict[str, Any]:
  """Append a security decision (a detected injection, an allowed or denied tool call) to its own daily JSONL.

  Kept apart from the call log so it does not distort its metrics. Callers pass identifiers and hashes,
  never the content of what was inspected.
  """
  payload = {
    "id": str(uuid.uuid4()),
    "created_at": datetime.now(timezone.utc).isoformat(),
    "kind": kind,
    **fields,
  }
  try:
    loop = asyncio.get_running_loop()
  except RuntimeError:
    _write_security_entry(payload)
    return payload
  task = loop.create_task(asyncio.to_thread(_write_security_entry, payload))
  _PENDING_WRITES.add(task)
  task.add_done_callback(_PENDING_WRITES.discard)
  return payload


def list_security_events(limit: int = 50, kind: str | None = None) -> list[dict[str, Any]]:
  """Latest security events, newest first."""
  if not SECURITY_DIR.exists():
    return []
  events = (event for event in _iter_jsonl_records(SECURITY_DIR) if not kind or event.get("kind") == kind)
  return list(islice(events, limit))


def percentile(values: list[float], pct: float) -> float | None:
  """Linear-interpolated percentile (pct in 0..100) or None for no data."""
  data = sorted(v for v in values if isinstance(v, (int, float)))
  if not data:
    return None
  rank = (len(data) - 1) * (pct / 100.0)
  low = int(rank)
  high = min(low + 1, len(data) - 1)
  return float(data[low] + (data[high] - data[low]) * (rank - low))


def _num(entry: dict[str, Any], key: str) -> float | None:
  value = entry.get(key)
  return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _total(logs: list[dict[str, Any]], key: str) -> float:
  return sum(_num(entry, key) or 0 for entry in logs)


def _positive_values(logs: list[dict[str, Any]], key: str) -> list[float]:
  return [value for value in (_num(entry, key) for entry in logs) if value]


def _round(value: float | None) -> float | None:
  return round(value, 2) if value is not None else None


def _ratio(part: float, whole: float) -> float:
  return round(part / whole, 4) if whole else 0.0


def _counts(logs: list[dict[str, Any]], key: str) -> dict[str, int]:
  return dict(Counter(str(entry.get(key)) for entry in logs if entry.get(key)))


def _latency_stats(logs: list[dict[str, Any]]) -> dict[str, Any]:
  durations = _positive_values(logs, "duration_ms")
  ttfts = _positive_values(logs, "ttft_ms")
  return {
    "avg_duration_ms": _round(sum(durations) / len(durations)) if durations else 0.0,
    "p50_duration_ms": _round(percentile(durations, 50)),
    "p95_duration_ms": _round(percentile(durations, 95)),
    "p50_ttft_ms": _round(percentile(ttfts, 50)),
    "p95_ttft_ms": _round(percentile(ttfts, 95)),
  }


def summarize_logs(logs: list[dict[str, Any]]) -> dict[str, Any]:
  """Aggregate metrics over log entries: tokens, cost, latency percentiles, fallback/cache/error rates."""
  total = len(logs)
  prompt_tokens = _total(logs, "prompt_tokens")
  cached_tokens = _total(logs, "cached_tokens")
  llm_calls = [entry for entry in logs if not entry.get("refused")]
  fallbacks = sum(1 for entry in llm_calls if entry.get("fallback_used"))
  errors = sum(1 for entry in logs if entry.get("error_code"))
  truncated = sum(1 for entry in logs if entry.get("finish_reason") == "length")
  return {
    "total_calls": total,
    "total_prompt_tokens": int(prompt_tokens),
    "total_completion_tokens": int(_total(logs, "completion_tokens")),
    "total_cached_tokens": int(cached_tokens),
    "total_cost_usd": round(_total(logs, "cost_usd"), 4),
    **_latency_stats(logs),
    "fallback_rate": _ratio(fallbacks, len(llm_calls)),
    "cache_hit_rate": _ratio(cached_tokens, prompt_tokens),
    "error_rate": _ratio(errors, total),
    "truncation_rate": _ratio(truncated, total),
    "routes": _counts(logs, "route"),
    # Chat SSE protocol per request: v1 can be retired once it stops appearing here.
    "protocols": _counts(logs, "protocol"),
    "intent_sources": _counts(logs, "intent_source"),
  }
