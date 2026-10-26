"""SQLAlchemy ORM History Repositories for PostgreSQL.

Replaces all JSON file writing with pure PostgreSQL persistence.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, List, Optional

from sqlalchemy import delete, select

from app.db.database import get_db
from app.db.models import (
  ChatMessageModel,
  ChatSessionModel,
  PRDReviewModel,
  StandupModel,
  TestPlanModel,
)


class ChatRepository:
  """PostgreSQL ORM repository for chat conversations and sessions."""

  async def save_session(self, session_data: dict[str, Any]) -> dict[str, Any]:
    session_id = session_data.get("id") or str(uuid.uuid4())
    user_id = session_data.get("user_id")
    title = session_data.get("title") or session_data.get("name") or "Nueva conversación"
    feature_slug = session_data.get("feature_slug") or session_data.get("specification") or "general"
    document_content = session_data.get("documentContent") or session_data.get("document_content") or ""
    artifacts = session_data.get("artifacts") or []
    active_art_id = session_data.get("activeArtifactId") or session_data.get("active_artifact_id")
    artifacts_json = json.dumps(artifacts, ensure_ascii=False) if artifacts else "[]"

    async with get_db() as db:
      stmt = select(ChatSessionModel).where(ChatSessionModel.id == session_id)
      result = await db.execute(stmt)
      session = result.scalar_one_or_none()

      if session:
        session.title = title
        session.feature_slug = feature_slug
        session.document_content = document_content
        session.artifacts_json = artifacts_json
        if active_art_id:
          session.active_artifact_id = active_art_id
        if user_id and not session.user_id:
          session.user_id = user_id
      else:
        session = ChatSessionModel(
          id=session_id,
          user_id=user_id,
          title=title,
          feature_slug=feature_slug,
          document_content=document_content,
          artifacts_json=artifacts_json,
          active_artifact_id=active_art_id,
        )
        db.add(session)

      await db.commit()
      await db.refresh(session)
      return session.to_dict()

  async def get_user_sessions(
    self,
    user_id: Optional[str] = None,
    feature_slug: Optional[str] = None,
    limit: int = 50,
  ) -> List[dict[str, Any]]:
    async with get_db() as db:
      stmt = select(ChatSessionModel).order_by(ChatSessionModel.updated_at.desc())
      if user_id:
        stmt = stmt.where(ChatSessionModel.user_id == user_id)
      if feature_slug:
        stmt = stmt.where(ChatSessionModel.feature_slug == feature_slug)
      if limit > 0:
        stmt = stmt.limit(limit)
      result = await db.execute(stmt)
      sessions = result.scalars().all()
      return [s.to_dict() for s in sessions]

  async def get_session(
    self, session_id: str, user_id: Optional[str] = None
  ) -> Optional[dict[str, Any]]:
    async with get_db() as db:
      stmt = select(ChatSessionModel).where(ChatSessionModel.id == session_id)
      if user_id:
        stmt = stmt.where(ChatSessionModel.user_id == user_id)
      result = await db.execute(stmt)
      session = result.scalar_one_or_none()
      if not session:
        return None
      res = session.to_dict()
      messages = await self.get_session_messages(session_id, user_id=user_id)
      res["messages"] = messages
      return res

  async def delete_session(self, session_id: str, user_id: Optional[str] = None) -> bool:
    async with get_db() as db:
      stmt = delete(ChatSessionModel).where(ChatSessionModel.id == session_id)
      if user_id:
        stmt = stmt.where(ChatSessionModel.user_id == user_id)
      await db.execute(stmt)
      await db.execute(delete(ChatMessageModel).where(ChatMessageModel.session_id == session_id))
      await db.commit()
      return True

  async def save_message(
    self,
    session_id: str,
    role: str,
    content: str,
    context_sources: Optional[List[dict[str, Any]]] = None,
    **kwargs: Any,
  ) -> dict[str, Any]:
    msg_id = kwargs.get("id") or str(uuid.uuid4())
    user_id = kwargs.get("user_id")
    attachments = kwargs.get("attachments") or []
    sources_json = json.dumps(context_sources, ensure_ascii=False) if context_sources else None
    attachments_json = json.dumps(attachments, ensure_ascii=False) if attachments else "[]"

    msg = ChatMessageModel(
      id=msg_id,
      session_id=session_id,
      user_id=user_id,
      role=role,
      content=content,
      context_sources_json=sources_json,
      attachments_json=attachments_json,
    )

    async with get_db() as db:
      db.add(msg)
      # Also update session last updated timestamp if session exists
      stmt = select(ChatSessionModel).where(ChatSessionModel.id == session_id)
      res = await db.execute(stmt)
      session = res.scalar_one_or_none()
      if session:
        session.updated_at = msg.created_at
      await db.commit()
      await db.refresh(msg)
      return msg.to_dict()

  async def get_session_messages(
    self, session_id: str, limit: int = 100, user_id: Optional[str] = None
  ) -> List[dict[str, Any]]:
    async with get_db() as db:
      stmt = (
        select(ChatMessageModel)
        .where(ChatMessageModel.session_id == session_id)
        .order_by(ChatMessageModel.created_at.asc())
      )
      if user_id:
        stmt = stmt.where(ChatMessageModel.user_id == user_id)
      if limit > 0:
        stmt = stmt.limit(limit)
      result = await db.execute(stmt)
      messages = result.scalars().all()
      return [m.to_dict() for m in messages]

  async def clear_session(self, session_id: str) -> bool:
    async with get_db() as db:
      stmt = delete(ChatMessageModel).where(ChatMessageModel.session_id == session_id)
      await db.execute(stmt)
      await db.commit()
      return True


class StandupRepository:
  """PostgreSQL ORM repository for generated daily standups."""

  async def create_standup(
    self,
    title: str,
    content: str,
    sources: Optional[List[str]] = None,
    user_id: Optional[str] = None,
  ) -> dict[str, Any]:
    standup_id = str(uuid.uuid4())
    sources_json = json.dumps(sources, ensure_ascii=False) if sources else None

    standup = StandupModel(
      id=standup_id,
      user_id=user_id,
      title=title,
      content=content,
      sources_json=sources_json,
    )

    async with get_db() as db:
      db.add(standup)
      await db.commit()
      await db.refresh(standup)
      return standup.to_dict()

  async def get_all_standups(
    self, limit: int = 20, user_id: Optional[str] = None
  ) -> List[dict[str, Any]]:
    async with get_db() as db:
      stmt = select(StandupModel).order_by(StandupModel.created_at.desc())
      if user_id:
        stmt = stmt.where(StandupModel.user_id == user_id)
      if limit > 0:
        stmt = stmt.limit(limit)
      result = await db.execute(stmt)
      items = result.scalars().all()
      return [i.to_dict() for i in items]


class PRDRepository:
  """PostgreSQL ORM repository for PRD reviews."""

  async def create_prd_review(
    self,
    prd_title: str,
    content: str,
    score: int = 0,
    risk_level: str = "MEDIUM",
    user_id: Optional[str] = None,
  ) -> dict[str, Any]:
    review_id = str(uuid.uuid4())

    review = PRDReviewModel(
      id=review_id,
      user_id=user_id,
      prd_title=prd_title,
      content=content,
      score=score,
      risk_level=risk_level,
    )

    async with get_db() as db:
      db.add(review)
      await db.commit()
      await db.refresh(review)
      return review.to_dict()

  async def get_all_prd_reviews(
    self, limit: int = 20, user_id: Optional[str] = None
  ) -> List[dict[str, Any]]:
    async with get_db() as db:
      stmt = select(PRDReviewModel).order_by(PRDReviewModel.created_at.desc())
      if user_id:
        stmt = stmt.where(PRDReviewModel.user_id == user_id)
      if limit > 0:
        stmt = stmt.limit(limit)
      result = await db.execute(stmt)
      items = result.scalars().all()
      return [i.to_dict() for i in items]


class TestPlanRepository:
  """PostgreSQL ORM repository for test plan drafts."""

  async def create_test_plan(
    self,
    feature_name: str,
    content: str,
    test_type: str = "general",
    user_id: Optional[str] = None,
  ) -> dict[str, Any]:
    plan_id = str(uuid.uuid4())

    plan = TestPlanModel(
      id=plan_id,
      user_id=user_id,
      feature_name=feature_name,
      test_type=test_type,
      content=content,
    )

    async with get_db() as db:
      db.add(plan)
      await db.commit()
      await db.refresh(plan)
      return plan.to_dict()

  async def get_all_test_plans(
    self, limit: int = 20, user_id: Optional[str] = None
  ) -> List[dict[str, Any]]:
    async with get_db() as db:
      stmt = select(TestPlanModel).order_by(TestPlanModel.created_at.desc())
      if user_id:
        stmt = stmt.where(TestPlanModel.user_id == user_id)
      if limit > 0:
        stmt = stmt.limit(limit)
      result = await db.execute(stmt)
      items = result.scalars().all()
      return [i.to_dict() for i in items]
