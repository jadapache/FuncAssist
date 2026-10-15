"""SQLAlchemy Declarative ORM Models for PostgreSQL.

Pure PostgreSQL - No local SQLite or JSON persistence.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
  pass


class UserModel(Base):
  __tablename__ = "users"

  id: Mapped[str] = mapped_column(String, primary_key=True)
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

  key: Mapped[str] = mapped_column(String, primary_key=True)
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
      "key": self.key,
      "value": parsed,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


class ChatMessageModel(Base):
  __tablename__ = "chat_messages"

  id: Mapped[str] = mapped_column(String, primary_key=True)
  session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
  user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  role: Mapped[str] = mapped_column(String, nullable=False)
  content: Mapped[str] = mapped_column(Text, nullable=False)
  context_sources_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

  def to_dict(self) -> Dict[str, Any]:
    sources = []
    if self.context_sources_json:
      try:
        sources = json.loads(self.context_sources_json)
      except Exception:
        sources = []
    return {
      "id": self.id,
      "session_id": self.session_id,
      "user_id": self.user_id,
      "role": self.role,
      "content": self.content,
      "context_sources": sources,
      "created_at": self.created_at.isoformat() if self.created_at else datetime.now(timezone.utc).isoformat(),
    }


class StandupModel(Base):
  __tablename__ = "standups"

  id: Mapped[str] = mapped_column(String, primary_key=True)
  user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  title: Mapped[str] = mapped_column(String, nullable=False)
  content: Mapped[str] = mapped_column(Text, nullable=False)
  sources_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

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

  id: Mapped[str] = mapped_column(String, primary_key=True)
  user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  prd_title: Mapped[str] = mapped_column(String, nullable=False)
  content: Mapped[str] = mapped_column(Text, nullable=False)
  score: Mapped[int] = mapped_column(Integer, default=0)
  risk_level: Mapped[str] = mapped_column(String, default="MEDIUM")
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

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

  id: Mapped[str] = mapped_column(String, primary_key=True)
  user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  feature_name: Mapped[str] = mapped_column(String, nullable=False)
  test_type: Mapped[str] = mapped_column(String, default="regression")
  content: Mapped[str] = mapped_column(Text, nullable=False)
  created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
  )

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "user_id": self.user_id,
      "feature_name": self.feature_name,
      "test_type": self.test_type,
      "content": self.content,
      "created_at": self.created_at.isoformat() if self.created_at else datetime.now(timezone.utc).isoformat(),
    }
