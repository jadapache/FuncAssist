from typing import Any, List, Optional
from app.ai.runner import run_grounded_feature


async def review_prd(
    query: str,
    document_ids: List[str],
    sources: Optional[List[str]] = None,
    chat_context: Optional[str] = None,
) -> dict:
    """Analyze PRD documentation for completeness, quality and risks."""
    return await run_grounded_feature(
        feature="prd_checker",
        query=query,
        sources=sources or ["knowledge"],
        document_ids=document_ids,
        chat_context=chat_context,
    )

