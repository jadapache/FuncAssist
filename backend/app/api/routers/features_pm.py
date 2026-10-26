from typing import Any, List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from app.ai.runner import run_grounded_feature
from app.api.deps import (
    get_chat_repository,
    get_optional_current_user,
    get_prd_repository,
    get_standup_repository,
)
from app.api.middleware.error_handlers import handle_grounded_errors
from app.db.repositories import ChatRepository, PRDRepository, StandupRepository
from app.features.change_impact.service import analyze_change_impact
from app.features.prd_checker.service import review_prd
from app.features.standup.service import generate_standup

router = APIRouter(prefix="/features", tags=["pm-features"])


class GroundedRequest(BaseModel):
    query: str = "Generate standup from recent work."
    sources: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None
    chat_context: Optional[str] = None


class FeatureWorkspaceRequest(BaseModel):
    query: str = Field(min_length=1)
    sources: Optional[List[str]] = None
    document_ids: List[str] = Field(default_factory=list)
    chat_context: Optional[str] = None


@router.post("/standup")
@handle_grounded_errors
async def standup(
    body: GroundedRequest = Body(default_factory=GroundedRequest),
    standup_repo: StandupRepository = Depends(get_standup_repository),
    current_user: Optional[dict[str, Any]] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    user_id = current_user.get("id") if current_user else None
    res = await generate_standup(body.query, user_id=user_id)
    if isinstance(res, dict) and "markdown" in res:
        await standup_repo.create_standup(
            title=f"Standup {res.get('date', '')}".strip(),
            content=res["markdown"],
            sources=body.sources or [],
            user_id=user_id,
        )
    return res


@router.post("/ask")
@handle_grounded_errors
async def ask_product(
    body: GroundedRequest = Body(...),
    chat_repo: ChatRepository = Depends(get_chat_repository),
    current_user: Optional[dict[str, Any]] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query is required.")
    user_id = current_user.get("id") if current_user else None
    res = await run_grounded_feature(
        feature="ask_product",
        query=body.query,
        sources=body.sources,
        document_ids=body.document_ids,
        chat_context=body.chat_context,
        user_id=user_id,
    )
    if isinstance(res, dict) and "markdown" in res:
        session_id = f"user_{user_id}_default" if user_id else "default"
        await chat_repo.save_message(
            session_id=session_id,
            role="user",
            content=body.query,
            user_id=user_id,
        )
        await chat_repo.save_message(
            session_id=session_id,
            role="assistant",
            content=res["markdown"],
            context_sources=res.get("context_sources") or [],
            user_id=user_id,
        )
    return res


@router.post("/prd-checker")
@handle_grounded_errors
async def prd_checker(
    body: FeatureWorkspaceRequest = Body(...),
    prd_repo: PRDRepository = Depends(get_prd_repository),
    current_user: Optional[dict[str, Any]] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    if not body.document_ids:
        raise HTTPException(status_code=400, detail="Upload at least one PRD or spec file.")
    user_id = current_user.get("id") if current_user else None
    res = await review_prd(
        query=body.query,
        document_ids=body.document_ids,
        sources=body.sources,
        chat_context=body.chat_context,
        user_id=user_id,
    )
    if isinstance(res, dict) and "markdown" in res:
        await prd_repo.create_prd_review(
            prd_title="Auditoría PRD",
            content=res["markdown"],
            user_id=user_id,
        )
    return res


@router.post("/change-impact")
@handle_grounded_errors
async def change_impact(
    body: FeatureWorkspaceRequest = Body(...),
    current_user: Optional[dict[str, Any]] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    sources = body.sources or []
    if not body.document_ids and not sources:
        raise HTTPException(
            status_code=400,
            detail="Upload files and/or enable live sources (Jira, GitHub, GitLab).",
        )
    user_id = current_user.get("id") if current_user else None
    return await analyze_change_impact(
        query=body.query,
        sources=body.sources,
        document_ids=body.document_ids,
        chat_context=body.chat_context,
        user_id=user_id,
    )
