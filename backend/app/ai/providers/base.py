"""AI provider abstraction."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Union

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
  id: str
  name: str
  arguments: dict[str, Any] = Field(default_factory=dict)


class AIMessage(BaseModel):
  role: str
  content: Union[str, list[dict[str, Any]]] = ""
  tool_call_id: str | None = None
  tool_calls: list[ToolCall] = Field(default_factory=list)

  def to_litellm(self) -> dict[str, Any]:
    """Serialize to the OpenAI/LiteLLM wire format, omitting empty tool fields.

    Plain messages must not carry `tool_call_id: None` / `tool_calls: []`:
    several providers (Anthropic, Groq) reject them.
    """
    payload: dict[str, Any] = {"role": self.role, "content": self.content}
    if self.tool_calls:
      payload["tool_calls"] = [
        {
          "id": tc.id,
          "type": "function",
          "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
        }
        for tc in self.tool_calls
      ]
    if self.tool_call_id:
      payload["tool_call_id"] = self.tool_call_id
    return payload


class AICompletion(BaseModel):
  text: str
  provider: str
  model: str
  raw: dict[str, Any] = Field(default_factory=dict)
  tool_calls: list[ToolCall] = Field(default_factory=list)
  finish_reason: str | None = None
  prompt_tokens: int | None = None
  completion_tokens: int | None = None
  cached_tokens: int | None = None
  cost_usd: float | None = None
  duration_ms: float | None = None


class AIProvider(ABC):
  id: str
  name: str

  @abstractmethod
  async def complete(
    self,
    messages: list[AIMessage],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
  ) -> AICompletion:
    raise NotImplementedError

  @abstractmethod
  async def complete_stream(
    self,
    messages: list[AIMessage],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
  ):
    raise NotImplementedError

