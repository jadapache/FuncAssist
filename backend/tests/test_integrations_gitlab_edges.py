"""GitLab: the shape of what it returns when fields are missing, and the defaults of stored connections."""

from __future__ import annotations

import pytest

from app.integrations.gitlab import integration as gl
from tests.test_integrations_gitlab import CONNECTED, mock_http, store  # noqa: F401  (fixture)
from tests.test_integrations_gitlab_service_account import token_handler


def test_a_merge_request_without_author_or_flags_still_converts():
  assert gl._merge_request("g/p", {"iid": 4}) == {
    "repo": "g/p", "number": 4, "title": None, "state": None, "user": None, "merged_at": None,
    "updated_at": None, "html_url": None, "draft": None,
  }


def test_a_merge_request_is_a_draft_under_either_flag():
  assert gl._merge_request("r", {"draft": True})["draft"] is True
  assert gl._merge_request("r", {"work_in_progress": True})["draft"] is True


def test_a_merge_request_takes_the_author_username():
  assert gl._merge_request("r", {"author": {"username": "ana"}})["user"] == "ana"


def test_an_issue_without_author_still_converts():
  assert gl._issue("g/p", {"iid": 2}) == {
    "repo": "g/p", "number": 2, "title": None, "state": None, "user": None, "updated_at": None, "html_url": None,
  }
  assert gl._issue("r", {"author": {"username": "bob"}})["user"] == "bob"


def test_a_commit_message_is_the_first_line_of_its_title_or_message():
  assert gl._commit("r", {"title": "T", "message": "M"})["message"] == "T"
  assert gl._commit("r", {"message": "first\nsecond"})["message"] == "first"
  assert gl._commit("r", {})["message"] == ""


def test_a_commit_sha_is_shortened_to_seven_characters():
  assert gl._commit("r", {"id": "abcdefghij"})["sha"] == "abcdefg"
  assert gl._commit("r", {})["sha"] == ""


def test_a_commit_author_and_date_come_from_the_first_field_present():
  assert gl._commit("r", {"author_name": "N", "author": {"name": "Z"}})["author"] == "N"
  assert gl._commit("r", {"author": {"name": "Z"}})["author"] == "Z"
  assert gl._commit("r", {})["author"] is None
  assert gl._commit("r", {"committed_date": "c", "created_at": "x"})["date"] == "c"
  assert gl._commit("r", {"created_at": "x"})["date"] == "x"


@pytest.mark.asyncio
async def test_items_without_dates_still_sort_and_truncate(store, monkeypatch):  # noqa: F811
  store["gitlab"] = {**CONNECTED, "selected_repos": ["g/a"]}
  mock_http(monkeypatch, lambda req: __import__("httpx").Response(200, json=[{"iid": 1}, {"iid": 2, "updated_at": "2024-01-01"}]))
  issues = await gl.GitLabIntegration().get_issues(max_results=1)
  assert [i["number"] for i in issues] == [2]


def test_a_connection_without_a_base_url_shows_the_default_host(store):  # noqa: F811
  store["gitlab"] = {"auth_method": "service_account", "service_token": "t"}
  info = gl.GitLabIntegration().get_info()
  assert info.details["base_url"] == "https://gitlab.com"


@pytest.mark.asyncio
async def test_testing_a_connection_without_a_base_url_reports_the_default_host(store, monkeypatch):  # noqa: F811
  store["gitlab"] = {"auth_method": "service_account", "service_token": "t"}
  mock_http(monkeypatch, token_handler())
  result = await gl.GitLabIntegration().test_connection()
  assert result.ok is True and result.details["base_url"] == "https://gitlab.com"


@pytest.mark.asyncio
async def test_a_token_that_does_not_say_whether_it_is_active_is_accepted(store, monkeypatch):  # noqa: F811
  import httpx

  def handler(req: httpx.Request):
    if req.url.path.endswith("/personal_access_tokens/self"):
      return httpx.Response(200, json={"scopes": ["read_api"], "expires_at": None, "name": "bot"})
    return httpx.Response(200, json={"username": "bot"})

  mock_http(monkeypatch, handler)
  await gl.GitLabIntegration().connect_with_service_account("glpat-x")
  assert store["gitlab"]["service_token"] == "glpat-x"


@pytest.mark.asyncio
async def test_connecting_keeps_the_projects_already_selected_unless_told_otherwise(store, monkeypatch):  # noqa: F811
  store["gitlab"] = {**CONNECTED, "selected_repos": ["g/old"]}
  mock_http(monkeypatch, token_handler())
  integ = gl.GitLabIntegration()
  await integ.connect_with_service_account("glpat-x")
  assert store["gitlab"]["selected_repos"] == ["g/old"]
  await integ.connect_with_service_account("glpat-x", selected_repos=["g/new"])
  assert store["gitlab"]["selected_repos"] == ["g/new"]
  await integ.connect_with_service_account("glpat-x", selected_repos=[])
  assert store["gitlab"]["selected_repos"] == []


@pytest.mark.asyncio
async def test_connecting_for_the_first_time_selects_nothing(store, monkeypatch):  # noqa: F811
  mock_http(monkeypatch, token_handler())
  await gl.GitLabIntegration().connect_with_service_account("glpat-x")
  assert store["gitlab"]["selected_repos"] == []
