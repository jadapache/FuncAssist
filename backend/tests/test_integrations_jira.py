"""Jira integration: pure helpers, OAuth/PAT flows and API reads with httpx mocked."""

from __future__ import annotations

import time

import httpx
import pytest

from app.integrations.base import ConnectionStatus
from app.integrations.jira import integration as jira

REAL_CLIENT = httpx.AsyncClient
OAUTH_CFG = {"configured": True, "client_id": "cid", "client_secret": "sec", "redirect_uri": "http://x/cb"}
PAT = {
  "auth_method": "pat", "pat_token": "tk", "account_email": "a@b.co",
  "site_url": "https://acme.atlassian.net",
}
OAUTH = {
  "auth_method": "oauth", "access_token": "at", "refresh_token": "rt", "cloud_id": "cl",
  "expires_at": time.time() + 3600, "site_url": "https://acme.atlassian.net",
}


@pytest.fixture
def store(monkeypatch):
  org: dict = {}
  users: dict = {}
  monkeypatch.setattr(jira, "load_connection", lambda _id: dict(org[_id]) if org.get(_id) else None)
  monkeypatch.setattr(jira, "save_connection", lambda _id, p: org.__setitem__(_id, dict(p)))
  monkeypatch.setattr(jira, "delete_connection", lambda _id: org.pop(_id, None))
  monkeypatch.setattr(jira, "load_user_integration", lambda uid, _id: dict(users[(uid, _id)]) if users.get((uid, _id)) else None)
  monkeypatch.setattr(jira, "save_user_integration", lambda uid, _id, p: users.__setitem__((uid, _id), dict(p)))
  monkeypatch.setattr(jira, "delete_user_integration", lambda uid, _id: users.pop((uid, _id), None))
  monkeypatch.setattr(jira, "get_jira_oauth_config", lambda: OAUTH_CFG)
  return type("Store", (), {"org": org, "users": users})


def mock_http(monkeypatch, handler):
  monkeypatch.setattr(jira.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw))


# ----------------------------------------------------------------- pure helpers


@pytest.mark.parametrize(
  "url,hint",
  [
    ("", None),
    ("https://acme.atlassian.net/browse/abc-12", "ABC"),
    ("https://acme.atlassian.net/jira/software/projects/xyz/boards/1", "XYZ"),
    ("https://acme.atlassian.net/other", "ACME"),
    ("https://example.com/none", None),
  ],
)
def test_infer_project_hint(url, hint):
  assert jira.infer_project_hint_from_url(url) == hint


def test_match_project_for_hint():
  projects = [{"key": "AAA", "name": "Alpha"}, {"key": "BBB", "name": "Beta Platform"}]
  assert jira.match_project_for_hint(projects, "bbb")["key"] == "BBB"
  assert jira.match_project_for_hint(projects, "platform")["key"] == "BBB"
  assert jira.match_project_for_hint(projects, "zzz") is None


def test_adf_to_text():
  doc = {"type": "doc", "content": [
    {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}, {"type": "text", "text": "world"}]},
    {"type": "paragraph", "content": []},
    {"type": "paragraph", "content": [{"type": "text"}]},
  ]}
  assert jira._adf_to_text(doc) == "Hello world"
  assert jira._adf_to_text(None) == "" and jira._adf_to_text("x") == "x" and jira._adf_to_text(5) == ""
  assert jira._adf_to_text([{"type": "text", "text": "a"}, "b"]) == "a b"


def test_oauth_scopes_with_extra(monkeypatch):
  from types import SimpleNamespace

  monkeypatch.setattr("app.core.settings.get_settings", lambda: SimpleNamespace(jira_oauth_extra_scopes="read:jira-user offline_access"))
  assert jira.get_jira_oauth_scopes() == ["read:jira-work", "offline_access", "read:jira-user"]
  monkeypatch.setattr("app.core.settings.get_settings", lambda: SimpleNamespace(jira_oauth_extra_scopes=""))
  assert jira.get_jira_oauth_scopes() == jira.JIRA_OAUTH_SCOPES_CORE


@pytest.mark.parametrize(
  "data,expected",
  [
    (None, False),
    (PAT, True),
    ({**PAT, "site_url": ""}, False),
    (OAUTH, True),
    ({"auth_method": "oauth", "access_token": "x"}, False),
    ({"auth_method": "other"}, False),
  ],
)
def test_is_connected(data, expected):
  assert jira.JiraIntegration()._is_connected(data) is expected


