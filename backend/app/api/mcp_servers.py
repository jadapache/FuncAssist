"""MCP servers are enabled by administrators for the whole organization.

Users only consume them (see `GET /api/me/mcp-servers`). Every tool starts unapproved and an
administrator approves it, classifies it as read-only or not, and pins it to the description and schema
that were reviewed (see `app.integrations.mcp_policy`).
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user, get_mcp_server_repository
from app.db.interfaces.mcp_server_repository import IMcpServerRepository
from app.integrations.executor import validate_mcp_endpoint_url
from app.integrations.mcp_policy import ToolDescriptor, approve_tool, normalize_domains, revoke_tool

logger = logging.getLogger("funcassist.tool_audit")

router = APIRouter(
  prefix="/mcp-servers",
  tags=["mcp-servers"],
  dependencies=[Depends(get_current_admin_user)],
)

ENDPOINT_ERROR = "URL de servidor MCP no permitida o insegura."
NOT_FOUND = "Servidor MCP no encontrado."


class McpServerCreate(BaseModel):
  name: str = Field(min_length=1, max_length=100)
  endpoint_url: str = Field(min_length=1)
  description: Optional[str] = None
  transport_type: str = "sse"
  auth_type: str = "none"


class McpServerUpdate(BaseModel):
  name: Optional[str] = Field(default=None, min_length=1, max_length=100)
  endpoint_url: Optional[str] = None
  description: Optional[str] = None
  transport_type: Optional[str] = None
  auth_type: Optional[str] = None
  status: Optional[str] = None
  # Hosts that tools of this server may be pointed at (navigation, fetching). Empty means none.
  allowed_domains: Optional[List[str]] = Field(default=None, max_length=100)


class ToolApproval(BaseModel):
  """One tool as the administrator reviewed it. `approved=False` revokes it."""

  name: str = Field(min_length=1, max_length=200)
  description: str = Field(default="", max_length=4000)
  input_schema: Optional[dict[str, Any]] = None
  read_only: bool = False
  approved: bool = True


class ToolEntry(BaseModel):
  name: str
  read_only: bool = False
  approved: bool = False
  fingerprint: Optional[str] = None
  approved_by: Optional[str] = None
  approved_at: Optional[str] = None


class McpServerAdminInfo(BaseModel):
  id: str
  name: str
  description: str = ""
  endpoint_url: str
  transport_type: str = "sse"
  auth_type: str = "none"
  status: str = "configured"
  tools: List[ToolEntry] = Field(default_factory=list)
  allowed_tools: List[str] = Field(default_factory=list)
  allowed_domains: List[str] = Field(default_factory=list)
  created_at: Optional[str] = None
  updated_at: Optional[str] = None


def _info(server: dict[str, Any]) -> McpServerAdminInfo:
  return McpServerAdminInfo(**{k: v for k, v in server.items() if k in McpServerAdminInfo.model_fields})


def _check_endpoint(url: str) -> None:
  if not validate_mcp_endpoint_url(url, resolve_dns=False):
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ENDPOINT_ERROR)


@router.get("", response_model=List[McpServerAdminInfo])
async def list_mcp_servers(
  mcp_repo: IMcpServerRepository = Depends(get_mcp_server_repository),
) -> List[McpServerAdminInfo]:
  return [_info(s) for s in await mcp_repo.list_all()]


@router.post("", response_model=McpServerAdminInfo)
async def create_mcp_server(
  body: McpServerCreate,
  admin: dict[str, Any] = Depends(get_current_admin_user),
  mcp_repo: IMcpServerRepository = Depends(get_mcp_server_repository),
) -> McpServerAdminInfo:
  _check_endpoint(body.endpoint_url)
  created = await mcp_repo.create(
    user_id=admin["id"],
    name=body.name,
    endpoint_url=body.endpoint_url,
    description=body.description,
    transport_type=body.transport_type,
    auth_type=body.auth_type,
    tools=[],  # default deny: nothing is approved until an administrator does it
  )
  logger.info("mcp_server_created admin=%s server=%s", admin["id"], created["id"])
  return _info(created)


@router.patch("/{server_id}", response_model=McpServerAdminInfo)
async def update_mcp_server(
  server_id: str,
  body: McpServerUpdate,
  admin: dict[str, Any] = Depends(get_current_admin_user),
  mcp_repo: IMcpServerRepository = Depends(get_mcp_server_repository),
) -> McpServerAdminInfo:
  updates = body.model_dump(exclude_unset=True)
  current = await mcp_repo.get_by_id(server_id)
  if not current:
    raise HTTPException(status_code=404, detail=NOT_FOUND)

  if updates.get("allowed_domains") is not None:
    try:
      updates["allowed_domains"] = normalize_domains(updates["allowed_domains"])
    except ValueError as exc:
      raise HTTPException(status_code=400, detail=str(exc)) from exc

  new_url = updates.get("endpoint_url")
  if new_url is not None:
    _check_endpoint(new_url)
    if new_url.strip() != current["endpoint_url"]:
      # A different endpoint is a different server: neither the approvals nor the domains carry over.
      updates["tools"] = []
      updates.setdefault("allowed_domains", [])
      logger.info("mcp_server_endpoint_changed admin=%s server=%s approvals_cleared=true", admin["id"], server_id)

  updated = await mcp_repo.update(server_id, None, updates)
  if not updated:
    raise HTTPException(status_code=404, detail=NOT_FOUND)
  return _info(updated)


@router.delete("/{server_id}")
async def delete_mcp_server(
  server_id: str,
  admin: dict[str, Any] = Depends(get_current_admin_user),
  mcp_repo: IMcpServerRepository = Depends(get_mcp_server_repository),
) -> dict[str, Any]:
  if not await mcp_repo.delete(server_id):
    raise HTTPException(status_code=404, detail=NOT_FOUND)
  logger.info("mcp_server_deleted admin=%s server=%s", admin["id"], server_id)
  return {"ok": True, "deleted_id": server_id}


@router.put("/{server_id}/tools", response_model=McpServerAdminInfo)
async def set_tool_approvals(
  server_id: str,
  body: List[ToolApproval],
  admin: dict[str, Any] = Depends(get_current_admin_user),
  mcp_repo: IMcpServerRepository = Depends(get_mcp_server_repository),
) -> McpServerAdminInfo:
  """Approve (pinning the reviewed description and schema) or revoke tools of a server."""
  server = await mcp_repo.get_by_id(server_id)
  if not server:
    raise HTTPException(status_code=404, detail=NOT_FOUND)

  tools = list(server.get("tools") or [])
  for item in body:
    if item.approved:
      try:
        tools = approve_tool(
          tools,
          ToolDescriptor(item.name, item.description, item.input_schema),
          read_only=item.read_only,
          approved_by=admin["id"],
        )
      except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
      tools = revoke_tool(tools, item.name)
    logger.info(
      "mcp_tool_%s admin=%s server=%s tool=%s read_only=%s",
      "approved" if item.approved else "revoked", admin["id"], server_id, item.name, item.read_only,
    )

  updated = await mcp_repo.update(server_id, None, {"tools": tools})
  if not updated:
    raise HTTPException(status_code=404, detail=NOT_FOUND)
  return _info(updated)


@router.post("/{server_id}/test")
async def test_mcp_server(
  server_id: str,
  mcp_repo: IMcpServerRepository = Depends(get_mcp_server_repository),
) -> dict[str, Any]:
  server = await mcp_repo.get_by_id(server_id)
  if not server:
    raise HTTPException(status_code=404, detail=NOT_FOUND)
  is_valid = validate_mcp_endpoint_url(server["endpoint_url"], resolve_dns=False)
  new_status = "connected" if is_valid else "error"
  await mcp_repo.update_status(server_id, None, new_status)
  return {"ok": is_valid, "status": new_status, "endpoint_url": server["endpoint_url"]}
