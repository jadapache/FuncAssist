"""MCP Client Manager for Outbound Connections to External MCP Servers.

Allows FuncAssist agentic models to dynamically connect to, discover, and execute
tools from external Model Context Protocol (MCP) servers (e.g. Jira, GitHub, Postgres,
Filesystem, APIs).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.mcp.repository import MCPServerRepository
from app.mcp.schema import (
    JSONRPCRequest,
    JSONRPCResponse,
    MCPServerConfig,
    MCPTool,
)

logger = logging.getLogger(__name__)


class MCPClientManager:
    """Manages connections, tool discovery, and tool execution for external MCP servers."""

    def __init__(self, repo: Optional[MCPServerRepository] = None) -> None:
        self.repo = repo or MCPServerRepository()

    async def _send_jsonrpc(
        self,
        server: MCPServerConfig,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        """Dispatches a JSON-RPC request to an external MCP server over HTTP/SSE."""
        req = JSONRPCRequest(method=method, params=params, id=1)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **(server.headers or {}),
        }

        # Normalize URL: if transport is sse and points to an SSE endpoint, target messages or direct url
        target_url = server.url.strip()
        if server.transport == "sse" and target_url.endswith("/sse"):
            messages_url = target_url.replace("/sse", "/messages")
        else:
            messages_url = target_url

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            try:
                resp = await client.post(messages_url, json=req.model_dump(), headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as ex:
                # Fallback to direct URL if /messages was a variant
                if messages_url != target_url:
                    try:
                        resp = await client.post(target_url, json=req.model_dump(), headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception:
                        raise RuntimeError(f"Fallo de conexión con el servidor MCP '{server.name}': {str(ex)}")
                else:
                    raise RuntimeError(f"Fallo de conexión con el servidor MCP '{server.name}': {str(ex)}")

        parsed = JSONRPCResponse(**data)
        if parsed.error:
            raise RuntimeError(f"Error devuelto por servidor MCP '{server.name}': {parsed.error.message}")

        return parsed.result or {}

    async def ping_and_sync_tools(self, server_id: str) -> Tuple[bool, str, List[MCPTool]]:
        """Pings external MCP server, initializes handshake, discovers tools, and saves to repository."""
        server = await self.repo.get_by_id(server_id)
        if not server:
            return False, f"Servidor MCP '{server_id}' no encontrado.", []

        try:
            # 1. Initialize Handshake
            init_result = await self._send_jsonrpc(
                server,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "funcassist-client", "version": "1.0.0"},
                },
            )

            # 2. Discover Tools
            tools_result = await self._send_jsonrpc(server, "tools/list", {})
            raw_tools = tools_result.get("tools", [])
            discovered_tools: List[MCPTool] = []

            for t in raw_tools:
                try:
                    discovered_tools.append(
                        MCPTool(
                            name=t.get("name", "unnamed_tool"),
                            description=t.get("description", "Sin descripción"),
                            inputSchema=t.get("inputSchema", {"type": "object", "properties": {}}),
                        )
                    )
                except Exception:
                    pass

            # Update cache in database
            await self.repo.update_cached_tools(server_id, discovered_tools)

            server_info = init_result.get("serverInfo", {})
            server_name = server_info.get("name", server.name)
            msg = f"Conexión exitosa con '{server_name}'. Se descubrieron {len(discovered_tools)} herramientas."
            return True, msg, discovered_tools

        except Exception as ex:
            logger.warning("Error pinging MCP server %s: %s", server_id, ex)
            return False, str(ex), []

    async def call_remote_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Executes a tool on an external MCP server."""
        server = await self.repo.get_by_id(server_id)
        if not server:
            raise ValueError(f"Servidor MCP '{server_id}' no encontrado.")
        if not server.enabled:
            raise ValueError(f"El servidor MCP '{server.name}' se encuentra deshabilitado.")

        result = await self._send_jsonrpc(
            server,
            "tools/call",
            {"name": tool_name, "arguments": arguments},
            timeout=30.0,
        )
        return result

    async def get_all_agentic_tools(self) -> List[Dict[str, Any]]:
        """Aggregates all enabled tools from all connected MCP servers in OpenAI function calling schema."""
        servers = await self.repo.get_all()
        aggregated: List[Dict[str, Any]] = []

        for s in servers:
            if not s.enabled:
                continue
            for tool in s.cached_tools:
                namespaced_name = f"mcp_{s.id}_{tool.name}"
                aggregated.append({
                    "type": "function",
                    "function": {
                        "name": namespaced_name,
                        "description": f"[{s.name}] {tool.description}",
                        "parameters": tool.inputSchema,
                    },
                    "_meta": {
                        "server_id": s.id,
                        "server_name": s.name,
                        "original_name": tool.name,
                    },
                })

        return aggregated


# Singleton instance
mcp_client = MCPClientManager()
