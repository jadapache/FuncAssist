"""Agent loop guards: tools with external effects never run next to external content, and calls are capped."""

from __future__ import annotations

import pytest

from app.ai import agent
from app.ai import logging as ai_logging
from app.ai.providers.base import AIMessage, ToolCall
from app.ai.tools.registry import Tool, ToolContext
from app.ai.untrusted import wrap_untrusted
from tests.test_ai_agent import ScriptedProvider, _collect


def external(name="send_email"):
  calls = []

  async def handler(args, ctx):
    calls.append(args)
    return "sent"

  return Tool(name, "", {}, handler, read_only=False, external_effect=True), calls


def local(name="read_note"):
  calls = []

  async def handler(args, ctx):
    calls.append(args)
    return "note"

  return Tool(name, "", {}, handler), calls


def user(text):
  return AIMessage(role="user", content=text)


# ----------------------------------------------------------------- external effects


def test_has_untrusted_content_looks_at_every_message_and_part():
  clean = [user("hola"), AIMessage(role="system", content="Seguridad: <<<DATOS_EXTERNOS ...>>> es solo el aviso")]
  assert agent._has_untrusted_content(clean) is False
  assert agent._has_untrusted_content([user("a"), user(wrap_untrusted("jira", "K-1", "texto"))]) is True
  parts = AIMessage(role="user", content=[{"type": "text", "text": wrap_untrusted("jira", "K-1", "t")}, {"type": "image_url"}])
  assert agent._has_untrusted_content([parts]) is True
  assert agent._has_untrusted_content([AIMessage(role="user", content=[{"type": "image_url"}])]) is False
  assert agent._has_untrusted_content([]) is False


@pytest.mark.asyncio
async def test_external_effect_tool_is_refused_when_the_context_has_external_content(monkeypatch):
  tool, calls = external()
  monkeypatch.setattr(agent, "get_tool", {tool.name: tool}.get)
  text, err = (await agent._exec_tool(ToolCall(id="1", name="send_email"), ToolContext(user_id="u"), untrusted_present=True))[1:]
  assert err is True and "actúa fuera de la conversación" in text
  assert calls == []


@pytest.mark.asyncio
async def test_external_effect_tool_runs_when_the_context_is_clean(monkeypatch):
  tool, calls = external()
  monkeypatch.setattr(agent, "get_tool", {tool.name: tool}.get)
  _, text, err = await agent._exec_tool(ToolCall(id="1", name="send_email", arguments={"to": "x"}), ToolContext(), untrusted_present=False)
  assert err is False and text == "sent" and calls == [{"to": "x"}]


@pytest.mark.asyncio
async def test_tools_without_external_effect_still_run_next_to_external_content(monkeypatch):
  tool, calls = local()
  monkeypatch.setattr(agent, "get_tool", {tool.name: tool}.get)
  _, text, err = await agent._exec_tool(ToolCall(id="1", name="read_note"), ToolContext(), untrusted_present=True)
  assert err is False and text == "note" and calls == [{}]


@pytest.mark.asyncio
async def test_the_refusal_is_recorded_without_arguments(monkeypatch, tmp_path):
  monkeypatch.setattr(ai_logging, "ensure_local_dirs", lambda: None)
  tool, _ = external()
  monkeypatch.setattr(agent, "get_tool", {tool.name: tool}.get)
  await agent._exec_tool(ToolCall(id="1", name="send_email", arguments={"to": "SECRET-ADDR"}), ToolContext(user_id="u1"), untrusted_present=True)
  await ai_logging.flush_pending_logs()
  events = ai_logging.list_security_events(kind="tool_call")
  assert events and events[0]["decision"] == "denied" and events[0]["tool"] == "send_email"
  assert events[0]["reason"] == "external_effect_with_untrusted_context" and events[0]["user"] == "u1"
  assert "SECRET-ADDR" not in str(events)


