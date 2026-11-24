"""assemble_context: merges live integrations (Jira/GitHub/GitLab) and knowledge hits."""

from __future__ import annotations

import pytest

from app.context import service
from app.context.models import ContextChunk, SourceType


class FakeJira:
  def __init__(self, authed=True, issues=None, fail=False):
    self.authed, self.issues, self.fail = authed, issues or [], fail
    self.user_ids = []

  async def authenticate(self, user_id=None):
    self.user_ids.append(user_id)
    return self.authed

  async def get_issues(self, max_results=25, user_id=None):
    if self.fail:
      raise RuntimeError("boom")
    return self.issues


class FakeGit:
  def __init__(self, authed=True, repos=("a/b",), fail=False):
    self.authed, self.repos, self.fail = authed, list(repos), fail

  async def authenticate(self):
    return self.authed

  def selected_repos(self):
    return self.repos

  async def get_pull_requests(self, max_results=20):
    if self.fail:
      raise RuntimeError("boom")
    return [{"number": 1, "repo": "a/b", "title": "PR", "state": "open", "user": "u"}]

  get_merge_requests = get_pull_requests

  async def get_commits(self, max_results=20):
    return [{"sha": "abc1234", "repo": "a/b", "message": "msg", "author": "n", "date": "d"}]

  async def get_issues(self, max_results=15):
    return [{"number": 5, "repo": "a/b", "title": "Bug", "state": "opened", "user": "u"}]


@pytest.fixture
def reg(monkeypatch):
  items = {}
  monkeypatch.setattr(service.registry, "get", lambda name: items[name])
  monkeypatch.setattr(service, "search_knowledge", lambda q, top_k=8: [])
  return items


ISSUES = [
  {"key": "AAA-1", "summary": "Login roto", "status": "Open", "description": "falla el login"},
  {"key": "AAA-2", "summary": "Otra cosa", "status": "Done"},
]


@pytest.mark.asyncio
async def test_jira_filters_by_query_and_passes_user(reg):
  reg["jira"] = FakeJira(issues=ISSUES)
  bundle = await service.assemble_context(query="login", sources=["Jira"], user_id="u1")
  assert reg["jira"].user_ids == ["u1"] and bundle.used_sources == ["jira"]
  assert [c.id for c in bundle.chunks] == ["jira:AAA-1"] and "Description: falla el login" in bundle.chunks[0].text


@pytest.mark.asyncio
async def test_jira_without_match_keeps_recent_issues_and_blank_query_keeps_all(reg):
  reg["jira"] = FakeJira(issues=ISSUES)
  bundle = await service.assemble_context(query="zzzzzz", sources=["jira"])
  assert len(bundle.chunks) == 2 and bundle.chunks[0].text.startswith("{")
  bundle = await service.assemble_context(query="  ", sources=["jira"])
  assert len(bundle.chunks) == 2 and bundle.chunks[0].text.startswith("Key:")


@pytest.mark.asyncio
async def test_jira_unauthenticated_and_error(reg):
  reg["jira"] = FakeJira(authed=False)
  assert (await service.assemble_context(query="q", sources=["jira"])).missing_sources == ["jira"]
  reg["jira"] = FakeJira(fail=True)
  bundle = await service.assemble_context(query="q", sources=["jira"])
  assert bundle.missing_sources == ["jira"] and bundle.chunks == []


@pytest.mark.asyncio
async def test_github_chunks_and_failure_modes(reg):
  reg["github"] = FakeGit()
  bundle = await service.assemble_context(query="q", sources=["github"])
  ids = [c.id for c in bundle.chunks]
  assert bundle.used_sources == ["github"]
  assert "github:pr:a/b:1" in ids and "github:commit:a/b:abc1234" in ids

  reg["github"] = FakeGit(authed=False)
  assert (await service.assemble_context(query="q", sources=["github"])).missing_sources == ["github"]
  reg["github"] = FakeGit(repos=[])
  assert (await service.assemble_context(query="q", sources=["github"])).missing_sources == ["github (no repositories selected)"]
  reg["github"] = FakeGit(fail=True)
  assert (await service.assemble_context(query="q", sources=["github"])).missing_sources == ["github"]


@pytest.mark.asyncio
async def test_gitlab_chunks_and_failure_modes(reg):
  reg["gitlab"] = FakeGit()
  bundle = await service.assemble_context(query="q", sources=["gitlab"])
  ids = [c.id for c in bundle.chunks]
  assert "gitlab:mr:a/b:1" in ids and "gitlab:commit:a/b:abc1234" in ids and "gitlab:issue:a/b:5" in ids

  reg["gitlab"] = FakeGit(authed=False)
  assert (await service.assemble_context(query="q", sources=["gitlab"])).missing_sources == ["gitlab"]
  reg["gitlab"] = FakeGit(repos=[])
  assert (await service.assemble_context(query="q", sources=["gitlab"])).missing_sources == ["gitlab (no projects selected)"]
  reg["gitlab"] = FakeGit(fail=True)
  assert (await service.assemble_context(query="q", sources=["gitlab"])).missing_sources == ["gitlab"]


def kchunk(cid, score):
  return ContextChunk(id=cid, source_type=SourceType.KNOWLEDGE, source_label="kb", title=cid, text=cid, score=score)


@pytest.mark.asyncio
async def test_knowledge_hits_sorted_by_score_and_capped(reg, monkeypatch):
  hits = [kchunk("low", 0.1), kchunk("none", None), kchunk("high", 0.9)]
  monkeypatch.setattr(service, "search_knowledge", lambda q, top_k=8: hits)
  bundle = await service.assemble_context(query="q", sources=["knowledge"])
  assert [c.id for c in bundle.chunks] == ["high", "low", "none"] and bundle.used_sources == ["knowledge"]

  many = [kchunk(f"c{i}", i / 100) for i in range(40)]
  monkeypatch.setattr(service, "search_knowledge", lambda q, top_k=8: many)
  assert len((await service.assemble_context(query="q", sources=["knowledge"], top_k=2)).chunks) == 24
  assert len((await service.assemble_context(query="q", sources=["knowledge"], top_k=10)).chunks) == 30


@pytest.mark.asyncio
async def test_knowledge_missing_reasons(reg, monkeypatch):
  monkeypatch.setattr("app.context.knowledge.list_documents", lambda: [])
  bundle = await service.assemble_context(query="q", sources=["knowledge"])
  assert bundle.missing_sources == ["knowledge (no documents uploaded)"] and bundle.is_empty
  monkeypatch.setattr("app.context.knowledge.list_documents", lambda: [{"id": "d"}])
  bundle = await service.assemble_context(query="q", sources=["knowledge", ""])
  assert bundle.missing_sources == ["knowledge (no matching chunks)"]


