"""Jira: boundaries of the OAuth flow and defaults of missing profile data."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.jira import integration as jira
from tests.test_integrations_jira import OAUTH, OAUTH_CFG, U, mock_http, store  # noqa: F401  (fixture)

NOW = 1_000_000.0


@pytest.fixture
def clock(monkeypatch):
  now = {"t": NOW}
  monkeypatch.setattr(jira.time, "time", lambda: now["t"])
  return now


def test_a_project_matches_by_name_or_by_key_but_not_by_either_alone_being_absent():
  projects = [{"key": "XABY", "name": "Zed"}, {"key": "QQQ", "name": "Has ab inside"}]
  assert jira.match_project_for_hint(projects, "ab")["key"] == "XABY"
  assert jira.match_project_for_hint([projects[1]], "ab")["key"] == "QQQ"
  assert jira.match_project_for_hint([{"key": "ZZZ", "name": "Zed"}], "ab") is None


def test_a_token_expires_a_minute_before_the_provider_says(clock):
  assert jira._expiry({"expires_in": 600}) == NOW + 540
  assert jira._expiry({}) == NOW + 3600 - 60


def test_the_profile_label_is_the_email_or_else_the_name():
  tokens = {"access_token": "a"}
  site = [{"id": "c", "url": "https://s", "name": "S"}]
  assert jira._oauth_payload(tokens, site, {"email": "a@b.co", "name": "Ana"})["account_label"] == "a@b.co"
  assert jira._oauth_payload(tokens, site, {"name": "Ana"})["account_label"] == "Ana"
  assert jira._oauth_payload(tokens, site, {})["account_label"] is None


def test_the_connection_info_shows_the_workspace_from_the_site_or_the_stored_label(store):  # noqa: F811
  integ = jira.JiraIntegration()
  store.users[(U, "jira")] = {**OAUTH, "site_url": None, "workspace_label": "From label"}
  assert integ.get_info(user_id=U).workspace_label == "From label"
  store.users[(U, "jira")] = {**OAUTH, "site_url": "https://site", "workspace_label": "From label"}
  assert integ.get_info(user_id=U).workspace_label == "https://site"


@pytest.mark.parametrize(("age", "valid"), [(600, True), (601, False)])
def test_an_oauth_state_is_valid_for_ten_minutes(clock, age, valid):
  state = f"u1::{int(NOW) - age}::nonce"
  if valid:
    assert jira.JiraIntegration()._state_user(state) == "u1"
  else:
    with pytest.raises(ValueError, match="expired"):
      jira.JiraIntegration()._state_user(state)


@pytest.mark.asyncio
async def test_projects_cannot_be_selected_without_a_connection_that_works(store):  # noqa: F811
  integ = jira.JiraIntegration()
  store.users[(U, "jira")] = {"auth_method": "api_token", "access_token": "x", "cloud_id": "c"}
  with pytest.raises(ValueError, match="not connected"):
    await integ.update_selected_projects(["AB"], user_id=U)


@pytest.mark.asyncio
async def test_blank_project_keys_are_dropped_and_the_rest_cleaned(store):  # noqa: F811
  store.users[(U, "jira")] = dict(OAUTH)
  info = await jira.JiraIntegration().update_selected_projects([" ", "ab ", "", "Cd"], user_id=U)
  assert info.details["selected_project_keys"] == ["AB", "CD"]


@pytest.mark.asyncio
async def test_a_project_without_a_key_is_not_auto_selected(store, monkeypatch):  # noqa: F811
  store.users[(U, "jira")] = dict(OAUTH)
  mock_http(monkeypatch, lambda req: httpx.Response(200, json={"values": [{"name": "Acme Platform"}]}))
  await jira.JiraIntegration().auto_select_projects_from_url("https://acme.atlassian.net/browse/ACME-1", user_id=U)
  assert "selected_project_keys" not in store.users[(U, "jira")]


@pytest.mark.asyncio
async def test_testing_a_missing_connection_is_not_ok(store):  # noqa: F811
  result = await jira.JiraIntegration().test_connection(user_id="nobody")
  assert result.ok is False and result.message == "Jira is not connected."


@pytest.mark.asyncio
async def test_a_token_that_expires_right_now_is_refreshed(store, clock, monkeypatch):  # noqa: F811
  store.users[(U, "jira")] = {**OAUTH, "expires_at": NOW}
  mock_http(monkeypatch, lambda req: httpx.Response(200, json={"access_token": "new", "expires_in": 100}))
  data = await jira.JiraIntegration()._ensure_fresh_oauth_token(dict(store.users[(U, "jira")]), user_id=U)
  assert data["access_token"] == "new" and data["expires_at"] == NOW + 40


@pytest.mark.asyncio
async def test_a_token_that_is_still_valid_is_not_refreshed(store, clock, monkeypatch):  # noqa: F811
  mock_http(monkeypatch, lambda req: (_ for _ in ()).throw(AssertionError("must not call the network")))
  data = {**OAUTH, "expires_at": NOW + 1}
  assert await jira.JiraIntegration()._ensure_fresh_oauth_token(data, user_id=U) is data


@pytest.mark.asyncio
async def test_a_connection_without_an_expiry_is_refreshed(store, clock, monkeypatch):  # noqa: F811
  mock_http(monkeypatch, lambda req: httpx.Response(200, json={"access_token": "new"}))
  data = {key: value for key, value in OAUTH.items() if key != "expires_at"}
  refreshed = await jira.JiraIntegration()._ensure_fresh_oauth_token(data, user_id=U)
  assert refreshed["access_token"] == "new"
