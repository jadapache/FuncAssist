from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.interfaces.secret_repository import IUserSecretRepository
from app.db.models import AuditEventModel, UserSecretModel

logger = logging.getLogger(__name__)


class UserSecretRepository(IUserSecretRepository):
  """Implementación PostgreSQL SQLAlchemy para IUserSecretRepository."""

  def __init__(self, session: Session) -> None:
    self.session = session

  def _to_dto(self, model: UserSecretModel) -> Dict[str, Any]:
    return {
      "id": model.id,
      "user_id": model.user_id,
      "purpose": model.purpose,
      "ciphertext": model.ciphertext,
      "nonce": model.nonce,
      "key_version": model.key_version,
      "created_at": model.created_at.isoformat() if model.created_at else None,
      "updated_at": model.updated_at.isoformat() if model.updated_at else None,
    }

  def get_by_id(self, secret_id: str) -> Optional[Dict[str, Any]]:
    stmt = select(UserSecretModel).where(UserSecretModel.id == secret_id)
    record = self.session.scalar(stmt)
    return self._to_dto(record) if record else None

  def create(
    self,
    secret_id: str,
    user_id: str,
    purpose: str,
    ciphertext: str,
    nonce: str,
    key_version: int,
  ) -> Dict[str, Any]:
    record = UserSecretModel(
      id=secret_id,
      user_id=user_id,
      purpose=purpose,
      ciphertext=ciphertext,
      nonce=nonce,
      key_version=key_version,
    )
    self.session.add(record)
    self.session.flush()
    return self._to_dto(record)

  def update_ciphertext(
    self,
    secret_id: str,
    user_id: str,
    ciphertext: str,
    nonce: str,
    key_version: int,
  ) -> Optional[Dict[str, Any]]:
    stmt = select(UserSecretModel).where(UserSecretModel.id == secret_id)
    record = self.session.scalar(stmt)
    if not record or record.user_id != user_id:
      return None
    record.ciphertext = ciphertext
    record.nonce = nonce
    record.key_version = key_version
    self.session.flush()
    return self._to_dto(record)

  def delete(self, secret_id: str, user_id: str) -> bool:
    stmt = select(UserSecretModel).where(UserSecretModel.id == secret_id)
    record = self.session.scalar(stmt)
    if not record or record.user_id != user_id:
      return False
    self.session.delete(record)
    self.session.flush()
    return True

  def record_audit_event(
    self,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
  ) -> None:
    try:
      event = AuditEventModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
      )
      self.session.add(event)
      self.session.flush()
    except Exception as exc:
      logger.debug("Failed logging audit event in UserSecretRepository: %s", exc)
