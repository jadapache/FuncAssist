"""Jira integration: pure helpers, personal OAuth flow and API reads with httpx mocked."""

from __future__ import annotations

import time

import httpx
import pytest

from app.integrations.base import AuthMethod, ConnectionStatus
from app.integrations.jira import integration as jira

REAL_CLIENT = httpx.AsyncClient
OAUTH_CFG = {"configured": True, "client_id": "cid", "client_secret": "sec", "redirect_uri": "http://x/cb"}
OAUTH = {
  "auth_method": "oauth", "access_token": "at", "refresh_token": "rt", "cloud_id": "cl",
  "expires_at": time.time() + 3600, "site_url": "https://acme.atlassian.net", "account_email": "a@b.co",
}
U = "u1"


@pytest.fixture
def store(monkeypatch):
  """Only per-user connections exist: Jira has no organization-level connection."""
  users: dict = {}
  monkeypatch.setattr(jira, "load_user_integration", lambda uid, _id: dict(users[(uid, _id)]) if users.get((uid, _id)) else None)
  monkeypatch.setattr(jira, "save_user_integration", lambda uid, _id, p: users.__setitem__((uid, _id), dict(p)))
  monkeypatch.setattr(jira, "delete_user_integration", lambda uid, _id: users.pop((uid, _id), None))
  monkeypatch.setattr(jira, "get_jira_oauth_config", lambda: OAUTH_CFG)
  return type("Store", (), {"users": users})


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


def test_default_oauth_scopes_are_read_only():
  """SEC-05: least privilege. No default scope may grant write or admin access."""
  for scope in jira.JIRA_OAUTH_SCOPES_CORE:
    assert not scope.startswith(("write:", "manage:", "delete:", "admin:")), scope
  assert all(s.startswith("read:") or s == "offline_access" for s in jira.get_jira_oauth_scopes())


@pytest.mark.parametrize(
  "data,expected",
  [
    (None, False),
    (OAUTH, True),
    ({"auth_method": "oauth", "access_token": "x"}, False),
    ({"auth_method": "other"}, False),
    ({"auth_method": "pat", "pat_token": "x", "account_email": "a@b.co", "site_url": "https://x"}, False),
  ],
)
def test_is_connected(data, expected):
  assert jira.JiraIntegration()._is_connected(data) is expected


def test_personal_access_tokens_are_not_supported():
  integ = jira.JiraIntegration()
  assert not hasattr(integ, "connect_with_pat")
  assert not hasattr(AuthMethod, "PERSONAL_ACCESS_TOKEN")
  assert [m.value for m in integ.get_info().auth_methods] == ["oauth"]


def test_info_and_default_jql(store):
  integ = jira.JiraIntegration()
  assert integ.get_info().status == ConnectionStatus.NOT_CONNECTED
  assert integ.get_info(user_id=U).status == ConnectionStatus.NOT_CONNECTED
  assert {c.value for c in integ.get_capabilities()} == {"get_issues", "get_projects", "get_sprints"}

  store.users[(U, "jira")] = {**OAUTH, "selected_project_keys": ["AAA"]}
  info = integ.get_info(user_id=U)
  assert info.status == ConnectionStatus.CONNECTED and info.account_label == "a@b.co"
  assert integ.selected_project_keys(U) == ["AAA"]
  assert integ._default_jql(U).startswith("project = AAA")

  store.users[(U, "jira")]["selected_project_keys"] = ["AAA", "BBB"]
  assert "project in (AAA, BBB)" in integ._default_jql(U)
  assert integ._default_jql().startswith("updated >= -14d")


def test_a_user_never_sees_another_users_connection(store):
  integ = jira.JiraIntegration()
  store.users[(U, "jira")] = {**OAUTH, "selected_project_keys": ["AAA"]}
  assert integ.get_info(user_id="someone-else").status == ConnectionStatus.NOT_CONNECTED
  assert integ.selected_project_keys("someone-else") == []
  assert integ._resolve_connection_data(None) is None


# ----------------------------------------------------------------- OAuth


@pytest.mark.asyncio
async def test_start_oauth_requires_a_user(store, monkeypatch):
  integ = jira.JiraIntegration()
  with pytest.raises(ValueError, match="personal"):
    await integ.start_oauth()

  res = await integ.start_oauth(user_id=U)
  assert res.state.startswith(f"{U}::") and store.users[(U, "jira")]["status"] == "pending_oauth"
  assert "client_id=cid" in res.authorization_url
  assert jira.JiraIntegration.user_id_from_state(res.state) == U

  monkeypatch.setattr(jira, "get_jira_oauth_config", lambda: {"configured": False})
  with pytest.raises(ValueError, match="not configured"):
    await integ.start_oauth(user_id=U)


