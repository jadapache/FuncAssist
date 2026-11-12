from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IUserSecretRepository(ABC):
  """Contrato para persistencia de secretos cifrados de usuario y eventos de auditoría."""

  @abstractmethod
  def get_by_id(self, secret_id: str) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  def create(
    self,
    secret_id: str,
    user_id: str,
    purpose: str,
    ciphertext: str,
    nonce: str,
    key_version: int,
  ) -> Dict[str, Any]:
    pass

  @abstractmethod
  def update_ciphertext(
    self,
    secret_id: str,
    user_id: str,
    ciphertext: str,
    nonce: str,
    key_version: int,
  ) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  def delete(self, secret_id: str, user_id: str) -> bool:
    pass

  @abstractmethod
  def record_audit_event(
    self,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
  ) -> None:
    pass
