from __future__ import annotations

import inspect
import json
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interfaces.mcp_server_repository import IMcpServerRepository
from app.db.models import McpServerModel
from app.integrations.mcp_policy import approved_names, normalize_domains, normalize_tools


_TRIMMED_FIELDS = ("name", "description", "endpoint_url")
_PLAIN_FIELDS = ("transport_type", "auth_type", "status")


class McpServerRepository(IMcpServerRepository):
  """Implementación PostgreSQL SQLAlchemy para IMcpServerRepository."""

  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  @staticmethod
  def _tools(model: McpServerModel) -> List[Dict[str, Any]]:
    try:
      raw = json.loads(model.allowed_tools_json) if model.allowed_tools_json else []
    except (TypeError, ValueError):
      raw = []
    return normalize_tools(raw)

  @staticmethod
  def _metadata(model: McpServerModel) -> Dict[str, Any]:
    try:
      meta = json.loads(model.metadata_json) if model.metadata_json else {}
    except (TypeError, ValueError):
      meta = {}
    return meta if isinstance(meta, dict) else {}

  def _to_dto(self, model: McpServerModel) -> Dict[str, Any]:
    tools = self._tools(model)
    return {
      "id": model.id,
      "user_id": model.user_id,
      "name": model.name,
      "description": model.description or "",
      "endpoint_url": model.endpoint_url,
      "transport_type": model.transport_type,
      "auth_type": model.auth_type,
      "status": model.status,
      "tools": tools,
      "allowed_tools": approved_names(tools),
      "allowed_domains": list(self._metadata(model).get("allowed_domains") or []),
      "created_at": model.created_at.isoformat() if model.created_at else None,
      "updated_at": model.updated_at.isoformat() if model.updated_at else None,
    }

  async def _find(self, server_id: str, user_id: Optional[str]) -> Optional[McpServerModel]:
    """A server by id; with a user, only when that user registered it (administrators pass None)."""
    stmt = select(McpServerModel).where(McpServerModel.id == server_id)
    if user_id:
      stmt = stmt.where(McpServerModel.user_id == user_id)
    return (await self.session.execute(stmt)).scalar_one_or_none()

  async def _flush_and_refresh(self, model: McpServerModel) -> None:
    await self.session.flush()
    if hasattr(self.session, "refresh"):
      refreshed = self.session.refresh(model)
      if inspect.isawaitable(refreshed):
        await refreshed

  def _apply_updates(self, server: McpServerModel, updates: Dict[str, Any]) -> None:
    """Only the fields that were given (not None) change."""
    given = {key: value for key, value in updates.items() if value is not None}
    for field in _TRIMMED_FIELDS:
      if field in given:
        setattr(server, field, given[field].strip())
    for field in _PLAIN_FIELDS:
      if field in given:
        setattr(server, field, given[field])
    if "tools" in given:
      server.allowed_tools_json = json.dumps(normalize_tools(given["tools"]))
    if "allowed_domains" in given:
      meta = self._metadata(server)
      meta["allowed_domains"] = normalize_domains(given["allowed_domains"])
      server.metadata_json = json.dumps(meta)

  async def get_by_id(self, server_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    item = await self._find(server_id, user_id)
    return self._to_dto(item) if item else None

  async def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
    stmt = select(McpServerModel).where(McpServerModel.user_id == user_id)
    res = await self.session.execute(stmt)
    servers = res.scalars().all()
    return [self._to_dto(s) for s in servers]

  async def list_all(self) -> List[Dict[str, Any]]:
    res = await self.session.execute(select(McpServerModel).order_by(McpServerModel.created_at))
    return [self._to_dto(s) for s in res.scalars().all()]

  async def create(
    self,
    user_id: str,
    name: str,
    endpoint_url: str,
    description: Optional[str] = None,
    transport_type: str = "sse",
    auth_type: str = "none",
    tools: Optional[List[Dict[str, Any]]] = None,
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
      allowed_tools_json=json.dumps(normalize_tools(tools)),
    )
    self.session.add(model)
    await self._flush_and_refresh(model)
    return self._to_dto(model)

  async def update(
    self,
    server_id: str,
    user_id: Optional[str],
    updates: Dict[str, Any],
  ) -> Optional[Dict[str, Any]]:
    server = await self._find(server_id, user_id)
    if not server:
      return None
    self._apply_updates(server, updates)
    await self._flush_and_refresh(server)
    return self._to_dto(server)

  async def delete(self, server_id: str, user_id: Optional[str] = None) -> bool:
    server = await self._find(server_id, user_id)
    if not server:
      return False
    await self.session.delete(server)
    await self.session.flush()
    return True

  async def update_status(
    self,
    server_id: str,
    user_id: Optional[str],
    status: str,
  ) -> Optional[Dict[str, Any]]:
    return await self.update(server_id, user_id, {"status": status})
