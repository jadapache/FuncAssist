"""Integration contracts and shared models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AuthMethod(str, Enum):
  OAUTH = "oauth"


class ConnectionStatus(str, Enum):
  CONNECTED = "connected"
  NOT_CONNECTED = "not_connected"
  ERROR = "error"


class Capability(str, Enum):
  GET_ISSUES = "get_issues"
  GET_PROJECTS = "get_projects"
  GET_SPRINTS = "get_sprints"
  GET_PULL_REQUESTS = "get_pull_requests"
  GET_COMMITS = "get_commits"
  GET_FILES_CHANGED = "get_files_changed"
  GET_REPOSITORIES = "get_repositories"


class IntegrationInfo(BaseModel):
  id: str
  name: str
  description: str
  status: ConnectionStatus
  auth_methods: list[AuthMethod]
  capabilities: list[Capability]
  account_label: str | None = None
  workspace_label: str | None = None
  details: dict[str, Any] = Field(default_factory=dict)
  error: str | None = None
  oauth_configured: bool = False


class AuthStartResponse(BaseModel):
  authorization_url: str
  state: str
  auth_method: AuthMethod


class TestConnectionResult(BaseModel):
  ok: bool
  message: str
  details: dict[str, Any] = Field(default_factory=dict)


class Integration(ABC):
  """Base contract every adapter must implement."""

  id: str
  name: str
  description: str

  @abstractmethod
  def get_info(self) -> IntegrationInfo:
    raise NotImplementedError

  @abstractmethod
  def get_capabilities(self) -> list[Capability]:
    raise NotImplementedError

  @abstractmethod
  async def start_oauth(self) -> AuthStartResponse:
    raise NotImplementedError

  @abstractmethod
  async def handle_oauth_callback(self, code: str, state: str) -> IntegrationInfo:
    raise NotImplementedError

  @abstractmethod
  async def disconnect(self) -> None:
    raise NotImplementedError

  @abstractmethod
  async def test_connection(self) -> TestConnectionResult:
    raise NotImplementedError

  @abstractmethod
  async def authenticate(self) -> bool:
    """Return True when a valid connection is available."""
    raise NotImplementedError