def test_info_and_default_jql(store):
  integ = jira.JiraIntegration()
  assert integ.get_info().status == ConnectionStatus.NOT_CONNECTED
  assert {c.value for c in integ.get_capabilities()} == {"get_issues", "get_projects", "get_sprints"}

  store.users[("u1", "jira")] = {**PAT, "selected_project_keys": ["AAA"]}
  info = integ.get_info(user_id="u1")
  assert info.status == ConnectionStatus.CONNECTED and info.account_label == "a@b.co"
  assert integ.selected_project_keys("u1") == ["AAA"]
  assert integ._default_jql("u1").startswith("project = AAA")

  store.users[("u1", "jira")]["selected_project_keys"] = ["AAA", "BBB"]
  assert "project in (AAA, BBB)" in integ._default_jql("u1")
  assert integ._default_jql().startswith("updated >= -14d")
  # user without a personal connection falls back to the organization one
  store.org["jira"] = dict(PAT)
  assert integ.get_info(user_id="nobody").status == ConnectionStatus.CONNECTED


# ----------------------------------------------------------------- OAuth


@pytest.mark.asyncio
async def test_start_oauth_org_and_user(store, monkeypatch):
  integ = jira.JiraIntegration()
  res = await integ.start_oauth()
  assert store.org["jira"]["oauth_state"] == res.state and "::" not in res.state
  assert "client_id=cid" in res.authorization_url

  res = await integ.start_oauth(user_id="u1")
  assert res.state.startswith("u1::") and store.users[("u1", "jira")]["status"] == "pending_oauth"

  monkeypatch.setattr(jira, "get_jira_oauth_config", lambda: {"configured": False})
  with pytest.raises(ValueError, match="not configured"):
    await integ.start_oauth()


def _oauth_handler(resources=None, me_status=200, token_status=200):
  def handler(req: httpx.Request):
    url = str(req.url)
    if url == jira.ATLASSIAN_TOKEN_URL:
      return httpx.Response(token_status, json={"access_token": "at", "refresh_token": "rt", "expires_in": 100}, text="x" if token_status >= 400 else None)
    if url == jira.ATLASSIAN_RESOURCES_URL:
      return httpx.Response(200, json=[{"id": "cl", "name": "Acme", "url": "https://acme.atlassian.net"}] if resources is None else resources)
    if url == jira.ATLASSIAN_ME_URL:
      return httpx.Response(me_status, json={"email": "a@b.co", "name": "Ana"})
    if "project/search" in url:
      return httpx.Response(200, json={"values": [{"key": "ACME", "name": "Acme"}]})
    return httpx.Response(404)

  return handler


@pytest.mark.asyncio
async def test_oauth_callback_org_flow(store, monkeypatch):
  integ = jira.JiraIntegration()
  with pytest.raises(ValueError, match="Invalid OAuth state"):
    await integ.handle_oauth_callback("c", "bogus")

  res = await integ.start_oauth()
  mock_http(monkeypatch, _oauth_handler())
  info = await integ.handle_oauth_callback("code", res.state)
  assert info.status == ConnectionStatus.CONNECTED and info.account_label == "a@b.co"
  saved = store.org["jira"]
  assert saved["cloud_id"] == "cl" and saved["selected_project_keys"] == ["ACME"]
  # state is consumed: replaying it fails
  with pytest.raises(ValueError, match="Invalid OAuth state"):
    await integ.handle_oauth_callback("code", res.state)


