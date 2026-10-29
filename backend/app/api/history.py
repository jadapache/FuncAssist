from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import (
  get_chat_repository,
  get_current_admin_user,
  get_current_user,
  get_prd_repository,
  get_standup_repository,
  get_test_plan_repository,
)
from app.core.storage import load_app_settings, save_app_settings
from app.db.database import get_db
from app.db.models import UserModel
from app.db.repositories import (
  ChatRepository,
  PRDRepository,
  StandupRepository,
  TestPlanRepository,
)

router = APIRouter()


class UserCreate(BaseModel):
  username: str = Field(min_length=1)
  email: str = ""
  full_name: str = ""
  role: str = "user"


class ChatMessageCreate(BaseModel):
  role: str = Field(pattern="^(user|assistant|system)$")
  content: str = Field(min_length=1)
  context_sources: Optional[List[dict[str, Any]]] = None
  attachments: Optional[List[dict[str, Any]]] = None


class ChatSessionSaveRequest(BaseModel):
  id: Optional[str] = None
  title: Optional[str] = None
  name: Optional[str] = None
  feature_slug: Optional[str] = "general"
  documentContent: Optional[str] = ""
  artifacts: Optional[List[dict[str, Any]]] = None
  activeArtifactId: Optional[str] = None


class SettingSetRequest(BaseModel):
  key: str = Field(min_length=1)
  value: Any


@router.get("/users", tags=["user"])
async def get_users(
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  try:
    async with get_db() as db:
      stmt = select(UserModel).where(UserModel.status == "approved")
      result = await db.execute(stmt)
      users = result.scalars().all()
      if users:
        return {
          "users": [
            {
              "id": u.id,
              "username": u.username,
              "display_name": u.full_name or u.username,
              "role": u.role,
            }
            for u in users
          ]
        }
  except Exception:
    pass

  return {"users": []}


# --- Settings Endpoints ---
@router.get("/db/settings", tags=["settings"])
async def get_db_settings(
  _admin: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
  all_settings = load_app_settings()
  return {"settings": all_settings}


@router.post("/db/settings", tags=["settings"])
async def set_db_setting(
  body: SettingSetRequest,
  _admin: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
  settings = load_app_settings()
  settings[body.key] = body.value
  save_app_settings(settings)
  return {"ok": True, "key": body.key, "value": body.value}


# --- Chat Sessions Endpoints ---
@router.get("/chat/sessions", tags=["chat"])
async def get_chat_sessions(
  feature_slug: Optional[str] = None,
  limit: int = 50,
  current_user: dict[str, Any] = Depends(get_current_user),
  repo: ChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
  user_id = current_user["id"]
  sessions = await repo.get_user_sessions(user_id=user_id, feature_slug=feature_slug, limit=limit)
  return {"sessions": sessions}


@router.post("/chat/sessions", tags=["chat"])
async def save_chat_session(
  body: ChatSessionSaveRequest,
  current_user: dict[str, Any] = Depends(get_current_user),
  repo: ChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
  data = body.model_dump(exclude_none=True)
  data["user_id"] = current_user["id"]
  session = await repo.save_session(data)
  return {"ok": True, "session": session}


@router.get("/chat/sessions/{session_id}", tags=["chat"])
async def get_chat_session(
  session_id: str,
  current_user: dict[str, Any] = Depends(get_current_user),
  repo: ChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
  user_id = current_user["id"]
  session = await repo.get_session(session_id, user_id=user_id)
  return {"session": session}


@router.delete("/chat/sessions/{session_id}", tags=["chat"])
async def delete_chat_session(
  session_id: str,
  current_user: dict[str, Any] = Depends(get_current_user),
  repo: ChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
  user_id = current_user["id"]
  await repo.delete_session(session_id, user_id=user_id)
  return {"ok": True, "session_id": session_id}


# --- Chat History Endpoints ---
@router.get("/chat/history/{session_id}", tags=["chat"])
async def get_chat_messages(
  session_id: str,
  limit: int = 100,
  current_user: dict[str, Any] = Depends(get_current_user),
  repo: ChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
  user_id = current_user["id"]
  history = await repo.get_session_messages(session_id, limit=limit, user_id=user_id)
  return {"session_id": session_id, "messages": history}


@router.post("/chat/history/{session_id}", tags=["chat"])
async def post_chat_message(
  session_id: str,
  body: ChatMessageCreate,
  current_user: dict[str, Any] = Depends(get_current_user),
  repo: ChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
  user_id = current_user["id"]
  message = await repo.save_message(
    session_id=session_id,
    role=body.role,
    content=body.content,
    context_sources=body.context_sources,
    attachments=body.attachments,
    user_id=user_id,
  )
  return {"message": message}


@router.delete("/chat/history/{session_id}", tags=["chat"])
async def delete_chat_messages(
  session_id: str,
  current_user: dict[str, Any] = Depends(get_current_user),
  repo: ChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
  await repo.clear_session(session_id)
  return {"ok": True, "session_id": session_id}


# --- Feature History Endpoints ---
@router.get("/history/standups", tags=["history"])
async def get_standup_history(
  limit: int = 20,
  current_user: dict[str, Any] = Depends(get_current_user),
  repo: StandupRepository = Depends(get_standup_repository),
) -> dict[str, Any]:
  user_id = current_user["id"]
  items = await repo.get_all_standups(limit=limit, user_id=user_id)
  return {"standups": items}


@router.get("/history/prd-reviews", tags=["history"])
async def get_prd_history(
  limit: int = 20,
  current_user: dict[str, Any] = Depends(get_current_user),
  repo: PRDRepository = Depends(get_prd_repository),
) -> dict[str, Any]:
  user_id = current_user["id"]
  items = await repo.get_all_prd_reviews(limit=limit, user_id=user_id)
  return {"prd_reviews": items}


@router.get("/history/test-plans", tags=["history"])
async def get_test_plan_history(
  limit: int = 20,
  current_user: dict[str, Any] = Depends(get_current_user),
  repo: TestPlanRepository = Depends(get_test_plan_repository),
) -> dict[str, Any]:
  user_id = current_user["id"]
  items = await repo.get_all_test_plans(limit=limit, user_id=user_id)
  return {"test_plans": items}