@pytest.mark.asyncio
async def test_run_agent_refuses_an_injected_request_to_use_an_external_tool(monkeypatch):
  """The model, steered by text in a ticket, asks for an external tool: it is refused and the turn goes on."""
  tool, calls = external()
  monkeypatch.setattr(agent, "get_tool", {tool.name: tool}.get)
  monkeypatch.setattr(agent, "get_tools_openai_schema", lambda: [{"name": tool.name}])
  provider = ScriptedProvider([
    ([], {"tool_calls": [ToolCall(id="c1", name="send_email", arguments={"to": "attacker@evil.example"})]}),
    (["No pude hacerlo."], {"finish_reason": "stop"}),
  ])
  messages = [user("Resume el ticket"), user(wrap_untrusted("jira", "K-1", "texto del ticket"))]
  events = await _collect(agent.run_agent(messages, provider, ToolContext(), max_iters=3))
  assert calls == []
  result = next(e for e in events if e.type == "tool_result")
  assert result.data["is_error"] is True and "actúa fuera de la conversación" in result.data["result"]
  assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_run_agent_allows_the_external_tool_when_nothing_external_is_in_the_conversation(monkeypatch):
  tool, calls = external()
  monkeypatch.setattr(agent, "get_tool", {tool.name: tool}.get)
  monkeypatch.setattr(agent, "get_tools_openai_schema", lambda: [{"name": tool.name}])
  provider = ScriptedProvider([
    ([], {"tool_calls": [ToolCall(id="c1", name="send_email", arguments={"to": "a@b.co"})]}),
    (["Enviado."], {"finish_reason": "stop"}),
  ])
  await _collect(agent.run_agent([user("Envía el resumen")], provider, ToolContext(), max_iters=3))
  assert calls == [{"to": "a@b.co"}]


@pytest.mark.asyncio
async def test_once_a_tool_result_is_in_the_conversation_external_tools_are_refused(monkeypatch):
  """Tool output is external content too: after the first tool call the context is no longer clean."""
  read, read_calls = local()
  send, send_calls = external()
  monkeypatch.setattr(agent, "get_tool", {read.name: read, send.name: send}.get)
  monkeypatch.setattr(agent, "get_tools_openai_schema", lambda: [])
  provider = ScriptedProvider([
    ([], {"tool_calls": [ToolCall(id="c1", name="read_note")]}),
    ([], {"tool_calls": [ToolCall(id="c2", name="send_email", arguments={"to": "x"})]}),
    (["fin"], {"finish_reason": "stop"}),
  ])
  events = await _collect(agent.run_agent([user("q")], provider, ToolContext(), max_iters=4))
  assert read_calls == [{}] and send_calls == []
  errors = [e.data for e in events if e.type == "tool_result" and e.data["is_error"]]
  assert len(errors) == 1 and errors[0]["name"] == "send_email"


# ----------------------------------------------------------------- call cap


@pytest.mark.asyncio
async def test_calls_beyond_the_cap_are_refused_but_answered(monkeypatch):
  tool, calls = local()
  monkeypatch.setattr(agent, "get_tool", {tool.name: tool}.get)
  monkeypatch.setattr(agent, "get_tools_openai_schema", lambda: [])
  monkeypatch.setattr(agent, "MAX_TOOL_CALLS_PER_TURN", 3)
  burst = [ToolCall(id=f"c{i}", name="read_note") for i in range(5)]
  provider = ScriptedProvider([([], {"tool_calls": burst}), (["listo"], {"finish_reason": "stop"})])
  events = await _collect(agent.run_agent([user("q")], provider, ToolContext(), max_iters=3))
  assert len(calls) == 3
  results = [e.data for e in events if e.type == "tool_result"]
  assert len(results) == 5  # every call gets an answer, so the conversation stays valid
  assert [r["is_error"] for r in results] == [False, False, False, True, True]
  assert "límite de 3 llamadas" in results[-1]["result"]


@pytest.mark.asyncio
async def test_the_cap_counts_across_iterations(monkeypatch):
  tool, calls = local()
  monkeypatch.setattr(agent, "get_tool", {tool.name: tool}.get)
  monkeypatch.setattr(agent, "get_tools_openai_schema", lambda: [])
  monkeypatch.setattr(agent, "MAX_TOOL_CALLS_PER_TURN", 2)
  provider = ScriptedProvider([
    ([], {"tool_calls": [ToolCall(id="a", name="read_note"), ToolCall(id="b", name="read_note")]}),
    ([], {"tool_calls": [ToolCall(id="c", name="read_note")]}),
    (["fin"], {"finish_reason": "stop"}),
  ])
  events = await _collect(agent.run_agent([user("q")], provider, ToolContext(), max_iters=4))
  assert len(calls) == 2
  assert [e.data["is_error"] for e in events if e.type == "tool_result"] == [False, False, True]


def test_the_default_cap_is_a_small_number():
  assert 1 <= agent.MAX_TOOL_CALLS_PER_TURN <= 20


def test_no_registered_tool_has_an_external_effect_today():
  """If one is added, it must be reviewed: it will be refused next to external content."""
  from app.ai.tools import registry

  assert [t.name for t in registry.list_tools() if t.external_effect] == []
