from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IUserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def create_user_with_password(
        self,
        username: str,
        password_hash: str,
        password_salt: str,
        email: str = "",
        full_name: str = "",
        role: str = "user",
        status: str = "pending",
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_pending_users(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def update_user_status(self, user_id: str, status: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def update(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def count(self) -> int:
        pass
