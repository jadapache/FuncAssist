"""PostgreSQL-backed history storage for chat, standups, PRD reviews, and test plans.

Pure PostgreSQL - All local JSON file reading and writing has been completely removed.
"""

from __future__ import annotations

from app.db.repositories.history_repository import (
  ChatRepository,
  PRDRepository,
  StandupRepository,
  TestPlanRepository,
)

# Backward-compatible aliases for legacy imports
JsonChatRepository = ChatRepository
JsonStandupRepository = StandupRepository
JsonPRDRepository = PRDRepository
JsonTestPlanRepository = TestPlanRepository

__all__ = [
  "JsonChatRepository",
  "JsonStandupRepository",
  "JsonPRDRepository",
  "JsonTestPlanRepository",
  "ChatRepository",
  "StandupRepository",
  "PRDRepository",
  "TestPlanRepository",
]
