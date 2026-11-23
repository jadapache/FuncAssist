"""Local AI call audit log supporting high-performance daily JSONL and metric tracking."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
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
    f.seek(0, os.SEEK_END)
    position = f.tell()
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


def list_logs(limit: int = 20) -> list[dict[str, Any]]:
  """Latest log entries, newest first, reading each daily file from its end."""
  ensure_local_dirs()
  LOGS_DIR.mkdir(parents=True, exist_ok=True)
  logs: list[dict[str, Any]] = []

  # 1. Daily JSONL files, newest file first, newest line first.
  for jf in sorted(LOGS_DIR.glob("*.jsonl"), reverse=True):
    try:
      for line in _iter_lines_reversed(jf):
        try:
          logs.append(json.loads(line))
        except json.JSONDecodeError:
          continue
        if len(logs) >= limit:
          return logs
    except OSError:
      continue

  # 2. Backward compatibility: legacy individual JSON files.
  if len(logs) < limit:
    json_files = sorted(LOGS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in json_files:
      try:
        logs.append(json.loads(path.read_text(encoding="utf-8")))
        if len(logs) >= limit:
          break
      except (json.JSONDecodeError, OSError):
        continue

  return logs


def percentile(values: list[float], pct: float) -> float | None:
  """Linear-interpolated percentile (pct in 0..100) or None for no data."""
  data = sorted(v for v in values if isinstance(v, (int, float)))
  if not data:
    return None
  if len(data) == 1:
    return float(data[0])
  rank = (len(data) - 1) * (pct / 100.0)
  low = int(rank)
  high = min(low + 1, len(data) - 1)
  return float(data[low] + (data[high] - data[low]) * (rank - low))


def summarize_logs(logs: list[dict[str, Any]]) -> dict[str, Any]:
  """Aggregate metrics over log entries: tokens, cost, latency percentiles, fallback/cache/error rates."""

  def _num(entry: dict[str, Any], key: str) -> float | None:
    value = entry.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

  total = len(logs)
  prompt_tokens = sum(_num(l, "prompt_tokens") or 0 for l in logs)
  completion_tokens = sum(_num(l, "completion_tokens") or 0 for l in logs)
  cached_tokens = sum(_num(l, "cached_tokens") or 0 for l in logs)
  cost = sum(_num(l, "cost_usd") or 0.0 for l in logs)
  durations = [d for d in (_num(l, "duration_ms") for l in logs) if d]
  ttfts = [t for t in (_num(l, "ttft_ms") for l in logs) if t]
  llm_calls = [l for l in logs if not l.get("refused")]
  fallbacks = sum(1 for l in llm_calls if l.get("fallback_used"))
  errors = sum(1 for l in logs if l.get("error_code"))
  truncated = sum(1 for l in logs if l.get("finish_reason") == "length")
  routes = Counter(str(l.get("route")) for l in logs if l.get("route"))
  # Chat SSE protocol per request: v1 can be retired once it stops appearing here.
  protocols = Counter(str(l.get("protocol")) for l in logs if l.get("protocol"))
  intent_sources = Counter(str(l.get("intent_source")) for l in logs if l.get("intent_source"))

  def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None

  return {
    "total_calls": total,
    "total_prompt_tokens": int(prompt_tokens),
    "total_completion_tokens": int(completion_tokens),
    "total_cached_tokens": int(cached_tokens),
    "total_cost_usd": round(cost, 4),
    "avg_duration_ms": _round(sum(durations) / len(durations)) if durations else 0.0,
    "p50_duration_ms": _round(percentile(durations, 50)),
    "p95_duration_ms": _round(percentile(durations, 95)),
    "p50_ttft_ms": _round(percentile(ttfts, 50)),
    "p95_ttft_ms": _round(percentile(ttfts, 95)),
    "fallback_rate": round(fallbacks / len(llm_calls), 4) if llm_calls else 0.0,
    "cache_hit_rate": round(cached_tokens / prompt_tokens, 4) if prompt_tokens else 0.0,
    "error_rate": round(errors / total, 4) if total else 0.0,
    "truncation_rate": round(truncated / total, 4) if total else 0.0,
    "routes": dict(routes),
    "protocols": dict(protocols),
    "intent_sources": dict(intent_sources),
  }
