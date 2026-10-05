"""Dependency injection providers - local JSON storage only."""

from app.core.json_history import (
    JsonChatRepository,
    JsonPRDRepository,
    JsonStandupRepository,
    JsonTestPlanRepository,
)


def get_chat_repository() -> JsonChatRepository:
    """Dependency provider for Chat Repository."""
    return JsonChatRepository()


def get_standup_repository() -> JsonStandupRepository:
    """Dependency provider for Standup Repository."""
    return JsonStandupRepository()


def get_prd_repository() -> JsonPRDRepository:
    """Dependency provider for PRD Repository."""
    return JsonPRDRepository()


def get_test_plan_repository() -> JsonTestPlanRepository:
    """Dependency provider for Test Plan Repository."""
    return JsonTestPlanRepository()
