from __future__ import annotations

import json
from typing import Any, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.interfaces.catalog_repository import IAIModelCatalogRepository
from app.db.models import AIModelCatalogModel


def _first(model: dict[str, Any], *keys: str) -> Any:
  """The first truthy value among these keys, or the last value looked at when none is truthy."""
  value = None
  for key in keys:
    value = model.get(key)
    if value:
      return value
  return value


def _lookup_names(model: dict[str, Any]) -> set[str]:
  """Everything a model can be asked for besides its id, lower-cased."""
  names = {str(alias).lower() for alias in model.get("aliases") or []}
  names.update(str(model.get(key) or "").lower() for key in ("filename", "tag"))
  names.discard("")
  return names


def _model_columns(model: dict[str, Any], model_id: str) -> dict[str, Any]:
  """The catalog row for one incoming model, accepting both snake_case and camelCase field names."""
  is_free = bool(model.get("is_free", False))
  features = _first(model, "required_features", "requiredFeatures") or []
  return {
    "id": model_id,
    "provider": model.get("provider", "groq"),
    "task_type": model.get("task_type", "chat_writing"),
    "name": model.get("name", model_id),
    "is_free": is_free,
    "tier_type": model.get("tier_type", "free" if is_free else "paid"),
    "vram_required_mb": _first(model, "vram_required_mb", "vramRequiredMB"),
    "context_window": _first(model, "context_window", "contextWindow", "tokens"),
    "download_size": _first(model, "download_size", "downloadSize", "size"),
    "tier": model.get("tier"),
    "required_features": json.dumps(features) if features else None,
    "payload_json": json.dumps(model, ensure_ascii=False),
  }


class AIModelCatalogRepository(IAIModelCatalogRepository):
  """PostgreSQL ORM repository for AI model catalog with injected Session."""

  def __init__(self, session: Session) -> None:
    self.session = session

  def get(self, model_id: str) -> Optional[dict[str, Any]]:
    clean = model_id.strip()
    if not clean:
      return None
    stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == clean)
    row = self.session.execute(stmt).scalar_one_or_none()
    if row:
      return row.to_dict()
    return self._find_by_alternative_name(clean.lower())

  def _find_by_alternative_name(self, name: str) -> Optional[dict[str, Any]]:
    for row in self.session.execute(select(AIModelCatalogModel)).scalars().all():
      model = row.to_dict()
      if name in _lookup_names(model):
        return model
    return None

  def list(self, task_type: Optional[str] = None) -> List[dict[str, Any]]:
    stmt = select(AIModelCatalogModel)
    if task_type:
      stmt = stmt.where(AIModelCatalogModel.task_type == task_type)
    stmt = stmt.order_by(AIModelCatalogModel.name.asc())
    result = self.session.execute(stmt)
    items = result.scalars().all()
    return [item.to_dict() for item in items]

  def delete_free_models(self) -> int:
    stmt = delete(AIModelCatalogModel).where(
      AIModelCatalogModel.provider.in_(["builtin", "local"])
    )
    res = self.session.execute(stmt)
    self.session.flush()
    return res.rowcount

  def bulk_upsert(self, models: List[dict[str, Any]]) -> int:
    count = 0
    for model in models:
      model_id = model.get("id")
      if not model_id:
        continue
      self._upsert_one(_model_columns(model, model_id))
      count += 1
    self.session.flush()
    return count

  def _upsert_one(self, columns: dict[str, Any]) -> None:
    stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == columns["id"])
    row = self.session.execute(stmt).scalar_one_or_none()
    if row is None:
      self.session.add(AIModelCatalogModel(**columns))
      return
    for name, value in columns.items():
      setattr(row, name, value)

  def replace_external(self, models: List[dict[str, Any]]) -> int:
    self.session.execute(delete(AIModelCatalogModel).where(
      AIModelCatalogModel.provider.notin_(["webllm", "browser_asr"])
    ))
    self.session.flush()
    return self.bulk_upsert(models)
