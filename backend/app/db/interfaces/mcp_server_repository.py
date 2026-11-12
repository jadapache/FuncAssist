from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IMcpServerRepository(ABC):
  """Contrato para persistencia de servidores MCP externos."""

  @abstractmethod
  async def get_by_id(self, server_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  async def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
    pass

  @abstractmethod
  async def create(
    self,
    user_id: str,
    name: str,
    endpoint_url: str,
    description: Optional[str] = None,
    transport_type: str = "sse",
    auth_type: str = "none",
    allowed_tools: Optional[List[str]] = None,
  ) -> Dict[str, Any]:
    pass

  @abstractmethod
  async def update(
    self,
    server_id: str,
    user_id: str,
    updates: Dict[str, Any],
  ) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  async def delete(self, server_id: str, user_id: str) -> bool:
    pass

  @abstractmethod
  async def update_status(
    self,
    server_id: str,
    user_id: str,
    status: str,
  ) -> Optional[Dict[str, Any]]:
    pass
