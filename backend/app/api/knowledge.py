from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.context.knowledge import (
  delete_document,
  get_knowledge_base_dir,
  ingest_document,
  list_documents,
)
from app.context.knowledge_migration import (
  export_to_json,
  rebuild_fts_index,
  verify_integrity,
)
from app.context.service import assemble_context
from app.core.storage import load_app_settings, save_app_settings

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class RetrieveRequest(BaseModel):
  query: str = Field(min_length=1)
  sources: list[str] = Field(default_factory=lambda: ["knowledge"])
  top_k: int = 8


class KnowledgeBasePathRequest(BaseModel):
  path: str  # empty string = revert to local default


@router.get("/documents")
async def get_documents() -> dict[str, Any]:
  return {"documents": list_documents()}


@router.post("/documents")
async def upload_document(
  file: UploadFile = File(...),
  tags: str = Form(default=""),
) -> dict[str, Any]:
  raw = await file.read()
  if not raw:
    raise HTTPException(status_code=400, detail="Empty file")
  tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
  try:
    entry = ingest_document(filename=file.filename or "upload.txt", raw=raw, tags=tag_list)
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  return {"document": entry}


@router.post("/documents/batch")
async def upload_documents_batch(
  files: list[UploadFile] = File(...),
  tags: str = Form(default=""),
) -> dict[str, Any]:
  if not files:
    raise HTTPException(status_code=400, detail="At least one file is required.")
  tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
  uploaded: list[dict[str, Any]] = []
  errors: list[str] = []
  for file in files:
    raw = await file.read()
    if not raw:
      errors.append(f"{file.filename or 'file'}: empty")
      continue
    try:
      entry = ingest_document(filename=file.filename or "upload.txt", raw=raw, tags=tag_list)
      uploaded.append(entry)
    except ValueError as exc:
      errors.append(f"{file.filename or 'file'}: {exc}")
  if not uploaded:
    raise HTTPException(status_code=400, detail="; ".join(errors) or "Upload failed")
  return {"documents": uploaded, "errors": errors}


@router.delete("/documents/{document_id}")
async def remove_document(document_id: str) -> dict[str, Any]:
  ok = delete_document(document_id)
  if not ok:
    raise HTTPException(status_code=404, detail="Document not found")
  return {"ok": True}


@router.post("/retrieve")
async def retrieve(body: RetrieveRequest) -> dict[str, Any]:
  bundle = await assemble_context(query=body.query, sources=body.sources, top_k=body.top_k)
  return bundle.model_dump()


# ---------------------------------------------------------------------------
# Path Configuration Endpoints
# ---------------------------------------------------------------------------


@router.get("/path")
async def get_knowledge_path() -> dict[str, Any]:
  settings = load_app_settings()
  current_path = settings.get("knowledge_base_path", "")
  resolved = str(get_knowledge_base_dir())
  return {
    "configured_path": current_path,
    "resolved_path": resolved,
    "is_custom": bool(current_path.strip()),
    "is_accessible": Path(resolved).exists() if current_path else True,
  }


@router.put("/path")
async def set_knowledge_path(body: KnowledgeBasePathRequest) -> dict[str, Any]:
  new_path = body.path.strip()

  if new_path:
    p = Path(new_path)
    if not p.exists():
      try:
        p.mkdir(parents=True, exist_ok=True)
      except Exception as exc:
        raise HTTPException(
          status_code=400,
          detail=f"Cannot access or create path '{new_path}': {exc}",
        ) from exc

  settings = load_app_settings()
  settings["knowledge_base_path"] = new_path
  save_app_settings(settings)

  resolved = str(get_knowledge_base_dir())
  return {
    "ok": True,
    "configured_path": new_path,
    "resolved_path": resolved,
    "is_custom": bool(new_path),
    "is_accessible": Path(resolved).exists() if new_path else True,
  }


# ---------------------------------------------------------------------------
# Admin / Recovery Endpoints
# ---------------------------------------------------------------------------


@router.get("/admin/integrity")
async def check_integrity() -> dict[str, Any]:
  """Run SQLite + FTS5 integrity checks. Safe to call at any time."""
  return verify_integrity()


@router.post("/admin/rebuild-index")
async def rebuild_index() -> dict[str, Any]:
  """Rebuild the FTS5 inverted index. Use after detecting search anomalies."""
  count = rebuild_fts_index()
  return {"ok": True, "chunks_reindexed": count}


@router.post("/admin/export-json")
async def export_json_backup() -> dict[str, Any]:
  """Export knowledge.db to manifest.export.json + chunks.export.json for backup."""
  manifest_path, chunks_path = export_to_json()
  return {
    "ok": True,
    "manifest_path": str(manifest_path),
    "chunks_path": str(chunks_path),
  }
