"""Local AI call audit log supporting high-performance daily JSONL and metric tracking."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.settings import USER_DATA_DIR, ensure_local_dirs

LOGS_DIR = USER_DATA_DIR / "ai" / "logs"


def _get_daily_log_path(dt: datetime | None = None) -> Path:
  ensure_local_dirs()
  LOGS_DIR.mkdir(parents=True, exist_ok=True)
  date_str = (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
  return LOGS_DIR / f"{date_str}.jsonl"


def _write_log_entry(payload: dict[str, Any]) -> None:
  path = _get_daily_log_path()
  with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def log_ai_call(entry: dict[str, Any]) -> dict[str, Any]:
  """Audit log entry append to daily JSONL."""
  payload = {
    "id": str(uuid.uuid4()),
    "created_at": datetime.now(timezone.utc).isoformat(),
    **entry,
  }
  try:
    loop = asyncio.get_running_loop()
    loop.create_task(asyncio.to_thread(_write_log_entry, payload))
  except RuntimeError:
    _write_log_entry(payload)
  return payload


def list_logs(limit: int = 20) -> list[dict[str, Any]]:
  """Read latest logs backwards from JSONL and fallback to legacy JSON files."""
  ensure_local_dirs()
  LOGS_DIR.mkdir(parents=True, exist_ok=True)
  logs: list[dict[str, Any]] = []

  # 1. Read JSONL daily files in reverse chronological order
  jsonl_files = sorted(LOGS_DIR.glob("*.jsonl"), reverse=True)
  for jf in jsonl_files:
    try:
      lines = jf.read_text(encoding="utf-8").strip().splitlines()
      for line in reversed(lines):
        if not line.strip():
          continue
        try:
          logs.append(json.loads(line))
          if len(logs) >= limit:
            return logs
        except json.JSONDecodeError:
          continue
    except OSError:
      continue

  # 2. Backward compatibility: if needed, read legacy individual JSON files
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
