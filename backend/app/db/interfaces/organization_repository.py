from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IOrganizationRepository(ABC):
  """Contrato para persistencia de organizaciones y membresías de usuario."""

  @abstractmethod
  async def get_by_id(self, org_id: str) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  async def get_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  async def create_organization(self, name: str, slug: str) -> Dict[str, Any]:
    pass

  @abstractmethod
  async def list_members(self, org_id: str) -> List[Dict[str, Any]]:
    pass

  @abstractmethod
  async def get_member(self, org_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  async def add_member(self, org_id: str, user_id: str, role: str = "member") -> Dict[str, Any]:
    pass

  @abstractmethod
  async def update_member_role(self, org_id: str, user_id: str, role: str) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  async def remove_member(self, org_id: str, user_id: str) -> bool:
    pass