@pytest.mark.asyncio
async def test_oauth_callback_user_flow_and_errors(store, monkeypatch):
  integ = jira.JiraIntegration()
  res = await integ.start_oauth(user_id="u1")
  mock_http(monkeypatch, _oauth_handler(me_status=500))
  info = await integ.handle_oauth_callback("code", res.state)
  assert ("u1", "jira") in store.users and store.users[("u1", "jira")]["cloud_id"] == "cl"
  assert info.status == ConnectionStatus.CONNECTED

  res = await integ.start_oauth(user_id="u2")
  mock_http(monkeypatch, _oauth_handler(token_status=400))
  with pytest.raises(ValueError, match="Token exchange failed"):
    await integ.handle_oauth_callback("code", res.state)

  res = await integ.start_oauth(user_id="u3")
  mock_http(monkeypatch, _oauth_handler(resources=[]))
  with pytest.raises(ValueError, match="No accessible Atlassian sites"):
    await integ.handle_oauth_callback("code", res.state)

  stale = f"u4::{int(time.time()) - 3600}::abc"
  with pytest.raises(ValueError, match="expired"):
    await integ.handle_oauth_callback("code", stale)

  # malformed timestamp -> treated as an org-level state, which does not match
  with pytest.raises(ValueError):
    await integ.handle_oauth_callback("code", "u5::notanint::abc")


# ----------------------------------------------------------------- PAT / selection


@pytest.mark.asyncio
async def test_connect_with_pat(store, monkeypatch):
  integ = jira.JiraIntegration()
  with pytest.raises(ValueError, match="requires token"):
    await integ.connect_with_pat("t", email="a@b.co")

  mock_http(monkeypatch, lambda req: httpx.Response(401))
  with pytest.raises(ValueError, match="authentication failed"):
    await integ.connect_with_pat("t", email="a@b.co", base_url="https://acme.atlassian.net")

  def ok(req: httpx.Request):
    if "myself" in req.url.path:
      assert req.headers["authorization"].startswith("Basic ")
      return httpx.Response(200, json={"displayName": "Ana"})
    return httpx.Response(200, json={"values": [{"key": "ACME", "name": "Acme"}]})

  mock_http(monkeypatch, ok)
  info = await integ.connect_with_pat("t", account_email="a@b.co", site_url="https://acme.atlassian.net/")
  assert info.status == ConnectionStatus.CONNECTED
  assert store.org["jira"]["site_name"] == "acme.atlassian.net" and store.org["jira"]["selected_project_keys"] == ["ACME"]


@pytest.mark.asyncio
async def test_update_selected_projects_and_disconnect(store):
  integ = jira.JiraIntegration()
  with pytest.raises(ValueError, match="not connected"):
    await integ.update_selected_projects(["a"])

  store.org["jira"] = dict(PAT)
  info = await integ.update_selected_projects([" aaa ", "", "bbb"])
  assert info.details["selected_project_keys"] == ["AAA", "BBB"]
  store.users[("u1", "jira")] = dict(PAT)
  await integ.update_selected_projects(["ccc"], user_id="u1")
  assert store.users[("u1", "jira")]["selected_project_keys"] == ["CCC"]

  await integ.disconnect(user_id="u1")
  assert ("u1", "jira") not in store.users and "jira" not in store.org


@pytest.mark.asyncio
async def test_auto_select_projects_edge_cases(store, monkeypatch):
  integ = jira.JiraIntegration()
  store.org["jira"] = {**PAT, "selected_project_keys": ["KEEP"]}
  await integ.auto_select_projects_from_url("https://acme.atlassian.net")  # already selected -> no-op
  assert store.org["jira"]["selected_project_keys"] == ["KEEP"]

  store.org["jira"] = dict(PAT)
  await integ.auto_select_projects_from_url("https://example.com")  # no hint
  assert "selected_project_keys" not in store.org["jira"]

  mock_http(monkeypatch, lambda req: httpx.Response(500))
  await integ.auto_select_projects_from_url("https://acme.atlassian.net")  # swallowed error
  assert "selected_project_keys" not in store.org["jira"]


# ----------------------------------------------------------------- auth / reads


@pytest.mark.asyncio
async def test_authenticate_variants(store, monkeypatch):
  integ = jira.JiraIntegration()
  assert await integ.authenticate() is False
  store.org["jira"] = dict(PAT)
  assert await integ.authenticate() is True
  store.org["jira"] = {"auth_method": "other"}
  assert await integ.authenticate() is False
  store.org["jira"] = dict(OAUTH)
  assert await integ.authenticate() is True
  store.org["jira"] = {"auth_method": "oauth", "expires_at": 0, "access_token": "old"}
  with pytest.raises(ValueError, match="no refresh token"):
    await integ.authenticate()


