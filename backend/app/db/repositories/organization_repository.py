from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interfaces.organization_repository import IOrganizationRepository
from app.db.models import OrganizationMemberModel, OrganizationModel


class OrganizationRepository(IOrganizationRepository):
  """Implementación PostgreSQL SQLAlchemy para IOrganizationRepository."""

  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  async def get_by_id(self, org_id: str) -> Optional[Dict[str, Any]]:
    stmt = select(OrganizationModel).where(OrganizationModel.id == org_id)
    res = await self.session.execute(stmt)
    org = res.scalar_one_or_none()
    return org.to_dict() if org else None

  async def get_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
    stmt = select(OrganizationModel).where(OrganizationModel.slug == slug)
    res = await self.session.execute(stmt)
    org = res.scalar_one_or_none()
    return org.to_dict() if org else None

  async def create_organization(self, name: str, slug: str) -> Dict[str, Any]:
    org_id = str(uuid.uuid4())
    org = OrganizationModel(id=org_id, name=name, slug=slug)
    self.session.add(org)
    await self.session.flush()
    if hasattr(self.session, "refresh"):
      res = self.session.refresh(org)
      import inspect
      if inspect.isawaitable(res):
        await res
    return org.to_dict()

  async def list_members(self, org_id: str) -> List[Dict[str, Any]]:
    stmt = select(OrganizationMemberModel).where(OrganizationMemberModel.organization_id == org_id)
    res = await self.session.execute(stmt)
    members = res.scalars().all()
    return [m.to_dict() for m in members]

  async def get_member(self, org_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    stmt = select(OrganizationMemberModel).where(
      OrganizationMemberModel.organization_id == org_id,
      OrganizationMemberModel.user_id == user_id,
    )
    res = await self.session.execute(stmt)
    m = res.scalar_one_or_none()
    return m.to_dict() if m else None

  async def add_member(self, org_id: str, user_id: str, role: str = "member") -> Dict[str, Any]:
    mem_id = str(uuid.uuid4())
    mem = OrganizationMemberModel(id=mem_id, organization_id=org_id, user_id=user_id, role=role)
    self.session.add(mem)
    await self.session.flush()
    if hasattr(self.session, "refresh"):
      res = self.session.refresh(mem)
      import inspect
      if inspect.isawaitable(res):
        await res
    return mem.to_dict()

  async def update_member_role(self, org_id: str, user_id: str, role: str) -> Optional[Dict[str, Any]]:
    stmt = select(OrganizationMemberModel).where(
      OrganizationMemberModel.organization_id == org_id,
      OrganizationMemberModel.user_id == user_id,
    )
    res = await self.session.execute(stmt)
    mem = res.scalar_one_or_none()
    if not mem:
      return None
    mem.role = role
    await self.session.flush()
    if hasattr(self.session, "refresh"):
      res = self.session.refresh(mem)
      import inspect
      if inspect.isawaitable(res):
        await res
    return mem.to_dict()

  async def remove_member(self, org_id: str, user_id: str) -> bool:
    stmt = select(OrganizationMemberModel).where(
      OrganizationMemberModel.organization_id == org_id,
      OrganizationMemberModel.user_id == user_id,
    )
    res = await self.session.execute(stmt)
    mem = res.scalar_one_or_none()
    if not mem:
      return False
    await self.session.delete(mem)
    await self.session.flush()
    return True
