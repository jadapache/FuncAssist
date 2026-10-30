"""SQLAlchemy Declarative ORM Models for PostgreSQL.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
  def __init__(self, **kwargs: Any) -> None:
    if "id" not in kwargs:
      kwargs["id"] = str(uuid.uuid4())
    for k, v in kwargs.items():
      setattr(self, k, v)


class UserModel(Base):
  __tablename__ = "users"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  username: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
  email: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="")
  full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="")
  role: Mapped[str] = mapped_column(String, default="user")
  password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  password_salt: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  status: Mapped[str] = mapped_column(String, default="pending")
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "username": self.username,
      "email": self.email or "",
      "full_name": self.full_name or self.username,
      "role": self.role,
      "password_hash": self.password_hash,
      "password_salt": self.password_salt,
      "status": self.status,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }


class SettingModel(Base):
  __tablename__ = "settings"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  key: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
  value_json: Mapped[str] = mapped_column(Text, nullable=False)
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  def to_dict(self) -> Dict[str, Any]:
    try:
      parsed = json.loads(self.value_json)
    except Exception:
      parsed = self.value_json
    return {
      "id": self.id,
      "key": self.key,
      "value": parsed,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


class OrganizationModel(Base):
  __tablename__ = "organizations"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  name: Mapped[str] = mapped_column(String(120), nullable=False)
  slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "name": self.name,
      "slug": self.slug,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


class OrganizationMemberModel(Base):
  __tablename__ = "organization_members"
  __table_args__ = (
    UniqueConstraint("organization_id", "user_id", name="uq_organization_members_org_user"),
  )

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  organization_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
  )
  user_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
  )
  role: Mapped[str] = mapped_column(String(50), default="member")
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

  organization = relationship("OrganizationModel", foreign_keys=[organization_id])
  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "organization_id": self.organization_id,
      "user_id": self.user_id,
      "role": self.role,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }


class UserSecretModel(Base):
  __tablename__ = "user_secrets"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  user_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
  )
  purpose: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
  ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
  nonce: Mapped[str] = mapped_column(Text, nullable=False)
  key_version: Mapped[int] = mapped_column(Integer, default=1)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "user_id": self.user_id,
      "purpose": self.purpose,
      "key_version": self.key_version,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


class UserPreferencesModel(Base):
  __tablename__ = "user_preferences"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  user_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
  )
  inference_provider: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  inference_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  transcription_provider: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  transcription_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  language: Mapped[Optional[str]] = mapped_column(String(10), default="es")
  settings_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "user_id": self.user_id,
      "inference_provider": self.inference_provider,
      "inference_model": self.inference_model,
      "transcription_provider": self.transcription_provider,
      "transcription_model": self.transcription_model,
      "language": self.language or "es",
      "settings_json": self.settings_json or {},
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


class UserProviderCredentialModel(Base):
  __tablename__ = "user_provider_credentials"
  __table_args__ = (
    UniqueConstraint("user_id", "provider", name="uq_user_provider_credentials_user_provider"),
  )

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  user_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
  )
  provider: Mapped[str] = mapped_column(Text, nullable=False)
  secret_id: Mapped[Optional[str]] = mapped_column(
    String(36), ForeignKey("user_secrets.id", ondelete="SET NULL"), nullable=True, index=True
  )
  secret_ref: Mapped[str] = mapped_column(Text, nullable=False)
  status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
  last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
  validation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  user = relationship("UserModel", foreign_keys=[user_id])
  secret = relationship("UserSecretModel", foreign_keys=[secret_id])

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "user_id": self.user_id,
      "provider": self.provider,
      "secret_id": self.secret_id,
      "secret_ref": self.secret_ref,
      "status": self.status,
      "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
      "validation_error": self.validation_error,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


class UserJiraConnectionModel(Base):
  __tablename__ = "user_jira_connections"
  __table_args__ = (
    UniqueConstraint("user_id", name="uq_user_jira_connections_user"),
  )

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  user_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
  )
  jira_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  cloud_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  account_email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  account_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  access_token_secret_id: Mapped[Optional[str]] = mapped_column(
    String(36), ForeignKey("user_secrets.id", ondelete="SET NULL"), nullable=True
  )
  refresh_token_secret_id: Mapped[Optional[str]] = mapped_column(
    String(36), ForeignKey("user_secrets.id", ondelete="SET NULL"), nullable=True
  )
  access_token_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  refresh_token_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  expires_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
  scopes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="[]")
  status: Mapped[str] = mapped_column(Text, nullable=False, default="connected")
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    try:
      scopes = json.loads(self.scopes_json) if self.scopes_json else []
    except Exception:
      scopes = []
    return {
      "id": self.id,
      "user_id": self.user_id,
      "jira_url": self.jira_url,
      "cloud_id": self.cloud_id,
      "account_email": self.account_email,
      "account_id": self.account_id,
      "expires_at": self.expires_at,
      "scopes": scopes,
      "status": self.status,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


class AuditEventModel(Base):
  __tablename__ = "audit_events"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  user_id: Mapped[Optional[str]] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
  )
  action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
  resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
  resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
  details_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
  ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "user_id": self.user_id,
      "action": self.action,
      "resource_type": self.resource_type,
      "resource_id": self.resource_id,
      "details": self.details_json or {},
      "ip_address": self.ip_address,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }


class OrganizationIntegrationModel(Base):
  __tablename__ = "organization_integrations"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  organization_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, default="default", index=True
  )
  provider: Mapped[str] = mapped_column(Text, nullable=False)
  client_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  client_secret_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
  created_by: Mapped[Optional[str]] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
  )
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  organization = relationship("OrganizationModel", foreign_keys=[organization_id])
  creator = relationship("UserModel", foreign_keys=[created_by])

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "organization_id": self.organization_id,
      "provider": self.provider,
      "client_id": self.client_id,
      "client_secret_ref": self.client_secret_ref,
      "status": self.status,
      "created_by": self.created_by,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


class UserIntegrationModel(Base):
  __tablename__ = "user_integrations"
  __table_args__ = (
    UniqueConstraint("user_id", "provider", name="uq_user_integrations_user_provider"),
  )

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  user_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
  )
  provider: Mapped[str] = mapped_column(Text, nullable=False, index=True)
  external_account_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  external_account_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  access_token_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  refresh_token_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  expires_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
  scopes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="[]")
  connection_metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="{}")
  status: Mapped[str] = mapped_column(Text, nullable=False, default="connected")
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    try:
      scopes = json.loads(self.scopes_json) if self.scopes_json else []
    except Exception:
      scopes = []
    try:
      metadata = json.loads(self.connection_metadata_json) if self.connection_metadata_json else {}
    except Exception:
      metadata = {}
    return {
      "id": self.id,
      "user_id": self.user_id,
      "provider": self.provider,
      "external_account_id": self.external_account_id,
      "external_account_name": self.external_account_name,
      "expires_at": self.expires_at,
      "scopes": scopes,
      "metadata": metadata,
      "status": self.status,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


class McpServerModel(Base):
  __tablename__ = "mcp_servers"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  organization_id: Mapped[str] = mapped_column(String, nullable=False, default="default", index=True)
  user_id: Mapped[Optional[str]] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
  )
  name: Mapped[str] = mapped_column(String, nullable=False)
  description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
  transport_type: Mapped[str] = mapped_column(String, nullable=False, default="sse")
  auth_type: Mapped[str] = mapped_column(String, nullable=False, default="none")
  auth_secret_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  status: Mapped[str] = mapped_column(Text, nullable=False, default="configured")
  allowed_tools_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="[]")
  metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="{}")
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    try:
      allowed_tools = json.loads(self.allowed_tools_json) if self.allowed_tools_json else []
    except Exception:
      allowed_tools = []
    try:
      meta = json.loads(self.metadata_json) if self.metadata_json else {}
    except Exception:
      meta = {}
    return {
      "id": self.id,
      "organization_id": self.organization_id,
      "user_id": self.user_id,
      "name": self.name,
      "description": self.description or "",
      "endpoint_url": self.endpoint_url,
      "transport_type": self.transport_type,
      "auth_type": self.auth_type,
      "status": self.status,
      "allowed_tools": allowed_tools,
      "metadata": meta,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


class ChatSessionModel(Base):
  __tablename__ = "chat_sessions"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  user_id: Mapped[Optional[str]] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
  )
  title: Mapped[str] = mapped_column(String, nullable=False, default="Nueva conversación")
  feature_slug: Mapped[str] = mapped_column(String, nullable=False, default="general", index=True)
  document_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
  artifacts_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="[]")
  active_artifact_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    try:
      artifacts = json.loads(self.artifacts_json) if self.artifacts_json else []
    except Exception:
      artifacts = []
    return {
      "id": self.id,
      "user_id": self.user_id,
      "name": self.title,
      "title": self.title,
      "feature_slug": self.feature_slug,
      "documentContent": self.document_content or "",
      "artifacts": artifacts,
      "activeArtifactId": self.active_artifact_id,
      "lastInteraction": self.updated_at.isoformat() if self.updated_at else datetime.now(timezone.utc).isoformat(),
      "created_at": self.created_at.isoformat() if self.created_at else datetime.now(timezone.utc).isoformat(),
    }


class ChatMessageModel(Base):
  __tablename__ = "chat_messages"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  session_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
  )
  user_id: Mapped[Optional[str]] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
  )
  role: Mapped[str] = mapped_column(String, nullable=False)
  content: Mapped[str] = mapped_column(Text, nullable=False)
  context_sources_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  attachments_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="[]")
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

  session = relationship("ChatSessionModel", foreign_keys=[session_id])
  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    sources = []
    if self.context_sources_json:
      try:
        sources = json.loads(self.context_sources_json)
      except Exception:
        sources = []
    attachments = []
    if self.attachments_json:
      try:
        attachments = json.loads(self.attachments_json)
      except Exception:
        attachments = []
    return {
      "id": self.id,
      "session_id": self.session_id,
      "user_id": self.user_id,
      "role": self.role,
      "content": self.content,
      "context_sources": sources,
      "attachments": attachments,
      "timestamp": self.created_at.strftime("%H:%M") if self.created_at else "",
      "created_at": self.created_at.isoformat() if self.created_at else datetime.now(timezone.utc).isoformat(),
    }


class StandupModel(Base):
  __tablename__ = "standups"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  user_id: Mapped[Optional[str]] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
  )
  title: Mapped[str] = mapped_column(String, nullable=False)
  content: Mapped[str] = mapped_column(Text, nullable=False)
  sources_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    sources = []
    if self.sources_json:
      try:
        sources = json.loads(self.sources_json)
      except Exception:
        sources = []
    return {
      "id": self.id,
      "user_id": self.user_id,
      "title": self.title,
      "content": self.content,
      "sources": sources,
      "created_at": self.created_at.isoformat() if self.created_at else datetime.now(timezone.utc).isoformat(),
    }


class PRDReviewModel(Base):
  __tablename__ = "prd_reviews"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  user_id: Mapped[Optional[str]] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
  )
  prd_title: Mapped[str] = mapped_column(String, nullable=False)
  content: Mapped[str] = mapped_column(Text, nullable=False)
  score: Mapped[int] = mapped_column(Integer, default=0)
  risk_level: Mapped[str] = mapped_column(String, default="MEDIUM")
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "user_id": self.user_id,
      "prd_title": self.prd_title,
      "content": self.content,
      "score": self.score,
      "risk_level": self.risk_level,
      "created_at": self.created_at.isoformat() if self.created_at else datetime.now(timezone.utc).isoformat(),
    }


class TestPlanModel(Base):
  __test__ = False
  __tablename__ = "test_plans"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  user_id: Mapped[Optional[str]] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
  )
  feature_name: Mapped[str] = mapped_column(String, nullable=False)
  test_type: Mapped[str] = mapped_column(String, default="regression")
  content: Mapped[str] = mapped_column(Text, nullable=False)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

  user = relationship("UserModel", foreign_keys=[user_id])

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "user_id": self.user_id,
      "feature_name": self.feature_name,
      "test_type": self.test_type,
      "content": self.content,
      "created_at": self.created_at.isoformat() if self.created_at else datetime.now(timezone.utc).isoformat(),
    }


class AITemplateModel(Base):
  """Current active version of an AI prompt or rubric template."""
  __tablename__ = "ai_templates"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))  
  template_type: Mapped[str] = mapped_column(String, nullable=False, index=True) 
  feature: Mapped[str] = mapped_column(String, nullable=False, index=True)
  version: Mapped[int] = mapped_column(Integer, default=1)
  payload_json: Mapped[str] = mapped_column(Text, nullable=False)
  updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  def to_dict(self) -> Dict[str, Any]:
    try:
      parsed = json.loads(self.payload_json)
    except Exception:
      parsed = {}
    return {
      "id": self.id,
      "template_type": self.template_type,
      "feature": self.feature,
      "version": self.version,
      "updated_by": self.updated_by,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
      **parsed,
    }


class AITemplateVersionModel(Base):
  """Audit history log of all prompt/rubric template changes."""
  __tablename__ = "ai_template_versions"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  template_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("ai_templates.id", ondelete="CASCADE"), nullable=False, index=True
  )
  template_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
  feature: Mapped[str] = mapped_column(String, nullable=False, index=True)
  version: Mapped[int] = mapped_column(Integer, nullable=False)
  payload_json: Mapped[str] = mapped_column(Text, nullable=False)
  change_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

  template = relationship("AITemplateModel", foreign_keys=[template_id])

  def to_dict(self) -> Dict[str, Any]:
    try:
      parsed = json.loads(self.payload_json)
    except Exception:
      parsed = {}
    return {
      "id": self.id,
      "template_id": self.template_id,
      "template_type": self.template_type,
      "feature": self.feature,
      "version": self.version,
      "change_summary": self.change_summary,
      "created_by": self.created_by,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      **parsed,
    }


class TranscriptionModel(Base):
  """Transcription, segments, summary, and audio metadata stored in PostgreSQL."""
  __tablename__ = "transcriptions"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  title: Mapped[str] = mapped_column(String, nullable=False, default="Reunión")
  description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
  original_filename: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="")
  stored_filename: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="")
  audio_path: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="")
  duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
  language: Mapped[str] = mapped_column(String, default="es")
  status: Mapped[str] = mapped_column(String, default="completed", index=True)
  model_info: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="Whisper")
  text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
  segments_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="[]")
  summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
  metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="{}")
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  def to_dict(self) -> Dict[str, Any]:
    try:
      segments = json.loads(self.segments_json) if self.segments_json else []
    except Exception:
      segments = []

    try:
      summary = json.loads(self.summary_json) if self.summary_json else None
    except Exception:
      summary = None

    try:
      meta = json.loads(self.metadata_json) if self.metadata_json else {}
    except Exception:
      meta = {}

    created_iso = self.created_at.isoformat() if self.created_at else datetime.now(timezone.utc).isoformat()

    return {
      "id": self.id,
      "media_id": self.id,
      "title": self.title,
      "description": self.description or "",
      "original_filename": self.original_filename or "",
      "filename": self.original_filename or "",
      "stored_filename": self.stored_filename or "",
      "path": self.audio_path or "",
      "created_at": created_iso,
      "status": self.status,
      "language": self.language,
      "duration_seconds": self.duration_seconds,
      "model_info": self.model_info or "Whisper",
      "segments": segments,
      "text": self.text or "",
      "summary": summary,
      "metadata": {
        "title": self.title,
        "description": self.description or "",
        **meta,
      },
      "media": {
        "id": self.id,
        "transcription_id": self.id,
        "original_filename": self.original_filename or "",
        "filename": self.original_filename or "",
        "title": self.title,
        "description": self.description or "",
        "created_at": created_iso,
        **meta.get("media", {}),
        "stored_filename": self.stored_filename or meta.get("media", {}).get("stored_filename", ""),
        "path": self.audio_path or meta.get("media", {}).get("path", ""),
        "is_video": (self.stored_filename or "").endswith((".mp4", ".mkv", ".avi", ".mov", ".webm")),
      },
    }


class CorporateTemplateModel(Base):
  """Corporate document templates metadata and content stored in PostgreSQL."""
  __tablename__ = "corporate_templates"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  title: Mapped[str] = mapped_column(String, nullable=False)
  filename: Mapped[str] = mapped_column(String, nullable=False)
  stored_filename: Mapped[str] = mapped_column(String, nullable=False)
  file_type: Mapped[str] = mapped_column(String, default="docx")
  file_size: Mapped[int] = mapped_column(Integer, default=0)
  module: Mapped[str] = mapped_column(String, default="general")
  tags_json: Mapped[str] = mapped_column(Text, default="[]")
  custom_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  def to_dict(self) -> Dict[str, Any]:
    try:
      tags = json.loads(self.tags_json) if self.tags_json else []
    except Exception:
      tags = []
    res: Dict[str, Any] = {
      "id": self.id,
      "title": self.title,
      "filename": self.filename,
      "stored_filename": self.stored_filename,
      "file_type": self.file_type,
      "file_size": self.file_size,
      "module": self.module,
      "tags": tags,
      "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
    }
    if self.custom_content is not None:
      res["custom_content"] = self.custom_content
    return res


class AIModelCatalogModel(Base):
  """Frontier and built-in AI models catalog synchronized into PostgreSQL."""
  __tablename__ = "ai_models_catalog"

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
  provider: Mapped[str] = mapped_column(String, nullable=False, index=True)
  task_type: Mapped[str] = mapped_column(String, nullable=False, default="chat_writing", index=True)
  name: Mapped[str] = mapped_column(String, nullable=False)
  is_free: Mapped[bool] = mapped_column(Boolean, default=False)
  tier_type: Mapped[str] = mapped_column(String, default="paid")
  payload_json: Mapped[str] = mapped_column(Text, nullable=False)
  updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now()
  )

  def to_dict(self) -> Dict[str, Any]:
    try:
      parsed = json.loads(self.payload_json)
    except Exception:
      parsed = {}
    return {
      "id": self.id,
      "provider": self.provider,
      "task_type": self.task_type,
      "name": self.name,
      "is_free": self.is_free,
      "tier_type": self.tier_type,
      **parsed,
    }


