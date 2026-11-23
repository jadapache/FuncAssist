"""Document agent: artifact follow-ups, persistence helpers, error messages and the SSE v2 stream."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.errors import AIError
from app.ai.events import AgentEvent
from app.api import document_agent
from app.api.document_agent import (
  router,
)


@pytest.fixture
def client() -> TestClient:
  app = FastAPI()
  app.include_router(router, prefix="/api")
  return TestClient(app)


def _sse_events(body: str) -> list[tuple[str, dict]]:
  events = []
  for frame in body.split("\n\n"):
    name, data = "", None
    for line in frame.splitlines():
      if line.startswith("event:"):
        name = line[6:].strip()
      elif line.startswith("data:"):
        data = json.loads(line[5:].strip())
    if data is not None:
      events.append((name, data))
  return events








async def _fake_run(cfg):
  cfg.run_info.update(route="plain", logged=True)
  yield AgentEvent(type="status", data={"message": "Generando respuesta...", "stage": "generate"})
  yield '<chat>Hola</chat>\n<artifact title="Plan" '
  yield 'extension="docx"># Plan\n</artifact>'


async def _failing_run(cfg):
  yield AgentEvent(type="status", data={"message": "Preparando", "stage": "context"})
  raise AIError(code="model_not_found", user_message="El modelo configurado no existe.")


class TestStreamProtocolV2:
  def test_v2_stream_emits_named_events(self, client):
    with patch.object(document_agent, "run_agentic_chat_stream", _fake_run), \
         patch.object(document_agent, "_load_active_template_info", AsyncMock(return_value=("", "docx"))):
      resp = client.post(
        "/api/doc-agent/agentic-prompt-stream?protocol=v2", json={"query": "genera un plan de pruebas"},
      )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    names = [n for n, _ in events]
    assert names[0] == "status" and events[0][1]["intent"] == "generic_plan"
    assert names.index("artifact_start") < names.index("artifact_delta") < names.index("artifact_end") < names.index("done")
    deltas = "".join(d["text"] for n, d in events if n == "delta")
    assert deltas.strip() == "Hola"
    done = events[-1][1]
    assert done["artifacts"][0]["title"] == "Plan" and done["artifacts"][0]["intent"] == "generic_plan"
    assert done["assistant_message"] == "Hola" and done["route"] == "plain"

  def test_v2_errors_carry_the_typed_code(self, client):
    with patch.object(document_agent, "run_agentic_chat_stream", _failing_run), \
         patch.object(document_agent, "_load_active_template_info", AsyncMock(return_value=("", "docx"))), \
         patch.object(document_agent, "log_ai_call") as log:
      resp = client.post("/api/doc-agent/agentic-prompt-stream?protocol=v2", json={"query": "hola"})
    error = next(d for n, d in _sse_events(resp.text) if n == "error")
    assert error["code"] == "model_not_found" and error["message"] == "El modelo configurado no existe."
    assert log.call_args.args[0]["error_code"] == "model_not_found"





