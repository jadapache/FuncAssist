"""Edges of the Jira OAuth settings shown to the UI and of which pull request files a sync reads."""

from __future__ import annotations

import pytest

from app.core import integration_config as cfg
from app.integrations import sync


# ----------------------------------------------------------------- public view of the OAuth settings


def test_the_public_view_of_missing_settings_shows_nothing_configured():
  assert cfg._public_oauth({}) == {
    "configured": False, "client_id": "", "client_id_set": False, "client_secret_set": False,
    "redirect_uri": "", "source": "none",
  }


def test_a_client_id_longer_than_eight_characters_is_shortened():
  assert cfg._public_oauth({"client_id": "123456789"})["client_id"] == "12345678…"
  assert cfg._public_oauth({"client_id": "12345678"})["client_id"] == "12345678"
  assert cfg._public_oauth({"client_id": "1234567"})["client_id"] == "1234567"


def test_the_public_view_never_includes_the_secret():
  view = cfg._public_oauth({"client_id": "abc", "client_secret": "s3cret", "redirect_uri": "http://x", "source": "local", "configured": True})
  assert "s3cret" not in str(view)
  assert (view["client_secret_set"], view["redirect_uri"], view["source"], view["configured"]) == (True, "http://x", "local", True)


class Settings:
  def __init__(self, client_id=None, client_secret=None, redirect_uri=None):
    self.jira_client_id, self.jira_client_secret, self.jira_redirect_uri = client_id, client_secret, redirect_uri


@pytest.fixture
def oauth(monkeypatch):
  def configure(local=None, env=None):
    monkeypatch.setattr(cfg, "get_settings", lambda: env or Settings())
    monkeypatch.setattr(cfg, "_oauth_block", lambda key: dict(local or {}))

  return configure


def test_an_oauth_app_needs_both_the_id_and_the_secret_to_be_configured(oauth):
  oauth(local={"client_id": "id"})
  assert cfg.get_jira_oauth_config()["configured"] is False
  oauth(local={"client_secret": "s"})
  assert cfg.get_jira_oauth_config()["configured"] is False
  oauth(local={"client_id": "id", "client_secret": "s"})
  assert cfg.get_jira_oauth_config()["configured"] is True


def test_local_settings_win_over_the_environment_and_are_trimmed(oauth):
  oauth(local={"client_id": " local-id ", "client_secret": " local-s ", "redirect_uri": " http://local/cb "},
        env=Settings("env-id", "env-s", "http://env/cb"))
  assert cfg.get_jira_oauth_config() == {
    "client_id": "local-id", "client_secret": "local-s", "redirect_uri": "http://local/cb", "configured": True, "source": "local",
  }


def test_the_environment_fills_what_the_local_settings_lack(oauth):
  oauth(local={}, env=Settings("env-id", "env-s", "http://env/cb"))
  assert cfg.get_jira_oauth_config() == {
    "client_id": "env-id", "client_secret": "env-s", "redirect_uri": "http://env/cb", "configured": True, "source": "env",
  }


def test_with_nothing_set_the_redirect_uri_is_the_local_default(oauth):
  oauth()
  assert cfg.get_jira_oauth_config() == {
    "client_id": "", "client_secret": "", "redirect_uri": cfg.DEFAULT_JIRA_REDIRECT_URI, "configured": False, "source": "none",
  }


# ----------------------------------------------------------------- files of the first pull request


class Git:
  def __init__(self, files=None, fails=False):
    self.files, self.fails, self.calls = files or [{"filename": "a.py"}], fails, []

  async def get_files_changed(self, pr_number, repo):
    self.calls.append((pr_number, repo))
    if self.fails:
      raise RuntimeError("boom")
    return self.files


@pytest.mark.asyncio
async def test_the_files_of_the_first_pull_request_are_read_with_its_number_and_repository():
  git = Git()
  assert await sync._first_pull_request_files(git, [{"number": "7", "repo": "a/b"}, {"number": 8, "repo": "c/d"}]) == [{"filename": "a.py"}]
  assert git.calls == [(7, "a/b")]


@pytest.mark.asyncio
@pytest.mark.parametrize("pull_requests", [[], [{"number": 5}], [{"repo": "a/b"}], [{"number": 0, "repo": "a/b"}], [{"number": 3, "repo": ""}]])
async def test_no_files_are_read_without_a_pull_request_with_number_and_repository(pull_requests):
  git = Git()
  assert await sync._first_pull_request_files(git, pull_requests) == []
  assert git.calls == []


@pytest.mark.asyncio
async def test_no_files_are_read_from_an_integration_that_cannot_list_them():
  assert await sync._first_pull_request_files(object(), [{"number": 1, "repo": "a/b"}]) == []


@pytest.mark.asyncio
async def test_a_failure_reading_the_files_leaves_the_list_empty():
  git = Git(fails=True)
  assert await sync._first_pull_request_files(git, [{"number": 1, "repo": "a/b"}]) == []
  assert git.calls == [(1, "a/b")]