@pytest.mark.parametrize("state,expected", [("u1::123::abc", "u1"), ("", None), (None, None), ("bogus", None), ("::1::x", None)])
def test_user_id_from_state(state, expected):
  assert jira.JiraIntegration.user_id_from_state(state) == expected


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
async def test_oauth_callback_saves_a_personal_connection(store, monkeypatch):
  integ = jira.JiraIntegration()
  res = await integ.start_oauth(user_id=U)
  mock_http(monkeypatch, _oauth_handler())
  info = await integ.handle_oauth_callback("code", res.state)
  assert info.status == ConnectionStatus.CONNECTED and info.account_label == "a@b.co"
  saved = store.users[(U, "jira")]
  assert saved["cloud_id"] == "cl" and saved["selected_project_keys"] == ["ACME"]
  # the state is consumed: replaying it fails
  with pytest.raises(ValueError, match="Invalid OAuth state"):
    await integ.handle_oauth_callback("code", res.state)


@pytest.mark.asyncio
async def test_oauth_callback_errors(store, monkeypatch):
  integ = jira.JiraIntegration()
  res = await integ.start_oauth(user_id=U)
  mock_http(monkeypatch, _oauth_handler(me_status=500))
  info = await integ.handle_oauth_callback("code", res.state)
  assert store.users[(U, "jira")]["cloud_id"] == "cl" and info.status == ConnectionStatus.CONNECTED

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


@pytest.mark.parametrize("state", ["bogus", "u5::notanint::abc", "::123::abc", ""])
@pytest.mark.asyncio
async def test_oauth_callback_rejects_states_without_a_user(store, state):
  with pytest.raises(ValueError, match="Invalid OAuth state"):
    await jira.JiraIntegration().handle_oauth_callback("code", state)


@pytest.mark.asyncio
async def test_oauth_callback_rejects_forged_state_for_another_user(store):
  integ = jira.JiraIntegration()
  await integ.start_oauth(user_id=U)  # u1 has a pending state; an attacker forges one for u1
  forged = f"{U}::{int(time.time())}::forged"
  with pytest.raises(ValueError, match="Invalid OAuth state"):
    await integ.handle_oauth_callback("code", forged)


# ----------------------------------------------------------------- selection


@pytest.mark.asyncio
async def test_update_selected_projects_and_disconnect(store):
  integ = jira.JiraIntegration()
  with pytest.raises(ValueError, match="not connected"):
    await integ.update_selected_projects(["a"], user_id=U)
  with pytest.raises(ValueError):  # a user is required
    await integ.update_selected_projects(["a"])

  store.users[(U, "jira")] = dict(OAUTH)
  info = await integ.update_selected_projects([" aaa ", "", "bbb"], user_id=U)
  assert info.details["selected_project_keys"] == ["AAA", "BBB"]
  await integ.update_selected_projects(["ccc"], user_id=U)
  assert store.users[(U, "jira")]["selected_project_keys"] == ["CCC"]

  with pytest.raises(ValueError, match="personal"):
    await integ.disconnect()
  await integ.disconnect(user_id=U)
  assert (U, "jira") not in store.users


@pytest.mark.asyncio
async def test_auto_select_projects_edge_cases(store, monkeypatch):
  integ = jira.JiraIntegration()
  store.users[(U, "jira")] = {**OAUTH, "selected_project_keys": ["KEEP"]}
  await integ.auto_select_projects_from_url("https://acme.atlassian.net", user_id=U)  # already selected
  assert store.users[(U, "jira")]["selected_project_keys"] == ["KEEP"]

  store.users[(U, "jira")] = dict(OAUTH)
  await integ.auto_select_projects_from_url("https://example.com", user_id=U)  # no hint
  assert "selected_project_keys" not in store.users[(U, "jira")]

  mock_http(monkeypatch, lambda req: httpx.Response(500))
  await integ.auto_select_projects_from_url("https://acme.atlassian.net", user_id=U)  # swallowed error
  assert "selected_project_keys" not in store.users[(U, "jira")]

  mock_http(monkeypatch, _oauth_handler())
  await integ.auto_select_projects_from_url("https://acme.atlassian.net", user_id=U)
  assert store.users[(U, "jira")]["selected_project_keys"] == ["ACME"]


# ----------------------------------------------------------------- auth / reads


@pytest.mark.asyncio
async def test_authenticate_variants(store):
  integ = jira.JiraIntegration()
  assert await integ.authenticate() is False  # no user, no connection
  assert await integ.authenticate(user_id=U) is False
  store.users[(U, "jira")] = {"auth_method": "other"}
  assert await integ.authenticate(user_id=U) is False
  store.users[(U, "jira")] = {"auth_method": "pat", "pat_token": "x"}
  assert await integ.authenticate(user_id=U) is False  # PATs are not a connection
  store.users[(U, "jira")] = dict(OAUTH)
  assert await integ.authenticate(user_id=U) is True
  assert await integ.authenticate(user_id="someone-else") is False
  store.users[(U, "jira")] = {"auth_method": "oauth", "expires_at": 0, "access_token": "old"}
  with pytest.raises(ValueError, match="no refresh token"):
    await integ.authenticate(user_id=U)


