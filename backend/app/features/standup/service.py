"""Standup feature — Jira + GitHub only."""

from __future__ import annotations

from typing import Any

from app.ai.runner import run_grounded_feature


STANDUP_SOURCES = ["jira", "github"]


async def generate_standup(query: str | None = None, user_id: str | None = None) -> dict[str, Any]:
  return await run_grounded_feature(
    feature="standup",
    query=query
    or "Generate today's standup from recent Jira issue updates and GitHub PRs/commits.",
    sources=STANDUP_SOURCES,
    user_id=user_id,
  )
