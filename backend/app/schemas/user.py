from __future__ import annotations

import re
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    email: Optional[str] = Field(default="", max_length=120)
    full_name: Optional[str] = Field(default="", max_length=80)
    role: str = "user"
    status: str = "pending"

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9]+$", v.strip()):
            raise ValueError("El nombre de usuario admite solo letras y números")
        return v.strip()


class UserCreate(UserBase):
    password_hash: Optional[str] = None
    password_salt: Optional[str] = None


class UserInDB(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    password_hash: Optional[str] = None
    password_salt: Optional[str] = None
    created_at: Optional[str] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: Optional[str] = ""
    full_name: Optional[str] = ""
    role: str
    status: str
    created_at: Optional[str] = None
