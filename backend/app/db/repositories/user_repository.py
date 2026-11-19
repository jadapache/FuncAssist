"""SQLAlchemy ORM-based User Repository for PostgreSQL.

Pure PostgreSQL - No SQLite, no raw file dependencies.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interfaces.user_repository import IUserRepository
from app.db.models import UserModel


class UserRepository(IUserRepository):
  """SQLAlchemy ORM implementation of IUserRepository targeting PostgreSQL."""

  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await self.session.execute(stmt)
    user = result.scalar_one_or_none()
    return user.to_dict() if user else None

  async def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
    stmt = select(UserModel).where(UserModel.username == username)
    result = await self.session.execute(stmt)
    user = result.scalar_one_or_none()
    return user.to_dict() if user else None

  async def count(self) -> int:
    stmt = select(func.count()).select_from(UserModel)
    result = await self.session.execute(stmt)
    return int(result.scalar() or 0)

  async def create_user_with_password(
    self,
    username: str,
    password_hash: str,
    password_salt: str,
    email: str = "",
    full_name: str = "",
    role: str = "user",
    status: str = "pending",
  ) -> Dict[str, Any]:
    user_id = str(uuid.uuid4())
    total_users = await self.count()

    # Bootstrap: First registered user automatically becomes admin and approved
    final_status = "approved" if total_users == 0 else status
    final_role = "admin" if total_users == 0 else role

    user = UserModel(
      id=user_id,
      username=username,
      email=email,
      full_name=full_name or username,
      role=final_role,
      password_hash=password_hash,
      password_salt=password_salt,
      status=final_status,
    )

    self.session.add(user)
    await self.session.flush()
    if hasattr(self.session, "refresh"):
      res = self.session.refresh(user)
      import inspect
      if inspect.isawaitable(res):
        await res
    return user.to_dict()

  async def get_pending_users(self) -> List[Dict[str, Any]]:
    stmt = select(UserModel).where(UserModel.status == "pending").order_by(UserModel.created_at.desc())
    result = await self.session.execute(stmt)
    users = result.scalars().all()
    return [u.to_dict() for u in users]

  async def get_approved_users(self) -> List[Dict[str, Any]]:
    stmt = select(UserModel).where(UserModel.status == "approved").order_by(UserModel.created_at.desc())
    result = await self.session.execute(stmt)
    users = result.scalars().all()
    return [u.to_dict() for u in users]

  async def update_user_status(self, user_id: str, status: str) -> Optional[Dict[str, Any]]:
    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await self.session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
      return None
    user.status = status
    await self.session.flush()
    if hasattr(self.session, "refresh"):
      res = self.session.refresh(user)
      import inspect
      if inspect.isawaitable(res):
        await res
    return user.to_dict()

  async def update(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not updates:
      return await self.get_by_id(user_id)

    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await self.session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
      return None
    for key, value in updates.items():
      if hasattr(user, key):
        setattr(user, key, value)
    await self.session.flush()
    if hasattr(self.session, "refresh"):
      res = self.session.refresh(user)
      import inspect
      if inspect.isawaitable(res):
        await res
    return user.to_dict()

  async def delete(self, user_id: str) -> bool:
    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await self.session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
      return False
    await self.session.delete(user)
    await self.session.flush()
    return True
