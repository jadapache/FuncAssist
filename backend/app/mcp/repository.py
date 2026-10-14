"""Repository for persisted external MCP Servers in SQLite."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from app.db.database import get_db
from app.mcp.schema import MCPServerConfig, MCPServerCreate, MCPServerUpdate, MCPTool


class MCPServerRepository:
    """Handles CRUD operations for external MCP server configurations."""

    @staticmethod
    def _row_to_config(row: Any) -> MCPServerConfig:
        headers = json.loads(row["headers_json"]) if row["headers_json"] else {}
        args = json.loads(row["args_json"]) if row["args_json"] else []
        cached_tools_raw = json.loads(row["cached_tools_json"]) if row["cached_tools_json"] else []
        cached_tools = [MCPTool(**t) for t in cached_tools_raw]

        return MCPServerConfig(
            id=row["id"],
            name=row["name"],
            transport=row["transport"],
            url=row["url"],
            command=row["command"],
            args=args,
            headers=headers,
            enabled=bool(row["enabled"]),
            cached_tools=cached_tools,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    async def get_all(self) -> List[MCPServerConfig]:
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM mcp_servers ORDER BY created_at DESC;")
            rows = await cursor.fetchall()
            return [self._row_to_config(r) for r in rows]

    async def get_by_id(self, server_id: str) -> Optional[MCPServerConfig]:
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM mcp_servers WHERE id = ?;", (server_id,))
            row = await cursor.fetchone()
            return self._row_to_config(row) if row else None

    async def create(self, data: MCPServerCreate) -> MCPServerConfig:
        server_id = f"mcp_{uuid.uuid4().hex[:12]}"
        headers_json = json.dumps(data.headers or {})
        args_json = json.dumps([])
        cached_tools_json = json.dumps([])

        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO mcp_servers (
                    id, name, transport, url, command, args_json, headers_json, enabled, cached_tools_json
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?);
                """,
                (
                    server_id,
                    data.name,
                    data.transport,
                    data.url,
                    args_json,
                    headers_json,
                    1 if data.enabled else 0,
                    cached_tools_json,
                ),
            )
            await db.commit()

        created = await self.get_by_id(server_id)
        if not created:
            raise RuntimeError(f"Error creating MCP server {server_id}")
        return created

    async def update(self, server_id: str, data: MCPServerUpdate) -> Optional[MCPServerConfig]:
        existing = await self.get_by_id(server_id)
        if not existing:
            return None

        name = data.name if data.name is not None else existing.name
        transport = data.transport if data.transport is not None else existing.transport
        url = data.url if data.url is not None else existing.url
        enabled = data.enabled if data.enabled is not None else existing.enabled
        headers = data.headers if data.headers is not None else existing.headers

        headers_json = json.dumps(headers or {})

        async with get_db() as db:
            await db.execute(
                """
                UPDATE mcp_servers
                SET name = ?, transport = ?, url = ?, headers_json = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (name, transport, url, headers_json, 1 if enabled else 0, server_id),
            )
            await db.commit()

        return await self.get_by_id(server_id)

    async def update_cached_tools(self, server_id: str, tools: List[MCPTool]) -> Optional[MCPServerConfig]:
        tools_json = json.dumps([t.model_dump() for t in tools])
        async with get_db() as db:
            await db.execute(
                """
                UPDATE mcp_servers
                SET cached_tools_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (tools_json, server_id),
            )
            await db.commit()
        return await self.get_by_id(server_id)

    async def delete(self, server_id: str) -> bool:
        async with get_db() as db:
            cursor = await db.execute("DELETE FROM mcp_servers WHERE id = ?;", (server_id,))
            await db.commit()
            return cursor.rowcount > 0
