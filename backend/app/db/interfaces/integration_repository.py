from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IIntegrationRepository(ABC):
  """Contrato para integraciones de usuario, integraciones de organización y credenciales BYOK."""

  @abstractmethod
  def get_user_integration(self, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  def save_user_integration(
    self,
    user_id: str,
    provider: str,
    external_account_id: Optional[str],
    external_account_name: Optional[str],
    access_token_ref: Optional[str],
    refresh_token_ref: Optional[str],
    expires_at: Optional[float],
    scopes_json: str,
    connection_metadata_json: str,
    status: str,
    jira_extra: Optional[Dict[str, Any]] = None,
  ) -> None:
    pass

  @abstractmethod
  def delete_user_integration(self, user_id: str, provider: str) -> bool:
    pass

  @abstractmethod
  def get_user_credential(self, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  def save_user_credential(
    self,
    user_id: str,
    provider: str,
    secret_id: str,
    secret_ref: str,
  ) -> None:
    pass

  @abstractmethod
  def delete_user_credential(self, user_id: str, provider: str) -> bool:
    pass

  @abstractmethod
  def list_user_credentials(self, user_id: str) -> List[Dict[str, Any]]:
    pass

  @abstractmethod
  def update_credential_validation(
    self,
    user_id: str,
    provider: str,
    status: str,
    error_msg: Optional[str],
  ) -> None:
    pass

  @abstractmethod
  def get_organization_integration(self, organization_id: str, provider: str) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  def save_organization_integration(
    self,
    organization_id: str,
    provider: str,
    client_id: Optional[str] = None,
    client_secret_ref: Optional[str] = None,
    status: str = "active",
    settings_payload: Optional[Dict[str, Any]] = None,
  ) -> None:
    pass

  @abstractmethod
  def delete_organization_integration(self, organization_id: str, provider: str) -> bool:
    pass

  @abstractmethod
  def organization_integration_exists(self, organization_id: str, provider: str) -> bool:
    pass
