"""Dependency injection providers."""

from __future__ import annotations

from typing import Any
from fastapi import Depends, Header, HTTPException, status

from app.core.json_history import (
    JsonChatRepository,
    JsonPRDRepository,
    JsonStandupRepository,
    JsonTestPlanRepository,
)
from app.core.security import decode_access_token
from app.db.interfaces import IUserRepository
from app.db.repositories import UserRepository


def get_user_repository() -> IUserRepository:
    """Dependency provider for User Repository."""
    return UserRepository()


def get_chat_repository() -> JsonChatRepository:
    """Dependency provider for Chat Repository."""
    return JsonChatRepository()


def get_standup_repository() -> JsonStandupRepository:
    """Dependency provider for Standup Repository."""
    return JsonStandupRepository()


def get_prd_repository() -> JsonPRDRepository:
    """Dependency provider for PRD Repository."""
    return JsonPRDRepository()


def get_test_plan_repository() -> JsonTestPlanRepository:
    """Dependency provider for Test Plan Repository."""
    return JsonTestPlanRepository()


async def get_current_user(
    authorization: str | None = Header(default=None),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> dict[str, Any]:
    """Dependency to retrieve and authenticate the current user from Bearer JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se proporcionó token de autorización.",
        )
    token = authorization.split(" ")[1].strip()
    payload = decode_access_token(token)
    if not payload or "username" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autorización inválido o expirado.",
        )
    user = await user_repo.get_by_username(payload["username"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    if user.get("status") != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario no autorizado o pendiente de aprobación.",
        )
    return {k: v for k, v in user.items() if k not in ("password_hash", "password_salt")}


async def get_current_admin_user(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Dependency to ensure the current authenticated user has admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido a administradores.",
        )
    return current_user