@pytest.mark.asyncio
async def test_refresh_token_persists(store, monkeypatch):
  integ = jira.JiraIntegration()
  mock_http(monkeypatch, lambda req: httpx.Response(200, json={"access_token": "new", "refresh_token": "rt2", "expires_in": 3600}))
  expired = {**OAUTH, "expires_at": 0}
  store.users[("u1", "jira")] = dict(expired)
  data = await integ._ensure_fresh_oauth_token(dict(expired), user_id="u1")
  assert data["access_token"] == "new" and store.users[("u1", "jira")]["refresh_token"] == "rt2"
  data = await integ._ensure_fresh_oauth_token(dict(expired))
  assert store.org["jira"]["access_token"] == "new"
  fresh = {**OAUTH}
  assert await integ._ensure_fresh_oauth_token(fresh) is fresh


@pytest.mark.asyncio
async def test_test_connection(store, monkeypatch):
  integ = jira.JiraIntegration()
  assert (await integ.test_connection()).message == "Jira is not connected."

  store.org["jira"] = dict(PAT)
  mock_http(monkeypatch, lambda req: httpx.Response(200, json={"displayName": "Ana"}))
  res = await integ.test_connection()
  assert res.ok and "PAT" in res.message and res.details["account"] == "Ana"

  store.org["jira"] = dict(OAUTH)
  paths = []

  def handler(req: httpx.Request):
    paths.append(req.url.path)
    return httpx.Response(200, json={"displayName": "Ana"})

  mock_http(monkeypatch, handler)
  res = await integ.test_connection()
  assert res.ok and "OAuth" in res.message and paths == ["/ex/jira/cl/rest/api/3/myself"]

  mock_http(monkeypatch, lambda req: httpx.Response(500))
  assert (await integ.test_connection()).ok is False


@pytest.mark.asyncio
async def test_projects_and_issues_pat(store, monkeypatch):
  integ = jira.JiraIntegration()
  with pytest.raises(ValueError, match="not connected"):
    await integ.get_projects()

  store.org["jira"] = {**PAT, "selected_project_keys": ["AAA"]}
  seen = {}

  def handler(req: httpx.Request):
    if "project/search" in req.url.path:
      return httpx.Response(200, json={"values": [{"id": "1", "key": "aaa", "name": "A"}, {"id": "2", "key": "BBB", "name": "B"}]})
    seen["jql"] = req.url.params["jql"]
    return httpx.Response(200, json={"issues": [
      {"id": "1", "key": "AAA-1", "self": "http://u", "fields": {
        "summary": "S", "status": {"name": "Open"}, "assignee": {"emailAddress": "e@x"}, "priority": {"name": "High"},
        "issuetype": {"name": "Bug"}, "labels": ["l"],
        "description": {"type": "doc", "content": [{"type": "text", "text": "desc"}]}}},
      {"id": "2", "key": "AAA-2", "fields": {"description": "plain"}},
      {"id": "3", "key": "AAA-3"},
    ]})

  mock_http(monkeypatch, handler)
  projects = await integ.get_projects()
  assert [(p["key"], p["selected"]) for p in projects] == [("aaa", True), ("BBB", False)]

  issues = await integ.get_issues()
  assert seen["jql"].startswith("project = AAA")
  assert issues[0]["description"] == "desc" and issues[0]["assignee"] == "e@x" and issues[0]["type"] == "Bug"
  assert issues[1]["description"] == "plain" and issues[2]["labels"] == []
  await integ.get_issues(jql="assignee = me")
  assert seen["jql"] == "assignee = me"


@pytest.mark.asyncio
async def test_sprints_oauth(store, monkeypatch):
  integ = jira.JiraIntegration()
  store.org["jira"] = dict(OAUTH)

  def handler(req: httpx.Request):
    path = req.url.path
    if path.endswith("/board"):
      return httpx.Response(200, json={"values": [{"id": 1, "name": "B1"}, {"name": "no id"}, {"id": 2, "name": "B2"}]})
    if "/board/1/" in path:
      return httpx.Response(200, json={"values": [{"id": 10, "name": "S1", "state": "active"}]})
    return httpx.Response(500)

  mock_http(monkeypatch, handler)
  sprints = await integ.get_sprints()
  assert [(s["id"], s["board_name"]) for s in sprints] == [(10, "B1")]

  mock_http(monkeypatch, lambda req: httpx.Response(500))
  assert await integ.get_sprints() == []
