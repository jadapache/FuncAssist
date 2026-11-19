"""Dependency injection providers."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Generator
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.database import get_db, get_sync_db
from app.db.interfaces import (
  IAITemplateRepository,
  ICorporateTemplateRepository,
  IIntegrationRepository,
  IMcpServerRepository,
  IOrganizationRepository,
  ISettingsRepository,
  ITranscriptionRepository,
  IUserRepository,
  IUserSecretRepository,
)
from app.db.repositories import (
  AITemplateRepository,
  ChatRepository,
  CorporateTemplateRepository,
  IntegrationRepository,
  McpServerRepository,
  OrganizationRepository,
  PRDRepository,
  SettingsRepository,
  StandupRepository,
  TestPlanRepository,
  TranscriptionRepository,
  UserRepository,
  UserSecretRepository,
)

security = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
  """Dependency provider for AsyncSession."""
  async with get_db() as session:
    yield session


def get_sync_db_session() -> Generator[Session, None]:
  """Dependency provider for sync Session."""
  with get_sync_db() as session:
    yield session


def get_user_repository(
  session: AsyncSession = Depends(get_db_session),
) -> IUserRepository:
  """Dependency provider for User Repository."""
  return UserRepository(session)


def get_mcp_server_repository(
  session: AsyncSession = Depends(get_db_session),
) -> IMcpServerRepository:
  """Dependency provider for McpServer Repository."""
  return McpServerRepository(session)


def get_organization_repository(
  session: AsyncSession = Depends(get_db_session),
) -> IOrganizationRepository:
  """Dependency provider for Organization Repository."""
  return OrganizationRepository(session)


def get_integration_repository(
  session: Session = Depends(get_sync_db_session),
) -> IIntegrationRepository:
  """Dependency provider for Integration Repository."""
  return IntegrationRepository(session)


def get_secret_repository(
  session: Session = Depends(get_sync_db_session),
) -> IUserSecretRepository:
  """Dependency provider for UserSecret Repository."""
  return UserSecretRepository(session)


def get_settings_repository(
  session: Session = Depends(get_sync_db_session),
) -> ISettingsRepository:
  """Dependency provider for Settings Repository."""
  return SettingsRepository(session)


def get_chat_repository(
  session: AsyncSession = Depends(get_db_session),
) -> ChatRepository:
  """Dependency provider for Chat Repository."""
  return ChatRepository(session)


def get_standup_repository(
  session: AsyncSession = Depends(get_db_session),
) -> StandupRepository:
  """Dependency provider for Standup Repository."""
  return StandupRepository(session)


def get_prd_repository(
  session: AsyncSession = Depends(get_db_session),
) -> PRDRepository:
  """Dependency provider for PRD Repository."""
  return PRDRepository(session)


def get_test_plan_repository(
  session: AsyncSession = Depends(get_db_session),
) -> TestPlanRepository:
  """Dependency provider for Test Plan Repository."""
  return TestPlanRepository(session)


def get_ai_template_repository(
  session: AsyncSession = Depends(get_db_session),
) -> IAITemplateRepository:
  """Dependency provider for AITemplate Repository."""
  return AITemplateRepository(session)


def get_transcription_repository(
  session: AsyncSession = Depends(get_db_session),
) -> ITranscriptionRepository:
  """Dependency provider for Transcription Repository."""
  return TranscriptionRepository(session)


def get_corporate_template_repository(
  session: AsyncSession = Depends(get_db_session),
) -> ICorporateTemplateRepository:
  """Dependency provider for Corporate Template Repository."""
  return CorporateTemplateRepository(session)


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
