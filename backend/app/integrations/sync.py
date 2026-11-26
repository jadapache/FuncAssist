"""Sync integration live data with Redis shared cache."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.ai.injection import annotate_items
from app.core.redis import get_redis_client
from app.integrations.registry import GIT_HOSTING_IDS, registry

CACHE_TTL_SECONDS = 3600 * 24  # 24 hours


PERSONAL_INTEGRATION_IDS = frozenset({"jira"})


def _cache_key(integration_id: str, tenant_or_user_id: str | None = None) -> str:
  """Personal integrations (Jira) are cached per user; organization ones (GitHub, GitLab) are shared."""
  if integration_id in PERSONAL_INTEGRATION_IDS:
    if not tenant_or_user_id:
      raise ValueError(f"{integration_id} is a personal integration: a user is required.")
    return f"funcassist:sync:user:{tenant_or_user_id}:{integration_id}"
  return f"funcassist:sync:global:{integration_id}"


async def _require_connected(integration: Any, integration_id: str, user_id: str | None) -> None:
  if integration_id in PERSONAL_INTEGRATION_IDS:
    if not user_id:
      raise ValueError(f"{integration_id} is a personal integration: a user is required.")
    connected = await integration.authenticate(user_id=user_id)
  else:
    connected = await integration.authenticate()
  if not connected:
    raise ValueError(f"{integration_id} is not connected.")


async def _jira_data(integration: Any, user_id: str | None) -> dict[str, Any]:
  issues = await integration.get_issues(max_results=50, user_id=user_id)
  data = {
    "issues": issues,
    "projects": await integration.get_projects(user_id=user_id),
    "sprints": await integration.get_sprints(user_id=user_id),
  }
  annotate_items(issues, ("summary", "description"))
  return data


async def _first_pull_request_files(integration: Any, pull_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """The files of the most recent pull request; a failure to read them leaves the list empty."""
  if not pull_requests or not hasattr(integration, "get_files_changed"):
    return []
  number, repo = pull_requests[0].get("number"), pull_requests[0].get("repo")
  if not (number and repo):
    return []
  try:
    return await integration.get_files_changed(pr_number=int(number), repo=str(repo))
  except Exception:
    return []


async def _git_hosting_data(integration: Any, integration_id: str) -> dict[str, Any]:
  data: dict[str, Any] = {
    "repositories": await integration.get_repositories(),
    "pull_requests": await integration.get_pull_requests(max_results=30),
    "commits": await integration.get_commits(max_results=30),
  }
  if integration_id == "gitlab":
    data["issues"] = await integration.get_issues(max_results=30)
    annotate_items(data["issues"], ("title", "summary", "description"))
  annotate_items(data["pull_requests"], ("title", "body"))
  annotate_items(data["commits"], ("message",))
  data["files_changed"] = await _first_pull_request_files(integration, data["pull_requests"] or [])
  return data


async def _fetch_integration_payload(integration_id: str, user_id: str | None = None) -> dict[str, Any]:
  integration = registry.get(integration_id)
  await _require_connected(integration, integration_id, user_id)

  synced_at = datetime.now(timezone.utc).isoformat()
  data: dict[str, Any] = {}
  if integration_id == "jira":
    data = await _jira_data(integration, user_id)
  elif integration_id in GIT_HOSTING_IDS:
    data = await _git_hosting_data(integration, integration_id)
  return {"integration_id": integration_id, "synced_at": synced_at, "data": data}


async def sync_integration(
  integration_id: str,
  user_id: str | None = None,
) -> dict[str, Any]:
  """Fetch live integration data and store exclusively in Redis cache."""
  key = _cache_key(integration_id, user_id)  # validates that personal integrations have a user
  payload = await _fetch_integration_payload(integration_id, user_id)
  redis = get_redis_client()
  await redis.set(key, json.dumps(payload, indent=2), ex=CACHE_TTL_SECONDS)
  return payload


async def load_sync_cache(
  integration_id: str,
  user_id: str | None = None,
) -> dict[str, Any] | None:
  """Load cached integration data exclusively from Redis."""
  key = _cache_key(integration_id, user_id)
  redis = get_redis_client()
  val = await redis.get(key)
  if not val:
    return None
  return json.loads(val)
