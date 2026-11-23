"""Document agent: artifact follow-ups, persistence helpers, error messages and the SSE v2 stream."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.ai.errors import AIError
from app.ai.events import AgentEvent
from app.api import document_agent
from app.api.document_agent import (
  _format_stream_error,
  _merge_session_artifacts,
  classify_prompt_intent,
  infer_active_artifact_intent,
  is_artifact_follow_up,
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


class TestArtifactFollowUps:
  @pytest.mark.parametrize("prompt", [
    "El documento está vacío",
    "regenera",
    "¿Puedes regenerarlo?",
    "Complétalo por favor",
    "completa la sección de riesgos",
    "vuelve a generar el informe",
    "el plan quedó cortado",
  ])
  def test_follow_up_keeps_the_active_artifact_intent(self, prompt):
    assert is_artifact_follow_up(prompt)
    assert classify_prompt_intent(prompt, active_artifact_intent="generic_plan") == "generic_plan"

  def test_without_active_artifact_it_stays_conversational(self):
    assert classify_prompt_intent("El documento está vacío") == "chat"

  def test_ordinary_questions_are_not_follow_ups(self):
    assert not is_artifact_follow_up("¿Qué es una prueba de humo?")
    assert classify_prompt_intent("¿Qué es una prueba de humo?", active_artifact_intent="generic_report") == "chat"

  def test_explicit_mode_wins(self):
    assert classify_prompt_intent("regenera", mode="chat", active_artifact_intent="generic_plan") == "chat"

  def test_infer_active_artifact_intent(self):
    assert infer_active_artifact_intent([{"title": "X", "intent": "generic_report"}]) == "generic_report"
    assert infer_active_artifact_intent([{"title": "Plan de pruebas"}]) == "generic_plan"
    assert infer_active_artifact_intent([{"title": "Mejora"}], template_id="t1") == "template_mutation"
    assert infer_active_artifact_intent([], has_current_document=True) == "generic_report"
    assert infer_active_artifact_intent([]) is None


class TestPersistenceHelpers:
  def test_merge_replaces_same_title_and_keeps_client_id(self):
    existing = [{"id": "art-1", "title": "Plan", "content": "viejo"}, {"id": "art-2", "title": "Otro", "content": "x"}]
    merged = _merge_session_artifacts(existing, [{"title": "plan", "content": "nuevo", "intent": "generic_plan"}])
    assert [a["id"] for a in merged] == ["art-1", "art-2"]
    assert merged[0]["content"] == "nuevo" and merged[0]["intent"] == "generic_plan"

  def test_merge_appends_new_titles(self):
    merged = _merge_session_artifacts([{"title": "A"}], [{"title": "B"}])
    assert [a["title"] for a in merged] == ["A", "B"]


class TestErrorMessages:
  def test_typed_errors_use_their_user_message(self):
    err = AIError(code="rate_limit", user_message="Espera 5s")
    assert _format_stream_error(err) == "Espera 5s"

  def test_configuration_errors_keep_their_text(self):
    assert _format_stream_error(ValueError("Groq Cloud is selected but API key is missing.")).startswith("Groq Cloud")

  def test_unknown_errors_are_not_guessed_from_substrings(self):
    msg = _format_stream_error(RuntimeError("author field 401"))
    assert "autenticación" not in msg and "author field 401" in msg


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

  def test_v1_stream_still_sends_full_packet(self, client):
    with patch.object(document_agent, "run_agentic_chat_stream", _fake_run), \
         patch.object(document_agent, "_load_active_template_info", AsyncMock(return_value=("", "docx"))):
      resp = client.post("/api/doc-agent/agentic-prompt-stream", json={"query": "genera un plan de pruebas"})
    packets = [d for n, d in _sse_events(resp.text) if not n]
    assert any(p.get("type") == "full" for p in packets)


class TestSettingsValidation:
  def test_unknown_fast_model_is_rejected(self):
    from app.api.routers import ai_settings

    with patch.object(ai_settings, "catalog_chat_models", return_value=["openai/gpt-oss-20b"]):
      with pytest.raises(HTTPException) as exc_info:
        ai_settings._validate_tier_models_against_catalog(
          {"provider": "groq", "fast_model": "llama-3.1-8b-instant"}, {"provider": "groq"},
        )
    assert exc_info.value.status_code == 400

  def test_unknown_fallbacks_are_rejected(self):
    from app.api.routers import ai_settings

    with patch.object(ai_settings, "catalog_chat_models", return_value=["a", "b"]):
      with pytest.raises(HTTPException):
        ai_settings._validate_tier_models_against_catalog({"fallback_models": ["a", "zz"]}, {"provider": "groq"})

  def test_provider_change_clears_stale_stored_values(self):
    from app.api.routers import ai_settings

    data = {"provider": "gemini"}
    current = {"provider": "groq", "fast_model": "openai/gpt-oss-20b", "fallback_models": ["gemini-2.5-flash", "x"]}
    with patch.object(ai_settings, "catalog_chat_models", return_value=["gemini-2.5-flash", "gemini-2.5-pro"]):
      ai_settings._validate_tier_models_against_catalog(data, current)
    assert data["fast_model"] == "" and data["fallback_models"] == ["gemini-2.5-flash"]

  def test_providers_without_catalog_are_not_validated(self):
    from app.api.routers import ai_settings

    data = {"provider": "ollama_remote", "fast_model": "qwen2.5:2b"}
    with patch.object(ai_settings, "catalog_chat_models", return_value=[]):
      ai_settings._validate_tier_models_against_catalog(data, {})
    assert data["fast_model"] == "qwen2.5:2b"


class TestDedupeScript:
  def test_consecutive_copies_within_window_are_duplicates(self):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from scripts.dedupe_chat_messages import find_duplicate_ids

    t0 = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)

    def msg(i, role, content, seconds):
      return SimpleNamespace(id=f"m{i}", role=role, content=content, created_at=t0 + timedelta(seconds=seconds))

    messages = [
      msg(1, "user", "hola", 0),
      msg(2, "user", "hola ", 2),        # copy → duplicate
      msg(3, "assistant", "respuesta", 3),
      msg(4, "assistant", "respuesta", 4),  # copy → duplicate
      msg(5, "user", "sí", 30),
      msg(6, "user", "sí", 60),          # same text but 30 s later → kept
    ]
    assert find_duplicate_ids(messages) == ["m2", "m4"]
