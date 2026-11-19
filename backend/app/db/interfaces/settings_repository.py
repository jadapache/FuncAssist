from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ISettingsRepository(ABC):
  """Contrato para persistencia de configuraciones globales y preferencias de usuario."""

  @abstractmethod
  def get_setting(self, key: str) -> Optional[str]:
    pass

  @abstractmethod
  def set_setting(self, key: str, value_json: str) -> None:
    pass

  @abstractmethod
  def get_all_settings(self) -> Dict[str, str]:
    pass

  @abstractmethod
  def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
    pass

  @abstractmethod
  def save_user_preferences(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    pass
