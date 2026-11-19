from __future__ import annotations

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.repositories.catalog_repository import AIModelCatalogRepository
from app.db.repositories.corporate_template_repository import CorporateTemplateRepository
from app.db.repositories.history_repository import (
  ChatRepository,
  PRDRepository,
  StandupRepository,
  TestPlanRepository,
)
from app.db.repositories.integration_repository import IntegrationRepository
from app.db.repositories.mcp_server_repository import McpServerRepository
from app.db.repositories.organization_repository import OrganizationRepository
from app.db.repositories.secret_repository import UserSecretRepository
from app.db.repositories.settings_repository import SettingsRepository
from app.db.repositories.template_repository import AITemplateRepository
from app.db.repositories.transcription_repository import TranscriptionRepository
from app.db.repositories.user_repository import UserRepository


class AsyncUnitOfWork:
  """Unit of Work asíncrono que administra la sesión y orquesta repositorios asíncronos."""

  def __init__(self, session_factory=None) -> None:
    self._session_factory = session_factory
    self._context_manager = None
    self.session: Optional[AsyncSession] = None

    self.users: Optional[UserRepository] = None
    self.mcp_servers: Optional[McpServerRepository] = None
    self.organizations: Optional[OrganizationRepository] = None
    self.chat: Optional[ChatRepository] = None
    self.standups: Optional[StandupRepository] = None
    self.prds: Optional[PRDRepository] = None
    self.test_plans: Optional[TestPlanRepository] = None
    self.ai_templates: Optional[AITemplateRepository] = None
    self.transcriptions: Optional[TranscriptionRepository] = None
    self.corporate_templates: Optional[CorporateTemplateRepository] = None

  async def __aenter__(self) -> "AsyncUnitOfWork":
    if self._session_factory:
      self.session = self._session_factory()
    else:
      from app.db.database import get_db
      self._context_manager = get_db()
      self.session = await self._context_manager.__aenter__()

    self.users = UserRepository(self.session)
    self.mcp_servers = McpServerRepository(self.session)
    self.organizations = OrganizationRepository(self.session)
    self.chat = ChatRepository(self.session)
    self.standups = StandupRepository(self.session)
    self.prds = PRDRepository(self.session)
    self.test_plans = TestPlanRepository(self.session)
    self.ai_templates = AITemplateRepository(self.session)
    self.transcriptions = TranscriptionRepository(self.session)
    self.corporate_templates = CorporateTemplateRepository(self.session)
    return self

  async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
    if exc_type is not None:
      await self.rollback()
    if self._context_manager is not None:
      await self._context_manager.__aexit__(exc_type, exc_val, exc_tb)
    elif self.session is not None and hasattr(self.session, "close"):
      res = self.session.close()
      import inspect
      if inspect.isawaitable(res):
        await res

  async def commit(self) -> None:
    if self.session and hasattr(self.session, "commit"):
      res = self.session.commit()
      import inspect
      if inspect.isawaitable(res):
        await res

  async def rollback(self) -> None:
    if self.session and hasattr(self.session, "rollback"):
      res = self.session.rollback()
      import inspect
      if inspect.isawaitable(res):
        await res


class SyncUnitOfWork:
  """Unit of Work síncrono que administra la sesión y orquesta repositorios síncronos."""

  def __init__(self, session_factory=None) -> None:
    self._session_factory = session_factory
    self._context_manager = None
    self.session: Optional[Session] = None

    self.secrets: Optional[UserSecretRepository] = None
    self.settings: Optional[SettingsRepository] = None
    self.integrations: Optional[IntegrationRepository] = None
    self.model_catalog: Optional[AIModelCatalogRepository] = None

  def __enter__(self) -> "SyncUnitOfWork":
    if self._session_factory:
      self.session = self._session_factory()
    else:
      from app.db.database import get_sync_db
      self._context_manager = get_sync_db()
      self.session = self._context_manager.__enter__()

    self.secrets = UserSecretRepository(self.session)
    self.settings = SettingsRepository(self.session)
    self.integrations = IntegrationRepository(self.session)
    self.model_catalog = AIModelCatalogRepository(self.session)
    return self

  def __exit__(self, exc_type, exc_val, exc_tb) -> None:
    if exc_type is not None:
      self.rollback()
    if self._context_manager is not None:
      self._context_manager.__exit__(exc_type, exc_val, exc_tb)
    elif self.session is not None and hasattr(self.session, "close"):
      self.session.close()

  def commit(self) -> None:
    if self.session and hasattr(self.session, "commit"):
      self.session.commit()

  def rollback(self) -> None:
    if self.session and hasattr(self.session, "rollback"):
      self.session.rollback()
