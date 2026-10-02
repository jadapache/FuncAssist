from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.template_storage import (
    delete_template,
    get_template_detail,
    list_templates,
    save_template_file,
    update_template_metadata,
)

router = APIRouter(prefix="/templates", tags=["templates"])


class TemplateMetadataUpdate(BaseModel):
    title: str | None = None
    module: str | None = None
    tags: list[str] | None = None
    content: str | None = None


@router.get("")
async def get_templates() -> dict[str, Any]:
    return {"templates": list_templates()}


@router.get("/{template_id}/content")
async def get_template_content_route(template_id: str) -> dict[str, Any]:
    detail = get_template_detail(template_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return detail


@router.post("/upload")
async def upload_template(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    module: str = Form(default="general"),
) -> dict[str, Any]:
    content = await file.read()
    item = save_template_file(
        filename=file.filename or "template",
        file_bytes=content,
        title=title,
        module=module,
    )
    return {"template": item}


@router.put("/{template_id}")
async def edit_template(template_id: str, body: TemplateMetadataUpdate = Body(...)) -> dict[str, Any]:
    updated = update_template_metadata(
        template_id,
        title=body.title,
        module=body.module,
        tags=body.tags,
        content=body.content,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return {"template": updated}


@router.delete("/{template_id}")
async def remove_template(template_id: str) -> dict[str, Any]:
    success = delete_template(template_id)
    if not success:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return {"ok": True, "template_id": template_id}
