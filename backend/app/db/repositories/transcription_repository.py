from __future__ import annotations

import json
from typing import Any, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interfaces.transcription_repository import ITranscriptionRepository
from app.db.models import TranscriptionModel


class TranscriptionRepository(ITranscriptionRepository):
  """PostgreSQL ORM repository for transcriptions with injected AsyncSession."""

  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  async def get(self, transcription_id: str) -> Optional[dict[str, Any]]:
    stmt = select(TranscriptionModel).where(TranscriptionModel.id == transcription_id)
    result = await self.session.execute(stmt)
    row = result.scalar_one_or_none()
    if row:
      return row.to_dict()

    parts = transcription_id.split("-")
    candidate_suffix = parts[-1] if len(parts[-1]) >= 8 else None
    if candidate_suffix:
      stmt2 = select(TranscriptionModel).where(TranscriptionModel.id.startswith(candidate_suffix))
      result2 = await self.session.execute(stmt2)
      row2 = result2.scalar_one_or_none()
      if row2:
        return row2.to_dict()

    all_stmt = select(TranscriptionModel)
    all_res = await self.session.execute(all_stmt)
    for r in all_res.scalars().all():
      d = r.to_dict()
      if d.get("slug") == transcription_id:
        return d
    return None

  async def list(self) -> List[dict[str, Any]]:
    stmt = select(TranscriptionModel).order_by(desc(TranscriptionModel.created_at))
    result = await self.session.execute(stmt)
    items = result.scalars().all()
    return [item.to_dict() for item in items]

  async def upsert(self, record: dict[str, Any]) -> dict[str, Any]:
    tid = record.get("id")
    if not tid:
      raise ValueError("Transcription record must have an 'id'")

    title = record.get("metadata", {}).get("title") or record.get("title") or "Reunión"
    description = record.get("metadata", {}).get("description") or record.get("description") or ""
    orig_filename = record.get("original_filename") or record.get("filename") or ""
    stored_filename = (
      record.get("stored_filename")
      or record.get("media", {}).get("stored_filename")
      or ""
    )
    audio_path = (
      record.get("path")
      or record.get("media", {}).get("path")
      or ""
    )
    dur = float(record.get("duration_seconds", 0.0) or 0.0)
    lang = record.get("language") or "es"
    status = record.get("status") or "completed"
    model_info = record.get("model_info") or "Whisper"
    text = record.get("text") or ""
    segments = record.get("segments") or []
    summary = record.get("summary")
    meta = dict(record.get("metadata") or {})
    if "saved_to_knowledge" in record:
      meta["saved_to_knowledge"] = bool(record["saved_to_knowledge"])
    if "document_id" in record:
      meta["document_id"] = record.get("document_id")

    stmt = select(TranscriptionModel).where(TranscriptionModel.id == tid)
    result = await self.session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
      row = TranscriptionModel(
        id=tid,
        title=title,
        description=description,
        original_filename=orig_filename,
        stored_filename=stored_filename,
        audio_path=audio_path,
        duration_seconds=dur,
        language=lang,
        status=status,
        model_info=model_info,
        text=text,
        segments_json=json.dumps(segments, ensure_ascii=False),
        summary_json=json.dumps(summary, ensure_ascii=False) if summary is not None else None,
        metadata_json=json.dumps(meta, ensure_ascii=False),
      )
      self.session.add(row)
    else:
      row.title = title
      row.description = description
      if orig_filename:
        row.original_filename = orig_filename
      if stored_filename:
        row.stored_filename = stored_filename
      if audio_path:
        row.audio_path = audio_path
      row.duration_seconds = dur
      row.language = lang
      row.status = status
      row.model_info = model_info
      row.text = text
      row.segments_json = json.dumps(segments, ensure_ascii=False)
      row.summary_json = json.dumps(summary, ensure_ascii=False) if summary is not None else None
      row.metadata_json = json.dumps(meta, ensure_ascii=False)

    await self.session.flush()
    if hasattr(self.session, "refresh"):
      res = self.session.refresh(row)
      import inspect
      if inspect.isawaitable(res):
        await res
    return row.to_dict()

  async def delete(self, transcription_id: str) -> bool:
    stmt = select(TranscriptionModel).where(TranscriptionModel.id == transcription_id)
    result = await self.session.execute(stmt)
    row = result.scalar_one_or_none()
    if row:
      await self.session.delete(row)
      await self.session.flush()
      return True
    return False
