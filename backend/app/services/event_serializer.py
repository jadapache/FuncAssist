"""Event serializer and lifecycle emitter for agent runs."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from app.schemas.agent_events import (
    AgentEvent,
    AgentEventType,
    ArtifactCreatedData,
    ArtifactUpdatedData,
    InteractionOption,
    InteractionRequiredData,
    MessageDeltaData,
    RunCancelledData,
    RunCompletedData,
    RunFailedData,
    RunStartedData,
    RunStepData,
    RunStepStatus,
    SourceFoundData,
    current_utc_timestamp,
)


class AgentRunEmitter:
    """Manages event sequencing and formatting for an active agent run."""

    def __init__(self, run_id: str, conversation_id: str) -> None:
        self.run_id = run_id
        self.conversation_id = conversation_id
        self._sequence = 0
        self._cancelled = False
        self._cancellation_reason = ""
        self._cancel_event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def request_cancellation(self, reason: str = "Cancellation requested by user") -> None:
        self._cancelled = True
        self._cancellation_reason = reason
        self._cancel_event.set()

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def build_event(self, event_type: AgentEventType, data: Any) -> AgentEvent:
        return AgentEvent(
            run_id=self.run_id,
            conversation_id=self.conversation_id,
            sequence=self._next_sequence(),
            type=event_type,
            timestamp=current_utc_timestamp(),
            data=data,
        )

    def started(self, task_profile: str, model_name: Optional[str] = None, prompt: str = "") -> AgentEvent:
        return self.build_event(
            AgentEventType.RUN_STARTED,
            RunStartedData(task_profile=task_profile, model_name=model_name, initial_prompt=prompt),
        )

    def step_started(self, step_id: str, label: str, details: Optional[str] = None) -> AgentEvent:
        return self.build_event(
            AgentEventType.RUN_STEP_STARTED,
            RunStepData(step_id=step_id, label=label, status=RunStepStatus.IN_PROGRESS, details=details),
        )

    def step_completed(self, step_id: str, label: str, details: Optional[str] = None) -> AgentEvent:
        return self.build_event(
            AgentEventType.RUN_STEP_COMPLETED,
            RunStepData(step_id=step_id, label=label, status=RunStepStatus.COMPLETED, details=details),
        )

    def step_failed(self, step_id: str, label: str, details: Optional[str] = None) -> AgentEvent:
        return self.build_event(
            AgentEventType.RUN_STEP_FAILED,
            RunStepData(step_id=step_id, label=label, status=RunStepStatus.FAILED, details=details),
        )

    def message_delta(self, delta: str) -> AgentEvent:
        return self.build_event(AgentEventType.MESSAGE_DELTA, MessageDeltaData(delta=delta))

    def source_found(self, source_id: str, title: str, source_type: str, snippet: Optional[str] = None) -> AgentEvent:
        return self.build_event(
            AgentEventType.SOURCE_FOUND,
            SourceFoundData(source_id=source_id, title=title, source_type=source_type, snippet=snippet),
        )

    def artifact_created(self, artifact_id: str, title: str, content: str, extension: str = "docx") -> AgentEvent:
        return self.build_event(
            AgentEventType.ARTIFACT_CREATED,
            ArtifactCreatedData(artifact_id=artifact_id, title=title, content=content, extension=extension),
        )

    def artifact_updated(self, artifact_id: str, title: str, content: str, extension: str = "docx") -> AgentEvent:
        return self.build_event(
            AgentEventType.ARTIFACT_UPDATED,
            ArtifactUpdatedData(artifact_id=artifact_id, title=title, content=content, extension=extension),
        )

    def interaction_required(
        self, interaction_id: str, question: str, options: List[Dict[str, str]], required: bool = True
    ) -> AgentEvent:
        mapped_options = [InteractionOption(label=opt["label"], value=opt["value"]) for opt in options]
        return self.build_event(
            AgentEventType.INTERACTION_REQUIRED,
            InteractionRequiredData(
                interaction_id=interaction_id, question=question, options=mapped_options, required=required
            ),
        )

    def completed(self, final_message: str, artifacts: List[Dict[str, Any]], sources: List[str]) -> AgentEvent:
        return self.build_event(
            AgentEventType.RUN_COMPLETED,
            RunCompletedData(final_message=final_message, artifacts=artifacts, sources_used=sources),
        )

    def failed(self, error_code: str, user_message: str, technical_details: Optional[str] = None) -> AgentEvent:
        return self.build_event(
            AgentEventType.RUN_FAILED,
            RunFailedData(error_code=error_code, user_message=user_message, technical_details=technical_details),
        )

    def cancelled(self, reason: Optional[str] = None) -> AgentEvent:
        return self.build_event(
            AgentEventType.RUN_CANCELLED,
            RunCancelledData(reason=reason or self._cancellation_reason or "Run cancelled by user"),
        )


class RunRegistry:
    """In-memory active run orchestrator registry for cancellation and lookup."""

    def __init__(self) -> None:
        self._active_runs: Dict[str, AgentRunEmitter] = {}

    def register(self, emitter: AgentRunEmitter) -> None:
        self._active_runs[emitter.run_id] = emitter

    def unregister(self, run_id: str) -> None:
        self._active_runs.pop(run_id, None)

    def get(self, run_id: str) -> Optional[AgentRunEmitter]:
        return self._active_runs.get(run_id)

    def cancel_run(self, run_id: str, reason: str = "User cancelled run") -> bool:
        emitter = self.get(run_id)
        if not emitter:
            return False
        emitter.request_cancellation(reason)
        return True


run_registry = RunRegistry()
