"""Agent tool-calling loop and the stoppable stream consumer."""

import asyncio

import pytest

from app.ai import agent
from app.ai.providers.base import AIMessage, ToolCall
from app.ai.stream_control import StreamStopped, iterate_until_stopped
from app.ai.tools.registry import Tool, ToolContext


class ScriptedProvider:
  """Each turn: (deltas, sink_dict). Records the tool_choice and conversations it sees."""

  def __init__(self, turns):
    self.turns = list(turns)
    self.calls = []

  async def complete_stream(self, messages, *, max_tokens=None, tools=None, tool_choice=None, usage_sink=None, **_):
    self.calls.append({"messages": list(messages), "tool_choice": tool_choice, "tools": tools})
    deltas, sink = self.turns.pop(0)
    for d in deltas:
      yield d
    usage_sink.update(sink)


async def _collect(gen):
  return [ev async for ev in gen]


def test_wrap_tool_output_clips_and_marks_untrusted():
  out = agent._wrap_tool_output("t", "x" * (agent.TOOL_RESULT_MAX_CHARS + 10))
  assert out.startswith("<<<DATOS_EXTERNOS id=") and "fuente=tool ref=t>>>" in out
  assert out.rstrip().endswith(">>>") and "<<<FIN_DATOS_EXTERNOS id=" in out
  assert "[...truncado]" in out
  assert "[...truncado]" not in agent._wrap_tool_output("t", "short")


@pytest.mark.asyncio
async def test_exec_tool_unknown_ok_error_and_exception(monkeypatch):
  async def ok(args, ctx):
    return f"hi {args['n']}"

  async def err_text(args, ctx):
    return "[Error]: bad"

  async def boom(args, ctx):
    raise ValueError("kaboom")

  tools = {n: Tool(n, "", {}, h) for n, h in (("ok", ok), ("errt", err_text), ("boom", boom))}
  monkeypatch.setattr(agent, "get_tool", tools.get)
  ctx = ToolContext()
  _, text, is_err = await agent._exec_tool(ToolCall(id="1", name="missing"), ctx)
  assert is_err and "no encontrada" in text
  _, text, is_err = await agent._exec_tool(ToolCall(id="2", name="ok", arguments={"n": 3}), ctx)
  assert (text, is_err) == ("hi 3", False)
  _, text, is_err = await agent._exec_tool(ToolCall(id="3", name="errt"), ctx)
  assert is_err
  _, text, is_err = await agent._exec_tool(ToolCall(id="4", name="boom"), ctx)
  assert is_err and "kaboom" in text


@pytest.mark.asyncio
async def test_run_agent_executes_tools_delivers_artifacts_and_sums_usage(monkeypatch):
  async def make_doc(args, ctx):
    ctx.artifacts.append({"title": "Doc", "extension": "md", "content": "# body"})
    return "created"

  monkeypatch.setattr(agent, "get_tool", {"make": Tool("make", "", {}, make_doc)}.get)
  monkeypatch.setattr(agent, "get_tools_openai_schema", lambda: [{"name": "make"}])
  provider = ScriptedProvider([
    (["thinking"], {"prompt_tokens": 10, "completion_tokens": 2, "cost_usd": 0.1, "ttft_ms": 5.0,
                    "tool_calls": [ToolCall(id="c1", name="make", arguments={"a": 1})]}),
    (["final ", "answer"], {"prompt_tokens": 20, "completion_tokens": 3, "cached_tokens": 4, "cost_usd": 0.2,
                            "finish_reason": "stop", "fallback_used": True, "ttft_ms": 99.0}),
  ])
  ctx = ToolContext()
  events = await _collect(agent.run_agent([AIMessage(role="user", content="q")], provider, ctx, max_iters=3))
  types = [e.type for e in events]
  assert types == ["status", "delta", "tool_call", "tool_result", "artifact_start", "artifact_delta",
                   "artifact_end", "delta", "delta", "usage", "done"]
  usage = events[-2].data
  assert usage["prompt_tokens"] == 30 and usage["completion_tokens"] == 5 and usage["cached_tokens"] == 4
  assert usage["cost_usd"] == pytest.approx(0.3)
  assert usage["iterations"] == 2 and usage["finish_reason"] == "stop"
  assert usage["fallback_used"] is True and usage["ttft_ms"] == 5.0
  # Second turn sees the assistant tool call and a wrapped tool message.
  second = provider.calls[1]["messages"]
  assert second[-2].role == "assistant" and second[-2].tool_calls[0].name == "make"
  assert second[-1].role == "tool" and "created" in second[-1].content
  assert provider.calls[0]["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_run_agent_last_iteration_forbids_tools(monkeypatch):
  monkeypatch.setattr(agent, "get_tools_openai_schema", lambda: [])
  monkeypatch.setattr(agent, "get_tool", lambda n: None)
  tc = ToolCall(id="x", name="nope")
  provider = ScriptedProvider([([], {"tool_calls": [tc]}), ([], {"tool_calls": [tc]})])
  events = await _collect(agent.run_agent([], provider, ToolContext(), max_iters=2))
  assert [c["tool_choice"] for c in provider.calls] == ["auto", "none"]
  assert events[-2].data["iterations"] == 2
  assert any(e.type == "tool_result" and e.data["is_error"] for e in events)


# --- stream_control -------------------------------------------------------


async def _never_stop():
  return None


@pytest.mark.asyncio
async def test_iterate_yields_all_items_from_async_generator():
  async def gen():
    for i in range(3):
      yield i

  assert [x async for x in iterate_until_stopped(gen(), _never_stop)] == [0, 1, 2]


@pytest.mark.asyncio
async def test_iterate_supports_plain_async_iterators_without_aclose():
  class It:
    def __init__(self):
      self.i = 0

    def __aiter__(self):
      return self

    async def __anext__(self):
      self.i += 1
      if self.i > 2:
        raise StopAsyncIteration
      return self.i

  assert [x async for x in iterate_until_stopped(It(), _never_stop)] == [1, 2]


@pytest.mark.asyncio
async def test_iterate_reraises_source_errors():
  async def gen():
    yield 1
    raise ValueError("source broke")

  out = []
  with pytest.raises(ValueError, match="source broke"):
    async for x in iterate_until_stopped(gen(), _never_stop):
      out.append(x)
  assert out == [1]


@pytest.mark.asyncio
async def test_iterate_stops_after_item_when_condition_fires():
  async def gen():
    for i in range(10):
      yield i

  async def stop():
    return "cancelled"

  with pytest.raises(StreamStopped) as exc:
    async for _ in iterate_until_stopped(gen(), stop):
      pass
  assert exc.value.reason == "cancelled"


@pytest.mark.asyncio
async def test_iterate_stops_while_waiting_and_cancels_source():
  cleaned = []

  async def slow():
    try:
      await asyncio.sleep(10)
      yield 1
    finally:
      cleaned.append(True)

  checks = []

  async def stop():
    checks.append(1)
    return "disconnected" if len(checks) >= 2 else None

  with pytest.raises(StreamStopped) as exc:
    async for _ in iterate_until_stopped(slow(), stop, poll_s=0.01):
      pass
  assert exc.value.reason == "disconnected"
  assert cleaned == [True]
