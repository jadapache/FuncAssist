from typing import Any, List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from app.ai.runner import run_grounded_feature
from app.api.deps import get_test_plan_repository
from app.api.middleware.error_handlers import handle_grounded_errors
from app.db.interfaces import ITestPlanRepository

router = APIRouter(prefix="/features", tags=["qa-features"])

QA_FEATURE_KEYS = {
    "regression",
    "api_qa",
    "visual_qa",
    "smart_test_data",
    "release_readiness",
}

QA_DEFAULT_SOURCES = {
    "regression": ["jira", "github", "gitlab", "knowledge"],
    "api_qa": ["knowledge", "github", "gitlab"],
    "visual_qa": ["knowledge", "jira"],
    "smart_test_data": ["knowledge"],
    "release_readiness": ["jira", "github", "gitlab", "knowledge"],
}


class FeatureWorkspaceRequest(BaseModel):
    query: str = Field(min_length=1)
    sources: Optional[List[str]] = None
    document_ids: List[str] = Field(default_factory=list)
    chat_context: Optional[str] = None


@router.post("/qa/{feature_key}")
@handle_grounded_errors
async def qa_feature(
    feature_key: str,
    body: FeatureWorkspaceRequest = Body(...),
    test_plan_repo: ITestPlanRepository = Depends(get_test_plan_repository),
) -> dict[str, Any]:
    if feature_key not in QA_FEATURE_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown QA feature: {feature_key}")
    sources = body.sources or QA_DEFAULT_SOURCES.get(feature_key, ["knowledge"])
    if not body.document_ids and not sources:
        raise HTTPException(status_code=400, detail="Upload files and/or enable live sources.")
    res = await run_grounded_feature(
        feature=feature_key,
        query=body.query,
        sources=sources,
        document_ids=body.document_ids,
        chat_context=body.chat_context,
    )
    if isinstance(res, dict) and "markdown" in res:
        await test_plan_repo.create_test_plan(
            feature_name=feature_key,
            content=res["markdown"],
            test_type=feature_key,
        )
    return res
