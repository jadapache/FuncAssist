"""GitHub integration through a read-only GitHub App, with httpx mocked via MockTransport."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.integrations import git_hosting
from app.integrations.base import AuthMethod, ConnectionStatus
from app.integrations.github import integration as gh

REAL_CLIENT = httpx.AsyncClient
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_KEY = _KEY.private_bytes(
  serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()
).decode()
PUBLIC_KEY = _KEY.public_key()
READ_ONLY = {"metadata": "read", "contents": "read", "pull_requests": "read", "issues": "read"}


def connected(**extra) -> dict:
  return {
    "auth_method": "service_account", "app_id": "123", "private_key": PRIVATE_KEY, "installation_id": "77",
    "account_login": "acme", "permissions": READ_ONLY, **extra,
  }


@pytest.fixture
def store(monkeypatch):
  data: dict = {}
  load = lambda _id: dict(data[_id]) if data.get(_id) else None  # noqa: E731
  save = lambda _id, payload: data.__setitem__(_id, dict(payload))  # noqa: E731
  monkeypatch.setattr(gh, "load_connection", load)
  monkeypatch.setattr(git_hosting, "load_connection", load)
  monkeypatch.setattr(git_hosting, "save_connection", save)
  monkeypatch.setattr(gh, "save_connection", lambda _id, payload: data.__setitem__(_id, dict(payload)))
  monkeypatch.setattr(gh, "delete_connection", lambda _id: data.pop(_id, None))
  gh.clear_token_cache()
  yield data
  gh.clear_token_cache()


def mock_http(monkeypatch, handler):
  monkeypatch.setattr(
    gh.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw)
  )


def expires_in(seconds: int) -> str:
  return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def github_app(inner=None, *, permissions=None, selection="selected", expires=3600, seen=None, installs=None):
  """A fake GitHub: App endpoints plus token minting, delegating everything else to `inner`."""
  minted = {"count": 0}
  installs = installs if installs is not None else [
    {"id": 77, "account": {"login": "acme"}, "permissions": READ_ONLY, "repository_selection": selection}
  ]

  def handler(req: httpx.Request):
    if seen is not None:
      seen.append((req.method, req.url.path, req.headers.get("authorization")))
    path = req.url.path
    if path == "/app":
      return httpx.Response(200, json={"name": "FuncAssist Reader", "slug": "funcassist-reader"})
    if path == "/app/installations":
      return httpx.Response(200, json=installs)
    if path.endswith("/access_tokens"):
      minted["count"] += 1
      return httpx.Response(201, json={
        "token": f"ghs_token{minted['count']}", "expires_at": expires_in(expires),
        "permissions": permissions if permissions is not None else READ_ONLY, "repository_selection": selection,
      })
    return inner(req) if inner else httpx.Response(404)

  handler.minted = minted
  return handler


def test_info_not_connected_and_connected(store):
  integ = gh.GitHubIntegration()
  info = integ.get_info()
  assert info.status == ConnectionStatus.NOT_CONNECTED and info.oauth_configured is False
  assert [m.value for m in info.auth_methods] == ["service_account"]
  assert {c.value for c in integ.get_capabilities()} >= {"get_pull_requests", "get_commits"}

  store["github"] = connected(selected_repos=["a/b"], repository_selection="selected", app_name="Reader")
  info = integ.get_info()
  assert info.status == ConnectionStatus.CONNECTED and info.account_label == "acme"
  assert info.details["selected_repos"] == ["a/b"] and info.details["permissions"] == READ_ONLY
  assert info.details["installation_id"] == "77" and info.details["repository_selection"] == "selected"
  assert "private_key" not in str(info.model_dump())  # the key is never exposed


@pytest.mark.parametrize(
  "data,expected",
  [
    (None, False),
    (connected(), True),
    ({**connected(), "private_key": ""}, False),
    ({**connected(), "app_id": ""}, False),
    ({**connected(), "installation_id": None}, False),
    ({**connected(), "auth_method": "oauth"}, False),
    ({"auth_method": "oauth", "access_token": "x"}, False),  # OAuth is no longer accepted
    ({"auth_method": "pat", "pat_token": "x"}, False),  # PATs are no longer accepted
    ({"other": 1}, False),
  ],
)
def test_is_connected(data, expected):
  assert gh.GitHubIntegration()._is_connected(data) is expected


def test_there_is_no_oauth_or_pat_flow():
  integ = gh.GitHubIntegration()
  assert not hasattr(integ, "connect_with_pat") and not hasattr(gh, "GITHUB_SCOPES")
  assert not hasattr(gh, "get_github_oauth_config")
  with pytest.raises(NotImplementedError):
    asyncio.run(integ.start_oauth())
  with pytest.raises(NotImplementedError):
    asyncio.run(integ.handle_oauth_callback("c", "s"))
  assert not hasattr(AuthMethod, "PERSONAL_ACCESS_TOKEN")


# -- connecting -------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connects_with_a_read_only_installation(store, monkeypatch):
  seen: list = []
  mock_http(monkeypatch, github_app(seen=seen))
  info = await gh.GitHubIntegration().connect_with_github_app(
    " 123 ", PRIVATE_KEY, selected_repos=["acme/api"], configured_by="admin-1"
  )
  saved = store["github"]
  assert saved["auth_method"] == "service_account" and saved["app_id"] == "123" and saved["installation_id"] == "77"
  assert saved["private_key"] == PRIVATE_KEY.strip() and saved["permissions"] == READ_ONLY
  assert saved["account_login"] == "acme" and saved["app_name"] == "FuncAssist Reader"
  assert saved["configured_by"] == "admin-1" and saved["configured_at"] and saved["repository_selection"] == "selected"
  assert saved["selected_repos"] == ["acme/api"]
  assert "ghs_" not in str(saved)  # the installation token is never stored
  assert info.status == ConnectionStatus.CONNECTED and info.account_label == "acme"

  # The App endpoints are authenticated with a JWT signed by the App key, issued for the App ID.
  app_calls = [auth for _, path, auth in seen if path in ("/app", "/app/installations")]
  claims = jwt.decode(app_calls[0].removeprefix("Bearer "), PUBLIC_KEY, algorithms=["RS256"])
  assert claims["iss"] == "123" and claims["exp"] - claims["iat"] <= 600


@pytest.mark.asyncio
async def test_a_given_installation_id_is_used(store, monkeypatch):
  installs = [
    {"id": 1, "account": {"login": "one"}, "permissions": READ_ONLY},
    {"id": 2, "account": {"login": "two"}, "permissions": READ_ONLY},
  ]
  mock_http(monkeypatch, github_app(installs=installs))
  info = await gh.GitHubIntegration().connect_with_github_app("123", PRIVATE_KEY, installation_id="2")
  assert info.account_label == "two" and store["github"]["installation_id"] == "2"


@pytest.mark.asyncio
async def test_reconnecting_keeps_the_enabled_repositories_unless_told_otherwise(store, monkeypatch):
  store["github"] = connected(selected_repos=["acme/keep"])
  mock_http(monkeypatch, github_app())
  await gh.GitHubIntegration().connect_with_github_app("123", PRIVATE_KEY)
  assert store["github"]["selected_repos"] == ["acme/keep"]
  await gh.GitHubIntegration().connect_with_github_app("123", PRIVATE_KEY, selected_repos=[])
  assert store["github"]["selected_repos"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
  "permissions,message",
  [
    ({**READ_ONLY, "contents": "write"}, "write or admin"),
    ({**READ_ONLY, "administration": "read"}, "more access than needed"),
    ({**READ_ONLY, "pull_requests": "admin"}, "write or admin"),
    ({"metadata": "read", "issues": "read"}, "lacks a required permission"),
  ],
)
async def test_wrong_permissions_are_rejected_and_nothing_is_stored(store, monkeypatch, permissions, message):
  mock_http(monkeypatch, github_app(permissions=permissions))
  with pytest.raises(ValueError, match=message):
    await gh.GitHubIntegration().connect_with_github_app("123", PRIVATE_KEY)
  assert "github" not in store


@pytest.mark.asyncio
@pytest.mark.parametrize(
  "app_id,key,message",
  [
    ("", PRIVATE_KEY, "App ID"),
    ("12 3!", PRIVATE_KEY, "App ID"),
    ("123", "", "PEM"),
    ("123", "not a key", "PEM"),
    ("123", "-----BEGIN PRIVATE KEY-----\nzzz\n-----END PRIVATE KEY-----", "could not be used"),
  ],
)
async def test_input_is_validated_before_any_request(store, monkeypatch, app_id, key, message):
  requests: list = []
  mock_http(monkeypatch, lambda req: requests.append(req) or httpx.Response(200, json={}))
  with pytest.raises(ValueError, match=message):
    await gh.GitHubIntegration().connect_with_github_app(app_id, key)
  assert requests == [] and "github" not in store


@pytest.mark.asyncio
async def test_escaped_newlines_in_the_key_are_accepted(store, monkeypatch):
  mock_http(monkeypatch, github_app())
  await gh.GitHubIntegration().connect_with_github_app("123", PRIVATE_KEY.strip().replace("\n", "\\n"))
  assert store["github"]["private_key"] == PRIVATE_KEY.strip()


@pytest.mark.asyncio
@pytest.mark.parametrize(
  "installs,kwargs,message",
  [
    ([], {}, "not installed"),
    ([{"id": 1}, {"id": 2}], {}, "several installations"),
    ([{"id": 1}], {"installation_id": "9"}, "does not exist"),
    ([{"id": 1, "suspended_at": "2024-01-01T00:00:00Z"}], {"installation_id": "1"}, "does not exist"),
  ],
)
async def test_installation_selection_errors(store, monkeypatch, installs, kwargs, message):
  mock_http(monkeypatch, github_app(installs=installs))
  with pytest.raises(ValueError, match=message):
    await gh.GitHubIntegration().connect_with_github_app("123", PRIVATE_KEY, **kwargs)
  assert "github" not in store


@pytest.mark.asyncio
async def test_github_rejecting_the_app_is_reported(store, monkeypatch):
  mock_http(monkeypatch, lambda req: httpx.Response(401, json={"message": "Bad credentials"}))
  with pytest.raises(ValueError, match="rejected the App credentials"):
    await gh.GitHubIntegration().connect_with_github_app("123", PRIVATE_KEY)

  def token_fails(req: httpx.Request):
    if req.url.path.endswith("/access_tokens"):
      return httpx.Response(404)
    return github_app()(req)

  mock_http(monkeypatch, token_fails)
  with pytest.raises(ValueError, match="installation was not found"):
    await gh.GitHubIntegration().connect_with_github_app("123", PRIVATE_KEY)
  assert "github" not in store


# -- installation tokens ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_installation_token_is_cached_and_renewed_before_it_expires(store, monkeypatch):
  store["github"] = connected()
  app = github_app()
  mock_http(monkeypatch, app)
  integ = gh.GitHubIntegration()
  assert await integ._installation_token() == "ghs_token1"
  assert await integ._installation_token() == "ghs_token1" and app.minted["count"] == 1
  assert (await integ._headers())["Authorization"] == "Bearer ghs_token1"

  # Close to expiry (inside the refresh margin) a new one is minted.
  gh._TOKEN_CACHE["77"] = ("ghs_old", time.time() + gh.TOKEN_REFRESH_MARGIN - 1)
  assert await integ._installation_token() == "ghs_token2"


@pytest.mark.asyncio
async def test_a_token_whose_permissions_grew_is_not_used(store, monkeypatch):
  store["github"] = connected()
  mock_http(monkeypatch, github_app(permissions={**READ_ONLY, "contents": "write"}))
  with pytest.raises(ValueError, match="write or admin"):
    await gh.GitHubIntegration()._installation_token()
  assert gh._TOKEN_CACHE == {}


@pytest.mark.asyncio
async def test_not_connected_has_no_token(store):
  with pytest.raises(ValueError, match="not connected"):
    await gh.GitHubIntegration()._installation_token()


@pytest.mark.asyncio
async def test_disconnect_authenticate_and_test_connection(store, monkeypatch):
  integ = gh.GitHubIntegration()
  assert await integ.authenticate() is False
  res = await integ.test_connection()
  assert res.ok is False and "not connected" in res.message

  store["github"] = connected(selected_repos=["a/b"])
  assert await integ.authenticate() is True
  app = github_app(lambda req: httpx.Response(200, json={"total_count": 3, "repositories": []}))
  mock_http(monkeypatch, app)
  res = await integ.test_connection()
  assert res.ok and res.details["accessible_repositories"] == 3 and res.details["account"] == "acme"
  await integ.test_connection()
  assert app.minted["count"] == 2  # permissions are re-checked on every test, never from the cache

  mock_http(monkeypatch, github_app(permissions={**READ_ONLY, "contents": "write"}))
  res = await integ.test_connection()
  assert res.ok is False and "write or admin" in res.message

  mock_http(monkeypatch, lambda req: httpx.Response(403))
  assert (await integ.test_connection()).ok is False

  await integ.disconnect()
  assert "github" not in store and gh._TOKEN_CACHE == {}


@pytest.mark.asyncio
async def test_update_selected_repos(store):
  integ = gh.GitHubIntegration()
  with pytest.raises(ValueError, match="not connected"):
    await integ.update_selected_repos(["a/b"])
  assert integ.selected_repos() == []
  store["github"] = connected()
  info = await integ.update_selected_repos(["a/b"])
  assert info.details["selected_repos"] == ["a/b"] and integ.selected_repos() == ["a/b"]


# -- reading ---------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_repositories(store, monkeypatch):
  integ = gh.GitHubIntegration()
  with pytest.raises(ValueError, match="not connected"):
    await integ.get_repositories()

  store["github"] = connected(selected_repos=["a/b"])
  seen = {}

  def inner(req: httpx.Request):
    seen["per_page"] = req.url.params["per_page"]
    seen["path"] = req.url.path
    seen["auth"] = req.headers["authorization"]
    return httpx.Response(200, json={"total_count": 2, "repositories": [
      {"full_name": "a/b", "name": "b", "private": True}, {"full_name": "c/d", "name": "d"},
    ]})

  mock_http(monkeypatch, github_app(inner))
  repos = await integ.get_repositories(max_results=500)
  assert seen == {"per_page": "100", "path": "/installation/repositories", "auth": "Bearer ghs_token1"}
  assert [(r["full_name"], r["selected"]) for r in repos] == [("a/b", True), ("c/d", False)]


@pytest.mark.asyncio
async def test_pull_requests_and_commits(store, monkeypatch):
  integ = gh.GitHubIntegration()
  store["github"] = connected()
  with pytest.raises(ValueError, match="No GitHub repositories"):
    await integ.get_pull_requests()
  with pytest.raises(ValueError, match="No GitHub repositories"):
    await integ.get_commits()

  store["github"] = connected(selected_repos=["a/b", "c/d"])

  def inner(req: httpx.Request):
    assert req.headers["authorization"] == "Bearer ghs_token1"
    parts = req.url.path.split("/")
    repo = parts[2] + "/" + parts[3]
    if req.url.path.endswith("/pulls"):
      day = "2024-02-01" if repo == "a/b" else "2024-03-01"
      return httpx.Response(200, json=[{"number": 1, "title": "T", "state": "open", "user": {"login": "u"}, "updated_at": day}])
    day = "2024-01-01" if repo == "a/b" else "2024-04-01"
    return httpx.Response(200, json=[{"sha": "abcdef123456", "commit": {"message": "first\nsecond", "author": {"name": "N", "date": day}}}])

  mock_http(monkeypatch, github_app(inner))
  prs = await integ.get_pull_requests(max_results=5)
  assert [p["repo"] for p in prs] == ["c/d", "a/b"] and prs[0]["user"] == "u"
  assert len(await integ.get_pull_requests(max_results=1)) == 1

  commits = await integ.get_commits()
  assert [c["repo"] for c in commits] == ["c/d", "a/b"]
  assert commits[0]["sha"] == "abcdef1" and commits[0]["message"] == "first" and commits[0]["author"] == "N"


@pytest.mark.asyncio
async def test_files_changed(store, monkeypatch):
  integ = gh.GitHubIntegration()
  store["github"] = connected()
  with pytest.raises(ValueError, match="Provide a repo"):
    await integ.get_files_changed(pr_number=1)

  store["github"] = connected(selected_repos=["a/b", "z/y"])
  paths = []

  def inner(req: httpx.Request):
    paths.append(req.url.path)
    return httpx.Response(200, json=[{"filename": "x.py", "status": "modified", "additions": 2, "deletions": 1, "changes": 3}])

  mock_http(monkeypatch, github_app(inner))
  files = await integ.get_files_changed(pr_number=7)
  assert paths[-1] == "/repos/a/b/pulls/7/files" and files[0]["filename"] == "x.py" and files[0]["repo"] == "a/b"
  await integ.get_files_changed(pr_number=7, repo="z/y")
  assert paths[-1] == "/repos/z/y/pulls/7/files"


@pytest.mark.asyncio
async def test_files_changed_only_for_enabled_repositories(store, monkeypatch):
  integ = gh.GitHubIntegration()
  store["github"] = connected(selected_repos=["a/b"])
  requests = []
  mock_http(monkeypatch, lambda req: requests.append(req) or httpx.Response(200, json=[]))
  for repo in ("other/private", "a/b/../../../user", "a/b/extra"):
    with pytest.raises(ValueError, match="not enabled"):
      await integ.get_files_changed(pr_number=1, repo=repo)
  assert requests == []  # nothing reached GitHub
