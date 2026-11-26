"""What GitHub and GitLab share: one organization connection and the repositories an administrator enabled."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from app.core.storage import load_connection, save_connection
from app.integrations.base import Integration, IntegrationInfo


class GitHostingIntegration(Integration):
  @abstractmethod
  def _is_connected(self, data: dict[str, Any] | None) -> bool:
    raise NotImplementedError

  def selected_repos(self) -> list[str]:
    data = load_connection(self.id) or {}
    return list(data.get("selected_repos") or [])

  async def update_selected_repos(self, repos: list[str]) -> IntegrationInfo:
    data = load_connection(self.id)
    if not data or not self._is_connected(data):
      raise ValueError(f"{self.name} is not connected.")
    data["selected_repos"] = repos
    save_connection(self.id, data)
    return self.get_info()
