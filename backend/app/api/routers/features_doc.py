from typing import Any, List, Optional
from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.ai.runner import run_grounded_feature
from app.api.middleware.error_handlers import handle_grounded_errors

router = APIRouter(prefix="/features", tags=["doc-features"])


class FeatureWorkspaceRequest(BaseModel):
    query: str = Field(min_length=1)
    sources: Optional[List[str]] = None
    document_ids: List[str] = Field(default_factory=list)
    chat_context: Optional[str] = None


@router.post("/mejoras")
@handle_grounded_errors
async def mejoras_doc(body: FeatureWorkspaceRequest = Body(...)) -> dict[str, Any]:
    return await run_grounded_feature(
        feature="mejoras_doc",
        query=body.query,
        sources=body.sources or ["jira", "github", "gitlab", "knowledge"],
        document_ids=body.document_ids,
        chat_context=body.chat_context,
    )


@router.post("/inventario")
@handle_grounded_errors
async def inventario_doc_endpoint(body: FeatureWorkspaceRequest = Body(...)) -> dict[str, Any]:
    return await run_grounded_feature(
        feature="inventario_doc",
        query=body.query,
        sources=body.sources or ["knowledge", "jira", "github"],
        document_ids=body.document_ids,
        chat_context=body.chat_context,
    )


@router.post("/levantamiento")
@handle_grounded_errors
async def levantamiento_doc_endpoint(body: FeatureWorkspaceRequest = Body(...)) -> dict[str, Any]:
    return await run_grounded_feature(
        feature="levantamiento_doc",
        query=body.query,
        sources=body.sources or ["knowledge", "jira", "github"],
        document_ids=body.document_ids,
        chat_context=body.chat_context,
    )
