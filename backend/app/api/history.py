from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import (
    get_chat_repository,
    get_prd_repository,
    get_standup_repository,
    get_test_plan_repository,
)
from app.core.json_history import (
    JsonChatRepository,
    JsonPRDRepository,
    JsonStandupRepository,
    JsonTestPlanRepository,
)
from app.core.storage import load_app_settings, save_app_settings

router = APIRouter(tags=["db-history"])


class UserCreate(BaseModel):
    username: str = Field(min_length=1)
    email: str = ""
    full_name: str = ""
    role: str = "user"


class ChatMessageCreate(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str = Field(min_length=1)
    context_sources: Optional[List[dict[str, Any]]] = None


class SettingSetRequest(BaseModel):
    key: str = Field(min_length=1)
    value: Any


# --- Users Endpoints ---
@router.get("/users")
async def get_users() -> dict[str, Any]:
    settings = load_app_settings()
    return {
        "users": [
            {
                "id": "local",
                "username": settings.get("display_name", "Usuario"),
                "display_name": settings.get("display_name", "Usuario"),
                "role": settings.get("user_role", "admin"),
            }
        ]
    }


# --- Settings Endpoints ---
@router.get("/db/settings")
async def get_db_settings() -> dict[str, Any]:
    all_settings = load_app_settings()
    return {"settings": all_settings}


@router.post("/db/settings")
async def set_db_setting(body: SettingSetRequest) -> dict[str, Any]:
    settings = load_app_settings()
    settings[body.key] = body.value
    save_app_settings(settings)
    return {"ok": True, "key": body.key, "value": body.value}


# --- Chat History Endpoints ---
@router.get("/chat/history/{session_id}")
async def get_chat_messages(
    session_id: str,
    limit: int = 50,
    repo: JsonChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
    history = await repo.get_session_messages(session_id, limit=limit)
    return {"session_id": session_id, "messages": history}


@router.post("/chat/history/{session_id}")
async def post_chat_message(
    session_id: str,
    body: ChatMessageCreate,
    repo: JsonChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
    message = await repo.save_message(
        session_id=session_id,
        role=body.role,
        content=body.content,
        context_sources=body.context_sources,
    )
    return {"message": message}


@router.delete("/chat/history/{session_id}")
async def delete_chat_messages(
    session_id: str,
    repo: JsonChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
    await repo.clear_session(session_id)
    return {"ok": True, "session_id": session_id}


# --- Feature History Endpoints ---
@router.get("/history/standups")
async def get_standup_history(
    limit: int = 20,
    repo: JsonStandupRepository = Depends(get_standup_repository),
) -> dict[str, Any]:
    items = await repo.get_all_standups(limit=limit)
    return {"standups": items}


@router.get("/history/prd-reviews")
async def get_prd_history(
    limit: int = 20,
    repo: JsonPRDRepository = Depends(get_prd_repository),
) -> dict[str, Any]:
    items = await repo.get_all_prd_reviews(limit=limit)
    return {"prd_reviews": items}


@router.get("/history/test-plans")
async def get_test_plan_history(
    limit: int = 20,
    repo: JsonTestPlanRepository = Depends(get_test_plan_repository),
) -> dict[str, Any]:
    items = await repo.get_all_test_plans(limit=limit)
    return {"test_plans": items}
