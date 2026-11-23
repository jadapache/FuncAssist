from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interfaces.transcription_repository import ITranscriptionRepository
from app.db.models import TRANSCRIPTION_RECORD_META_KEYS, TranscriptionModel


def _parse_dt(value: Any) -> Optional[datetime]:
  if isinstance(value, datetime):
    return value
  if isinstance(value, str) and value:
    try:
      return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
      return None
  return None


class TranscriptionRepository(ITranscriptionRepository):
  """PostgreSQL ORM repository for transcriptions with injected AsyncSession."""

  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  async def _row(self, transcription_id: str) -> Optional[TranscriptionModel]:
    result = await self.session.execute(select(TranscriptionModel).where(TranscriptionModel.id == transcription_id))
    return result.scalar_one_or_none()

  async def get(self, transcription_id: str) -> Optional[dict[str, Any]]:
    row = await self._row(transcription_id)
    if row:
      return row.to_dict()
    # Slugs end with the first 8 characters of the id ("titulo-reunion-1a2b3c4d").
    suffix = transcription_id.rsplit("-", 1)[-1]
    if len(suffix) >= 8 and suffix != transcription_id:
      result = await self.session.execute(select(TranscriptionModel).where(TranscriptionModel.id.startswith(suffix)))
      for candidate in result.scalars().all():
        data = candidate.to_dict()
        if data.get("slug") == transcription_id or candidate.id.startswith(suffix):
          return data
    return None

  async def list(self, user_id: Optional[str] = None) -> List[dict[str, Any]]:
    """Records owned by `user_id`, newest first. Without a user, every record (maintenance scripts only)."""
    stmt = select(TranscriptionModel).order_by(desc(TranscriptionModel.created_at))
    if user_id is not None:
      stmt = stmt.where(TranscriptionModel.user_id == user_id)
    result = await self.session.execute(stmt)
    return [item.to_dict() for item in result.scalars().all()]

  async def list_by_status(self, statuses: Iterable[str], user_id: Optional[str] = None) -> List[dict[str, Any]]:
    wanted = set(statuses)
    stmt = select(TranscriptionModel)
    if user_id is not None:
      stmt = stmt.where(TranscriptionModel.user_id == user_id)
    else:
      stmt = stmt.where(TranscriptionModel.status.in_(sorted(wanted)))
    result = await self.session.execute(stmt)
    return [row.to_dict() for row in result.scalars().all() if row.status in wanted]

  async def upsert(self, record: dict[str, Any]) -> dict[str, Any]:
    tid = record.get("id")
    if not tid:
      raise ValueError("Transcription record must have an 'id'")

    metadata = dict(record.get("metadata") or {})
    title = metadata.get("title") or record.get("title") or "Reunión"
    description = metadata.get("description") or record.get("description") or ""
    media = record.get("media") if isinstance(record.get("media"), dict) else None
    orig_filename = record.get("original_filename") or record.get("filename") or (media or {}).get("original_filename") or ""
    stored_filename = record.get("stored_filename") or (media or {}).get("stored_filename") or ""
    audio_path = record.get("path") or (media or {}).get("path") or ""

    meta = {k: v for k, v in metadata.items() if k not in TRANSCRIPTION_RECORD_META_KEYS and k not in {"title", "description"}}
    for key in TRANSCRIPTION_RECORD_META_KEYS:
      if key in record:
        meta[key] = record[key]
    if media:
      meta["media"] = {k: v for k, v in media.items() if k not in {"id", "transcription_id"}}
    if "saved_to_knowledge" in record:
      meta["saved_to_knowledge"] = bool(record["saved_to_knowledge"])
    if "document_id" in record:
      meta["document_id"] = record.get("document_id")

    row = await self._row(tid)
    if row is None:
      row = TranscriptionModel(id=tid)
      self.session.add(row)
    row.title = title
    row.description = description
    if orig_filename:
      row.original_filename = orig_filename
    if stored_filename:
      row.stored_filename = stored_filename
    if audio_path:
      row.audio_path = audio_path
    row.duration_seconds = float(record.get("duration_seconds", 0.0) or 0.0)
    row.language = record.get("language") or "es"
    row.status = record.get("status") or "complete"
    row.model_info = record.get("model_info") or "Whisper"
    row.text = record.get("text") or ""
    row.segments_json = json.dumps(record.get("segments") or [], ensure_ascii=False)
    summary = record.get("summary")
    row.summary_json = json.dumps(summary, ensure_ascii=False) if summary is not None else None
    row.metadata_json = json.dumps(meta, ensure_ascii=False)
    if record.get("user_id"):
      row.user_id = str(record["user_id"])
    if "progress" in record:
      row.progress_json = json.dumps(record["progress"], ensure_ascii=False) if record["progress"] is not None else None
    if "error_code" in record:
      row.error_code = record.get("error_code")
    if record.get("started_at"):
      row.started_at = _parse_dt(record["started_at"])
    if "finished_at" in record:
      row.finished_at = _parse_dt(record.get("finished_at"))

    await self.session.flush()
    return row.to_dict()

  async def update_progress(
    self,
    transcription_id: str,
    snapshot: dict[str, Any],
    *,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
  ) -> bool:
    """Write only the job columns; the transcript payload is untouched."""
    row = await self._row(transcription_id)
    if row is None:
      return False
    row.progress_json = json.dumps(snapshot, ensure_ascii=False)
    row.status = str(snapshot.get("stage") or row.status)
    row.error_code = snapshot.get("error_code")
    if started_at is not None and row.started_at is None:
      row.started_at = started_at
    if finished_at is not None:
      row.finished_at = finished_at
    await self.session.flush()
    return True

  async def assign_owner(self, user_id: str, only_unowned: bool = True) -> int:
    stmt = select(TranscriptionModel)
    if only_unowned:
      stmt = stmt.where(TranscriptionModel.user_id.is_(None))
    rows = (await self.session.execute(stmt)).scalars().all()
    for row in rows:
      row.user_id = user_id
    await self.session.flush()
    return len(rows)

  async def delete(self, transcription_id: str) -> bool:
    row = await self._row(transcription_id)
    if row:
      await self.session.delete(row)
      await self.session.flush()
      return True
    return False
