from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import (
    get_current_admin_user,
    get_current_user,
    get_user_repository,
)
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.interfaces import IUserRepository

router = APIRouter(prefix="/auth", tags=["auth"])

_SENSITIVE_FIELDS = frozenset({"password_hash", "password_salt"})


def _sanitize_user(user: dict[str, Any]) -> dict[str, Any]:
    """Retorna el diccionario del usuario sin campos sensibles de contraseña."""
    return {k: v for k, v in user.items() if k not in _SENSITIVE_FIELDS}


import re

PASSWORD_REGEX = re.compile(r"^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{10,}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=10)
    email: str = Field(min_length=3, max_length=120)
    full_name: str = Field(min_length=1, max_length=80)
    role: str = "user"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    token: Optional[str] = None
    status: str = "approved"
    message: str = ""
    user: dict[str, Any]


@router.post("/register", response_model=AuthResponse)
async def register(
    body: RegisterRequest,
    user_repo: IUserRepository = Depends(get_user_repository),
) -> dict[str, Any]:
    username = body.username.strip()
    full_name = body.full_name.strip()
    email = body.email.strip()

    if not username or len(username) < 3 or len(username) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario debe tener entre 3 y 20 caracteres.",
        )
    if not full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre completo es requerido.",
        )
    if len(full_name) > 80:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre completo no puede superar los 80 caracteres.",
        )
    if not email or not EMAIL_REGEX.match(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ingresado no es válido.",
        )
    if not PASSWORD_REGEX.match(body.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe tener al menos 10 caracteres, una letra mayúscula, un número y un carácter especial.",
        )

    existing = await user_repo.get_by_username(username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El usuario '{username}' ya está registrado.",
        )

    pwd_hash, pwd_salt = hash_password(body.password)

    user = await user_repo.create_user_with_password(
        username=username,
        password_hash=pwd_hash,
        password_salt=pwd_salt,
        email=email,
        full_name=full_name,
        role=body.role,
        status="pending",
    )

    clean_user = _sanitize_user(user)
    user_status = user.get("status", "pending")

    if user_status == "approved":
        token = create_access_token({
            "sub": user["id"],
            "username": user["username"],
            "role": user.get("role", "admin"),
        })
        return {
            "token": token,
            "status": "approved",
            "message": "Cuenta creada y aprobada automáticamente como Administrador.",
            "user": clean_user,
        }

    return {
        "token": None,
        "status": "pending",
        "message": "Solicitud de acceso enviada correctamente. Un administrador debe aprobar tu cuenta antes de que puedas ingresar.",
        "user": clean_user,
    }


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    user_repo: IUserRepository = Depends(get_user_repository),
) -> dict[str, Any]:
    user = await user_repo.get_by_username(body.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nombre de usuario o contraseña incorrectos.",
        )

    pwd_hash = user.get("password_hash")
    pwd_salt = user.get("password_salt")

    if not pwd_hash or not pwd_salt:
        new_hash, new_salt = hash_password(body.password)
        await user_repo.update(user["id"], {"password_hash": new_hash, "password_salt": new_salt})
        pwd_hash, pwd_salt = new_hash, new_salt

    if not verify_password(body.password, pwd_hash, pwd_salt):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nombre de usuario o contraseña incorrectos.",
        )

    user_status = user.get("status", "approved")
    if user_status == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu solicitud de acceso está pendiente de aprobación por el administrador.",
        )
    elif user_status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu solicitud de acceso ha sido rechazada por el administrador.",
        )

    clean_user = _sanitize_user(user)
    token = create_access_token({
        "sub": user["id"],
        "username": user["username"],
        "role": user.get("role", "user"),
    })

    return {
        "token": token,
        "status": user_status,
        "message": "Inicio de sesión exitoso.",
        "user": clean_user,
    }


@router.get("/me")
async def get_me(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return {"user": current_user}


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


@router.put("/me")
async def update_me(
    body: UpdateProfileRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if body.full_name is not None:
        full_name = body.full_name.strip()
        if len(full_name) > 80:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre completo no puede superar los 80 caracteres.",
            )
        if full_name:
            updates["full_name"] = full_name

    if body.email is not None and body.email.strip():
        email = body.email.strip()
        if not EMAIL_REGEX.match(email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo electrónico ingresado no es válido.",
            )
        updates["email"] = email

    if body.password is not None and body.password.strip():
        pwd = body.password.strip()
        if not PASSWORD_REGEX.match(pwd):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La contraseña debe tener al menos 10 caracteres, una letra mayúscula, un número y un carácter especial.",
            )
        pwd_hash, pwd_salt = hash_password(pwd)
        updates["password_hash"] = pwd_hash
        updates["password_salt"] = pwd_salt

    if updates:
        updated = await user_repo.update(current_user["id"], updates)
        if updated:
            current_user = _sanitize_user(updated)

    return {"message": "Perfil actualizado exitosamente.", "user": current_user}


@router.get("/access-requests")
async def get_access_requests(
    _admin: dict[str, Any] = Depends(get_current_admin_user),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> dict[str, Any]:
    pending = await user_repo.get_pending_users()
    clean_pending = [_sanitize_user(u) for u in pending]
    return {"requests": clean_pending}


@router.post("/access-requests/{user_id}/approve")
async def approve_access_request(
    user_id: str,
    _admin: dict[str, Any] = Depends(get_current_admin_user),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> dict[str, Any]:
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada.")
    updated = await user_repo.update_user_status(user_id, "approved")
    clean_user = _sanitize_user(updated or {})
    return {"status": "approved", "user": clean_user}


@router.post("/access-requests/{user_id}/reject")
async def reject_access_request(
    user_id: str,
    _admin: dict[str, Any] = Depends(get_current_admin_user),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> dict[str, Any]:
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada.")
    updated = await user_repo.update_user_status(user_id, "rejected")
    clean_user = _sanitize_user(updated or {})
    return {"status": "rejected", "user": clean_user}
