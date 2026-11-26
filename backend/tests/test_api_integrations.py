"""HTTP tests for app/api/integrations.py with a fake integration registry."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import integrations as mod
from app.integrations.base import AuthMethod, AuthStartResponse, IntegrationInfo
from app.integrations.base import TestConnectionResult as ConnResult


def _info(iid: str, **kw) -> IntegrationInfo:
  return IntegrationInfo(id=iid, name=iid.title(), description="d", status="connected",
                         auth_methods=[], capabilities=[], **kw)


class FakeIntegration:
  def __init__(self, iid: str):
    self.id = iid
    self.raise_exc: dict[str, Exception] = {}
    self.calls: list[tuple] = []
    self.auth_ok = True

  def _maybe(self, name, *args, **kw):
    self.calls.append((name, args, kw))
    if name in self.raise_exc:
      raise self.raise_exc[name]

  def get_info(self, **kw):
    self._maybe("get_info", **kw)
    return _info(self.id, account_label=kw.get("user_id"))

  async def start_oauth(self, **kw):
    self._maybe("start_oauth", **kw)
    return AuthStartResponse(authorization_url="https://auth/x", state="s", auth_method=AuthMethod.OAUTH)

  async def handle_oauth_callback(self, code, state):
    self._maybe("handle_oauth_callback", code, state)

  def user_id_from_state(self, state):
    return f"user-of-{state}"

  async def connect_with_service_account(self, token, **kw):
    self._maybe("connect_with_service_account", token, **kw)
    return IntegrationInfo(
      id=self.id, name=self.id.title(), description="d", status="connected", auth_methods=[], capabilities=[],
      details={"scopes": ["read_api"], "expires_at": "2027-01-01"},
    )

  async def connect_with_github_app(self, app_id, private_key, **kw):
    self._maybe("connect_with_github_app", app_id, private_key, **kw)
    return IntegrationInfo(
      id=self.id, name=self.id.title(), description="d", status="connected", auth_methods=[], capabilities=[],
      details={"permissions": {"contents": "read", "metadata": "read"}},
    )

  async def authenticate(self, **kw):
    self._maybe("authenticate", **kw)
    return self.auth_ok

  async def test_connection(self, **kw):
    self._maybe("test_connection", **kw)
    return ConnResult(ok=True, message="ok", details=kw)

  async def disconnect(self, **kw):
    self._maybe("disconnect", **kw)

  async def get_projects(self, **kw):
    self._maybe("get_projects", **kw)
    return [{"key": "P"}]

  async def update_selected_projects(self, projects, **kw):
    self._maybe("update_selected_projects", projects, **kw)
    return _info(self.id)

  async def auto_select_projects_from_url(self, url, **kw):
    self._maybe("auto_select_projects_from_url", url, **kw)

  async def get_issues(self, **kw):
    self._maybe("get_issues", **kw)
    return [{"key": "I-1"}]

  async def get_sprints(self, **kw):
    self._maybe("get_sprints", **kw)
    return [{"id": 1}]

  async def get_repositories(self):
    self._maybe("get_repositories")
    return ["a/b"]

  async def update_selected_repos(self, repos):
    self._maybe("update_selected_repos", repos)
    return _info(self.id)

  async def get_pull_requests(self, **kw):
    self._maybe("get_pull_requests", **kw)
    return [{"n": 1}]

  async def get_commits(self, **kw):
    self._maybe("get_commits", **kw)
    return [{"sha": "x"}]

  async def get_files_changed(self, **kw):
    self._maybe("get_files_changed", **kw)
    return ["f.py"]


class FakeRegistry:
  def __init__(self):
    self.items = {k: FakeIntegration(k) for k in ("jira", "github", "gitlab", "notion")}

  def get(self, iid):
    if iid not in self.items:
      raise KeyError(f"Unknown integration: {iid}")
    return self.items[iid]

  def list_info(self):
    return [i.get_info() for i in self.items.values()]


@pytest.fixture
def reg(monkeypatch):
  r = FakeRegistry()
  monkeypatch.setattr(mod, "registry", r)
  state = {"sync_calls": [], "sync_exc": None, "cache": None}

  async def fake_sync(iid, user_id=None):
    state["sync_calls"].append((iid, user_id))
    if state["sync_exc"]:
      raise state["sync_exc"]
    return {"integration": iid, "synced": True}

  async def fake_cache(iid, user_id=None):
    return state["cache"]

  monkeypatch.setattr(mod, "sync_integration", fake_sync)
  monkeypatch.setattr(mod, "load_sync_cache", fake_cache)
  r.state = state
  return r


@pytest.fixture
def client(reg):
  app = FastAPI()
  app.include_router(mod.router, prefix="/api")
  return TestClient(app, base_url="https://testserver", follow_redirects=False)


def test_list_and_auth_methods(client):
  r = client.get("/api/integrations")
  assert r.status_code == 200
  assert {i["id"] for i in r.json()} == {"jira", "github", "gitlab", "notion"}
  r = client.get("/api/integrations/auth-methods")
  assert r.status_code == 200 and r.json()["methods"] == ["oauth"]


@pytest.mark.parametrize("iid", ["github", "gitlab"])
def test_github_and_gitlab_have_no_oauth_callback(client, reg, iid):
  assert client.get(f"/api/integrations/{iid}/callback", params={"code": "c", "state": "s"}).status_code == 404
  assert not any(name == "handle_oauth_callback" for name, *_ in reg.items[iid].calls)


@pytest.mark.parametrize("iid", ["jira"])
def test_oauth_callbacks(client, reg, iid):
  base = f"/api/integrations/{iid}/callback"
  r = client.get(base, params={"error": "denied x"})
  assert r.status_code == 307
  assert f"{iid}=error" in r.headers["location"] and "denied%20x" in r.headers["location"]
  r = client.get(base, params={"code": "c"})
  assert "missing_code" in r.headers["location"]
  r = client.get(base, params={"code": "c", "state": "s"})
  assert r.headers["location"].endswith(f"{iid}=connected")
  assert reg.state["sync_calls"][-1][0] == iid
  # Jira is personal: the sync runs for the user the OAuth state belongs to. GitHub and GitLab are shared.
  assert reg.state["sync_calls"][-1][1] == ("user-of-s" if iid == "jira" else None)
  reg.items[iid].raise_exc["handle_oauth_callback"] = RuntimeError("bad token")
  r = client.get(base, params={"code": "c", "state": "s"})
  assert "bad%20token" in r.headers["location"]


def test_get_integration(client, reg):
  r = client.get("/api/integrations/jira")
  assert r.status_code == 200 and r.json()["account_label"] == "test-user-id"
  r = client.get("/api/integrations/github")
  assert r.status_code == 200 and r.json()["account_label"] is None
  assert client.get("/api/integrations/nope").status_code == 404


def test_start_oauth(client, reg):
  r = client.post("/api/integrations/jira/oauth/start")
  assert r.status_code == 200 and r.json()["authorization_url"] == "https://auth/x"
  assert reg.items["jira"].calls[-1][2] == {"user_id": "test-user-id"}
  reg.items["jira"].raise_exc["start_oauth"] = ValueError("not configured")
  assert client.post("/api/integrations/jira/oauth/start").status_code == 400
  reg.items["jira"].raise_exc["start_oauth"] = NotImplementedError("no oauth")
  assert client.post("/api/integrations/jira/oauth/start").status_code == 501


@pytest.mark.parametrize("iid", ["github", "gitlab", "notion", "nope"])
def test_only_jira_uses_oauth(client, reg, iid):
  """GitHub and GitLab connect through service accounts; OAuth is never started for them."""
  r = client.post(f"/api/integrations/{iid}/oauth/start")
  assert r.status_code == 501 and "service accounts" in r.json()["detail"]
  assert not any(name == "start_oauth" for item in reg.items.values() for name, *_ in item.calls)


@pytest.fixture
def regular_client(client):
  """The same app, but the caller is a regular user instead of an administrator."""
  from app.api.deps import get_current_user

  client.app.dependency_overrides[get_current_user] = lambda: {"id": "regular-user", "role": "user"}
  return client


@pytest.mark.parametrize("iid", ["github", "gitlab", "notion"])
def test_organization_integrations_require_an_administrator(regular_client, reg, iid):
  assert regular_client.post(f"/api/integrations/{iid}/oauth/start").status_code == 403
  assert regular_client.post(f"/api/integrations/{iid}/disconnect").status_code == 403
  if iid != "notion":
    assert regular_client.put(f"/api/integrations/{iid}/repositories", json={"selected_repos": ["a/b"]}).status_code == 403
  # nothing reached the adapter
  assert reg.items[iid].calls == []


@pytest.mark.parametrize("iid", ["github", "gitlab"])
def test_administrators_manage_organization_integrations(client, reg, iid):
  assert client.put(f"/api/integrations/{iid}/repositories", json={"selected_repos": ["a/b"]}).status_code == 200
  assert client.post(f"/api/integrations/{iid}/disconnect").status_code == 200


def test_regular_users_connect_their_own_jira(regular_client, reg):
  assert regular_client.post("/api/integrations/jira/oauth/start").status_code == 200
  assert reg.items["jira"].calls[-1][2] == {"user_id": "regular-user"}
  assert regular_client.post("/api/integrations/jira/disconnect").status_code == 200


def test_regular_users_can_still_read_organization_integrations(regular_client, reg):
  assert regular_client.get("/api/integrations/github").status_code == 200
  assert regular_client.get("/api/integrations/github/repositories").status_code == 200
  assert regular_client.post("/api/integrations/github/test").status_code == 200


def test_administrators_connect_gitlab_with_a_service_account(client, reg):
  r = client.post("/api/integrations/gitlab/service-account", json={
    "token": "glpat-x", "base_url": "https://git.corp.io", "selected_repos": ["g/p"],
  })
  assert r.status_code == 200 and r.json()["details"]["scopes"] == ["read_api"]
  name, args, kwargs = reg.items["gitlab"].calls[-1]
  assert name == "connect_with_service_account" and args == ("glpat-x",)
  assert kwargs == {"base_url": "https://git.corp.io", "selected_repos": ["g/p"], "configured_by": "test-user-id"}
  assert reg.state["sync_calls"][-1][0] == "gitlab"


def test_the_service_account_connection_is_recorded_without_the_token(client, reg):
  from app.ai import logging as ai_logging

  client.post("/api/integrations/gitlab/service-account", json={"token": "glpat-super-secret"})
  events = ai_logging.list_security_events(kind="service_account_connected")
  assert events and events[0]["admin"] == "test-user-id" and events[0]["provider"] == "gitlab"
  assert events[0]["scopes"] == ["read_api"] and "glpat-super-secret" not in str(events)


def test_a_rejected_credential_is_reported(client, reg):
  reg.items["gitlab"].raise_exc["connect_with_service_account"] = ValueError("more access than needed: api")
  r = client.post("/api/integrations/gitlab/service-account", json={"token": "glpat-x"})
  assert r.status_code == 400 and "more access" in r.json()["detail"]
  assert reg.state["sync_calls"] == []


def test_a_failing_sync_does_not_undo_the_connection(client, reg):
  reg.state["sync_exc"] = RuntimeError("redis down")
  assert client.post("/api/integrations/gitlab/service-account", json={"token": "glpat-x"}).status_code == 200


def test_regular_users_cannot_connect_service_accounts(regular_client, reg):
  r = regular_client.post("/api/integrations/gitlab/service-account", json={"token": "glpat-x"})
  assert r.status_code == 403
  assert reg.items["gitlab"].calls == []


@pytest.mark.parametrize("iid,status", [("jira", 501), ("notion", 501), ("nope", 404)])
def test_token_service_accounts_are_only_available_for_gitlab(client, reg, iid, status):
  assert client.post(f"/api/integrations/{iid}/service-account", json={"token": "t"}).status_code == status


GITHUB_APP = {
  "app_id": "12345",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----",
}
APP_PERMISSIONS = {"contents": "read", "metadata": "read"}


def test_administrators_connect_github_with_a_github_app(client, reg):
  r = client.post("/api/integrations/github/service-account",
                  json={**GITHUB_APP, "installation_id": "99", "selected_repos": ["o/r"]})
  assert r.status_code == 200 and r.json()["details"]["permissions"] == APP_PERMISSIONS
  name, args, kwargs = reg.items["github"].calls[-1]
  assert name == "connect_with_github_app" and args == ("12345", GITHUB_APP["private_key"])
  assert kwargs == {"installation_id": "99", "selected_repos": ["o/r"], "configured_by": "test-user-id"}
  assert reg.state["sync_calls"][-1][0] == "github"


def test_the_github_app_connection_is_recorded_without_the_private_key(client, reg):
  from app.ai import logging as ai_logging

  client.post("/api/integrations/github/service-account", json=GITHUB_APP)
  events = ai_logging.list_security_events(kind="service_account_connected")
  assert events and events[0]["provider"] == "github" and events[0]["permissions"] == APP_PERMISSIONS
  assert "PRIVATE KEY" not in str(events)


def test_a_github_app_with_write_access_is_reported(client, reg):
  reg.items["github"].raise_exc["connect_with_github_app"] = ValueError("write or admin access: contents")
  r = client.post("/api/integrations/github/service-account", json=GITHUB_APP)
  assert r.status_code == 400 and "write or admin" in r.json()["detail"]
  assert reg.state["sync_calls"] == []


def test_github_being_unreachable_is_a_bad_gateway(client, reg):
  import httpx

  reg.items["github"].raise_exc["connect_with_github_app"] = httpx.ConnectError("down")
  assert client.post("/api/integrations/github/service-account", json=GITHUB_APP).status_code == 502


def test_regular_users_cannot_connect_a_github_app(regular_client, reg):
  assert regular_client.post("/api/integrations/github/service-account", json=GITHUB_APP).status_code == 403
  assert reg.items["github"].calls == []


@pytest.mark.parametrize("payload", [{}, {"app_id": "1"}, {"private_key": "k"},
                                     {**GITHUB_APP, "private_key": "x" * 9000}])
def test_github_app_payload_is_validated(client, reg, payload):
  assert client.post("/api/integrations/github/service-account", json=payload).status_code == 422


@pytest.mark.parametrize("payload", [{}, {"token": ""}, {"token": "x" * 600}])
def test_service_account_payload_is_validated(client, reg, payload):
  assert client.post("/api/integrations/gitlab/service-account", json=payload).status_code == 422


@pytest.mark.parametrize("iid", ["jira", "github", "gitlab", "nope"])
def test_pat_endpoint_does_not_exist(client, reg, iid):
  """Personal access tokens are not a supported way to connect."""
  r = client.post(f"/api/integrations/{iid}/pat", json={"token": "t", "email": "a@b.c", "base_url": "https://x"})
  assert r.status_code in (404, 405)
  assert not any(name == "connect_with_pat" for item in reg.items.values() for name, *_ in item.calls)


def test_test_and_disconnect(client, reg):
  r = client.post("/api/integrations/jira/test")
  assert r.status_code == 200 and r.json()["details"] == {"user_id": "test-user-id"}
  assert client.post("/api/integrations/github/test").json()["ok"] is True
  assert client.post("/api/integrations/nope/test").status_code == 404
  r = client.post("/api/integrations/jira/disconnect")
  assert r.status_code == 200 and r.json()["account_label"] == "test-user-id"
  assert client.post("/api/integrations/github/disconnect").status_code == 200
  assert client.post("/api/integrations/nope/disconnect").status_code == 404


def test_projects(client, reg):
  assert client.get("/api/integrations/github/projects").status_code == 501
  r = client.get("/api/integrations/jira/projects")
  assert r.status_code == 200 and r.json() == {"projects": [{"key": "P"}]}
  reg.items["jira"].raise_exc["get_projects"] = ValueError("x")
  assert client.get("/api/integrations/jira/projects").status_code == 400
  reg.items["jira"].raise_exc["get_projects"] = KeyError("x")
  assert client.get("/api/integrations/jira/projects").status_code == 404

  assert client.put("/api/integrations/github/projects", json={"selected_projects": []}).status_code == 501
  assert client.put("/api/integrations/jira/projects", json={}).status_code == 422
  reg.state["sync_exc"] = RuntimeError("x")
  r = client.put("/api/integrations/jira/projects", json={"selected_projects": ["P"]})
  assert r.status_code == 200 and r.json()["id"] == "jira"
  reg.items["jira"].raise_exc["update_selected_projects"] = ValueError("bad")
  assert client.put("/api/integrations/jira/projects", json={"selected_projects": ["P"]}).status_code == 400
  reg.items["jira"].raise_exc["update_selected_projects"] = KeyError("bad")
  assert client.put("/api/integrations/jira/projects", json={"selected_projects": ["P"]}).status_code == 404


def test_auto_select_project(client, reg, monkeypatch):
  import app.core.storage as storage
  conn = {"value": None}
  monkeypatch.setattr(storage, "load_user_integration", lambda uid, iid: conn["value"])
  r = client.post("/api/integrations/jira/auto-select-project")
  assert r.status_code == 400 and "site URL" in r.json()["detail"]
  conn["value"] = {"site_url": "https://acme.atlassian.net/jira/software/projects/ABC"}
  reg.state["sync_exc"] = RuntimeError("x")
  r = client.post("/api/integrations/jira/auto-select-project")
  assert r.status_code == 200
  assert ("auto_select_projects_from_url", (conn["value"]["site_url"],), {"user_id": "test-user-id"}) in reg.items["jira"].calls
  del reg.items["jira"]
  assert client.post("/api/integrations/jira/auto-select-project").status_code == 404


def test_issues_and_sprints(client, reg):
  r = client.get("/api/integrations/jira/issues", params={"jql": "project=P", "max_results": 5})
  assert r.status_code == 200 and r.json()["issues"][0]["key"] == "I-1"
  assert reg.items["jira"].calls[-1][2] == {"jql": "project=P", "max_results": 5, "user_id": "test-user-id"}
  assert client.get("/api/integrations/gitlab/issues").status_code == 200
  assert client.get("/api/integrations/github/issues").status_code == 501
  for iid in ("jira", "gitlab"):
    reg.items[iid].raise_exc["get_issues"] = ValueError("x")
    assert client.get(f"/api/integrations/{iid}/issues").status_code == 400
    reg.items[iid].raise_exc["get_issues"] = KeyError("x")
    assert client.get(f"/api/integrations/{iid}/issues").status_code == 404

  assert client.get("/api/integrations/gitlab/sprints").status_code == 501
  assert client.get("/api/integrations/jira/sprints").json() == {"sprints": [{"id": 1}]}
  reg.items["jira"].raise_exc["get_sprints"] = ValueError("x")
  assert client.get("/api/integrations/jira/sprints").status_code == 400
  reg.items["jira"].raise_exc["get_sprints"] = KeyError("x")
  assert client.get("/api/integrations/jira/sprints").status_code == 404


@pytest.mark.parametrize("path,method,key,meth,body", [
  ("repositories", "get", "repositories", "get_repositories", None),
  ("repositories", "put", "id", "update_selected_repos", {"selected_repos": ["a/b"]}),
  ("pull-requests", "get", "pull_requests", "get_pull_requests", None),
  ("commits", "get", "commits", "get_commits", None),
])
def test_git_hosting_endpoints(client, reg, path, method, key, meth, body):
  def call(iid):
    kw = {"json": body} if body is not None else {}
    return getattr(client, method)(f"/api/integrations/{iid}/{path}", **kw)

  reg.state["sync_exc"] = RuntimeError("sync fails silently")
  r = call("github")
  assert r.status_code == 200 and key in r.json()
  assert call("jira").status_code == 501
  reg.items["gitlab"].raise_exc[meth] = ValueError("x")
  assert call("gitlab").status_code == 400
  reg.items["gitlab"].raise_exc[meth] = KeyError("x")
  assert call("gitlab").status_code == 404


def test_files_changed(client, reg):
  r = client.get("/api/integrations/github/files-changed", params={"pr_number": 3, "repo": "a/b"})
  assert r.status_code == 200 and r.json() == {"files": ["f.py"]}
  assert reg.items["github"].calls[-1][2] == {"pr_number": 3, "repo": "a/b"}
  assert client.get("/api/integrations/github/files-changed").status_code == 422
  assert client.get("/api/integrations/jira/files-changed", params={"pr_number": 1}).status_code == 501
  reg.items["gitlab"].raise_exc["get_files_changed"] = ValueError("x")
  assert client.get("/api/integrations/gitlab/files-changed", params={"pr_number": 1}).status_code == 400
  reg.items["gitlab"].raise_exc["get_files_changed"] = KeyError("x")
  assert client.get("/api/integrations/gitlab/files-changed", params={"pr_number": 1}).status_code == 404


def test_sync_endpoints(client, reg):
  r = client.post("/api/integrations/jira/sync")
  assert r.status_code == 200 and r.json() == {"integration": "jira", "synced": True}
  assert reg.state["sync_calls"][-1] == ("jira", "test-user-id")
  reg.state["sync_exc"] = KeyError("nope")
  assert client.post("/api/integrations/x/sync").status_code == 404
  reg.state["sync_exc"] = ValueError("not connected")
  assert client.post("/api/integrations/jira/sync").status_code == 400

  assert client.get("/api/integrations/jira/sync").status_code == 404
  reg.state["cache"] = {"items": [1]}
  r = client.get("/api/integrations/jira/sync")
  assert r.status_code == 200 and r.json() == {"items": [1]}
