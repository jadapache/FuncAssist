"""Registry and definitions for AI Agent tools following security and permission validation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.ai.artifacts import artifacts_to_dict, extract_artifacts
from app.context.retrieval import chunks_from_documents
from app.context.service import assemble_context


@dataclass
class ToolContext:
    """Server-side permission boundary for tool execution.

    Tool arguments come from the model (and indirectly from document content),
    so every handler must clamp them against these fields, never trust them.
    """
    user_id: str | None = None
    allowed_sources: list[str] | None = None
    allowed_document_ids: list[str] = field(default_factory=list)
    token_budget: int = 4000
    artifacts: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    handler: Callable[[dict[str, Any], ToolContext], Awaitable[str]]
    read_only: bool = True


_TOOL_REGISTRY: dict[str, Tool] = {}


def register_tool(tool: Tool) -> None:
    _TOOL_REGISTRY[tool.name] = tool


def get_tool(name: str) -> Tool | None:
    return _TOOL_REGISTRY.get(name)


def list_tools() -> list[Tool]:
    return list(_TOOL_REGISTRY.values())


def get_tools_openai_schema() -> list[dict[str, Any]]:
    schemas = []
    for t in _TOOL_REGISTRY.values():
        schemas.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.schema,
            },
        })
    return schemas


# --- Default Tools Implementations ---

async def _search_knowledge(args: dict[str, Any], ctx: ToolContext) -> str:
    query = str(args.get("query", ""))
    if not query:
        return "[Error]: Query vacía"
    permitted = list(ctx.allowed_sources or [])
    if not permitted:
        return "[Error]: No hay fuentes de conocimiento habilitadas para esta conversación."
    requested = [str(s) for s in (args.get("sources") or []) if isinstance(s, str)]
    sources = [s for s in requested if s in permitted] if requested else permitted
    if not sources:
        return f"[Error]: Fuentes no permitidas. Disponibles: {', '.join(permitted)}"
    bundle = await assemble_context(query=query, sources=sources, user_id=ctx.user_id)
    if bundle.is_empty:
        return "[Resultado]: No se encontró información en las fuentes conectadas."
    parts = []
    for c in bundle.chunks[:5]:
        parts.append(f"[Chunk ID: {c.id} | Fuente: {c.source_label}]:\n{c.text[:800]}")
    return "\n\n---\n\n".join(parts)


async def _read_document(args: dict[str, Any], ctx: ToolContext) -> str:
    doc_id = str(args.get("document_id", ""))
    if not doc_id:
        return "[Error]: document_id requerido"
    # Knowledge chunks carry no owner, so only documents attached to this request are readable.
    if doc_id not in ctx.allowed_document_ids:
        return "[Error]: Documento no disponible en esta conversación."
    chunks = await asyncio.to_thread(chunks_from_documents, [doc_id])
    if not chunks:
        return f"[Resultado]: Documento {doc_id} no contiene texto o no fue encontrado."
    content = "\n".join(c.text for c in chunks[:3])
    return f"[Documento {doc_id}]:\n{content[:2000]}"


async def _create_artifact(args: dict[str, Any], ctx: ToolContext) -> str:
    title = str(args.get("title", "Documento"))
    extension = str(args.get("extension", "docx")).lstrip(".")
    content = str(args.get("content", ""))
    if not content.strip():
        return "[Error]: content vacío"
    # Collected for delivery to the user by the agent loop; the model only gets a confirmation.
    ctx.artifacts.append({"title": title, "extension": extension, "content": content})
    return f"[OK]: Artefacto '{title}.{extension}' creado y entregado al usuario. No repitas su contenido."


# Register foundational tools
register_tool(
    Tool(
        name="search_knowledge",
        description="Busca fragmentos relevantes en la base de conocimiento conectada y devuelve citas.",
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Término o consulta de búsqueda"},
                "sources": {"type": "array", "items": {"type": "string"}, "description": "Fuentes a consultar"},
            },
            "required": ["query"],
        },
        handler=_search_knowledge,
        read_only=True,
    )
)

register_tool(
    Tool(
        name="read_document",
        description="Lee el contenido de un documento subido o adjunto.",
        schema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "ID del documento"},
            },
            "required": ["document_id"],
        },
        handler=_read_document,
        read_only=True,
    )
)

register_tool(
    Tool(
        name="create_artifact",
        description="Crea o emite un artefacto documental estructurado formal.",
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Título formal del documento"},
                "extension": {"type": "string", "description": "Extensión (docx, xlsx, md)"},
                "content": {"type": "string", "description": "Contenido Markdown completo"},
            },
            "required": ["title", "content"],
        },
        handler=_create_artifact,
        read_only=False,
    )
)
