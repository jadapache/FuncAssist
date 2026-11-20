"""Typed SSE protocol events for streaming AI agents and runners."""

from __future__ import annotations

import json
from typing import Any, Literal
from pydantic import BaseModel, Field


EventType = Literal[
    "status",
    "delta",
    "tool_call",
    "tool_result",
    "artifact_start",
    "artifact_delta",
    "artifact_end",
    "plan",
    "usage",
    "error",
    "done",
]


class AgentEvent(BaseModel):
    """Structured SSE event contract for modern reactive UX."""
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Format as valid SSE event string."""
        payload = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.type}\ndata: {payload}\n\n"
