"""Chat runner: route selection, truncation handling and one log entry per request."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.ai import runner
from app.ai.events import AgentEvent
from app.ai.policies import INTENT_MAX_TOKENS, resolve_intent_max_tokens
from app.ai.providers.base import AICompletion, AIMessage
from app.ai.runner import AgenticChatConfig, continue_if_truncated, run_agentic_chat_stream
from app.ai.section_generator import DocumentPlan, PlanSection

BASE = [
  AIMessage(role="system", content="sys"),
  AIMessage(role="system", content="DOCUMENTOS"),
  AIMessage(role="user", content="q"),
]


class _Provider:
  """Streams scripted (text, finish_reason) parts; `complete` serves section calls."""

  id = "mock"
  default_model = "m"

  def __init__(self, parts=(), tools=False):
    self.parts = list(parts)
    self.calls: list[list[AIMessage]] = []
    self._tools = tools

  def supports_tools(self, model=None):
    return self._tools

  async def complete_stream(self, messages, *, max_tokens=None, usage_sink=None, **kwargs):
    self.calls.append(list(messages))
    text, reason = self.parts.pop(0)
    yield text
    if usage_sink is not None:
      usage_sink.update({"finish_reason": reason, "prompt_tokens": 10, "completion_tokens": 5, "model": "m"})

  async def complete(self, messages, **kwargs):
    return AICompletion(text="Sección", provider="mock", model="m", prompt_tokens=1, completion_tokens=1)


def _prep(provider):
  return runner._ChatPrep(
    provider=provider,
    fast=SimpleNamespace(get=AsyncMock(return_value=provider)),
    base_prompt="base",
    sys_prompt="sys",
    messages=list(BASE),
    history=[],
    context_docs_text="",
    used_sources=["knowledge"],
    input_budget=1000,
    out_tokens=100,
    allowed=["knowledge"],
  )


async def _drain(gen):
  return [item async for item in gen]


def _text(items):
  return "".join(i for i in items if isinstance(i, str))


class TestPolicies:
  def test_chat_budget_fits_long_answers(self):
    assert INTENT_MAX_TOKENS["chat"] == 4096 and resolve_intent_max_tokens("qna") == 4096


class TestContinuation:
  @pytest.mark.asyncio
  async def test_length_finish_reason_continues_with_full_context(self):
    provider = _Provider([(" y fin.", "stop")])
    accumulated = ["Respuesta larga"]
    sink: dict = {}
    out = await _drain(continue_if_truncated(
      accumulated, provider, BASE, finish_reason="length", max_tokens=50, max_continuations=1, usage_sink=sink,
    ))
    assert out == [" y fin."] and "".join(accumulated) == "Respuesta larga y fin."
    sent = provider.calls[0]
    assert sent[:3] == BASE and sent[3].role == "assistant" and sent[4].role == "user"
    assert sink["finish_reason"] == "stop" and sink["continuations"] == 1

  @pytest.mark.asyncio
  async def test_complete_answer_is_not_continued(self):
    provider = _Provider()
    sink: dict = {}
    out = await _drain(continue_if_truncated(["Hola."], provider, BASE, finish_reason="stop", usage_sink=sink))
    assert out == [] and provider.calls == [] and sink["continuations"] == 0


class TestPlainRoute:
  @pytest.mark.asyncio
  async def test_still_truncated_answer_gets_a_notice_and_is_logged(self):
    provider = _Provider([("parte 1", "length"), (" parte 2", "length")])
    cfg = AgenticChatConfig(query="q", intent="chat")
    with patch("app.ai.runner.log_ai_call") as log:
      items = await _drain(runner._plain_route(cfg, _prep(provider)))
    assert runner.TRUNCATION_NOTICE in _text(items)
    assert len(provider.calls) == 2  # chat intents continue once
    assert cfg.run_info["truncated"] is True
    entry = log.call_args.args[0]
    assert entry["route"] == "plain" and entry["finish_reason"] == "length" and entry["continuations"] == 1
    assert entry["completion_tokens"] == 10  # first call + continuation
    usage = next(i for i in items if isinstance(i, AgentEvent) and i.type == "usage")
    assert usage.data["route"] == "plain"

  @pytest.mark.asyncio
  async def test_unclosed_artifact_is_closed_before_the_notice(self):
    provider = _Provider([('<chat>ok</chat><artifact title="P" extension="docx"># A', "length")] * 3)
    cfg = AgenticChatConfig(query="q", intent="generic_report")
    with patch("app.ai.runner.log_ai_call"):
      items = await _drain(runner._plain_route(cfg, _prep(provider)))
    tail = _text(items)[-200:]
    assert "</artifact>" in tail and f"<chat>{runner.TRUNCATION_NOTICE}</chat>" in tail


class TestRouteSelection:
  @pytest.mark.asyncio
  async def test_document_intent_uses_sections_when_a_plan_exists(self, monkeypatch):
    monkeypatch.delenv("AI_AGENT_MODE", raising=False)
    provider = _Provider()
    plan = DocumentPlan(title="Plan", extension="docx", chat_intro="", sections=[PlanSection("A"), PlanSection("B")])
    cfg = AgenticChatConfig(query="genera un plan", intent="generic_plan")
    with patch("app.ai.runner._prepare_chat", AsyncMock(return_value=_prep(provider))), \
         patch("app.ai.runner.plan_document", AsyncMock(return_value=plan)), \
         patch("app.ai.runner.log_ai_call") as log:
      items = await _drain(run_agentic_chat_stream(cfg))
    assert cfg.run_info["route"] == "sections"
    assert any(isinstance(i, AgentEvent) and i.type == "plan" for i in items)
    entry = log.call_args.args[0]
    assert entry["route"] == "sections" and entry["sections"] == 2
    assert log.call_count == 1

  @pytest.mark.asyncio
  async def test_missing_plan_falls_back_to_plain_and_is_recorded(self, monkeypatch):
    monkeypatch.delenv("AI_AGENT_MODE", raising=False)
    provider = _Provider([("<chat>x</chat>", "stop")])
    cfg = AgenticChatConfig(query="genera un informe", intent="generic_report")
    with patch("app.ai.runner._prepare_chat", AsyncMock(return_value=_prep(provider))), \
         patch("app.ai.runner.plan_document", AsyncMock(return_value=None)), \
         patch("app.ai.runner.log_ai_call") as log:
      await _drain(run_agentic_chat_stream(cfg))
    entry = log.call_args.args[0]
    assert entry["route"] == "plain" and entry["section_plan_failed"] is True

  @pytest.mark.asyncio
  async def test_agent_mode_without_tool_support_uses_the_normal_route(self, monkeypatch):
    monkeypatch.setenv("AI_AGENT_MODE", "on")
    provider = _Provider([("hola", "stop")], tools=False)
    cfg = AgenticChatConfig(query="hola", intent="chat")
    with patch("app.ai.runner._prepare_chat", AsyncMock(return_value=_prep(provider))), \
         patch("app.ai.runner.log_ai_call"):
      await _drain(run_agentic_chat_stream(cfg))
    assert cfg.run_info["route"] == "plain" and cfg.run_info["agent_unsupported"] is True


class TestFailureLogging:
  @pytest.mark.asyncio
  async def test_failure_before_generation_is_logged_with_stage(self):
    cfg = AgenticChatConfig(query="q", intent="chat")
    with patch("app.ai.runner._prepare_chat", AsyncMock(side_effect=ValueError("API key is missing"))), \
         patch("app.ai.runner.log_ai_call") as log:
      with pytest.raises(ValueError):
        await _drain(run_agentic_chat_stream(cfg))
    entry = log.call_args.args[0]
    assert entry["error_code"] == "ValueError" and entry["stage"] == "context"
    assert cfg.run_info["logged"] is True

  @pytest.mark.asyncio
  async def test_closing_the_stream_logs_a_cancellation(self):
    cfg = AgenticChatConfig(query="q", intent="chat")
    with patch("app.ai.runner.log_ai_call") as log:
      gen = run_agentic_chat_stream(cfg)
      first = await gen.__anext__()
      assert first.type == "status"
      await gen.aclose()
    assert log.call_args.args[0]["error_code"] == "cancelled"
