"""User profile endpoints - local-only, no authentication."""

from typing import Any, Literal, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_optional_current_user
from app.core.settings import USER_DOCUMENTS_DIR
from app.core.storage import get_user_preferences, load_app_settings, save_app_settings, save_user_preferences

router = APIRouter(prefix="/user", tags=["user"])

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
    current_user: Optional[dict[str, Any]] = Depends(get_optional_current_user),
) -> UserProfile:
    """Get current user profile and documents directory preference."""
    settings = load_app_settings()
    user_id = current_user.get("id") if current_user else None
    user_prefs = get_user_preferences(user_id) if user_id else {}

    docs_path = user_prefs.get("documents_path") or settings.get("documents_path") or str(USER_DOCUMENTS_DIR)

    return UserProfile(
        display_name=settings.get("display_name", "Usuario"),
        user_role=settings.get("user_role", "admin"),
        documents_path=docs_path,
    )


@router.put("/profile")
async def update_user_profile(
    body: UpdateProfileRequest,
    current_user: Optional[dict[str, Any]] = Depends(get_optional_current_user),
) -> UserProfile:
    """Update user profile (display_name, user_role, documents_path)."""
    settings = load_app_settings()
    user_id = current_user.get("id") if current_user else None

    if body.display_name:
        settings["display_name"] = body.display_name
    if body.user_role:
        settings["user_role"] = body.user_role
    if body.documents_path is not None:
        clean_path = body.documents_path.strip()
        settings["documents_path"] = clean_path
        if user_id:
            save_user_preferences(user_id, {"documents_path": clean_path})

    save_app_settings(settings, user_id=user_id)

    user_prefs = get_user_preferences(user_id) if user_id else {}
    resolved_path = user_prefs.get("documents_path") or settings.get("documents_path") or str(USER_DOCUMENTS_DIR)

    return UserProfile(
        display_name=settings.get("display_name", "Usuario"),
        user_role=settings.get("user_role", "admin"),
        documents_path=resolved_path,
    )


@router.post("/setup")
async def first_time_setup(body: UserProfile) -> UserProfile:
    """First-time setup: save display name and role."""
    settings = load_app_settings()
    settings["display_name"] = body.display_name
    settings["user_role"] = body.user_role
    if body.documents_path:
        settings["documents_path"] = body.documents_path.strip()
    save_app_settings(settings)
    return body
