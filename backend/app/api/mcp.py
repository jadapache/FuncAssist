"""FastAPI Endpoints for Model Context Protocol (MCP) Server and Client Management."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from app.mcp.client import mcp_client
from app.mcp.repository import MCPServerRepository
from app.mcp.schema import (
    JSONRPCRequest,
    JSONRPCResponse,
    MCPServerCallToolRequest,
    MCPServerConfig,
    MCPServerCreate,
    MCPServerUpdate,
)
from app.mcp.server import MCP_PROTOCOL_VERSION, mcp_server

router = APIRouter(prefix="/mcp", tags=["mcp"])
repo = MCPServerRepository()

# Active SSE client sessions
_active_sse_sessions: Dict[str, asyncio.Queue] = {}


# =====================================================================
# 1. MCP SERVER ENDPOINTS (External agentic models connect to FuncAssist)
# =====================================================================

@router.post("", response_model=JSONRPCResponse)
async def handle_jsonrpc_direct(req: JSONRPCRequest) -> JSONRPCResponse:
    """Direct JSON-RPC 2.0 endpoint for external MCP clients."""
    return await mcp_server.handle_request(req)


@router.get("/sse")
async def sse_handshake(request: Request) -> StreamingResponse:
    """
    Server-Sent Events (SSE) handshake for standard MCP clients (Claude Desktop, Cursor).
    Establishes an active stream and returns the message posting endpoint.
    """
    session_id = uuid.uuid4().hex
    queue: asyncio.Queue[str] = asyncio.Queue()
    _active_sse_sessions[session_id] = queue

    async def event_generator():
        # First event: endpoint specification according to MCP SSE transport spec
        endpoint_url = f"/api/mcp/messages?sessionId={session_id}"
        yield f"event: endpoint\ndata: {endpoint_url}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait for message to push or send heartbeat every 15 seconds
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: message\ndata: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            _active_sse_sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/messages")
async def handle_sse_messages(
    request: Request,
    sessionId: str | None = None,
) -> JSONRPCResponse:
    """Receives JSON-RPC requests associated with an active SSE session."""
    body_bytes = await request.body()
    try:
        body_dict = json.loads(body_bytes.decode("utf-8"))
        req = JSONRPCRequest(**body_dict)
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON-RPC request: {str(ex)}",
        )

    response = await mcp_server.handle_request(req)

    # If session is active, push message to SSE queue
    if sessionId and sessionId in _active_sse_sessions:
        await _active_sse_sessions[sessionId].put(json.dumps(response.model_dump()))

    return response


@router.get("/info")
async def get_mcp_server_info(request: Request) -> Dict[str, Any]:
    """Provides public connection info and pre-configured snippets for external tools."""
    base_url = str(request.base_url).rstrip("/")
    mcp_direct_url = f"{base_url}/api/mcp"
    mcp_sse_url = f"{base_url}/api/mcp/sse"

    tools = [t.model_dump() for t in mcp_server.get_tools()]
    resources = [r.model_dump() for r in mcp_server.get_resources()]

    claude_config = {
        "mcpServers": {
            "funcassist": {
                "url": mcp_sse_url,
                "transport": "sse",
            }
        }
    }

    cursor_config = {
        "mcpServers": {
            "funcassist": {
                "url": mcp_sse_url,
            }
        }
    }

    return {
        "status": "online",
        "name": mcp_server.server_info["name"],
        "version": mcp_server.server_info["version"],
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "directUrl": mcp_direct_url,
        "sseUrl": mcp_sse_url,
        "toolsCount": len(tools),
        "tools": tools,
        "resourcesCount": len(resources),
        "resources": resources,
        "configSnippets": {
            "claudeDesktop": claude_config,
            "cursor": cursor_config,
        },
    }


# =====================================================================
# 2. MCP CLIENT ENDPOINTS (Manage external MCP servers in FuncAssist)
# =====================================================================

@router.get("/servers", response_model=List[MCPServerConfig])
async def list_mcp_servers() -> List[MCPServerConfig]:
    """Lists all configured external MCP servers."""
    return await repo.get_all()


@router.post("/servers", response_model=MCPServerConfig)
async def create_mcp_server(data: MCPServerCreate) -> MCPServerConfig:
    """Registers a new external MCP server."""
    created = await repo.create(data)
    try:
        asyncio.create_task(mcp_client.ping_and_sync_tools(created.id))
    except Exception:
        pass
    return created


@router.put("/servers/{server_id}", response_model=MCPServerConfig)
async def update_mcp_server(server_id: str, data: MCPServerUpdate) -> MCPServerConfig:
    """Updates an existing external MCP server configuration."""
    updated = await repo.update(server_id, data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Servidor MCP '{server_id}' no encontrado.",
        )
    return updated


@router.delete("/servers/{server_id}")
async def delete_mcp_server(server_id: str) -> Dict[str, Any]:
    """Deletes an external MCP server."""
    success = await repo.delete(server_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Servidor MCP '{server_id}' no encontrado.",
        )
    return {"message": "Servidor MCP eliminado correctamente.", "id": server_id}


@router.post("/servers/{server_id}/ping")
async def ping_mcp_server(server_id: str) -> Dict[str, Any]:
    """Tests connection to an external MCP server and synchronizes its tools."""
    ok, message, tools = await mcp_client.ping_and_sync_tools(server_id)
    return {
        "success": ok,
        "message": message,
        "toolsCount": len(tools),
        "tools": [t.model_dump() for t in tools],
    }


@router.post("/servers/{server_id}/call")
async def call_external_mcp_tool(
    server_id: str,
    payload: MCPServerCallToolRequest,
) -> Dict[str, Any]:
    """Executes a tool on a connected external MCP server."""
    try:
        result = await mcp_client.call_remote_tool(
            server_id=server_id,
            tool_name=payload.tool_name,
            arguments=payload.arguments,
        )
        return {"success": True, "result": result}
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error invocando herramienta MCP: {str(ex)}",
        )
