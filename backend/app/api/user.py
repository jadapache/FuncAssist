"""User profile endpoints - local-only, no authentication."""

from typing import Literal, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.storage import load_app_settings, save_app_settings

router = APIRouter(prefix="/user", tags=["user"])

UserRole = Literal["admin", "pm", "funcional", "dev", "qa"]


class UserProfile(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    user_role: UserRole


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    user_role: Optional[UserRole] = None


@router.get("/profile")
async def get_user_profile() -> UserProfile:
    """Get current user profile from app.json."""
    settings = load_app_settings()
    return UserProfile(
        display_name=settings.get("display_name", "Usuario"),
        user_role=settings.get("user_role", "admin"),
    )


@router.put("/profile")
async def update_user_profile(body: UpdateProfileRequest) -> UserProfile:
    """Update user profile (display_name and/or user_role)."""
    settings = load_app_settings()

    if body.display_name:
        settings["display_name"] = body.display_name
    if body.user_role:
        settings["user_role"] = body.user_role

    save_app_settings(settings)

    return UserProfile(
        display_name=settings.get("display_name", "Usuario"),
        user_role=settings.get("user_role", "admin"),
    )


@router.post("/setup")
async def first_time_setup(body: UserProfile) -> UserProfile:
    """First-time setup: save display name and role."""
    settings = load_app_settings()
    settings["display_name"] = body.display_name
    settings["user_role"] = body.user_role
    save_app_settings(settings)
    return body
