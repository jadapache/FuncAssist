from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_chat_repository, get_current_user
from app.db.repositories import ChatRepository
from app.features.drafts.storage import (
  delete_generated_draft,
  get_generated_draft,
  list_generated_drafts,
  save_draft_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drafts", tags=["drafts"])


class SaveDraftRequest(BaseModel):
  id: Optional[str] = None
  name: Optional[str] = None
  title: Optional[str] = None
  specification: Optional[str] = None
  feature_slug: Optional[str] = None
  lastInteraction: Optional[str] = None
  messages: List[Dict[str, Any]] = Field(default_factory=list)
  documentContent: Optional[str] = ""
  artifacts: List[Dict[str, Any]] = Field(default_factory=list)
  activeArtifactId: Optional[str] = None


@router.post("/save")
async def save_draft(
  body: SaveDraftRequest,
  current_user: Dict[str, Any] = Depends(get_current_user),
  chat_repo: ChatRepository = Depends(get_chat_repository),
) -> Dict[str, Any]:
  """Save conversation and its artifacts to PostgreSQL entity and Documents/QA MGMT/Borradores."""
  try:
    payload = body.model_dump()
    user_id = current_user["id"]
    payload["user_id"] = user_id

    # 1. Save session and artifacts to PostgreSQL
    await chat_repo.save_session(payload)

    # 2. Save individual messages to PostgreSQL chat_messages
    for msg in body.messages:
      content = msg.get("content", "").strip()
      if content:
        await chat_repo.save_message(
          session_id=payload.get("id") or "default",
          role=msg.get("role", "user"),
          content=content,
          context_sources=msg.get("context_sources"),
          attachments=msg.get("attachments"),
          user_id=user_id,
        )

    # 3. Persist file-based draft backup
    saved = save_draft_session(payload)
    return {"ok": True, "draft": saved, "message": "Borrador guardado exitosamente."}
  except Exception as exc:
    logger.exception(f"Error saving draft session: {exc}")
    raise HTTPException(status_code=500, detail=f"Error guardando borrador: {exc}") from exc


@router.get("/list")
async def list_drafts(
  specification: Optional[str] = None,
  current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
  """List all saved drafts filtered by user and optionally specification."""
  user_id = current_user["id"]
  items = list_generated_drafts(specification=specification, user_id=user_id)
  return {"ok": True, "drafts": items}


@router.get("/{draft_id}")
async def get_draft(draft_id: str) -> Dict[str, Any]:
  """Get detail and chat transcript of a draft."""
  item = get_generated_draft(draft_id)
  if not item:
    raise HTTPException(status_code=404, detail="Borrador no encontrado.")
  return {"ok": True, "draft": item}


@router.delete("/{draft_id}")
async def delete_draft(
  draft_id: str,
  current_user: Dict[str, Any] = Depends(get_current_user),
  chat_repo: ChatRepository = Depends(get_chat_repository),
) -> Dict[str, Any]:
  """Delete a draft session from database and disk."""
  user_id = current_user["id"]
  await chat_repo.delete_session(draft_id, user_id=user_id)
  deleted = delete_generated_draft(draft_id)
  return {"ok": True, "message": "Borrador eliminado con éxito."}
