"""GitHub integration with httpx mocked via MockTransport and an in-memory connection store."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.base import AuthMethod, ConnectionStatus
from app.integrations.github import integration as gh

OAUTH_CFG = {"configured": True, "client_id": "cid", "client_secret": "sec", "redirect_uri": "http://x/cb"}


@pytest.fixture
def store(monkeypatch):
  data: dict = {}
  monkeypatch.setattr(gh, "load_connection", lambda _id: dict(data[_id]) if data.get(_id) else None)
  monkeypatch.setattr(gh, "save_connection", lambda _id, payload: data.__setitem__(_id, dict(payload)))
  monkeypatch.setattr(gh, "delete_connection", lambda _id: data.pop(_id, None))
  monkeypatch.setattr(gh, "get_github_oauth_config", lambda: OAUTH_CFG)
  return data


REAL_CLIENT = httpx.AsyncClient


def mock_http(monkeypatch, handler):
  monkeypatch.setattr(
    gh.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw)
  )


def test_info_not_connected_and_connected(store):
  integ = gh.GitHubIntegration()
  info = integ.get_info()
  assert info.status == ConnectionStatus.NOT_CONNECTED and info.oauth_configured is True
  assert {c.value for c in integ.get_capabilities()} >= {"get_pull_requests", "get_commits"}

  store["github"] = {"auth_method": "oauth", "access_token": "t", "account_login": "ana", "selected_repos": ["a/b"]}
  info = integ.get_info()
  assert info.status == ConnectionStatus.CONNECTED and info.account_label == "ana"
  assert info.details["selected_repos"] == ["a/b"]


@pytest.mark.parametrize(
  "data,expected",
  [
    (None, False),
    ({"auth_method": "oauth", "access_token": "x"}, True),
    ({"auth_method": "oauth"}, False),
    ({"access_token": "x"}, False),  # a token without the OAuth method is not a connection
    ({"auth_method": "pat", "pat_token": "x"}, False),  # PATs are no longer accepted
    ({"other": 1}, False),
  ],
)
def test_is_connected(data, expected):
  assert gh.GitHubIntegration()._is_connected(data) is expected


@pytest.mark.asyncio
async def test_start_oauth(store, monkeypatch):
  res = await gh.GitHubIntegration().start_oauth()
  assert res.authorization_url.startswith(gh.GITHUB_AUTHORIZE_URL) and "client_id=cid" in res.authorization_url
  assert res.auth_method == AuthMethod.OAUTH and store["github"]["oauth_state"] == res.state

  monkeypatch.setattr(gh, "get_github_oauth_config", lambda: {"configured": False})
  with pytest.raises(ValueError, match="not configured"):
    await gh.GitHubIntegration().start_oauth()


@pytest.mark.asyncio
async def test_oauth_callback_flow(store, monkeypatch):
  integ = gh.GitHubIntegration()
  with pytest.raises(ValueError, match="Invalid OAuth state"):
    await integ.handle_oauth_callback("c", "s")

  store["github"] = {"oauth_state": "st", "selected_repos": ["a/b"]}

  def handler(req: httpx.Request):
    if req.url.host == "github.com":
      return httpx.Response(200, json={"access_token": "tok", "scope": "repo"})
    assert req.headers["authorization"] == "Bearer tok"
    return httpx.Response(200, json={"login": "ana", "name": "Ana"})

  mock_http(monkeypatch, handler)
  info = await integ.handle_oauth_callback("code", "st")
  assert info.status == ConnectionStatus.CONNECTED and info.account_label == "ana"
  assert store["github"]["access_token"] == "tok" and store["github"]["selected_repos"] == ["a/b"]
  assert store["github"]["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_oauth_callback_errors(store, monkeypatch):
  integ = gh.GitHubIntegration()
  store["github"] = {"oauth_state": "st"}
  mock_http(monkeypatch, lambda req: httpx.Response(500, text="boom"))
  with pytest.raises(ValueError, match="token exchange failed"):
    await integ.handle_oauth_callback("c", "st")

  mock_http(monkeypatch, lambda req: httpx.Response(200, json={}))
  with pytest.raises(ValueError, match="did not return an access token"):
    await integ.handle_oauth_callback("c", "st")


@pytest.mark.asyncio
async def test_disconnect_authenticate_and_test_connection(store, monkeypatch):
  integ = gh.GitHubIntegration()
  assert await integ.authenticate() is False
  res = await integ.test_connection()
  assert res.ok is False and "not connected" in res.message

  store["github"] = {"auth_method": "oauth", "access_token": "t", "selected_repos": ["a/b"]}
  assert await integ.authenticate() is True
  mock_http(monkeypatch, lambda req: httpx.Response(200, json={"login": "ana"}))
  res = await integ.test_connection()
  assert res.ok and res.details["login"] == "ana"

  mock_http(monkeypatch, lambda req: httpx.Response(403))
  assert (await integ.test_connection()).ok is False

  await integ.disconnect()
  assert "github" not in store


def test_token_selection(store):
  integ = gh.GitHubIntegration()
  with pytest.raises(ValueError):
    integ._token()
  store["github"] = {"auth_method": "oauth", "access_token": "o"}
  assert integ._token() == "o" and integ._headers()["Authorization"] == "Bearer o"
  store["github"] = {"auth_method": "pat", "pat_token": "p"}  # legacy PAT data is ignored
  with pytest.raises(ValueError):
    integ._token()
  store["github"] = {"auth_method": "oauth"}
  with pytest.raises(ValueError):
    integ._token()
  assert integ.selected_repos() == []


@pytest.mark.asyncio
async def test_update_selected_repos(store):
  integ = gh.GitHubIntegration()
  with pytest.raises(ValueError, match="not connected"):
    await integ.update_selected_repos(["a/b"])
  store["github"] = {"auth_method": "oauth", "access_token": "t"}
  info = await integ.update_selected_repos(["a/b"])
  assert info.details["selected_repos"] == ["a/b"]


@pytest.mark.asyncio
async def test_get_repositories(store, monkeypatch):
  integ = gh.GitHubIntegration()
  with pytest.raises(ValueError, match="not connected"):
    await integ.get_repositories()

  store["github"] = {"auth_method": "oauth", "access_token": "t", "selected_repos": ["a/b"]}
  seen = {}

  def handler(req: httpx.Request):
    seen["per_page"] = req.url.params["per_page"]
    return httpx.Response(200, json=[{"full_name": "a/b", "name": "b", "private": True}, {"full_name": "c/d", "name": "d"}])

  mock_http(monkeypatch, handler)
  repos = await integ.get_repositories(max_results=500)
  assert seen["per_page"] == "100"
  assert [(r["full_name"], r["selected"]) for r in repos] == [("a/b", True), ("c/d", False)]


@pytest.mark.asyncio
async def test_pull_requests_and_commits(store, monkeypatch):
  integ = gh.GitHubIntegration()
  with pytest.raises(ValueError, match="No GitHub repositories"):
    await integ.get_pull_requests()
  with pytest.raises(ValueError, match="No GitHub repositories"):
    await integ.get_commits()

  store["github"] = {"auth_method": "oauth", "access_token": "t", "selected_repos": ["a/b", "c/d"]}

  def handler(req: httpx.Request):
    parts = req.url.path.split("/")
    repo = parts[2] + "/" + parts[3]
    if req.url.path.endswith("/pulls"):
      day = "2024-02-01" if repo == "a/b" else "2024-03-01"
      return httpx.Response(200, json=[{"number": 1, "title": "T", "state": "open", "user": {"login": "u"}, "updated_at": day}])
    day = "2024-01-01" if repo == "a/b" else "2024-04-01"
    return httpx.Response(200, json=[{"sha": "abcdef123456", "commit": {"message": "first\nsecond", "author": {"name": "N", "date": day}}}])

  mock_http(monkeypatch, handler)
  prs = await integ.get_pull_requests(max_results=5)
  assert [p["repo"] for p in prs] == ["c/d", "a/b"] and prs[0]["user"] == "u"
  assert len(await integ.get_pull_requests(max_results=1)) == 1

  commits = await integ.get_commits()
  assert [c["repo"] for c in commits] == ["c/d", "a/b"]
  assert commits[0]["sha"] == "abcdef1" and commits[0]["message"] == "first" and commits[0]["author"] == "N"


@pytest.mark.asyncio
async def test_files_changed(store, monkeypatch):
  integ = gh.GitHubIntegration()
  with pytest.raises(ValueError, match="Provide a repo"):
    await integ.get_files_changed(pr_number=1)

  store["github"] = {"auth_method": "oauth", "access_token": "t", "selected_repos": ["a/b"]}
  paths = []

  def handler(req: httpx.Request):
    paths.append(req.url.path)
    return httpx.Response(200, json=[{"filename": "x.py", "status": "modified", "additions": 2, "deletions": 1, "changes": 3}])

  mock_http(monkeypatch, handler)
  files = await integ.get_files_changed(pr_number=7)
  assert paths[-1] == "/repos/a/b/pulls/7/files" and files[0]["filename"] == "x.py" and files[0]["repo"] == "a/b"
  await integ.get_files_changed(pr_number=7, repo="z/y")
  assert paths[-1] == "/repos/z/y/pulls/7/files"


def test_personal_access_tokens_are_not_supported():
  integ = gh.GitHubIntegration()
  assert not hasattr(integ, "connect_with_pat")
  assert not hasattr(AuthMethod, "PERSONAL_ACCESS_TOKEN")
  assert [m.value for m in integ.get_info().auth_methods] == ["oauth"]
