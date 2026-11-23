"""Environment-driven settings for the transcription pipeline (see docs/TRANSCRIPTION_PROCESS.md §8)."""

from __future__ import annotations

import os
from pathlib import Path


def _env_float(name: str, default: float) -> float:
  try:
    return float(os.getenv(name, "") or default)
  except ValueError:
    return default


def _env_int(name: str, default: int) -> int:
  try:
    return int(os.getenv(name, "") or default)
  except ValueError:
    return default


def _env_flag(name: str, default: bool) -> bool:
  raw = (os.getenv(name) or "").strip().lower()
  if not raw:
    return default
  return raw in {"1", "true", "on", "yes"}


def max_upload_bytes() -> int:
  return _env_int("TRANSCRIPTION_MAX_UPLOAD_MB", 2048) * 1024 * 1024


def max_duration_s() -> float:
  return _env_float("TRANSCRIPTION_MAX_DURATION_S", 14_400)


def chunk_seconds() -> float:
  return max(60.0, _env_float("TRANSCRIPTION_CHUNK_S", 600))


def chunk_concurrency(provider: str) -> int:
  default = 2 if provider == "groq" else 4
  return max(1, _env_int("TRANSCRIPTION_CHUNK_CONCURRENCY", default))


def max_concurrent_jobs() -> int:
  return max(1, _env_int("TRANSCRIPTION_MAX_CONCURRENT_JOBS", 2))


def num_retries() -> int:
  return max(0, _env_int("TRANSCRIPTION_NUM_RETRIES", 3))


def request_timeout_s() -> float:
  return _env_float("TRANSCRIPTION_TIMEOUT_S", 300)


def hallucination_filter_enabled() -> bool:
  return _env_flag("TRANSCRIPTION_HALLUCINATION_FILTER", True)


def trim_silence_enabled() -> bool:
  return _env_flag("TRANSCRIPTION_TRIM_SILENCE", True)


def min_silence_s() -> float:
  return max(0.5, _env_float("TRANSCRIPTION_MIN_SILENCE_S", 2.0))


def turn_gap_s() -> float:
  return max(0.0, _env_float("TRANSCRIPTION_TURN_GAP_S", 8.0))


def default_cleanup_mode() -> str:
  mode = (os.getenv("TRANSCRIPTION_CLEANUP") or "rules").strip().lower()
  return mode if mode in {"off", "rules", "llm"} else "rules"


def diarize_model() -> str:
  return (os.getenv("TRANSCRIPTION_DIARIZE_MODEL") or "gpt-4o-transcribe-diarize").strip()


def desktop_mode() -> bool:
  return _env_flag("TRANSCRIPTION_DESKTOP_MODE", False)


def local_roots() -> list[Path]:
  raw = os.getenv("TRANSCRIPTION_LOCAL_ROOTS") or ""
  parts = [p.strip() for p in raw.replace(";", ",").split(",")]
  return [Path(p).resolve() for p in parts if p]


def media_ttl_days() -> int | None:
  value = _env_int("TRANSCRIPTION_MEDIA_TTL_DAYS", 0)
  return value if value > 0 else None
