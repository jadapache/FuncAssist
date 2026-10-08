from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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


@router.post("/save")
async def save_draft(body: SaveDraftRequest) -> Dict[str, Any]:
  """Save conversation and its artifacts to Documents/QA MGMT/Borradores and index in Generated/_index.json."""
  try:
    saved = save_draft_session(body.model_dump())
    return {"ok": True, "draft": saved, "message": "Borrador guardado exitosamente."}
  except Exception as exc:
    logger.exception(f"Error saving draft session: {exc}")
    raise HTTPException(status_code=500, detail=f"Error guardando borrador: {exc}") from exc


@router.get("/list")
async def list_drafts(specification: Optional[str] = None) -> Dict[str, Any]:
  """List all saved drafts, optionally filtered by specification (Mejoras, Levantamiento, Inventario)."""
  items = list_generated_drafts(specification=specification)
  return {"ok": True, "drafts": items}


@router.get("/{draft_id}")
async def get_draft(draft_id: str) -> Dict[str, Any]:
  """Get detail and chat transcript of a draft."""
  item = get_generated_draft(draft_id)
  if not item:
    raise HTTPException(status_code=404, detail="Borrador no encontrado.")
  return {"ok": True, "draft": item}


@router.delete("/{draft_id}")
async def delete_draft(draft_id: str) -> Dict[str, Any]:
  """Delete a draft session from disk and remove from _index.json."""
  deleted = delete_generated_draft(draft_id)
  if not deleted:
    raise HTTPException(status_code=404, detail="Borrador no encontrado.")
  return {"ok": True, "message": "Borrador eliminado con éxito."}
