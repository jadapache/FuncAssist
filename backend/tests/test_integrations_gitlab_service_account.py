"""GitLab connected as a read-only service account: validation, storage and periodic re-checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.integrations.base import ConnectionStatus
from app.integrations.gitlab import integration as gl
from tests.test_integrations_gitlab import CONNECTED, mock_http, store  # noqa: F401  (fixture)

FUTURE = (datetime.now(timezone.utc) + timedelta(days=200)).strftime("%Y-%m-%d")
SOON = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d")


def token_handler(*, scopes=("read_api",), active=True, revoked=False, expires=FUTURE, status=200, seen=None):
  def handler(req: httpx.Request):
    if seen is not None:
      seen.append((req.url.host, req.url.path, req.headers.get("private-token")))
    if req.url.path.endswith("/personal_access_tokens/self"):
      if status != 200:
        return httpx.Response(status)
      return httpx.Response(200, json={
        "active": active, "revoked": revoked, "scopes": list(scopes), "expires_at": expires, "name": "funcassist-bot",
      })
    if req.url.path.endswith("/user"):
      return httpx.Response(200, json={"username": "funcassist-bot", "name": "FuncAssist Bot"})
    return httpx.Response(404)

  return handler


@pytest.mark.asyncio
async def test_connects_with_a_read_only_token(store, monkeypatch):  # noqa: F811
  seen: list = []
  mock_http(monkeypatch, token_handler(seen=seen, scopes=("read_api", "read_repository")))
  info = await gl.GitLabIntegration().connect_with_service_account(
    "glpat-secret-token", base_url="https://git.corp.io/", configured_by="admin-1"
  )
  saved = store["gitlab"]
  assert saved["auth_method"] == "service_account" and saved["service_token"] == "glpat-secret-token"
  assert saved["scopes"] == ["read_api", "read_repository"] and saved["expires_at"] == FUTURE
  assert saved["configured_by"] == "admin-1" and saved["configured_at"] and saved["token_name"] == "funcassist-bot"
  assert saved["base_url"] == "https://git.corp.io" and saved["api_base"] == "https://git.corp.io/api/v4"
  assert saved["account_login"] == "funcassist-bot"
  assert {host for host, _, _ in seen} == {"git.corp.io"} and {t for _, _, t in seen} == {"glpat-secret-token"}
  assert info.status == ConnectionStatus.CONNECTED and info.account_label == "funcassist-bot"
  assert info.details["scopes"] == ["read_api", "read_repository"] and info.details["expiry"] == "ok"
  assert "glpat-secret-token" not in str(info.model_dump())  # the token is never exposed


@pytest.mark.asyncio
@pytest.mark.parametrize("scopes", [("api",), ("read_api", "write_repository"), ("read_api", "sudo"), ("read_repository",)])
async def test_wrong_permissions_are_rejected_and_nothing_is_stored(store, monkeypatch, scopes):  # noqa: F811
  mock_http(monkeypatch, token_handler(scopes=scopes))
  with pytest.raises(ValueError):
    await gl.GitLabIntegration().connect_with_service_account("glpat-x")
  assert "gitlab" not in store


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs,message", [
  ({"active": False}, "not active"),
  ({"revoked": True}, "not active"),
  ({"expires": "2020-01-01"}, "expired"),
  ({"status": 401}, "rejected"),
  ({"status": 403}, "rejected"),
])
async def test_a_bad_token_is_rejected(store, monkeypatch, kwargs, message):  # noqa: F811
  mock_http(monkeypatch, token_handler(**kwargs))
  with pytest.raises(ValueError, match=message):
    await gl.GitLabIntegration().connect_with_service_account("glpat-x")
  assert "gitlab" not in store


@pytest.mark.asyncio
@pytest.mark.parametrize("token,url,message", [
  ("", None, "required"),
  ("   ", None, "required"),
  ("glpat-x", "http://git.corp.io", "HTTPS"),
  ("glpat-x", "ftp://git.corp.io", "HTTPS"),
])
async def test_input_is_validated_before_any_request(store, monkeypatch, token, url, message):  # noqa: F811
  def no_request(req):
    raise AssertionError("no request expected")

  mock_http(monkeypatch, no_request)
  with pytest.raises(ValueError, match=message):
    await gl.GitLabIntegration().connect_with_service_account(token, base_url=url)


@pytest.mark.asyncio
async def test_defaults_to_gitlab_com_and_accepts_a_token_without_expiry(store, monkeypatch):  # noqa: F811
  seen: list = []
  mock_http(monkeypatch, token_handler(seen=seen, expires=None))
  info = await gl.GitLabIntegration().connect_with_service_account("glpat-x")
  assert {host for host, _, _ in seen} == {"gitlab.com"} and info.details["expiry"] == "none"


@pytest.mark.asyncio
async def test_reconnecting_keeps_the_enabled_projects_unless_told_otherwise(store, monkeypatch):  # noqa: F811
  mock_http(monkeypatch, token_handler())
  integ = gl.GitLabIntegration()
  store["gitlab"] = {**CONNECTED, "selected_repos": ["g/keep"]}
  await integ.connect_with_service_account("glpat-x")
  assert store["gitlab"]["selected_repos"] == ["g/keep"]
  await integ.connect_with_service_account("glpat-x", selected_repos=["g/new"])
  assert store["gitlab"]["selected_repos"] == ["g/new"]
  await integ.connect_with_service_account("glpat-x", selected_repos=[])
  assert store["gitlab"]["selected_repos"] == []


def test_connection_state_and_headers(store):  # noqa: F811
  integ = gl.GitLabIntegration()
  assert integ._is_connected({"auth_method": "service_account", "service_token": "t"}) is True
  assert integ._is_connected({"auth_method": "service_account"}) is False
  assert integ._is_connected({"service_token": "t"}) is False
  store["gitlab"] = {"auth_method": "service_account", "service_token": "glpat-abc", "base_url": "https://gitlab.com"}
  assert integ._headers() == {"PRIVATE-TOKEN": "glpat-abc"}


@pytest.mark.asyncio
async def test_testing_the_connection_checks_the_permissions_again(store, monkeypatch):  # noqa: F811
  integ = gl.GitLabIntegration()
  store["gitlab"] = {
    "auth_method": "service_account", "service_token": "glpat-abc", "base_url": "https://gitlab.com", "selected_repos": ["g/p"],
  }
  mock_http(monkeypatch, token_handler(expires=SOON))
  result = await integ.test_connection()
  assert result.ok and result.details["scopes"] == ["read_api"] and result.details["expiry"] == "expiring"
  assert result.details["days_left"] in (4, 5) and result.details["username"] == "funcassist-bot"

  # the token gained write access after it was connected: it stops being accepted
  mock_http(monkeypatch, token_handler(scopes=("read_api", "write_repository")))
  result = await integ.test_connection()
  assert result.ok is False and "more access" in result.message and "write_repository" in result.message

  mock_http(monkeypatch, token_handler(expires="2020-01-01"))
  assert (await integ.test_connection()).ok is False
  mock_http(monkeypatch, token_handler(revoked=True))
  assert (await integ.test_connection()).ok is False


@pytest.mark.asyncio
async def test_reads_use_the_service_account_token(store, monkeypatch):  # noqa: F811
  integ = gl.GitLabIntegration()
  store["gitlab"] = {
    "auth_method": "service_account", "service_token": "glpat-abc", "base_url": "https://gitlab.com", "selected_repos": ["g/p"],
  }
  headers: list = []

  def handler(req: httpx.Request):
    headers.append(req.headers.get("private-token"))
    return httpx.Response(200, json=[{"path_with_namespace": "g/p", "name": "p", "visibility": "private"}])

  mock_http(monkeypatch, handler)
  repos = await integ.get_repositories()
  assert repos[0]["selected"] is True and headers == ["glpat-abc"]
