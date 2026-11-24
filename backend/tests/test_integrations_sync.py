"""Sync: Jira is personal (per-user token and cache), GitHub and GitLab are organization-wide."""

from __future__ import annotations

import json

import pytest

from app.integrations import sync


class FakeRedis:
  def __init__(self):
    self.data: dict[str, str] = {}

  async def set(self, key, value, ex=None):
    self.data[key] = value

  async def get(self, key):
    return self.data.get(key)


class FakeJira:
  def __init__(self):
    self.calls: list[tuple] = []
    self.connected_users = {"alice", "bob"}

  async def authenticate(self, user_id=None):
    self.calls.append(("authenticate", user_id))
    return user_id in self.connected_users

  async def get_issues(self, max_results=50, user_id=None):
    self.calls.append(("get_issues", user_id))
    return [{"key": f"{user_id}-1"}]

  async def get_projects(self, user_id=None):
    self.calls.append(("get_projects", user_id))
    return [{"key": f"P-{user_id}"}]

  async def get_sprints(self, user_id=None):
    self.calls.append(("get_sprints", user_id))
    return []


class FakeGit:
  def __init__(self):
    self.calls: list[str] = []

  async def authenticate(self):
    self.calls.append("authenticate")
    return True

  async def get_repositories(self):
    return [{"full_name": "a/b"}]

  async def get_pull_requests(self, max_results=30):
    return [{"number": 1, "repo": "a/b"}]

  async def get_commits(self, max_results=30):
    return [{"sha": "abc"}]

  async def get_issues(self, max_results=30):
    return [{"iid": 5}]

  async def get_files_changed(self, pr_number, repo):
    return [{"filename": "x.py"}]


@pytest.fixture
def env(monkeypatch):
  redis = FakeRedis()
  jira, github, gitlab = FakeJira(), FakeGit(), FakeGit()
  items = {"jira": jira, "github": github, "gitlab": gitlab}
  monkeypatch.setattr(sync, "get_redis_client", lambda: redis)
  monkeypatch.setattr(sync.registry, "get", lambda iid: items[iid])
  return type("Env", (), {"redis": redis, "jira": jira, "github": github, "gitlab": gitlab})


def test_cache_keys():
  assert sync._cache_key("jira", "alice") == "funcassist:sync:user:alice:jira"
  assert sync._cache_key("github") == "funcassist:sync:global:github"
  # Organization integrations are shared whoever syncs them.
  assert sync._cache_key("github", "alice") == sync._cache_key("github", "bob")
  assert sync._cache_key("gitlab", "alice") == "funcassist:sync:global:gitlab"
  with pytest.raises(ValueError, match="personal"):
    sync._cache_key("jira")


@pytest.mark.asyncio
async def test_jira_sync_requires_a_user(env):
  with pytest.raises(ValueError, match="personal"):
    await sync.sync_integration("jira")
  assert env.jira.calls == [] and env.redis.data == {}


@pytest.mark.asyncio
async def test_jira_sync_uses_the_users_own_connection(env):
  payload = await sync.sync_integration("jira", user_id="alice")
  assert payload["data"]["issues"] == [{"key": "alice-1"}]
  assert payload["data"]["projects"] == [{"key": "P-alice"}]
  # every Jira call carried the user, none fell back to an organization connection
  assert env.jira.calls and all(user == "alice" for _, user in env.jira.calls)


@pytest.mark.asyncio
async def test_jira_sync_fails_without_the_users_connection(env):
  with pytest.raises(ValueError, match="not connected"):
    await sync.sync_integration("jira", user_id="carol")
  assert env.redis.data == {}


@pytest.mark.asyncio
async def test_two_users_never_share_jira_data(env):
  await sync.sync_integration("jira", user_id="alice")
  await sync.sync_integration("jira", user_id="bob")
  alice = await sync.load_sync_cache("jira", user_id="alice")
  bob = await sync.load_sync_cache("jira", user_id="bob")
  assert alice["data"]["issues"] == [{"key": "alice-1"}]
  assert bob["data"]["issues"] == [{"key": "bob-1"}]
  assert await sync.load_sync_cache("jira", user_id="carol") is None


@pytest.mark.asyncio
async def test_git_hosting_cache_is_organization_wide(env):
  payload = await sync.sync_integration("github", user_id="alice")
  assert payload["data"]["pull_requests"] == [{"number": 1, "repo": "a/b"}]
  assert payload["data"]["files_changed"] == [{"filename": "x.py"}]
  assert "issues" not in payload["data"]
  # another user reads the same shared cache
  assert await sync.load_sync_cache("github", user_id="bob") == json.loads(
    env.redis.data["funcassist:sync:global:github"]
  )

  gitlab = await sync.sync_integration("gitlab")
  assert gitlab["data"]["issues"] == [{"iid": 5}]


@pytest.mark.asyncio
async def test_git_hosting_requires_a_connection(env, monkeypatch):
  async def not_connected():
    return False

  monkeypatch.setattr(env.github, "authenticate", not_connected)
  with pytest.raises(ValueError, match="not connected"):
    await sync.sync_integration("github")


@pytest.mark.asyncio
async def test_files_changed_failure_is_tolerated(env, monkeypatch):
  async def boom(pr_number, repo):
    raise RuntimeError("api down")

  monkeypatch.setattr(env.github, "get_files_changed", boom)
  payload = await sync.sync_integration("github")
  assert payload["data"]["files_changed"] == []


@pytest.mark.asyncio
async def test_load_sync_cache_when_empty(env):
  assert await sync.load_sync_cache("github") is None
