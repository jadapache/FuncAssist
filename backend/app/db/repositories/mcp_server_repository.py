from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interfaces.mcp_server_repository import IMcpServerRepository
from app.db.models import McpServerModel


class McpServerRepository(IMcpServerRepository):
  """Implementación PostgreSQL SQLAlchemy para IMcpServerRepository."""

  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  def _to_dto(self, model: McpServerModel) -> Dict[str, Any]:
    return {
      "id": model.id,
      "user_id": model.user_id,
      "name": model.name,
      "description": model.description or "",
      "endpoint_url": model.endpoint_url,
      "transport_type": model.transport_type,
      "auth_type": model.auth_type,
      "status": model.status,
      "allowed_tools": json.loads(model.allowed_tools_json) if model.allowed_tools_json else [],
      "created_at": model.created_at.isoformat() if model.created_at else None,
      "updated_at": model.updated_at.isoformat() if model.updated_at else None,
    }

  async def get_by_id(self, server_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    stmt = select(McpServerModel).where(McpServerModel.id == server_id)
    if user_id:
      stmt = stmt.where(McpServerModel.user_id == user_id)
    res = await self.session.execute(stmt)
    item = res.scalar_one_or_none()
    return self._to_dto(item) if item else None

  async def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
    stmt = select(McpServerModel).where(McpServerModel.user_id == user_id)
    res = await self.session.execute(stmt)
    servers = res.scalars().all()
    return [self._to_dto(s) for s in servers]

  async def create(
    self,
    user_id: str,
    name: str,
    endpoint_url: str,
    description: Optional[str] = None,
    transport_type: str = "sse",
    auth_type: str = "none",
    allowed_tools: Optional[List[str]] = None,
  ) -> Dict[str, Any]:
    server_id = str(uuid.uuid4())
    model = McpServerModel(
      id=server_id,
      user_id=user_id,
      name=name.strip(),
      description=description.strip() if description else None,
      endpoint_url=endpoint_url.strip(),
      transport_type=transport_type,
      auth_type=auth_type,
      status="configured",
      allowed_tools_json=json.dumps(allowed_tools or []),
    )
    self.session.add(model)
    await self.session.flush()
    if hasattr(self.session, "refresh"):
      res = self.session.refresh(model)
      import inspect
      if inspect.isawaitable(res):
        await res
    return self._to_dto(model)

  async def update(
    self,
    server_id: str,
    user_id: str,
    updates: Dict[str, Any],
  ) -> Optional[Dict[str, Any]]:
    stmt = select(McpServerModel).where(
      McpServerModel.id == server_id,
      McpServerModel.user_id == user_id,
    )
    res = await self.session.execute(stmt)
    server = res.scalar_one_or_none()
    if not server:
      return None

    if "name" in updates and updates["name"] is not None:
      server.name = updates["name"].strip()
    if "description" in updates and updates["description"] is not None:
      server.description = updates["description"].strip()
    if "endpoint_url" in updates and updates["endpoint_url"] is not None:
      server.endpoint_url = updates["endpoint_url"].strip()
    if "transport_type" in updates and updates["transport_type"] is not None:
      server.transport_type = updates["transport_type"]
    if "auth_type" in updates and updates["auth_type"] is not None:
      server.auth_type = updates["auth_type"]
    if "status" in updates and updates["status"] is not None:
      server.status = updates["status"]
    if "allowed_tools" in updates and updates["allowed_tools"] is not None:
      server.allowed_tools_json = json.dumps(updates["allowed_tools"])

    await self.session.flush()
    if hasattr(self.session, "refresh"):
      res = self.session.refresh(server)
      import inspect
      if inspect.isawaitable(res):
        await res
    return self._to_dto(server)

  async def delete(self, server_id: str, user_id: str) -> bool:
    stmt = select(McpServerModel).where(
      McpServerModel.id == server_id,
      McpServerModel.user_id == user_id,
    )
    res = await self.session.execute(stmt)
    server = res.scalar_one_or_none()
    if not server:
      return False
    await self.session.delete(server)
    await self.session.flush()
    return True

  async def update_status(
    self,
    server_id: str,
    user_id: str,
    status: str,
  ) -> Optional[Dict[str, Any]]:
    return await self.update(server_id, user_id, {"status": status})
