from typing import Any, List, Optional
from app.ai.runner import run_grounded_feature


async def analyze_change_impact(
    query: str,
    sources: Optional[List[str]] = None,
    document_ids: Optional[List[str]] = None,
    chat_context: Optional[str] = None,
) -> dict:
    """Analyze change impact across codebase, tickets and requirements."""
    return await run_grounded_feature(
        feature="change_impact",
        query=query,
        sources=sources or ["jira", "github", "knowledge"],
        document_ids=document_ids,
        chat_context=chat_context,
    )

