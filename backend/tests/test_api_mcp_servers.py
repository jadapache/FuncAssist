"""Only administrators register MCP servers and approve their tools; users only consume them."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import mcp_servers as mod
from app.api.deps import get_current_admin_user, get_current_user, get_mcp_server_repository
from app.integrations.mcp_policy import approved_names, normalize_tools

ADMIN = {"id": "admin-1", "role": "admin"}
SNAPSHOT = {
  "name": "snapshot", "description": "Page snapshot", "read_only": True,
  "input_schema": {"type": "object", "properties": {"selector": {"type": "string"}}},
}


class FakeRepo:
  def __init__(self):
    self.servers: dict[str, dict] = {}
    self.status_updates: list[tuple] = []

  def _dto(self, server):
    tools = normalize_tools(server["tools"])
    return {**server, "tools": tools, "allowed_tools": approved_names(tools)}

  async def list_all(self):
    return [self._dto(s) for s in self.servers.values()]

  async def get_by_id(self, sid, user_id=None):
    server = self.servers.get(sid)
    return self._dto(server) if server else None

  async def create(self, user_id, name, endpoint_url, description=None, transport_type="sse", auth_type="none", tools=None):
    sid = f"srv-{len(self.servers) + 1}"
    self.servers[sid] = {
      "id": sid, "user_id": user_id, "name": name, "endpoint_url": endpoint_url, "description": description or "",
      "transport_type": transport_type, "auth_type": auth_type, "status": "configured", "tools": tools or [],
    }
    return self._dto(self.servers[sid])

  async def update(self, sid, user_id, updates):
    server = self.servers.get(sid)
    if not server:
      return None
    server.update({k: v for k, v in updates.items() if v is not None})
    return self._dto(server)

  async def delete(self, sid, user_id=None):
    return self.servers.pop(sid, None) is not None

  async def update_status(self, sid, user_id, status):
    self.status_updates.append((sid, user_id, status))
    return await self.update(sid, user_id, {"status": status})


@pytest.fixture
def repo(monkeypatch):
  monkeypatch.setattr(mod, "validate_mcp_endpoint_url", lambda url, resolve_dns=False: url.startswith("https://"))
  return FakeRepo()


def build_client(repo, user):
  app = FastAPI()
  app.include_router(mod.router, prefix="/api")
  app.dependency_overrides[get_mcp_server_repository] = lambda: repo
  app.dependency_overrides[get_current_user] = lambda: user
  if user["role"] == "admin":
    app.dependency_overrides[get_current_admin_user] = lambda: user
  else:
    app.dependency_overrides.pop(get_current_admin_user, None)
  return TestClient(app, base_url="https://testserver")


@pytest.fixture
def admin(repo):
  return build_client(repo, ADMIN)


@pytest.fixture
def regular(repo):
  return build_client(repo, {"id": "user-1", "role": "user"})


# ----------------------------------------------------------------- only administrators


@pytest.mark.parametrize("method,path", [
  ("get", "/api/mcp-servers"),
  ("post", "/api/mcp-servers"),
  ("patch", "/api/mcp-servers/srv-1"),
  ("delete", "/api/mcp-servers/srv-1"),
  ("put", "/api/mcp-servers/srv-1/tools"),
  ("post", "/api/mcp-servers/srv-1/test"),
])
def test_regular_users_cannot_manage_mcp_servers(regular, repo, method, path):
  body = [SNAPSHOT] if path.endswith("/tools") else {"name": "s", "endpoint_url": "https://mcp.example.com"}
  assert regular.request(method.upper(), path, json=body).status_code == 403
  assert repo.servers == {}


# ----------------------------------------------------------------- server lifecycle


def test_create_starts_with_nothing_approved(admin, repo):
  r = admin.post("/api/mcp-servers", json={"name": "Playwright", "endpoint_url": "https://mcp.example.com/sse", "description": "d"})
  assert r.status_code == 200
  body = r.json()
  assert body["tools"] == [] and body["allowed_tools"] == [] and body["status"] == "configured"
  assert repo.servers[body["id"]]["user_id"] == "admin-1"  # who registered it
  assert admin.get("/api/mcp-servers").json()[0]["id"] == body["id"]


@pytest.mark.parametrize("payload", [
  {"name": "s", "endpoint_url": "http://127.0.0.1/sse"},
  {"name": "s", "endpoint_url": "ftp://x"},
])
def test_unsafe_endpoints_are_rejected(admin, repo, payload):
  assert admin.post("/api/mcp-servers", json=payload).status_code == 400
  assert repo.servers == {}


def test_validation(admin):
  assert admin.post("/api/mcp-servers", json={"name": "", "endpoint_url": "https://x"}).status_code == 422
  assert admin.post("/api/mcp-servers", json={"name": "s"}).status_code == 422


def test_update_rename_and_unknown(admin, repo):
  sid = admin.post("/api/mcp-servers", json={"name": "s", "endpoint_url": "https://mcp.example.com"}).json()["id"]
  r = admin.patch(f"/api/mcp-servers/{sid}", json={"name": "renamed"})
  assert r.status_code == 200 and r.json()["name"] == "renamed"
  assert admin.patch("/api/mcp-servers/missing", json={"name": "x"}).status_code == 404
  assert admin.patch(f"/api/mcp-servers/{sid}", json={"endpoint_url": "http://internal"}).status_code == 400


def test_changing_the_endpoint_clears_every_approval(admin, repo):
  sid = admin.post("/api/mcp-servers", json={"name": "s", "endpoint_url": "https://good.example.com"}).json()["id"]
  admin.put(f"/api/mcp-servers/{sid}/tools", json=[SNAPSHOT])
  assert repo.servers[sid]["tools"][0]["approved"] is True

  # same endpoint: approvals stay
  admin.patch(f"/api/mcp-servers/{sid}", json={"endpoint_url": "https://good.example.com", "name": "n"})
  assert admin.get("/api/mcp-servers").json()[0]["allowed_tools"] == ["snapshot"]

  # a different endpoint is a different server
  r = admin.patch(f"/api/mcp-servers/{sid}", json={"endpoint_url": "https://other.example.com"})
  assert r.status_code == 200 and r.json()["allowed_tools"] == [] and r.json()["tools"] == []


def test_delete(admin, repo):
  sid = admin.post("/api/mcp-servers", json={"name": "s", "endpoint_url": "https://mcp.example.com"}).json()["id"]
  assert admin.delete(f"/api/mcp-servers/{sid}").json() == {"ok": True, "deleted_id": sid}
  assert admin.delete(f"/api/mcp-servers/{sid}").status_code == 404


def test_connection_test_updates_the_status(admin, repo):
  sid = admin.post("/api/mcp-servers", json={"name": "s", "endpoint_url": "https://mcp.example.com"}).json()["id"]
  r = admin.post(f"/api/mcp-servers/{sid}/test")
  assert r.json() == {"ok": True, "status": "connected", "endpoint_url": "https://mcp.example.com"}
  repo.servers[sid]["endpoint_url"] = "http://internal"
  assert admin.post(f"/api/mcp-servers/{sid}/test").json()["status"] == "error"
  assert admin.post("/api/mcp-servers/missing/test").status_code == 404


# ----------------------------------------------------------------- tool approval


def test_approving_tools_pins_what_the_administrator_reviewed(admin, repo):
  sid = admin.post("/api/mcp-servers", json={"name": "s", "endpoint_url": "https://mcp.example.com"}).json()["id"]
  click = {"name": "click", "description": "Click", "read_only": False}
  r = admin.put(f"/api/mcp-servers/{sid}/tools", json=[SNAPSHOT, click])
  assert r.status_code == 200
  tools = {t["name"]: t for t in r.json()["tools"]}
  assert tools["snapshot"]["approved"] is True and tools["snapshot"]["read_only"] is True
  assert tools["click"]["approved"] is True and tools["click"]["read_only"] is False
  assert tools["snapshot"]["fingerprint"] and tools["snapshot"]["approved_by"] == "admin-1"
  assert tools["snapshot"]["fingerprint"] != tools["click"]["fingerprint"]
  assert set(r.json()["allowed_tools"]) == {"snapshot", "click"}


def test_a_tool_defaults_to_not_read_only(admin, repo):
  sid = admin.post("/api/mcp-servers", json={"name": "s", "endpoint_url": "https://mcp.example.com"}).json()["id"]
  r = admin.put(f"/api/mcp-servers/{sid}/tools", json=[{"name": "navigate"}])
  assert r.json()["tools"][0]["read_only"] is False  # unclassified means it can change things


def test_revoking_and_renewing_a_tool(admin, repo):
  sid = admin.post("/api/mcp-servers", json={"name": "s", "endpoint_url": "https://mcp.example.com"}).json()["id"]
  first = admin.put(f"/api/mcp-servers/{sid}/tools", json=[SNAPSHOT]).json()["tools"][0]["fingerprint"]
  revised = {**SNAPSHOT, "description": "A different description"}
  second = admin.put(f"/api/mcp-servers/{sid}/tools", json=[revised]).json()["tools"][0]["fingerprint"]
  assert first != second  # renewing pins the new text

  r = admin.put(f"/api/mcp-servers/{sid}/tools", json=[{"name": "snapshot", "approved": False}])
  assert r.json()["tools"] == [] and r.json()["allowed_tools"] == []


def test_tool_approval_rejects_bad_input(admin, repo):
  sid = admin.post("/api/mcp-servers", json={"name": "s", "endpoint_url": "https://mcp.example.com"}).json()["id"]
  bad_schema = {"name": "t", "input_schema": {"type": "nonsense"}}
  assert admin.put(f"/api/mcp-servers/{sid}/tools", json=[bad_schema]).status_code == 400
  assert admin.put(f"/api/mcp-servers/{sid}/tools", json=[{"name": ""}]).status_code == 422
  assert admin.put("/api/mcp-servers/missing/tools", json=[SNAPSHOT]).status_code == 404
  assert repo.servers[sid]["tools"] == []
