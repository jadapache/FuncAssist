"""Async persistence of transcription records (one short session per call, never blocking the loop)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional, TypeVar

from app.db.database import get_db
from app.db.repositories.transcription_repository import TranscriptionRepository
from app.features.transcription import storage
from app.features.transcription.segments import normalize_record

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def _run(fn: Callable[[TranscriptionRepository], Awaitable[T]]) -> T:
  async with get_db() as db:
    return await fn(TranscriptionRepository(db))


def _finish(record: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
  if record is None:
    return None
  normalize_record(record)
  record["has_media"] = storage.has_media(record["id"], record)
  meta = record.setdefault("metadata", {})
  media = record.get("media") or {}
  if not meta.get("size_bytes") and media.get("size_bytes"):
    meta["size_bytes"] = media["size_bytes"]
    meta["file_size_formatted"] = storage.format_size_bytes(int(media["size_bytes"]))
  return record


def can_access(record: dict[str, Any], user: Optional[dict[str, Any]]) -> bool:
  """Owner only, administrators included. Ownerless legacy records are visible to nobody until
  assigned with `scripts.assign_transcriptions_owner`."""
  if not user:
    return False
  owner = record.get("user_id")
  return owner is not None and str(owner) == str(user.get("id"))


async def get_record(transcription_id: str) -> Optional[dict[str, Any]]:
  return _finish(await _run(lambda repo: repo.get(transcription_id)))


async def save_record(record: dict[str, Any]) -> dict[str, Any]:
  saved = await _run(lambda repo: repo.upsert(record))
  return _finish(saved) or saved


async def update_record(transcription_id: str, mutate: Callable[[dict[str, Any]], Any]) -> Optional[dict[str, Any]]:
  """Read-modify-write in one session. `mutate` edits the normalized record in place."""

  async def _apply(repo: TranscriptionRepository) -> Optional[dict[str, Any]]:
    current = await repo.get(transcription_id)
    if current is None:
      return None
    normalize_record(current)
    mutate(current)
    current.pop("has_media", None)
    return await repo.upsert(current)

  return _finish(await _run(_apply))


async def list_records(user: dict[str, Any]) -> list[dict[str, Any]]:
  items = await _run(lambda repo: repo.list(user_id=str(user.get("id"))))
  return [r for r in (_finish(item) for item in items) if r is not None]


async def list_by_status(statuses: Iterable[str], user_id: Optional[str] = None) -> list[dict[str, Any]]:
  wanted = list(statuses)
  return await _run(lambda repo: repo.list_by_status(wanted, user_id=user_id))


async def delete_record(transcription_id: str) -> bool:
  storage.delete_folder(transcription_id)
  return await _run(lambda repo: repo.delete(transcription_id))


async def save_progress(transcription_id: str, snapshot: dict[str, Any], *, started: bool = False, finished: bool = False) -> None:
  now = datetime.now(timezone.utc)
  await _run(
    lambda repo: repo.update_progress(
      transcription_id,
      snapshot,
      started_at=now if started else None,
      finished_at=now if finished else None,
    )
  )


async def assign_owner(user_id: str, only_unowned: bool = True) -> int:
  return await _run(lambda repo: repo.assign_owner(user_id, only_unowned))
