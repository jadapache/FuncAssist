"""AI provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Union

from pydantic import BaseModel, Field


class AIMessage(BaseModel):
  role: str
  content: Union[str, list[dict[str, Any]]]


class AICompletion(BaseModel):
  text: str
  provider: str
  model: str
  raw: dict[str, Any] = Field(default_factory=dict)


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

