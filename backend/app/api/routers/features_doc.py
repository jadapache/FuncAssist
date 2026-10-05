from typing import Any, List, Optional
from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.api.middleware.error_handlers import handle_grounded_errors
from app.features.inventario.service import generate_inventario_report
from app.features.levantamiento.service import generate_levantamiento_report
from app.features.mejoras.service import generate_mejoras_report

router = APIRouter(prefix="/features", tags=["doc-features"])


class FeatureWorkspaceRequest(BaseModel):
    query: str = Field(min_length=1)
    sources: Optional[List[str]] = None
    document_ids: List[str] = Field(default_factory=list)
    chat_context: Optional[str] = None


@router.post("/mejoras")
@handle_grounded_errors
async def mejoras_doc(body: FeatureWorkspaceRequest = Body(...)) -> dict[str, Any]:
    return await generate_mejoras_report(
        query=body.query,
        sources=body.sources,
        document_ids=body.document_ids,
        chat_context=body.chat_context,
    )


@router.post("/inventario")
@handle_grounded_errors
async def inventario_doc_endpoint(body: FeatureWorkspaceRequest = Body(...)) -> dict[str, Any]:
    return await generate_inventario_report(
        query=body.query,
        sources=body.sources,
        document_ids=body.document_ids,
        chat_context=body.chat_context,
    )


@router.post("/levantamiento")
@handle_grounded_errors
async def levantamiento_doc_endpoint(body: FeatureWorkspaceRequest = Body(...)) -> dict[str, Any]:
    return await generate_levantamiento_report(
        query=body.query,
        sources=body.sources,
        document_ids=body.document_ids,
        chat_context=body.chat_context,
    )
