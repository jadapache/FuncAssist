import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.ai.logging import list_logs
from app.ai.templates import (
    get_prompt,
    get_rubric,
    get_template_history,
    list_prompts,
    list_rubrics,
    reset_prompt,
    reset_rubric,
    save_prompt,
    save_rubric,
)
from app.api.middleware.error_handlers import handle_grounded_errors


router = APIRouter(prefix="/ai", tags=["ai-templates"])



class TemplateUpdate(BaseModel):

    model_config = ConfigDict(extra="allow")

    system: str | None = None

    user_template: str | None = None

    allowed_sources: list[str] | None = None

    change_summary: str | None = None

    updated_by: str | None = None



class RubricUpdate(BaseModel):

    model_config = ConfigDict(extra="allow")

    criteria: list[str]

    change_summary: str | None = None

    updated_by: str | None = None



@router.get("/prompts")
@handle_grounded_errors
async def prompts() -> dict[str, Any]:
    return {"prompts": await list_prompts()}



@router.get("/prompts/{feature}")

@handle_grounded_errors

async def prompt_detail(feature: str) -> dict[str, Any]:
    try:

        return await get_prompt(feature)

    except KeyError as exc:

        raise HTTPException(status_code=404, detail=str(exc)) from exc



@router.get("/prompts/{feature}/history")

@handle_grounded_errors

async def prompt_history(feature: str, limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:

    return {"history": await get_template_history("prompt", feature, limit=limit)}



@router.put("/prompts/{feature}")

@handle_grounded_errors

async def update_prompt(feature: str, body: TemplateUpdate = Body(...)) -> dict[str, Any]:
    try:

        dump = body.model_dump(exclude_none=True)

        change_summary = dump.pop("change_summary", None)

        updated_by = dump.pop("updated_by", None)

        return await save_prompt(
            feature,
            dump,

            updated_by=updated_by,

            change_summary=change_summary,
        )

    except KeyError as exc:

        raise HTTPException(status_code=404, detail=str(exc)) from exc



@router.post("/prompts/{feature}/reset")

@handle_grounded_errors

async def reset_prompt_endpoint(feature: str) -> dict[str, Any]:
    try:

        return await reset_prompt(feature)

    except KeyError as exc:

        raise HTTPException(status_code=404, detail=str(exc)) from exc



@router.get("/rubrics")

@handle_grounded_errors

async def rubrics() -> dict[str, Any]:

    return {"rubrics": await list_rubrics()}



@router.get("/rubrics/{feature}")

@handle_grounded_errors

async def rubric_detail(feature: str) -> dict[str, Any]:
    try:

        return await get_rubric(feature)

    except KeyError as exc:

        raise HTTPException(status_code=404, detail=str(exc)) from exc



@router.get("/rubrics/{feature}/history")

@handle_grounded_errors

async def rubric_history(feature: str, limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:

    return {"history": await get_template_history("rubric", feature, limit=limit)}



@router.put("/rubrics/{feature}")

@handle_grounded_errors

async def update_rubric(feature: str, body: RubricUpdate = Body(...)) -> dict[str, Any]:
    try:

        dump = body.model_dump(exclude_none=True)

        change_summary = dump.pop("change_summary", None)

        updated_by = dump.pop("updated_by", None)

        return await save_rubric(
            feature,
            dump,

            updated_by=updated_by,

            change_summary=change_summary,
        )

    except KeyError as exc:

        raise HTTPException(status_code=404, detail=str(exc)) from exc



@router.post("/rubrics/{feature}/reset")

@handle_grounded_errors

async def reset_rubric_endpoint(feature: str) -> dict[str, Any]:
    try:

        return await reset_rubric(feature)

    except KeyError as exc:

        raise HTTPException(status_code=404, detail=str(exc)) from exc



@router.get("/logs")
@handle_grounded_errors
async def ai_logs(limit: int = 20) -> dict[str, Any]:
    logs = await asyncio.to_thread(list_logs, limit=limit)
    return {"logs": logs}

