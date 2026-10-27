"""Assemble context from live integrations + knowledge for a feature query."""

from __future__ import annotations

import json
from typing import Iterable

from app.context.models import ContextBundle, ContextChunk, SourceType
from app.context.retrieval import search_knowledge
from app.integrations.registry import registry


async def assemble_context(
  *,
  query: str,
  sources: Iterable[str],
  top_k: int = 8,
  user_id: str | None = None,
) -> ContextBundle:
  requested = {source.strip().lower() for source in sources if source}
  chunks: list[ContextChunk] = []
  missing: list[str] = []
  used: list[str] = []

  if "jira" in requested:
    jira = registry.get("jira")
    # Personal Jira scope: strictly require authenticated personal connection if user_id is provided
    is_authed = await jira.authenticate(user_id=user_id) if hasattr(jira, "authenticate") else await jira.authenticate()
    if not is_authed:
      missing.append("jira")
    else:
      try:
        issues = await jira.get_issues(max_results=25, user_id=user_id) if hasattr(jira, "get_issues") else await jira.get_issues(max_results=25)
        used.append("jira")
        for issue in issues:
          text = (
            f"Key: {issue.get('key')}\n"
            f"Summary: {issue.get('summary')}\n"
            f"Status: {issue.get('status')}\n"
            f"Assignee: {issue.get('assignee')}\n"
            f"Priority: {issue.get('priority')}\n"
            f"Updated: {issue.get('updated')}\n"
            f"Description: {issue.get('description') or ''}"
          )
          if query.strip() and not _rough_match(query, text):
            continue
          chunks.append(
            ContextChunk(
              id=f"jira:{issue.get('key')}",
              source_type=SourceType.JIRA,
              source_label=str(issue.get("key")),
              title=str(issue.get("summary") or issue.get("key")),
              text=text,
              metadata=issue,
            )
          )
        # If query filtering removed everything, keep recent issues as context
        if not any(chunk.source_type == SourceType.JIRA for chunk in chunks) and issues:
          for issue in issues[:12]:
            chunks.append(
              ContextChunk(
                id=f"jira:{issue.get('key')}",
                source_type=SourceType.JIRA,
                source_label=str(issue.get("key")),
                title=str(issue.get("summary") or issue.get("key")),
                text=json.dumps(issue, indent=2)[:1500],
                metadata=issue,
              )
            )
      except Exception:
        missing.append("jira")

  if "github" in requested:
    github = registry.get("github")
    if not await github.authenticate():
      missing.append("github")
    else:
      try:
        selected = github.selected_repos()  # type: ignore[attr-defined]
        if not selected:
          missing.append("github (no repositories selected)")
        else:
          used.append("github")
          prs = await github.get_pull_requests(max_results=20)  # type: ignore[attr-defined]
          commits = await github.get_commits(max_results=20)  # type: ignore[attr-defined]
          for pr in prs:
            text = (
              f"PR #{pr.get('number')} in {pr.get('repo')}\n"
              f"Title: {pr.get('title')}\n"
              f"State: {pr.get('state')}\n"
              f"Author: {pr.get('user')}\n"
              f"Updated: {pr.get('updated_at')}\n"
              f"Merged: {pr.get('merged_at')}"
            )
            chunks.append(
              ContextChunk(
                id=f"github:pr:{pr.get('repo')}:{pr.get('number')}",
                source_type=SourceType.GITHUB,
                source_label=str(pr.get("repo")),
                title=f"PR #{pr.get('number')}: {pr.get('title')}",
                text=text,
                metadata=pr,
              )
            )
          for commit in commits:
            chunks.append(
              ContextChunk(
                id=f"github:commit:{commit.get('repo')}:{commit.get('sha')}",
                source_type=SourceType.GITHUB,
                source_label=str(commit.get("repo")),
                title=f"{commit.get('sha')} {commit.get('message')}",
                text=(
                  f"Commit {commit.get('sha')} in {commit.get('repo')}\n"
                  f"Author: {commit.get('author')}\n"
                  f"Date: {commit.get('date')}\n"
                  f"Message: {commit.get('message')}"
                ),
                metadata=commit,
              )
            )
      except Exception:
        missing.append("github")

  if "gitlab" in requested:
    gitlab = registry.get("gitlab")
    if not await gitlab.authenticate():
      missing.append("gitlab")
    else:
      try:
        selected = gitlab.selected_repos()  # type: ignore[attr-defined]
        if not selected:
          missing.append("gitlab (no projects selected)")
        else:
          used.append("gitlab")
          mrs = await gitlab.get_merge_requests(max_results=20)  # type: ignore[attr-defined]
          commits = await gitlab.get_commits(max_results=20)  # type: ignore[attr-defined]
          issues = await gitlab.get_issues(max_results=15)  # type: ignore[attr-defined]
          for mr in mrs:
            text = (
              f"MR !{mr.get('number')} in {mr.get('repo')}\n"
              f"Title: {mr.get('title')}\n"
              f"State: {mr.get('state')}\n"
              f"Author: {mr.get('user')}\n"
              f"Updated: {mr.get('updated_at')}\n"
              f"Merged: {mr.get('merged_at')}"
            )
            chunks.append(
              ContextChunk(
                id=f"gitlab:mr:{mr.get('repo')}:{mr.get('number')}",
                source_type=SourceType.GITLAB,
                source_label=str(mr.get("repo")),
                title=f"MR !{mr.get('number')}: {mr.get('title')}",
                text=text,
                metadata=mr,
              )
            )
          for commit in commits:
            chunks.append(
              ContextChunk(
                id=f"gitlab:commit:{commit.get('repo')}:{commit.get('sha')}",
                source_type=SourceType.GITLAB,
                source_label=str(commit.get("repo")),
                title=f"{commit.get('sha')} {commit.get('message')}",
                text=(
                  f"Commit {commit.get('sha')} in {commit.get('repo')}\n"
                  f"Author: {commit.get('author')}\n"
                  f"Date: {commit.get('date')}\n"
                  f"Message: {commit.get('message')}"
                ),
                metadata=commit,
              )
            )
          for issue in issues:
            chunks.append(
              ContextChunk(
                id=f"gitlab:issue:{issue.get('repo')}:{issue.get('number')}",
                source_type=SourceType.GITLAB,
                source_label=str(issue.get("repo")),
                title=f"Issue #{issue.get('number')}: {issue.get('title')}",
                text=(
                  f"Issue #{issue.get('number')} in {issue.get('repo')}\n"
                  f"Title: {issue.get('title')}\n"
                  f"State: {issue.get('state')}\n"
                  f"Author: {issue.get('user')}\n"
                  f"Updated: {issue.get('updated_at')}"
                ),
                metadata=issue,
              )
            )
      except Exception:
        missing.append("gitlab")

  if "knowledge" in requested:
    knowledge_hits = search_knowledge(query, top_k=top_k)
    if knowledge_hits:
      used.append("knowledge")
      chunks.extend(knowledge_hits)
    else:
      from app.context.knowledge import list_documents

      if not list_documents():
        missing.append("knowledge (no documents uploaded)")
      else:
        missing.append("knowledge (no matching chunks)")

  # Prefer higher BM25 scores first, then live items
  chunks.sort(key=lambda item: item.score if item.score is not None else 0.0, reverse=True)
  return ContextBundle(
    query=query,
    chunks=chunks[: max(top_k * 3, 24)],
    missing_sources=missing,
    used_sources=used,
  )


def _rough_match(query: str, text: str) -> bool:
  tokens = [token for token in query.lower().split() if len(token) > 2]
  if not tokens:
    return True
  hay = text.lower()
  return any(token in hay for token in tokens)
