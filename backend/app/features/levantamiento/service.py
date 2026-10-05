from typing import Any, List, Optional
from app.ai.runner import run_grounded_feature


async def generate_levantamiento_report(
    query: str,
    sources: Optional[List[str]] = None,
    document_ids: Optional[List[str]] = None,
    chat_context: Optional[str] = None,
) -> dict:
    """Generate requirement gathering and functional survey document."""
    return await run_grounded_feature(
        feature="levantamiento_doc",
        query=query,
        sources=sources or ["knowledge", "jira", "github"],
        document_ids=document_ids,
        chat_context=chat_context,
    )