@pytest.mark.asyncio
async def test_refresh_token_persists_for_the_user(store, monkeypatch):
  integ = jira.JiraIntegration()
  mock_http(monkeypatch, lambda req: httpx.Response(200, json={"access_token": "new", "refresh_token": "rt2", "expires_in": 3600}))
  expired = {**OAUTH, "expires_at": 0}
  store.users[(U, "jira")] = dict(expired)
  data = await integ._ensure_fresh_oauth_token(dict(expired), user_id=U)
  assert data["access_token"] == "new" and store.users[(U, "jira")]["refresh_token"] == "rt2"
  with pytest.raises(ValueError, match="personal"):
    await integ._ensure_fresh_oauth_token(dict(expired))
  fresh = {**OAUTH}
  assert await integ._ensure_fresh_oauth_token(fresh) is fresh


@pytest.mark.asyncio
async def test_test_connection(store, monkeypatch):
  integ = jira.JiraIntegration()
  assert (await integ.test_connection()).message == "Jira is not connected."
  assert (await integ.test_connection(user_id=U)).message == "Jira is not connected."

  store.users[(U, "jira")] = dict(OAUTH)
  paths = []

  def handler(req: httpx.Request):
    paths.append(req.url.path)
    return httpx.Response(200, json={"displayName": "Ana"})

  mock_http(monkeypatch, handler)
  res = await integ.test_connection(user_id=U)
  assert res.ok and "OAuth" in res.message and res.details["account"] == "Ana"
  assert paths == ["/ex/jira/cl/rest/api/3/myself"]

  mock_http(monkeypatch, lambda req: httpx.Response(500))
  assert (await integ.test_connection(user_id=U)).ok is False


@pytest.mark.asyncio
async def test_projects_and_issues(store, monkeypatch):
  integ = jira.JiraIntegration()
  with pytest.raises(ValueError, match="not connected"):
    await integ.get_projects(user_id=U)

  store.users[(U, "jira")] = {**OAUTH, "selected_project_keys": ["AAA"]}
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
  projects = await integ.get_projects(user_id=U)
  assert [(p["key"], p["selected"]) for p in projects] == [("aaa", True), ("BBB", False)]

  issues = await integ.get_issues(user_id=U)
  assert seen["jql"].startswith("project = AAA")
  assert issues[0]["description"] == "desc" and issues[0]["assignee"] == "e@x" and issues[0]["type"] == "Bug"
  assert issues[1]["description"] == "plain" and issues[2]["labels"] == []
  await integ.get_issues(jql="assignee = me", user_id=U)
  assert seen["jql"] == "assignee = me"


@pytest.mark.asyncio
async def test_reads_use_the_callers_own_token(store, monkeypatch):
  """Two users with different Jira accounts must each reach Jira with their own token."""
  integ = jira.JiraIntegration()
  store.users[("alice", "jira")] = {**OAUTH, "access_token": "alice-token", "cloud_id": "alice-cloud"}
  store.users[("bob", "jira")] = {**OAUTH, "access_token": "bob-token", "cloud_id": "bob-cloud"}
  seen = []

  def handler(req: httpx.Request):
    seen.append((req.url.path, req.headers["authorization"]))
    return httpx.Response(200, json={"values": []})

  mock_http(monkeypatch, handler)
  await integ.get_projects(user_id="alice")
  await integ.get_projects(user_id="bob")
  assert seen[0] == ("/ex/jira/alice-cloud/rest/api/3/project/search", "Bearer alice-token")
  assert seen[1] == ("/ex/jira/bob-cloud/rest/api/3/project/search", "Bearer bob-token")


@pytest.mark.asyncio
async def test_sprints_oauth(store, monkeypatch):
  integ = jira.JiraIntegration()
  store.users[(U, "jira")] = dict(OAUTH)

  def handler(req: httpx.Request):
    path = req.url.path
    if path.endswith("/board"):
      return httpx.Response(200, json={"values": [{"id": 1, "name": "B1"}, {"name": "no id"}, {"id": 2, "name": "B2"}]})
    if "/board/1/" in path:
      return httpx.Response(200, json={"values": [{"id": 10, "name": "S1", "state": "active"}]})
    return httpx.Response(500)

  mock_http(monkeypatch, handler)
  sprints = await integ.get_sprints(user_id=U)
  assert [(s["id"], s["board_name"]) for s in sprints] == [(10, "B1")]

  mock_http(monkeypatch, lambda req: httpx.Response(500))
  assert await integ.get_sprints(user_id=U) == []
