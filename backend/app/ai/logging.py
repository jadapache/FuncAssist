"""Local AI call audit log."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.settings import USER_DATA_DIR, ensure_local_dirs

LOGS_DIR = USER_DATA_DIR / "ai" / "logs"


def log_ai_call(entry: dict[str, Any]) -> dict[str, Any]:
  ensure_local_dirs()
  LOGS_DIR.mkdir(parents=True, exist_ok=True)
  payload = {
    "id": str(uuid.uuid4()),
    "created_at": datetime.now(timezone.utc).isoformat(),
    **entry,
  }
  path = LOGS_DIR / f"{payload['id']}.json"
  path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  return payload


def list_logs(limit: int = 20) -> list[dict[str, Any]]:
  ensure_local_dirs()
  LOGS_DIR.mkdir(parents=True, exist_ok=True)
  files = sorted(LOGS_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
  logs: list[dict[str, Any]] = []
  for path in files[:limit]:
    try:
      logs.append(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
      continue
  return logs
