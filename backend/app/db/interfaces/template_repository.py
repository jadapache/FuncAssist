from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class IAITemplateRepository(ABC):
  """Contrato para plantillas de IA, rúbricas e historial de versiones."""

  @abstractmethod
  async def get_template(self, template_type: str, feature: str) -> Optional[dict[str, Any]]:
    pass

  @abstractmethod
  async def list_templates(self, template_type: str, tag: Optional[str] = None) -> List[dict[str, Any]]:
    pass

  @abstractmethod
  async def save_template_update(
    self,
    template_type: str,
    feature: str,
    new_data: dict[str, Any],
    updated_by: Optional[str] = None,
    change_summary: Optional[str] = None,
  ) -> dict[str, Any]:
    pass

  @abstractmethod
  async def get_version_history(
    self, template_type: str, feature: str, limit: int = 50
  ) -> List[dict[str, Any]]:
    pass

  @abstractmethod
  async def seed_defaults(
    self,
    default_prompts: dict[str, Any],
    default_rubrics: dict[str, Any],
  ) -> None:
    pass
