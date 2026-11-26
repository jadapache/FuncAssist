from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.interfaces.integration_repository import IIntegrationRepository
from app.db.models import (
  OrganizationIntegrationModel,
  UserIntegrationModel,
  UserJiraConnectionModel,
  UserProviderCredentialModel,
)

logger = logging.getLogger(__name__)

_USER_INTEGRATION_FIELDS = (
  "external_account_id", "external_account_name", "access_token_ref", "refresh_token_ref", "expires_at",
  "scopes_json", "connection_metadata_json", "status",
)
_JIRA_SHARED_FIELDS = ("access_token_ref", "refresh_token_ref", "expires_at", "scopes_json", "status")
_JIRA_EXTRA_FIELDS = (
  "jira_url", "cloud_id", "account_email", "account_id", "access_token_secret_id", "refresh_token_secret_id",
)


def _iso(moment: Optional[datetime]) -> Optional[str]:
  return moment.isoformat() if moment else None


class IntegrationRepository(IIntegrationRepository):
  """Implementación PostgreSQL SQLAlchemy para IIntegrationRepository."""

  def __init__(self, session: Session) -> None:
    self.session = session

  def _user_integration(self, user_id: str, provider: str) -> Optional[UserIntegrationModel]:
    return self.session.scalar(select(UserIntegrationModel).where(UserIntegrationModel.user_id == user_id, UserIntegrationModel.provider == provider))

  def _jira_connection(self, user_id: str) -> Optional[UserJiraConnectionModel]:
    return self.session.scalar(select(UserJiraConnectionModel).where(UserJiraConnectionModel.user_id == user_id))

  def _credential(self, user_id: str, provider: str) -> Optional[UserProviderCredentialModel]:
    return self.session.scalar(select(UserProviderCredentialModel).where(UserProviderCredentialModel.user_id == user_id, UserProviderCredentialModel.provider == provider))

  def _organization_integration(self, organization_id: str, provider: str) -> Optional[OrganizationIntegrationModel]:
    return self.session.scalar(select(OrganizationIntegrationModel).where(OrganizationIntegrationModel.organization_id == organization_id, OrganizationIntegrationModel.provider == provider))

  def get_user_integration(self, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
    item = self._user_integration(user_id, provider)
    if not item:
      return None
    return {
      "id": item.id,
      "user_id": item.user_id,
      "provider": item.provider,
      **{field: getattr(item, field) for field in _USER_INTEGRATION_FIELDS},
    }

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
    values = {
      "external_account_id": external_account_id,
      "external_account_name": external_account_name,
      "access_token_ref": access_token_ref,
      "refresh_token_ref": refresh_token_ref,
      "expires_at": expires_at,
      "scopes_json": scopes_json,
      "connection_metadata_json": connection_metadata_json,
      "status": status,
    }
    item = self._user_integration(user_id, provider)
    if item:
      for field, value in values.items():
        setattr(item, field, value)
    else:
      self.session.add(UserIntegrationModel(id=str(uuid.uuid4()), user_id=user_id, provider=provider, **values))

    if provider == "jira" and jira_extra is not None:
      self._save_jira_connection(user_id, values, jira_extra)

    self.session.flush()

  def _save_jira_connection(self, user_id: str, shared: Dict[str, Any], jira_extra: Dict[str, Any]) -> None:
    """Jira keeps a second row per user with the connection data the Jira client reads."""
    values = {field: jira_extra.get(field) for field in _JIRA_EXTRA_FIELDS}
    values.update({field: shared[field] for field in _JIRA_SHARED_FIELDS})
    jira_item = self._jira_connection(user_id)
    if jira_item:
      for field, value in values.items():
        setattr(jira_item, field, value)
    else:
      self.session.add(UserJiraConnectionModel(id=str(uuid.uuid4()), user_id=user_id, **values))

  def delete_user_integration(self, user_id: str, provider: str) -> bool:
    item = self._user_integration(user_id, provider)
    if item:
      self.session.delete(item)

    jira_item = self._jira_connection(user_id) if provider == "jira" else None
    if jira_item:
      self.session.delete(jira_item)

    self.session.flush()
    return bool(item)

  def get_user_credential(self, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
    cred = self._credential(user_id, provider)
    if not cred:
      return None
    return {
      "id": cred.id,
      "user_id": cred.user_id,
      "provider": cred.provider,
      "secret_id": cred.secret_id,
      "secret_ref": cred.secret_ref,
      "status": cred.status,
      "validation_error": cred.validation_error,
      "last_validated_at": cred.last_validated_at,
      "updated_at": cred.updated_at,
    }

  def save_user_credential(
    self,
    user_id: str,
    provider: str,
    secret_id: str,
    secret_ref: str,
  ) -> None:
    cred = self._credential(user_id, provider)
    if cred:
      cred.secret_id = secret_id
      cred.secret_ref = secret_ref
      cred.status = "active"
      cred.validation_error = None
    else:
      self.session.add(UserProviderCredentialModel(
        id=str(uuid.uuid4()), user_id=user_id, provider=provider, secret_id=secret_id, secret_ref=secret_ref, status="active",
      ))

    self.session.flush()

  def delete_user_credential(self, user_id: str, provider: str) -> bool:
    cred = self._credential(user_id, provider)
    if not cred:
      return False
    self.session.delete(cred)
    self.session.flush()
    return True

  def list_user_credentials(self, user_id: str) -> List[Dict[str, Any]]:
    if not user_id:
      return []
    creds = self.session.scalars(select(UserProviderCredentialModel).where(UserProviderCredentialModel.user_id == user_id)).all()
    return [
      {
        "provider": c.provider,
        "status": c.status,
        "is_configured": True,
        "last_validated_at": _iso(c.last_validated_at),
        "validation_error": c.validation_error,
        "updated_at": _iso(c.updated_at),
      }
      for c in creds
    ]

  def update_credential_validation(
    self,
    user_id: str,
    provider: str,
    status: str,
    error_msg: Optional[str],
  ) -> None:
    cred = self._credential(user_id, provider)
    if cred:
      cred.status = status
      cred.last_validated_at = datetime.now(timezone.utc)
      cred.validation_error = error_msg
      self.session.flush()

  def get_organization_integration(self, organization_id: str, provider: str) -> Optional[Dict[str, Any]]:
    item = self._organization_integration(organization_id, provider)
    return item.to_dict() if item else None

  def save_organization_integration(
    self,
    organization_id: str,
    provider: str,
    client_id: Optional[str] = None,
    client_secret_ref: Optional[str] = None,
    status: str = "active",
    settings_payload: Optional[Dict[str, Any]] = None,
  ) -> None:
    item = self._organization_integration(organization_id, provider)
    if item is None:
      item = OrganizationIntegrationModel(id=str(uuid.uuid4()), organization_id=organization_id, provider=provider)
      self.session.add(item)
    # What was not given stays as it was, so a partial update never clears a stored secret.
    # `settings_payload` is part of the interface but the table has no column for it, so it is not stored.
    changes = {"client_id": client_id, "client_secret_ref": client_secret_ref, "status": status}
    for field, value in changes.items():
      if value is not None:
        setattr(item, field, value)
    self.session.flush()

  def delete_organization_integration(self, organization_id: str, provider: str) -> bool:
    item = self._organization_integration(organization_id, provider)
    if not item:
      return False
    self.session.delete(item)
    self.session.flush()
    return True

  def organization_integration_exists(self, organization_id: str, provider: str) -> bool:
    return self._organization_integration(organization_id, provider) is not None
