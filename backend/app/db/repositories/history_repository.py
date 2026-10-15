"""SQLAlchemy ORM History Repositories for PostgreSQL.

Replaces all JSON file writing with pure PostgreSQL persistence.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, List, Optional

from sqlalchemy import delete, select

from app.db.database import get_db
from app.db.models import ChatMessageModel, PRDReviewModel, StandupModel, TestPlanModel


class ChatRepository:
  """PostgreSQL ORM repository for chat conversations."""

  async def save_message(
    self,
    session_id: str,
    role: str,
    content: str,
    context_sources: Optional[List[dict[str, Any]]] = None,
    user_id: Optional[str] = None,
  ) -> dict[str, Any]:
    msg_id = str(uuid.uuid4())
    sources_json = json.dumps(context_sources, ensure_ascii=False) if context_sources else None

    msg = ChatMessageModel(
      id=msg_id,
      session_id=session_id,
      user_id=user_id,
      role=role,
      content=content,
      context_sources_json=sources_json,
    )

    async with get_db() as db:
      db.add(msg)
      await db.commit()
      await db.refresh(msg)
      return msg.to_dict()

  async def get_session_messages(
    self, session_id: str, limit: int = 50
  ) -> List[dict[str, Any]]:
    async with get_db() as db:
      stmt = (
        select(ChatMessageModel)
        .where(ChatMessageModel.session_id == session_id)
        .order_by(ChatMessageModel.created_at.asc())
      )
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

  async def get_all_standups(self, limit: int = 20) -> List[dict[str, Any]]:
    async with get_db() as db:
      stmt = select(StandupModel).order_by(StandupModel.created_at.desc())
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

  async def get_all_prd_reviews(self, limit: int = 20) -> List[dict[str, Any]]:
    async with get_db() as db:
      stmt = select(PRDReviewModel).order_by(PRDReviewModel.created_at.desc())
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

  async def get_all_test_plans(self, limit: int = 20) -> List[dict[str, Any]]:
    async with get_db() as db:
      stmt = select(TestPlanModel).order_by(TestPlanModel.created_at.desc())
      if limit > 0:
        stmt = stmt.limit(limit)
      result = await db.execute(stmt)
      items = result.scalars().all()
      return [i.to_dict() for i in items]
