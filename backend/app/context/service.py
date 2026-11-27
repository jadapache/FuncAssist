"""Assemble context from live integrations + knowledge for a feature query."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.context.models import ContextBundle, ContextChunk, SourceType
from app.context.retrieval import search_knowledge
from app.integrations.registry import registry


@dataclass
class _Collected:
  """What the sources contributed so far. A source may be both used and missing when it fails half way."""

  chunks: list[ContextChunk] = field(default_factory=list)
  used: list[str] = field(default_factory=list)
  missing: list[str] = field(default_factory=list)


def _chunk(source: SourceType, kind: str, repo: Any, ref: Any, title: str, text: str, metadata: dict[str, Any]) -> ContextChunk:
  return ContextChunk(
    id=f"{source.value}:{kind}:{repo}:{ref}", source_type=source, source_label=str(repo), title=title, text=text, metadata=metadata,
  )


# --- Jira -------------------------------------------------------------------------------------


def _jira_text(issue: dict[str, Any]) -> str:
  return (
    f"Key: {issue.get('key')}\n"
    f"Summary: {issue.get('summary')}\n"
    f"Status: {issue.get('status')}\n"
    f"Assignee: {issue.get('assignee')}\n"
    f"Priority: {issue.get('priority')}\n"
    f"Updated: {issue.get('updated')}\n"
    f"Description: {issue.get('description') or ''}"
  )


def _jira_chunk(issue: dict[str, Any], text: str) -> ContextChunk:
  return ContextChunk(
    id=f"jira:{issue.get('key')}",
    source_type=SourceType.JIRA,
    source_label=str(issue.get("key")),
    title=str(issue.get("summary") or issue.get("key")),
    text=text,
    metadata=issue,
  )


def _jira_chunks(issues: list[dict[str, Any]], query: str) -> list[ContextChunk]:
  """Issues matching the query; when none match, the most recent ones, so the model still gets something."""
  matching = []
  for issue in issues:
    text = _jira_text(issue)
    if not query.strip() or _rough_match(query, text):
      matching.append(_jira_chunk(issue, text))
  if matching or not issues:
    return matching
  return [_jira_chunk(issue, json.dumps(issue, indent=2)[:1500]) for issue in issues[:12]]


async def _collect_jira(found: _Collected, query: str, user_id: str | None) -> None:
  jira = registry.get("jira")
  # Personal Jira scope: strictly require authenticated personal connection if user_id is provided
  if not await jira.authenticate(user_id=user_id):
    found.missing.append("jira")
    return
  try:
    issues = await jira.get_issues(max_results=25, user_id=user_id)
    found.used.append("jira")
    found.chunks.extend(_jira_chunks(issues, query))
  except Exception:
    found.missing.append("jira")


# --- GitHub and GitLab ------------------------------------------------------------------------


def _request_chunk(source: SourceType, kind: str, mark: str, item: dict[str, Any]) -> ContextChunk:
  """A GitHub pull request (`PR #`) or a GitLab merge request (`MR !`)."""
  number = item.get("number")
  text = (
    f"{mark}{number} in {item.get('repo')}\n"
    f"Title: {item.get('title')}\n"
    f"State: {item.get('state')}\n"
    f"Author: {item.get('user')}\n"
    f"Updated: {item.get('updated_at')}\n"
    f"Merged: {item.get('merged_at')}"
  )
  return _chunk(source, kind, item.get("repo"), number, f"{mark}{number}: {item.get('title')}", text, item)


def _commit_chunk(source: SourceType, commit: dict[str, Any]) -> ContextChunk:
  text = (
    f"Commit {commit.get('sha')} in {commit.get('repo')}\n"
    f"Author: {commit.get('author')}\n"
    f"Date: {commit.get('date')}\n"
    f"Message: {commit.get('message')}"
  )
  return _chunk(source, "commit", commit.get("repo"), commit.get("sha"), f"{commit.get('sha')} {commit.get('message')}", text, commit)


def _gitlab_issue_chunk(issue: dict[str, Any]) -> ContextChunk:
  number = issue.get("number")
  text = (
    f"Issue #{number} in {issue.get('repo')}\n"
    f"Title: {issue.get('title')}\n"
    f"State: {issue.get('state')}\n"
    f"Author: {issue.get('user')}\n"
    f"Updated: {issue.get('updated_at')}"
  )
  return _chunk(SourceType.GITLAB, "issue", issue.get("repo"), number, f"Issue #{number}: {issue.get('title')}", text, issue)


async def _github_chunks(github) -> list[ContextChunk]:
  prs = await github.get_pull_requests(max_results=20)
  commits = await github.get_commits(max_results=20)
  return [_request_chunk(SourceType.GITHUB, "pr", "PR #", pr) for pr in prs] + [_commit_chunk(SourceType.GITHUB, c) for c in commits]


async def _gitlab_chunks(gitlab) -> list[ContextChunk]:
  mrs = await gitlab.get_merge_requests(max_results=20)
  commits = await gitlab.get_commits(max_results=20)
  issues = await gitlab.get_issues(max_results=15)
  return (
    [_request_chunk(SourceType.GITLAB, "mr", "MR !", mr) for mr in mrs]
    + [_commit_chunk(SourceType.GITLAB, c) for c in commits]
    + [_gitlab_issue_chunk(issue) for issue in issues]
  )


async def _collect_repositories(found: _Collected, name: str, no_selection: str, chunks_of) -> None:
  """GitHub and GitLab share the flow: authenticated, something selected, then their own listings."""
  client = registry.get(name)
  if not await client.authenticate():
    found.missing.append(name)
    return
  try:
    if not client.selected_repos():
      found.missing.append(f"{name} ({no_selection})")
      return
    found.used.append(name)
    found.chunks.extend(await chunks_of(client))
  except Exception:
    found.missing.append(name)


# --- Knowledge --------------------------------------------------------------------------------


def _collect_knowledge(found: _Collected, query: str, top_k: int) -> None:
  hits = search_knowledge(query, top_k=top_k)
  if hits:
    found.used.append("knowledge")
    found.chunks.extend(hits)
    return
  from app.context.knowledge import list_documents

  reason = "no matching chunks" if list_documents() else "no documents uploaded"
  found.missing.append(f"knowledge ({reason})")


async def assemble_context(
  *,
  query: str,
  sources: Iterable[str],
  top_k: int = 8,
  user_id: str | None = None,
) -> ContextBundle:
  requested = {source.strip().lower() for source in sources if source}
  found = _Collected()
  if "jira" in requested:
    await _collect_jira(found, query, user_id)
  if "github" in requested:
    await _collect_repositories(found, "github", "no repositories selected", _github_chunks)
  if "gitlab" in requested:
    await _collect_repositories(found, "gitlab", "no projects selected", _gitlab_chunks)
  if "knowledge" in requested:
    _collect_knowledge(found, query, top_k)

  # Prefer higher relevance scores first, then live items
  found.chunks.sort(key=lambda item: item.score if item.score is not None else 0.0, reverse=True)
  return ContextBundle(
    query=query,
    chunks=found.chunks[: max(top_k * 3, 24)],
    missing_sources=found.missing,
    used_sources=found.used,
  )


def _rough_match(query: str, text: str) -> bool:
  tokens = [token for token in query.lower().split() if len(token) > 2]
  if not tokens:
    return True
  hay = text.lower()
  return any(token in hay for token in tokens)
