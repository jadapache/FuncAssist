"""Sync integration live data with Redis shared cache."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.redis import get_redis_client
from app.integrations.registry import GIT_HOSTING_IDS, registry

CACHE_TTL_SECONDS = 3600 * 24  # 24 hours


def _cache_key(integration_id: str, tenant_or_user_id: str | None = None) -> str:
  prefix = f"user:{tenant_or_user_id}:" if tenant_or_user_id else "global:"
  return f"funcassist:sync:{prefix}{integration_id}"


async def _fetch_integration_payload(integration_id: str) -> dict[str, Any]:
  integration = registry.get(integration_id)
  if not await integration.authenticate():
    raise ValueError(f"{integration_id} is not connected.")

  synced_at = datetime.now(timezone.utc).isoformat()
  payload: dict[str, Any] = {
    "integration_id": integration_id,
    "synced_at": synced_at,
    "data": {},
  }

  if integration_id == "jira":
    payload["data"]["issues"] = await integration.get_issues(max_results=50)  # type: ignore[attr-defined]
    payload["data"]["projects"] = await integration.get_projects()  # type: ignore[attr-defined]
    payload["data"]["sprints"] = await integration.get_sprints()  # type: ignore[attr-defined]
  elif integration_id in GIT_HOSTING_IDS:
    payload["data"]["repositories"] = await integration.get_repositories()  # type: ignore[attr-defined]
    payload["data"]["pull_requests"] = await integration.get_pull_requests(max_results=30)  # type: ignore[attr-defined]
    payload["data"]["commits"] = await integration.get_commits(max_results=30)  # type: ignore[attr-defined]

    if integration_id == "gitlab":
      payload["data"]["issues"] = await integration.get_issues(max_results=30)  # type: ignore[attr-defined]

    prs = payload["data"].get("pull_requests") or []
    files_changed: list[dict[str, Any]] = []
    if prs and hasattr(integration, "get_files_changed"):
      first = prs[0]
      number = first.get("number")
      repo = first.get("repo")
      if number and repo:
        try:
          files_changed = await integration.get_files_changed(pr_number=int(number), repo=str(repo))  # type: ignore[attr-defined]
        except Exception:
          files_changed = []
    payload["data"]["files_changed"] = files_changed

  return payload


async def sync_integration(
  integration_id: str,
  user_id: str | None = None,
) -> dict[str, Any]:
  """Fetch live integration data and store exclusively in Redis cache."""
  payload = await _fetch_integration_payload(integration_id)
  key = _cache_key(integration_id, user_id)
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
