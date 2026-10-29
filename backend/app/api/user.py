"""User profile endpoints - local-only, no authentication."""

from typing import Any, Literal, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.settings import USER_DOCUMENTS_DIR
from app.core.storage import get_user_preferences, load_app_settings, save_app_settings, save_user_preferences

router = APIRouter(
    prefix="/user",
    tags=["user"],
    dependencies=[Depends(get_current_user)],
)

UserRole = Literal["admin", "pm", "funcional", "dev", "qa"]


class UserProfile(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    user_role: UserRole
    documents_path: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    user_role: Optional[UserRole] = None
    documents_path: Optional[str] = None


@router.get("/profile")
async def get_user_profile(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UserProfile:
    """Get current user profile and documents directory preference."""
    user_id = current_user["id"]
    user_prefs = get_user_preferences(user_id)
    docs_path = user_prefs.get("documents_path") or str(USER_DOCUMENTS_DIR)

    display_name = user_prefs.get("display_name") or current_user.get("full_name") or current_user.get("username", "Usuario")
    user_role = user_prefs.get("user_role") or current_user.get("role", "funcional")

    return UserProfile(
        display_name=display_name,
        user_role=user_role,
        documents_path=docs_path,
    )


@router.put("/profile")
async def update_user_profile(
    body: UpdateProfileRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UserProfile:
    """Update user profile preferences."""
    user_id = current_user["id"]
    prefs_update: dict[str, Any] = {}

    if body.display_name:
        prefs_update["display_name"] = body.display_name.strip()
    if body.user_role:
        prefs_update["user_role"] = body.user_role
    if body.documents_path is not None:
        clean_path = body.documents_path.strip()
        prefs_update["documents_path"] = clean_path

    if prefs_update:
        save_user_preferences(user_id, prefs_update)

    user_prefs = get_user_preferences(user_id)
    resolved_path = user_prefs.get("documents_path") or str(USER_DOCUMENTS_DIR)

    display_name = user_prefs.get("display_name") or current_user.get("full_name") or current_user.get("username", "Usuario")
    user_role = user_prefs.get("user_role") or current_user.get("role", "funcional")

    return UserProfile(
        display_name=display_name,
        user_role=user_role,
        documents_path=resolved_path,
    )


@router.post("/setup")
async def first_time_setup(
    body: UserProfile,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UserProfile:
    """Setup user profile preferences."""
    user_id = current_user["id"]
    prefs_update: dict[str, Any] = {
        "display_name": body.display_name.strip(),
        "user_role": body.user_role,
    }
    if body.documents_path:
        prefs_update["documents_path"] = body.documents_path.strip()
    save_user_preferences(user_id, prefs_update)
    return body
