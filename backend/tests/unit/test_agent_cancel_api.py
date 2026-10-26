"""Unit tests for agent run cancellation endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.document_agent import router, AgenticPromptRequest
from app.services.event_serializer import AgentRunEmitter, run_registry


@pytest.fixture
def test_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)



def test_agentic_prompt_request_run_id_alias() -> None:
    req = AgenticPromptRequest(
        query="test query",
        runId="run-custom-123",
        conversationId="conv-custom-456",
    )
    assert req.run_id == "run-custom-123"
    assert req.conversation_id == "conv-custom-456"


def test_cancel_nonexistent_run_returns_404(test_client: TestClient) -> None:
    response = test_client.post("/api/doc-agent/runs/nonexistent-run-xyz/cancel")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_cancel_active_run_via_api(test_client: TestClient) -> None:
    run_id = "run-active-test"
    emitter = AgentRunEmitter(run_id=run_id, conversation_id="conv-1")
    run_registry.register(emitter)

    try:
        assert emitter.is_cancelled is False

        response = test_client.post(f"/api/doc-agent/runs/{run_id}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["run_id"] == run_id
        assert emitter.is_cancelled is True
    finally:
        run_registry.unregister(run_id)
