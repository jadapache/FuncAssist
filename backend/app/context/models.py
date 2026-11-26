"""Unified context models for live + document sources."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.ai.injection import prepare_untrusted


class SourceType(str, Enum):
  JIRA = "jira"
  GITHUB = "github"
  GITLAB = "gitlab"
  KNOWLEDGE = "knowledge"


class ContextChunk(BaseModel):
  id: str
  source_type: SourceType
  source_label: str
  title: str
  text: str
  metadata: dict[str, Any] = Field(default_factory=dict)
  score: float | None = None


class ContextBundle(BaseModel):
  query: str
  chunks: list[ContextChunk] = Field(default_factory=list)
  missing_sources: list[str] = Field(default_factory=list)
  used_sources: list[str] = Field(default_factory=list)

  @property
  def is_empty(self) -> bool:
    return len(self.chunks) == 0

  def to_prompt_block(self) -> str:
    if not self.chunks:
      return "No context chunks available."
    parts: list[str] = []
    for index, chunk in enumerate(self.chunks, start=1):
      parts.append(f"[{index}] " + prepare_untrusted(chunk.source_type, chunk.source_label, f"{chunk.title}\n{chunk.text}", max_chars=None))
    return "\n\n".join(parts)
