"""Pydantic models for AI model catalog information."""

from __future__ import annotations

from pydantic import BaseModel


class AIModelInfo(BaseModel):
  id: str
  raw_id: str
  name: str
  provider: str
  provider_name: str
  description: str
  context_window: str
  context_length: int
  task_type: str = "chat_writing"
  task_label: str = "Redacción y Chat"
  tier_type: str
  pricing_prompt: float = 0.0
  pricing_completion: float = 0.0
  pricing_label: str
  rate_limits: str
  max_output_tokens: int | None = None
  badge: str | None = None
  is_free: bool = False
  size: str | None = None
  accuracy: str | None = None
  is_downloaded: bool | None = None
  disk_size_mb: float | None = None


class ModelCatalogResponse(BaseModel):
  updated_at: str
  source: str
  providers: list[str]
  models: list[AIModelInfo]
  error: str | None = None
