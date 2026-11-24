"""HTTP tests for app/api/me.py (preferences, BYOK credentials, Jira, MCP servers)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import me as mod
from app.api.deps import get_mcp_server_repository
from app.integrations.base import AuthMethod, AuthStartResponse, IntegrationInfo


class FakeJira:
  def __init__(self):
    self.calls = []
    self.callback_exc = None
    self.disconnect_exc = None

  async def start_oauth(self, user_id=None):
    self.calls.append(("oauth", user_id))
    return AuthStartResponse(authorization_url="https://auth/jira", state="st", auth_method=AuthMethod.OAUTH)

  async def handle_oauth_callback(self, code, state):
    if self.callback_exc:
      raise self.callback_exc

  async def disconnect(self, user_id=None):
    self.calls.append(("disconnect", user_id))
    if self.disconnect_exc:
      raise self.disconnect_exc


class FakeRegistry:
  def __init__(self):
    self.jira = FakeJira()

  def get(self, iid):
    return self.jira


class FakeMcpRepo:
  def __init__(self):
    self.servers: dict[str, dict] = {}
    self.status_updates = []

  async def list_by_user(self, user_id):
    return [s for s in self.servers.values() if s["_user"] == user_id]

  async def create(self, user_id, name, endpoint_url, description, transport_type, auth_type, allowed_tools):
    sid = f"srv-{len(self.servers) + 1}"
    self.servers[sid] = {"id": sid, "_user": user_id, "name": name, "endpoint_url": endpoint_url,
                         "description": description or "", "transport_type": transport_type,
                         "auth_type": auth_type, "allowed_tools": allowed_tools}
    return self.servers[sid]

  async def get_by_id(self, sid, user_id):
    s = self.servers.get(sid)
    return s if s and s["_user"] == user_id else None

  async def update(self, sid, user_id, updates):
    s = await self.get_by_id(sid, user_id)
    if not s:
      return None
    s.update({k: v for k, v in updates.items() if v is not None})
    return s

  async def delete(self, sid, user_id):
    return self.servers.pop(sid, None) is not None

  async def update_status(self, sid, user_id, status):
    self.status_updates.append((sid, status))


@pytest.fixture
def env(monkeypatch):
  state = {"prefs": {}, "creds": {}, "validation": [], "integration": None, "saved_integration": None,
           "deleted_integration": False}
  reg = FakeRegistry()
  monkeypatch.setattr(mod, "registry", reg)
  monkeypatch.setattr(mod, "get_user_preferences", lambda uid: dict(state["prefs"]))

  def save_prefs(uid, payload):
    state["prefs"].update(payload)
    return {**state["prefs"], "updated_at": "2026-01-01T00:00:00"}

  monkeypatch.setattr(mod, "save_user_preferences", save_prefs)
  monkeypatch.setattr(mod, "list_user_credentials_info",
                      lambda uid: [{"provider": p, "status": "active"} for p in state["creds"]])
  monkeypatch.setattr(mod, "save_user_credential", lambda uid, p, k: state["creds"].__setitem__(p, k))
  monkeypatch.setattr(mod, "load_user_credential", lambda uid, p: state["creds"].get(p))
  monkeypatch.setattr(mod, "update_credential_validation",
                      lambda uid, p, status, error_msg: state["validation"].append((p, status, error_msg)))
  monkeypatch.setattr(mod, "delete_user_credential", lambda uid, p: state["creds"].pop(p, None) is not None)
  monkeypatch.setattr(mod, "load_user_integration", lambda uid, iid: state["integration"])
  monkeypatch.setattr(mod, "save_user_integration",
                      lambda uid, iid, data: state.__setitem__("saved_integration", data))

  def del_int(uid, iid):
    state["deleted_integration"] = True
    return True

  monkeypatch.setattr(mod, "delete_user_integration", del_int)
  state["reg"] = reg
  state["repo"] = FakeMcpRepo()
  return state


@pytest.fixture
def client(env):
  app = FastAPI()
  app.include_router(mod.router, prefix="/api/me")
  app.dependency_overrides[get_mcp_server_repository] = lambda: env["repo"]
  return TestClient(app, base_url="https://testserver", follow_redirects=False)


def test_preferences_roundtrip(client, env):
  r = client.get("/api/me/preferences")
  assert r.status_code == 200 and r.json()["language"] == "es" and r.json()["settings_json"] == {}
  r = client.patch("/api/me/preferences", json={"inference_provider": "openai", "language": "en",
                                                 "settings_json": {"a": 1}})
  assert r.status_code == 200
  body = r.json()
  assert body["inference_provider"] == "openai" and body["language"] == "en"
  assert body["settings_json"] == {"a": 1} and body["updated_at"]
  assert env["prefs"] == {"inference_provider": "openai", "language": "en", "settings_json": {"a": 1}}
  assert client.get("/api/me/preferences").json()["language"] == "en"
  assert client.patch("/api/me/preferences", json={"settings_json": "x"}).status_code == 422


@pytest.mark.parametrize("provider", ["openrouter", "deepseek"])
def test_provider_credentials_for_openrouter_and_deepseek(client, env, provider):
  r = client.put(f"/api/me/provider-credentials/{provider.upper()}", json={"api_key": "sk-123456"})
  assert r.status_code == 200 and r.json()["provider"] == provider
  assert env["creds"][provider] == "sk-123456"
  r = client.post(f"/api/me/provider-credentials/{provider}/test")
  assert r.status_code == 200 and r.json() == {"ok": True, "provider": provider, "status": "active"}


def test_provider_credentials(client, env):
  r = client.put("/api/me/provider-credentials/OpenAI", json={"api_key": "sk-123456"})
  assert r.status_code == 200 and r.json() == {"provider": "openai", "status": "active", "is_configured": True,
                                                "last_validated_at": None, "validation_error": None,
                                                "updated_at": None}
  assert env["creds"]["openai"] == "sk-123456"
  assert client.put("/api/me/provider-credentials/foo", json={"api_key": "x"}).status_code == 400
  assert client.put("/api/me/provider-credentials/openai", json={"api_key": ""}).status_code == 422

  r = client.get("/api/me/provider-credentials")
  assert r.status_code == 200 and [c["provider"] for c in r.json()] == ["openai"]

  for suffix in ("test", "validate"):
    r = client.post(f"/api/me/provider-credentials/openai/{suffix}")
    assert r.status_code == 200 and r.json() == {"ok": True, "provider": "openai", "status": "active"}
  assert client.post("/api/me/provider-credentials/groq/test").status_code == 404
  env["creds"]["groq"] = "abc"
  r = client.post("/api/me/provider-credentials/groq/test")
  assert r.status_code == 400
  assert ("groq", "validation_failed", "Formato de llave inválido") in env["validation"]

  r = client.delete("/api/me/provider-credentials/OpenAI")
  assert r.json() == {"ok": True, "provider": "openai"}
  assert client.delete("/api/me/provider-credentials/openai").json()["ok"] is False


def test_jira_connect_is_oauth_only(client, env):
  r = client.post("/api/me/integrations/jira/connect")
  assert r.status_code == 200 and r.json()["authorization_url"] == "https://auth/jira"
  assert env["reg"].jira.calls[-1] == ("oauth", "test-user-id")


def test_jira_connect_ignores_a_token_in_the_body(client, env):
  """SEC-05: a personal access token sent to the connect endpoint is never stored or used."""
  r = client.post("/api/me/integrations/jira/connect",
                  json={"auth_method": "pat", "token": "tok", "email": "a@b.c", "jira_url": "https://j"})
  assert r.status_code == 200 and "authorization_url" in r.json()
  assert env["reg"].jira.calls[-1] == ("oauth", "test-user-id")
  assert env.get("saved_integration") in (None, {}) or "pat_token" not in env["saved_integration"]


@pytest.mark.parametrize("params,exc,expected", [
  ({"error": "access_denied"}, None, "message=oauth_error"),
  ({"code": "c"}, None, "message=missing_code"),
  ({"code": "c", "state": "s"}, None, "jira=connected"),
  ({"code": "c", "state": "s"}, ValueError("Invalid state"), "message=invalid_state"),
  ({"code": "c", "state": "s"}, ValueError("other"), "message=oauth_error"),
  ({"code": "c", "state": "s"}, RuntimeError("net"), "message=oauth_error"),
])
def test_jira_callback(client, env, params, exc, expected):
  env["reg"].jira.callback_exc = exc
  r = client.get("/api/me/integrations/jira/callback", params=params)
  assert r.status_code == 307
  assert "/profile?" in r.headers["location"] and expected in r.headers["location"]
  assert r.headers["cache-control"].startswith("no-store")


def test_jira_status(client, env):
  for path in ("/api/me/integrations/jira", "/api/me/integrations/jira/status"):
    assert client.get(path).json() == {"connected": False, "account_email": None, "cloud_id": None,
                                       "jira_url": None, "scopes": [], "expires_at": None,
                                       "status": "disconnected"}
  env["integration"] = {"status": "connected", "email": "a@b.c", "site_url": "https://s",
                        "scopes": "read write", "cloud_id": "c1", "expires_at": 12.5}
  body = client.get("/api/me/integrations/jira").json()
  assert body["connected"] is True and body["scopes"] == ["read", "write"]
  assert body["account_email"] == "a@b.c" and body["jira_url"] == "https://s" and body["expires_at"] == 12.5
  env["integration"] = {"status": "connected", "scopes": ["x"]}
  assert client.get("/api/me/integrations/jira").json()["scopes"] == ["x"]


def test_jira_disconnect(client, env):
  r = client.delete("/api/me/integrations/jira")
  assert r.status_code == 200 and r.json() == {"ok": True, "status": "disconnected"}
  assert env["deleted_integration"] is True
  env["reg"].jira.disconnect_exc = RuntimeError("revoke failed")
  env["deleted_integration"] = False
  r = client.delete("/api/me/integrations/jira/conn-1")
  assert r.status_code == 200 and env["deleted_integration"] is True


def test_mcp_servers_crud(client, env, monkeypatch):
  monkeypatch.setattr(mod, "validate_mcp_endpoint_url", lambda url, resolve_dns=False: url.startswith("https://"))
  assert client.get("/api/me/mcp-servers").json() == []
  assert client.post("/api/me/mcp-servers", json={"name": "s", "endpoint_url": "http://127.0.0.1"}).status_code == 400
  assert client.post("/api/me/mcp-servers", json={"name": "", "endpoint_url": "https://x"}).status_code == 422
  r = client.post("/api/me/mcp-servers", json={"name": "s", "endpoint_url": "https://mcp.example.com",
                                                "allowed_tools": ["t1"]})
  assert r.status_code == 200
  sid = r.json()["id"]
  assert r.json()["allowed_tools"] == ["t1"] and "_user" not in r.json()
  assert [s["id"] for s in client.get("/api/me/mcp-servers").json()] == [sid]

  assert client.patch(f"/api/me/mcp-servers/{sid}", json={"endpoint_url": "ftp://bad"}).status_code == 400
  r = client.patch(f"/api/me/mcp-servers/{sid}", json={"name": "renamed"})
  assert r.status_code == 200 and r.json()["name"] == "renamed"
  assert client.patch("/api/me/mcp-servers/missing", json={"name": "x"}).status_code == 404

  r = client.post(f"/api/me/mcp-servers/{sid}/test")
  assert r.json() == {"ok": True, "status": "connected", "endpoint_url": "https://mcp.example.com"}
  env["repo"].servers[sid]["endpoint_url"] = "http://internal"
  r = client.post(f"/api/me/mcp-servers/{sid}/test")
  assert r.json()["ok"] is False and r.json()["status"] == "error"
  assert env["repo"].status_updates == [(sid, "connected"), (sid, "error")]
  assert client.post("/api/me/mcp-servers/missing/test").status_code == 404

  assert client.delete(f"/api/me/mcp-servers/{sid}").json() == {"ok": True, "deleted_id": sid}
  assert client.delete(f"/api/me/mcp-servers/{sid}").status_code == 404
