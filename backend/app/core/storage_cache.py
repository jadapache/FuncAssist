"""In-memory cache structures and cache isolation for settings and connections."""

from __future__ import annotations

from typing import Any

# In-memory fallbacks when database is initializing or during tests
_CACHE_APP_SETTINGS: dict[str, Any] = {}
# Isolated by composite key: f"{org_id}:{integration_id}"
_CACHE_CONNECTIONS: dict[str, bytes] = {}

DEFAULT_APP_SETTINGS: dict[str, Any] = {
  "display_name": "Usuario",
  "user_role": "admin",
  "theme": "command-center",
  "selected_repos": [],
}


def make_conn_cache_key(org_id: str, integration_id: str) -> str:
  """Build isolated composite key for connection cache."""
  resolved_org = (org_id or "default").strip()
  return f"{resolved_org}:{integration_id.strip()}"


def clear_storage_caches() -> None:
  """Clear all storage-related in-memory caches."""
  _CACHE_APP_SETTINGS.clear()
  _CACHE_CONNECTIONS.clear()

