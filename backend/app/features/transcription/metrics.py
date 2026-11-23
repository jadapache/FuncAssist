"""Per-job transcription metrics: one JSON line per finished job, aggregated by `/transcription/stats`."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.core.settings import USER_DATA_DIR

logger = logging.getLogger(__name__)

LOG_DIR = USER_DATA_DIR / "transcription" / "logs"


def _log_path(now: datetime) -> Path:
  return LOG_DIR / f"{now:%Y-%m-%d}.jsonl"


def _append(path: Path, line: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a", encoding="utf-8") as fh:
    fh.write(line + "\n")


async def log_job(entry: dict[str, Any]) -> None:
  now = datetime.now(timezone.utc)
  payload = {"timestamp": now.isoformat(), **entry}
  audio_s = float(payload.get("audio_s") or 0.0)
  total_ms = sum((payload.get("stage_ms") or {}).values())
  if audio_s > 0 and total_ms:
    payload["rtf"] = round(total_ms / 1000 / audio_s, 4)
  try:
    await asyncio.to_thread(_append, _log_path(now), json.dumps(payload, ensure_ascii=False, default=str))
  except OSError as exc:
    logger.warning("Could not write transcription metrics: %s", exc)


def read_entries(limit: int = 500) -> list[dict[str, Any]]:
  """Newest entries first, across daily files."""
  if not LOG_DIR.exists():
    return []
  entries: list[dict[str, Any]] = []
  for path in sorted(LOG_DIR.glob("*.jsonl"), reverse=True):
    try:
      lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
      continue
    for line in reversed(lines):
      if not line.strip():
        continue
      try:
        entries.append(json.loads(line))
      except ValueError:
        continue
      if len(entries) >= limit:
        return entries
  return entries


def _percentile(values: list[float], pct: float) -> float | None:
  if not values:
    return None
  ordered = sorted(values)
  k = (len(ordered) - 1) * pct / 100
  lower = int(k)
  upper = min(lower + 1, len(ordered) - 1)
  return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower), 4)


def summarize(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
  items = list(entries)
  by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for item in items:
    by_provider[str(item.get("provider") or "unknown")].append(item)

  def _block(group: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [g for g in group if g.get("status") == "complete"]
    rtf = [float(g["rtf"]) for g in ok if g.get("rtf") is not None]
    return {
      "jobs": len(group),
      "completed": len(ok),
      "failed": sum(1 for g in group if g.get("status") == "failed"),
      "cancelled": sum(1 for g in group if g.get("status") == "cancelled"),
      "audio_hours": round(sum(float(g.get("audio_s") or 0) for g in ok) / 3600, 2),
      "silence_trimmed_hours": round(sum(float(g.get("silence_trimmed_s") or 0) for g in ok) / 3600, 2),
      "rtf_p50": _percentile(rtf, 50),
      "rtf_p95": _percentile(rtf, 95),
      "retries": sum(int(g.get("retries") or 0) for g in group),
      "fillers_removed": sum(int(g.get("fillers_removed") or 0) for g in ok),
      "hallucinations_removed": sum(int(g.get("hallucinations_removed") or 0) for g in ok),
      "cost_estimate": round(sum(float(g.get("cost_estimate") or 0) for g in ok), 4),
    }

  errors: dict[str, int] = defaultdict(int)
  for item in items:
    if item.get("error_code"):
      errors[str(item["error_code"])] += 1
  return {
    "total": _block(items),
    "providers": {name: _block(group) for name, group in by_provider.items()},
    "error_codes": dict(errors),
  }
