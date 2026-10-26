"""Unit tests for agent event schemas, serialization, and lifecycle emitter."""

import json
import pytest
from app.schemas.agent_events import (
    AgentEvent,
    AgentEventType,
    RunStartedData,
    RunStepData,
    RunStepStatus,
    MessageDeltaData,
    SourceFoundData,
    ArtifactCreatedData,
    ArtifactUpdatedData,
    InteractionRequiredData,
    InteractionOption,
    RunCompletedData,
    RunFailedData,
    RunCancelledData,
)
from app.services.event_serializer import AgentRunEmitter, RunRegistry


def test_agent_event_sse_serialization() -> None:
    data = RunStartedData(task_profile="document_generator", model_name="gpt-4o", initial_prompt="Draft report")
    event = AgentEvent(
        run_id="run-101",
        conversation_id="conv-202",
        sequence=1,
        type=AgentEventType.RUN_STARTED,
        data=data,
    )
    packet = event.to_sse_packet()

    assert packet.startswith("data: ")
    assert packet.endswith("\n\n")

    raw_json = packet.replace("data: ", "").strip()
    payload = json.loads(raw_json)
    assert payload["run_id"] == "run-101"
    assert payload["conversation_id"] == "conv-202"
    assert payload["sequence"] == 1
    assert payload["type"] == "run.started"
    assert payload["data"]["task_profile"] == "document_generator"


def test_agent_run_emitter_monotonic_sequence() -> None:
    emitter = AgentRunEmitter(run_id="run-test", conversation_id="conv-test")

    e1 = emitter.started(task_profile="general", prompt="Hello")
    e2 = emitter.step_started(step_id="step-1", label="Analyzing requirements")
    e3 = emitter.step_completed(step_id="step-1", label="Analyzing requirements")
    e4 = emitter.message_delta(delta="Processing finished")
    e5 = emitter.completed(final_message="Done", artifacts=[], sources=[])

    assert [e.sequence for e in [e1, e2, e3, e4, e5]] == [1, 2, 3, 4, 5]
    assert e1.type == AgentEventType.RUN_STARTED
    assert e2.type == AgentEventType.RUN_STEP_STARTED
    assert e3.type == AgentEventType.RUN_STEP_COMPLETED
    assert e4.type == AgentEventType.MESSAGE_DELTA
    assert e5.type == AgentEventType.RUN_COMPLETED


def test_agent_run_emitter_artifact_events() -> None:
    emitter = AgentRunEmitter(run_id="run-art", conversation_id="conv-art")

    created = emitter.artifact_created(artifact_id="doc-1", title="Proposal", content="Content", extension="docx")
    updated = emitter.artifact_updated(artifact_id="doc-1", title="Proposal", content="Updated", extension="docx")

    assert created.type == AgentEventType.ARTIFACT_CREATED
    assert created.data.artifact_id == "doc-1"
    assert updated.type == AgentEventType.ARTIFACT_UPDATED
    assert updated.data.content == "Updated"


def test_agent_run_emitter_interaction_and_sources() -> None:
    emitter = AgentRunEmitter(run_id="run-int", conversation_id="conv-int")

    source_ev = emitter.source_found(source_id="s1", title="Policy", source_type="doc", snippet="Excerpt")
    assert source_ev.type == AgentEventType.SOURCE_FOUND
    assert source_ev.data.snippet == "Excerpt"

    options = [{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}]
    inter_ev = emitter.interaction_required(interaction_id="iq-1", question="Approve outline?", options=options)
    assert inter_ev.type == AgentEventType.INTERACTION_REQUIRED
    assert len(inter_ev.data.options) == 2
    assert inter_ev.data.options[0].value == "yes"


def test_agent_run_emitter_cancellation_and_failure() -> None:
    emitter = AgentRunEmitter(run_id="run-err", conversation_id="conv-err")

    fail_ev = emitter.failed(error_code="LLM_TIMEOUT", user_message="Model took too long")
    assert fail_ev.type == AgentEventType.RUN_FAILED
    assert fail_ev.data.error_code == "LLM_TIMEOUT"

    emitter.request_cancellation(reason="User stopped run")
    assert emitter.is_cancelled is True

    cancel_ev = emitter.cancelled()
    assert cancel_ev.type == AgentEventType.RUN_CANCELLED
    assert cancel_ev.data.reason == "User stopped run"


def test_run_registry_registration_and_cancellation() -> None:
    registry = RunRegistry()
    emitter = AgentRunEmitter(run_id="run-reg", conversation_id="conv-reg")

    registry.register(emitter)
    assert registry.get("run-reg") is emitter

    cancelled = registry.cancel_run("run-reg", reason="Client aborted")
    assert cancelled is True
    assert emitter.is_cancelled is True

    cancelled_unknown = registry.cancel_run("unknown-run")
    assert cancelled_unknown is False

    registry.unregister("run-reg")
    assert registry.get("run-reg") is None
