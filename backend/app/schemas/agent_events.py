"""Pydantic models for the structured agent event protocol."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class AgentEventType(str, Enum):
    RUN_STARTED = "run.started"
    RUN_STATUS = "run.status"
    RUN_STEP_STARTED = "run.step.started"
    RUN_STEP_COMPLETED = "run.step.completed"
    RUN_STEP_FAILED = "run.step.failed"
    MESSAGE_DELTA = "message.delta"
    SOURCE_FOUND = "source.found"
    ARTIFACT_CREATED = "artifact.created"
    ARTIFACT_UPDATED = "artifact.updated"
    INTERACTION_REQUIRED = "interaction.required"
    RUN_HEARTBEAT = "run.heartbeat"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"


class RunStepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class RunStartedData(BaseModel):
    task_profile: str = "general"
    model_name: Optional[str] = None
    initial_prompt: str = ""


class RunStatusData(BaseModel):
    status: str
    message: Optional[str] = None


class RunStepData(BaseModel):
    step_id: str
    label: str
    status: RunStepStatus = RunStepStatus.IN_PROGRESS
    details: Optional[str] = None


class MessageDeltaData(BaseModel):
    delta: str
    role: str = "assistant"


class SourceFoundData(BaseModel):
    source_id: str
    title: str
    source_type: str
    snippet: Optional[str] = None
    score: Optional[float] = None


class ArtifactCreatedData(BaseModel):
    artifact_id: str
    title: str
    extension: str = "docx"
    content: str
    version_id: Optional[str] = None


class ArtifactUpdatedData(BaseModel):
    artifact_id: str
    title: str
    extension: str = "docx"
    content: str
    version_id: Optional[str] = None


class InteractionOption(BaseModel):
    label: str
    value: str


class InteractionRequiredData(BaseModel):
    interaction_id: str
    kind: Literal["clarification", "confirmation"] = "clarification"
    question: str
    options: List[InteractionOption] = Field(default_factory=list)
    required: bool = True


class RunHeartbeatData(BaseModel):
    uptime_seconds: float = 0.0


class RunCompletedData(BaseModel):
    final_message: str = ""
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    sources_used: List[str] = Field(default_factory=list)


class RunFailedData(BaseModel):
    error_code: str
    user_message: str
    technical_details: Optional[str] = None


class RunCancelledData(BaseModel):
    reason: str = "User cancelled run"


EventDataUnion = Union[
    RunStartedData,
    RunStatusData,
    RunStepData,
    MessageDeltaData,
    SourceFoundData,
    ArtifactCreatedData,
    ArtifactUpdatedData,
    InteractionRequiredData,
    RunHeartbeatData,
    RunCompletedData,
    RunFailedData,
    RunCancelledData,
    Dict[str, Any],
]


def current_utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    run_id: str
    conversation_id: str
    sequence: int
    type: AgentEventType
    timestamp: str = Field(default_factory=current_utc_timestamp)
    data: EventDataUnion

    def to_sse_packet(self) -> str:
        payload = self.model_dump(mode="json", by_alias=True)
        if self.type == AgentEventType.MESSAGE_DELTA:
            delta_val = self.data.delta if isinstance(self.data, MessageDeltaData) else (self.data.get("delta") if isinstance(self.data, dict) else "")
            payload["text"] = delta_val
        elif self.type == AgentEventType.RUN_STARTED:
            profile_val = self.data.task_profile if isinstance(self.data, RunStartedData) else (self.data.get("task_profile") if isinstance(self.data, dict) else "")
            payload["intent"] = profile_val
        import json
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

