from __future__ import annotations

import json
from typing import Any, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.interfaces.catalog_repository import IAIModelCatalogRepository
from app.db.models import AIModelCatalogModel


class AIModelCatalogRepository(IAIModelCatalogRepository):
  """PostgreSQL ORM repository for AI model catalog with injected Session."""

  def __init__(self, session: Session) -> None:
    self.session = session

  def get(self, model_id: str) -> Optional[dict[str, Any]]:
    clean = model_id.strip()
    stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == clean)
    result = self.session.execute(stmt)
    row = result.scalar_one_or_none()
    if row:
      return row.to_dict()

    stmt_all = select(AIModelCatalogModel)
    for r in self.session.execute(stmt_all).scalars().all():
      d = r.to_dict()
      aliases = [a.lower() for a in d.get("aliases", [])]
      if (
        clean.lower() in aliases
        or clean.lower() == d.get("filename", "").lower()
        or clean.lower() == d.get("tag", "").lower()
      ):
        return d
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
    for m in models:
      mid = m.get("id")
      if not mid:
        continue
      prov = m.get("provider", "groq")
      task_type = m.get("task_type", "chat_writing")
      name = m.get("name", mid)
      is_free = bool(m.get("is_free", False))
      tier_type = m.get("tier_type", "free" if is_free else "paid")
      vram_mb = m.get("vram_required_mb") or m.get("vramRequiredMB")
      context_win = m.get("context_window") or m.get("contextWindow") or m.get("tokens")
      down_size = m.get("download_size") or m.get("downloadSize") or m.get("size")
      tier = m.get("tier")
      req_features = m.get("required_features") or m.get("requiredFeatures") or []
      req_features_json = json.dumps(req_features) if req_features else None
      payload_json = json.dumps(m, ensure_ascii=False)

      stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == mid)
      result = self.session.execute(stmt)
      row = result.scalar_one_or_none()

      if row is None:
        row = AIModelCatalogModel(
          id=mid,
          provider=prov,
          task_type=task_type,
          name=name,
          is_free=is_free,
          tier_type=tier_type,
          vram_required_mb=vram_mb,
          context_window=context_win,
          download_size=down_size,
          tier=tier,
          required_features=req_features_json,
          payload_json=payload_json,
        )
        self.session.add(row)
      else:
        row.provider = prov
        row.task_type = task_type
        row.name = name
        row.is_free = is_free
        row.tier_type = tier_type
        row.vram_required_mb = vram_mb
        row.context_window = context_win
        row.download_size = down_size
        row.tier = tier
        row.required_features = req_features_json
        row.payload_json = payload_json
      count += 1
    self.session.flush()
    return count

  def replace_external(self, models: List[dict[str, Any]]) -> int:
    self.session.execute(delete(AIModelCatalogModel).where(
      AIModelCatalogModel.provider.notin_(["webllm", "browser_asr"])
    ))
    self.session.flush()
    return self.bulk_upsert(models)
