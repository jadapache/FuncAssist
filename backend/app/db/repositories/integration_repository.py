from __future__ import annotations

from datetime import datetime, timezone
import json
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


class IntegrationRepository(IIntegrationRepository):
  """Implementación PostgreSQL SQLAlchemy para IIntegrationRepository."""

  def __init__(self, session: Session) -> None:
    self.session = session

  def get_user_integration(self, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
    item = self.session.scalar(
      select(UserIntegrationModel).where(
        UserIntegrationModel.user_id == user_id,
        UserIntegrationModel.provider == provider,
      )
    )
    if not item:
      return None
    return {
      "id": item.id,
      "user_id": item.user_id,
      "provider": item.provider,
      "external_account_id": item.external_account_id,
      "external_account_name": item.external_account_name,
      "access_token_ref": item.access_token_ref,
      "refresh_token_ref": item.refresh_token_ref,
      "expires_at": item.expires_at,
      "scopes_json": item.scopes_json,
      "connection_metadata_json": item.connection_metadata_json,
      "status": item.status,
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
    item = self.session.scalar(
      select(UserIntegrationModel).where(
        UserIntegrationModel.user_id == user_id,
        UserIntegrationModel.provider == provider,
      )
    )
    if item:
      item.external_account_id = external_account_id
      item.external_account_name = external_account_name
      item.access_token_ref = access_token_ref
      item.refresh_token_ref = refresh_token_ref
      item.expires_at = expires_at
      item.scopes_json = scopes_json
      item.connection_metadata_json = connection_metadata_json
      item.status = status
    else:
      new_item = UserIntegrationModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        provider=provider,
        external_account_id=external_account_id,
        external_account_name=external_account_name,
        access_token_ref=access_token_ref,
        refresh_token_ref=refresh_token_ref,
        expires_at=expires_at,
        scopes_json=scopes_json,
        connection_metadata_json=connection_metadata_json,
        status=status,
      )
      self.session.add(new_item)

    if provider == "jira" and jira_extra is not None:
      jira_item = self.session.scalar(
        select(UserJiraConnectionModel).where(UserJiraConnectionModel.user_id == user_id)
      )
      jira_url = jira_extra.get("jira_url")
      cloud_id = jira_extra.get("cloud_id")
      account_email = jira_extra.get("account_email")
      account_id = jira_extra.get("account_id")
      access_secret_id = jira_extra.get("access_token_secret_id")
      refresh_secret_id = jira_extra.get("refresh_token_secret_id")

      if jira_item:
        jira_item.jira_url = jira_url
        jira_item.cloud_id = cloud_id
        jira_item.account_email = account_email
        jira_item.account_id = account_id
        jira_item.access_token_secret_id = access_secret_id
        jira_item.refresh_token_secret_id = refresh_secret_id
        jira_item.access_token_ref = access_token_ref
        jira_item.refresh_token_ref = refresh_token_ref
        jira_item.expires_at = expires_at
        jira_item.scopes_json = scopes_json
        jira_item.status = status
      else:
        new_jira = UserJiraConnectionModel(
          id=str(uuid.uuid4()),
          user_id=user_id,
          jira_url=jira_url,
          cloud_id=cloud_id,
          account_email=account_email,
          account_id=account_id,
          access_token_secret_id=access_secret_id,
          refresh_token_secret_id=refresh_secret_id,
          access_token_ref=access_token_ref,
          refresh_token_ref=refresh_token_ref,
          expires_at=expires_at,
          scopes_json=scopes_json,
          status=status,
        )
        self.session.add(new_jira)

    self.session.flush()

  def delete_user_integration(self, user_id: str, provider: str) -> bool:
    item = self.session.scalar(
      select(UserIntegrationModel).where(
        UserIntegrationModel.user_id == user_id,
        UserIntegrationModel.provider == provider,
      )
    )
    if item:
      self.session.delete(item)

    if provider == "jira":
      jira_item = self.session.scalar(
        select(UserJiraConnectionModel).where(UserJiraConnectionModel.user_id == user_id)
      )
      if jira_item:
        self.session.delete(jira_item)

    self.session.flush()
    return bool(item)

  def get_user_credential(self, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
    cred = self.session.scalar(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id,
        UserProviderCredentialModel.provider == provider,
      )
    )
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
    cred = self.session.scalar(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id,
        UserProviderCredentialModel.provider == provider,
      )
    )
    if cred:
      cred.secret_id = secret_id
      cred.secret_ref = secret_ref
      cred.status = "active"
      cred.validation_error = None
    else:
      cred = UserProviderCredentialModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        provider=provider,
        secret_id=secret_id,
        secret_ref=secret_ref,
        status="active",
      )
      self.session.add(cred)

    self.session.flush()

  def delete_user_credential(self, user_id: str, provider: str) -> bool:
    cred = self.session.scalar(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id,
        UserProviderCredentialModel.provider == provider,
      )
    )
    if not cred:
      return False
    self.session.delete(cred)
    self.session.flush()
    return True

  def list_user_credentials(self, user_id: str) -> List[Dict[str, Any]]:
    if not user_id:
      return []
    creds = self.session.scalars(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id
      )
    ).all()
    return [
      {
        "provider": c.provider,
        "status": c.status,
        "is_configured": True,
        "last_validated_at": c.last_validated_at.isoformat() if c.last_validated_at else None,
        "validation_error": c.validation_error,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
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
    cred = self.session.scalar(
      select(UserProviderCredentialModel).where(
        UserProviderCredentialModel.user_id == user_id,
        UserProviderCredentialModel.provider == provider,
      )
    )
    if cred:
      cred.status = status
      cred.last_validated_at = datetime.now(timezone.utc)
      cred.validation_error = error_msg
      self.session.flush()

  def get_organization_integration(self, organization_id: str, provider: str) -> Optional[Dict[str, Any]]:
    item = self.session.scalar(
      select(OrganizationIntegrationModel).where(
        OrganizationIntegrationModel.organization_id == organization_id,
        OrganizationIntegrationModel.provider == provider,
      )
    )
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
    item = self.session.scalar(
      select(OrganizationIntegrationModel).where(
        OrganizationIntegrationModel.organization_id == organization_id,
        OrganizationIntegrationModel.provider == provider,
      )
    )
    if item:
      if client_id is not None:
        item.client_id = client_id
      if client_secret_ref is not None:
        item.client_secret_ref = client_secret_ref
      if status is not None:
        item.status = status
      if settings_payload is not None:
        item.settings_json = settings_payload
    else:
      item = OrganizationIntegrationModel(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        provider=provider,
        client_id=client_id,
        client_secret_ref=client_secret_ref,
        status=status,
        settings_json=settings_payload,
      )
      self.session.add(item)
    self.session.flush()

  def delete_organization_integration(self, organization_id: str, provider: str) -> bool:
    item = self.session.scalar(
      select(OrganizationIntegrationModel).where(
        OrganizationIntegrationModel.organization_id == organization_id,
        OrganizationIntegrationModel.provider == provider,
      )
    )
    if not item:
      return False
    self.session.delete(item)
    self.session.flush()
    return True

  def organization_integration_exists(self, organization_id: str, provider: str) -> bool:
    item = self.session.scalar(
      select(OrganizationIntegrationModel.id).where(
        OrganizationIntegrationModel.organization_id == organization_id,
        OrganizationIntegrationModel.provider == provider,
      )
    )
    return item is not None
