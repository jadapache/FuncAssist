from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, ConfigDict

from app.ai.logging import list_logs
from app.ai.templates import (
    get_prompt,
    get_rubric,
    list_prompts,
    list_rubrics,
    reset_prompt,
    reset_rubric,
    save_prompt,
    save_rubric,
)

router = APIRouter(prefix="/ai", tags=["ai-templates"])


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
    system: str | None = None
    user_template: str | None = None
    allowed_sources: list[str] | None = None


class RubricUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
    criteria: list[str]


@router.get("/prompts")
async def prompts() -> dict[str, Any]:
    return {"prompts": list_prompts()}


@router.get("/prompts/{feature}")
async def prompt_detail(feature: str) -> dict[str, Any]:
    try:
        return get_prompt(feature)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/prompts/{feature}")
async def update_prompt(feature: str, body: TemplateUpdate = Body(...)) -> dict[str, Any]:
    try:
        return save_prompt(feature, body.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/prompts/{feature}/reset")
async def reset_prompt_endpoint(feature: str) -> dict[str, Any]:
    try:
        return reset_prompt(feature)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/rubrics")
async def rubrics() -> dict[str, Any]:
    return {"rubrics": list_rubrics()}


@router.get("/rubrics/{feature}")
async def rubric_detail(feature: str) -> dict[str, Any]:
    try:
        return get_rubric(feature)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/rubrics/{feature}")
async def update_rubric(feature: str, body: RubricUpdate = Body(...)) -> dict[str, Any]:
    try:
        return save_rubric(feature, body.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/rubrics/{feature}/reset")
async def reset_rubric_endpoint(feature: str) -> dict[str, Any]:
    try:
        return reset_rubric(feature)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/logs")
async def ai_logs(limit: int = 20) -> dict[str, Any]:
    return {"logs": list_logs(limit=limit)}
