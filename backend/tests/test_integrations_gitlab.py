"""GitLab integration with httpx mocked via MockTransport and an in-memory connection store."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.base import AuthMethod, ConnectionStatus
from app.integrations.gitlab import integration as gl

REAL_CLIENT = httpx.AsyncClient
OAUTH_CFG = {
  "configured": True, "client_id": "cid", "client_secret": "sec",
  "redirect_uri": "http://x/cb", "base_url": "https://git.example.com/",
}
CONNECTED = {"auth_method": "oauth", "access_token": "glat", "base_url": "https://gitlab.com"}


@pytest.fixture
def store(monkeypatch):
  data: dict = {}
  monkeypatch.setattr(gl, "load_connection", lambda _id: dict(data[_id]) if data.get(_id) else None)
  monkeypatch.setattr(gl, "save_connection", lambda _id, payload: data.__setitem__(_id, dict(payload)))
  monkeypatch.setattr(gl, "delete_connection", lambda _id: data.pop(_id, None))
  monkeypatch.setattr(gl, "get_gitlab_oauth_config", lambda: OAUTH_CFG)
  return data


def mock_http(monkeypatch, handler):
  monkeypatch.setattr(gl.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw))


def test_api_base_variants(store):
  integ = gl.GitLabIntegration()
  assert integ._api_base() == "https://gitlab.com/api/v4"
  assert integ._api_base({"api_base": "https://x/api/v4/"}) == "https://x/api/v4"
  assert integ._api_base({"base_url": "https://git.co/"}) == "https://git.co/api/v4"
  assert integ._encode_project("grp/sub/proj") == "grp%2Fsub%2Fproj"
  assert {c.value for c in integ.get_capabilities()} >= {"get_issues", "get_pull_requests"}


def test_info_and_is_connected(store):
  integ = gl.GitLabIntegration()
  assert integ.get_info().status == ConnectionStatus.NOT_CONNECTED
  store["gitlab"] = {**CONNECTED, "account_login": "ana", "selected_repos": ["g/p"], "base_url": "https://git.example.com"}
  info = integ.get_info()
  assert info.status == ConnectionStatus.CONNECTED and info.workspace_label == "git.example.com"
  assert info.details["selected_repos"] == ["g/p"]
  assert integ._is_connected({"auth_method": "oauth", "access_token": "t"}) is True
  assert integ._is_connected({"auth_method": "oauth"}) is False
  assert integ._is_connected({"auth_method": "pat", "pat_token": "x"}) is False  # PATs are no longer accepted
  assert integ._is_connected(None) is False


@pytest.mark.asyncio
async def test_start_oauth(store, monkeypatch):
  res = await gl.GitLabIntegration().start_oauth()
  assert res.authorization_url.startswith("https://git.example.com/oauth/authorize?") and res.auth_method == AuthMethod.OAUTH
  assert store["gitlab"]["oauth_state"] == res.state
  monkeypatch.setattr(gl, "get_gitlab_oauth_config", lambda: {"configured": False})
  with pytest.raises(ValueError, match="not configured"):
    await gl.GitLabIntegration().start_oauth()


@pytest.mark.asyncio
async def test_oauth_callback(store, monkeypatch):
  integ = gl.GitLabIntegration()
  with pytest.raises(ValueError, match="Invalid OAuth state"):
    await integ.handle_oauth_callback("c", "s")

  store["gitlab"] = {"oauth_state": "st", "selected_repos": ["g/p"]}

  def ok(req: httpx.Request):
    if req.url.path == "/oauth/token":
      return httpx.Response(200, json={"access_token": "tok", "refresh_token": "r"})
    assert req.headers["authorization"] == "Bearer tok"
    return httpx.Response(200, json={"username": "ana", "name": "Ana"})

  mock_http(monkeypatch, ok)
  info = await integ.handle_oauth_callback("code", "st")
  assert info.account_label == "ana"
  assert store["gitlab"]["api_base"] == "https://git.example.com/api/v4" and store["gitlab"]["selected_repos"] == ["g/p"]
  assert store["gitlab"]["refresh_token"] == "r"

  store["gitlab"] = {"oauth_state": "st"}
  mock_http(monkeypatch, lambda req: httpx.Response(400, text="bad"))
  with pytest.raises(ValueError, match="token exchange failed"):
    await integ.handle_oauth_callback("c", "st")
  mock_http(monkeypatch, lambda req: httpx.Response(200, json={}))
  with pytest.raises(ValueError, match="did not return an access token"):
    await integ.handle_oauth_callback("c", "st")


@pytest.mark.asyncio
async def test_connection_lifecycle(store, monkeypatch):
  integ = gl.GitLabIntegration()
  assert await integ.authenticate() is False
  assert (await integ.test_connection()).ok is False
  with pytest.raises(ValueError):
    integ._headers()
  with pytest.raises(ValueError, match="not connected"):
    await integ.update_selected_repos(["a"])
  with pytest.raises(ValueError, match="not connected"):
    await integ.get_repositories()

  store["gitlab"] = dict(CONNECTED)
  assert integ._headers() == {"Authorization": "Bearer glat"}
  mock_http(monkeypatch, lambda req: httpx.Response(200, json={"username": "ana"}))
  assert (await integ.test_connection()).details["username"] == "ana"
  mock_http(monkeypatch, lambda req: httpx.Response(500))
  assert (await integ.test_connection()).ok is False

  info = await integ.update_selected_repos(["g/p"])
  assert info.details["selected_repos"] == ["g/p"]

  store["gitlab"] = {"auth_method": "oauth", "access_token": "o"}
  assert integ._headers() == {"Authorization": "Bearer o"}
  store["gitlab"] = {"auth_method": "oauth"}
  with pytest.raises(ValueError):
    integ._headers()

  await integ.disconnect()
  assert "gitlab" not in store


@pytest.mark.asyncio
async def test_get_repositories(store, monkeypatch):
  store["gitlab"] = {**CONNECTED, "selected_repos": ["g/p"]}
  mock_http(monkeypatch, lambda req: httpx.Response(200, json=[
    {"path_with_namespace": "g/p", "name": "p", "visibility": "private"},
    {"path_with_namespace": "g/q", "name": "q", "visibility": "public"},
  ]))
  repos = await gl.GitLabIntegration().get_repositories()
  assert [(r["full_name"], r["private"], r["selected"]) for r in repos] == [("g/p", True, True), ("g/q", False, False)]


@pytest.mark.asyncio
async def test_merge_requests_commits_issues(store, monkeypatch):
  integ = gl.GitLabIntegration()
  for call in (integ.get_merge_requests, integ.get_pull_requests, integ.get_commits, integ.get_issues):
    with pytest.raises(ValueError, match="No GitLab projects"):
      await call()

  store["gitlab"] = {**CONNECTED, "selected_repos": ["g/a", "g/b"]}
  states = []

  def handler(req: httpx.Request):
    repo_new = "g%2Fb" in str(req.url)
    if req.url.path.endswith("/merge_requests"):
      states.append(req.url.params.get("state"))
      return httpx.Response(200, json=[{"iid": 1, "title": "MR", "state": "opened", "author": {"username": "u"},
                                        "updated_at": "2024-02-01" if repo_new else "2024-01-01", "work_in_progress": True}])
    if req.url.path.endswith("/commits"):
      return httpx.Response(200, json=[{"id": "abcdef12345", "title": "t\nx", "author_name": "N",
                                        "committed_date": "2024-05-01" if repo_new else "2024-01-01"}])
    return httpx.Response(200, json=[{"iid": 3, "title": "I", "state": "opened", "author": {"username": "u"},
                                      "updated_at": "2024-06-01" if repo_new else "2024-01-01"}])

  mock_http(monkeypatch, handler)
  mrs = await integ.get_merge_requests(state="open")
  assert [m["repo"] for m in mrs] == ["g/b", "g/a"] and mrs[0]["draft"] is True and states == ["opened", "opened"]
  await integ.get_pull_requests(state="all")
  assert states[-1] is None
  assert len(await integ.get_merge_requests(max_results=1)) == 1

  commits = await integ.get_commits()
  assert commits[0]["repo"] == "g/b" and commits[0]["sha"] == "abcdef1" and commits[0]["message"] == "t"
  issues = await integ.get_issues()
  assert [i["number"] for i in issues] == [3, 3] and issues[0]["repo"] == "g/b"


@pytest.mark.asyncio
async def test_files_changed(store, monkeypatch):
  integ = gl.GitLabIntegration()
  with pytest.raises(ValueError, match="Provide a project"):
    await integ.get_files_changed(pr_number=1)

  store["gitlab"] = {**CONNECTED, "selected_repos": ["g/p"]}
  paths = []

  def handler(req: httpx.Request):
    paths.append(req.url.raw_path.decode().split("?")[0])
    return httpx.Response(200, json={"changes": [
      {"new_path": "b.py", "old_path": "a.py", "renamed_file": True},
      {"new_path": None, "old_path": "c.py"},
    ]})

  mock_http(monkeypatch, handler)
  files = await integ.get_files_changed(pr_number=4)
  assert paths[-1] == "/api/v4/projects/g%2Fp/merge_requests/4/changes"
  assert [(f["filename"], f["status"]) for f in files] == [("b.py", "renamed"), ("c.py", "modified")]


def test_personal_access_tokens_are_not_supported():
  integ = gl.GitLabIntegration()
  assert not hasattr(integ, "connect_with_pat")
  assert [m.value for m in integ.get_info().auth_methods] == ["service_account", "oauth"]
  with pytest.raises(ValueError):
    gl.GitLabIntegration()._headers()


@pytest.mark.asyncio
async def test_files_changed_only_for_enabled_projects(store, monkeypatch):
  integ = gl.GitLabIntegration()
  store["gitlab"] = {**CONNECTED, "selected_repos": ["g/p"]}
  requests = []
  mock_http(monkeypatch, lambda req: requests.append(req) or httpx.Response(200, json={"changes": []}))
  for repo in ("other/secret", "g/p/../../x"):
    with pytest.raises(ValueError, match="not enabled"):
      await integ.get_files_changed(pr_number=1, repo=repo)
  assert requests == []
