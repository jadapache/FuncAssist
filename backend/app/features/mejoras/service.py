from typing import Any, List, Optional
from app.ai.runner import run_grounded_feature


async def generate_mejoras_report(
    query: str,
    sources: Optional[List[str]] = None,
    document_ids: Optional[List[str]] = None,
    chat_context: Optional[str] = None,
) -> dict:
    """Generate improvements and findings analysis for QA & architecture."""
    return await run_grounded_feature(
        feature="mejoras_doc",
        query=query,
        sources=sources or ["jira", "github", "gitlab", "knowledge"],
        document_ids=document_ids,
        chat_context=chat_context,
    )

