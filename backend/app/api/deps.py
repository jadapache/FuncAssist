"""Dependency injection providers."""

from __future__ import annotations

from typing import Any
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.db.interfaces import IUserRepository
from app.db.repositories import (
  ChatRepository,
  PRDRepository,
  StandupRepository,
  TestPlanRepository,
  UserRepository,
)

security = HTTPBearer(auto_error=False)


def get_user_repository() -> IUserRepository:
  """Dependency provider for User Repository."""
  return UserRepository()


def get_chat_repository() -> ChatRepository:
  """Dependency provider for Chat Repository."""
  return ChatRepository()


def get_standup_repository() -> StandupRepository:
  """Dependency provider for Standup Repository."""
  return StandupRepository()


def get_prd_repository() -> PRDRepository:
  """Dependency provider for PRD Repository."""
  return PRDRepository()


def get_test_plan_repository() -> TestPlanRepository:
  """Dependency provider for Test Plan Repository."""
  return TestPlanRepository()


def _extract_token_from_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials.strip()
    auth_hdr = request.headers.get("authorization")
    if auth_hdr and auth_hdr.startswith("Bearer "):
        return auth_hdr.split(" ")[1].strip()
    query_token = request.query_params.get("token")
    if query_token:
        return query_token.strip()
    return None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> dict[str, Any]:
    """Dependency to retrieve and authenticate current user via Bearer JWT token."""
    raw_token = _extract_token_from_request(request, credentials)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se proporcionó token de autorización.",
        )

    payload = decode_access_token(raw_token)
    if not payload or "username" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autorización inválido o expirado.",
        )

    try:
        user = await user_repo.get_by_username(payload["username"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Error al conectar con la base de datos de usuarios.",
        ) from exc

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
