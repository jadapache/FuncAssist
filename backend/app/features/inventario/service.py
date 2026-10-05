from typing import Any, List, Optional
from app.ai.runner import run_grounded_feature


async def generate_inventario_report(
    query: str,
    sources: Optional[List[str]] = None,
    document_ids: Optional[List[str]] = None,
    chat_context: Optional[str] = None,
) -> dict:
    """Generate system inventory analysis with components, endpoints and test vectors."""
    return await run_grounded_feature(
        feature="inventario_doc",
        query=query,
        sources=sources or ["knowledge", "jira", "github"],
        document_ids=document_ids,
        chat_context=chat_context,
    )

