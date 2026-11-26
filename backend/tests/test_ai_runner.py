"""Grounded runner, continuation logic and the agentic chat routes (all LLM/context calls faked)."""

import asyncio
import logging
from types import SimpleNamespace

import pytest

from app.ai import runner
from app.ai.errors import AIError
from app.ai.events import AgentEvent
from app.ai.providers.base import AICompletion, AIMessage
from app.ai.request_types import DocumentFeatureRequest, GroundedFeatureRequest, SimpleFeatureRequest
from app.context.models import ContextBundle, ContextChunk, SourceType


def _chunk(i, text="body"):
  return ContextChunk(id=f"c{i}", source_type=SourceType.KNOWLEDGE, source_label="kb", title=f"T{i}", text=text)


class FakeProvider:
  """Streams scripted turns; `complete` returns scripted completions."""

  id = "fake"
  default_model = "fake-model"

  def __init__(self, streams=(), completions=(), tools=False):
    self.streams = list(streams)
    self.completions = list(completions)
    self.stream_calls = []
    self.complete_calls = []
    self._tools = tools

  async def complete_stream(self, messages, *, max_tokens=None, usage_sink=None, **_):
    self.stream_calls.append(messages)
    chunks, sink = self.streams.pop(0)
    for c in chunks:
      yield c
    if usage_sink is not None:
      usage_sink.update(sink)

  async def complete(self, messages, *, max_tokens=None, **_):
    self.complete_calls.append(messages)
    return self.completions.pop(0)

  def supports_tools(self, model=None):
    if self._tools == "raise":
      raise RuntimeError("no idea")
    return self._tools


def _completion(text, reason="stop", **kw):
  return AICompletion(text=text, provider="fake", model="fake-model", finish_reason=reason, **kw)


async def _collect(gen):
  return [x async for x in gen]


@pytest.fixture
def logs(monkeypatch):
  entries = []

  def fake_log(entry):
    entries.append(entry)
    return {"id": f"log{len(entries)}", **entry}

  monkeypatch.setattr(runner, "log_ai_call", fake_log)
  return entries


# --- helpers ----------------------------------------------------------------


def test_needs_continuation_and_truncation_tail():
  assert runner.needs_continuation("ok", "length")
  assert runner.needs_continuation('<artifact title="a" extension="md">half', "stop")
  assert not runner.needs_continuation("done.", "stop")
  assert runner.truncation_tail("plain").startswith("\n\n_(")
  tail = runner.truncation_tail('<artifact title="x" extension="md">open')
  assert tail.startswith("\n</artifact>") and "<chat>" in tail
  closed = runner.truncation_tail('<artifact title="x">a</artifact>')
  assert not closed.startswith("\n</artifact>") and "<chat>" in closed


def test_merge_usage_sums_numbers_only():
  total = {"prompt_tokens": 1}
  runner._merge_usage(total, {"prompt_tokens": 2, "cost_usd": 0.5, "completion_tokens": True, "cached_tokens": "x"})
  assert total == {"prompt_tokens": 3, "cost_usd": 0.5}


def test_error_log_fields():
  assert runner.error_log_fields(asyncio.CancelledError())["error_code"] == "cancelled"
  assert runner.error_log_fields(GeneratorExit())["error_code"] == "cancelled"
  f = runner.error_log_fields(AIError("rate", "slow down", original_error=ValueError("429")))
  assert f == {"error_code": "rate", "error_message": "slow down", "error_detail": "429"}
  assert runner.error_log_fields(AIError("x", "msg"))["error_detail"] == "msg"
  assert runner.error_log_fields(KeyError("k"))["error_code"] == "KeyError"


@pytest.mark.asyncio
async def test_continue_if_truncated_streams_until_finished():
  prov = FakeProvider(streams=[(["more"], {"finish_reason": "length", "prompt_tokens": 2}),
                               ([" end"], {"finish_reason": "stop", "prompt_tokens": 3})])
  acc = ["start"]
  sink = {}
  out = await _collect(runner.continue_if_truncated(acc, prov, [AIMessage(role="user", content="q")],
                                                    finish_reason="length", max_continuations=5, usage_sink=sink))
  assert out == ["more", " end"]
  assert "".join(acc) == "startmore end"
  assert sink == {"prompt_tokens": 5, "finish_reason": "stop", "continuations": 2}
  # continuation conversation = original + partial answer + resume order
  msgs = prov.stream_calls[0]
  assert msgs[1].role == "assistant" and msgs[1].content == "start" and "ATENCIÓN" in msgs[2].content




@pytest.mark.asyncio
async def test_complete_with_continuation_accumulates():
  prov = FakeProvider(completions=[
    _completion("a", "length", prompt_tokens=1, cost_usd=0.1),
    _completion("b", "length", prompt_tokens=2, cost_usd=0.2),
    _completion("", "stop"),
  ])
  res = await runner.complete_with_continuation(prov, [], max_tokens=10)
  assert res.text == "ab" and res.prompt_tokens == 3 and res.cost_usd == pytest.approx(0.3)
  assert res.finish_reason == "length"
  prov = FakeProvider(completions=[_completion("done", "stop")])
  assert (await runner.complete_with_continuation(prov, [], max_tokens=1)).text == "done"


# --- grounded -----------------------------------------------------------------


@pytest.fixture
def grounded(monkeypatch):
  state = SimpleNamespace(
    prompt={"version": "p1", "allowed_sources": ["knowledge"], "system": "SYS",
            "user_template": "{context}|{rubric}|{query}|{chat_context}|{template}"},
    bundle=ContextBundle(query="q", chunks=[_chunk(1), _chunk(2)], used_sources=["knowledge"]),
    uploads=[],
    budget=100000,
  )

  async def get_prompt(f):
    return state.prompt

  async def get_rubric(f):
    return {"version": "r1"}

  async def assemble(query, sources, user_id=None):
    return state.bundle

  monkeypatch.setattr(runner, "get_prompt", get_prompt)
  monkeypatch.setattr(runner, "get_rubric", get_rubric)
  monkeypatch.setattr(runner, "rubric_to_text", lambda r: "RUB")
  monkeypatch.setattr(runner, "assemble_context", assemble)
  monkeypatch.setattr(runner, "chunks_from_documents", lambda ids: state.uploads)
  monkeypatch.setattr(runner, "calculate_input_budget", lambda *a: state.budget)
  return state


@pytest.mark.asyncio
async def test_prepare_refuses_without_sources(grounded):
  grounded.prompt = {"allowed_sources": []}
  res = await runner._prepare_grounded_context(feature="f", query="q", sources=None, document_ids=None,
                                               chat_context=None, template_content=None)
  assert res["refused"] and "fuentes" in res["reason"]


@pytest.mark.asyncio
async def test_prepare_refuses_on_empty_bundle_and_logs(grounded, logs):
  grounded.bundle = ContextBundle(query="q", missing_sources=["jira"])
  res = await runner._prepare_grounded_context(feature="f", query="q", sources=None, document_ids=None,
                                               chat_context=None, template_content=None)
  assert res["refused"] and "jira" in res["reason"]
  assert logs[0]["refused"] is True


@pytest.mark.asyncio
async def test_prepare_refuses_when_all_sources_hard_missing(grounded):
  grounded.bundle = ContextBundle(query="q", chunks=[_chunk(1)], missing_sources=["knowledge"])
  res = await runner._prepare_grounded_context(feature="f", query="q", sources=None, document_ids=None,
                                               chat_context=None, template_content=None)
  assert res["refused"] and "not connected" in res["reason"]


@pytest.mark.asyncio
async def test_prepare_merges_uploads_formats_prompt_and_trims(grounded, monkeypatch):
  grounded.uploads = [_chunk(9), _chunk(1)]  # c1 already present -> not duplicated
  grounded.budget = 0
  monkeypatch.setattr(runner, "count_tokens", lambda m, t: len(t))
  prov = FakeProvider()
  prep = await runner._prepare_grounded_context(feature="f", query="Q", sources=None, document_ids=["d"],
                                                chat_context="  chat ", template_content="TPL", provider=prov)
  assert "uploads" in prep.bundle.used_sources
  assert [c.id for c in prep.bundle.chunks] == ["c9"]  # trimmed down to one chunk, uploads first
  user = prep.messages[1].content
  assert user.endswith("|RUB|Q|chat|TPL") and prep.messages[0].content == "SYS"


@pytest.mark.asyncio
async def test_prepare_drops_unused_placeholders(grounded):
  grounded.prompt = {"allowed_sources": ["knowledge"], "user_template": "{context}::{query}"}
  prep = await runner._prepare_grounded_context(feature="f", query="Q", sources=None, document_ids=None,
                                                chat_context=None, template_content=None)
  assert prep.messages[1].content.endswith("::Q")


@pytest.mark.asyncio
async def test_run_grounded_feature_success_and_wrappers(grounded, logs, monkeypatch):
  def make_provider(**kw):
    return FakeProvider(completions=[_completion('<chat>hi</chat><artifact title="D" extension="md">x</artifact>')])

  monkeypatch.setattr(runner, "resolve_provider", make_provider)
  res = await runner.run_grounded_feature(feature="f", query="q")
  assert res["ok"] and len(res["citations"]) == 2 and res["citations"][0]["index"] == 1
  assert res["meta"]["artifact_count"] == 1 and res["meta"]["log_id"] == "log1"
  assert (await runner.run_simple_feature(SimpleFeatureRequest(feature="f", query="q")))["refused"] is False
  assert (await runner.run_document_feature(DocumentFeatureRequest("f", "q", ["d"])))["ok"]
  assert (await runner.run_grounded_request(GroundedFeatureRequest("f", "q")))["ok"]


@pytest.mark.asyncio
async def test_run_grounded_feature_refusal_and_error(grounded, logs, monkeypatch):
  grounded.prompt = {"allowed_sources": []}
  monkeypatch.setattr(runner, "resolve_provider", lambda **kw: FakeProvider())
  assert (await runner.run_grounded_feature(feature="f", query="q"))["refused"]
  grounded.prompt = {"allowed_sources": ["knowledge"]}

  class Broken(FakeProvider):
    async def complete(self, *a, **k):
      raise AIError("down", "Servicio caído")

  monkeypatch.setattr(runner, "resolve_provider", lambda **kw: Broken())
  with pytest.raises(AIError):
    await runner.run_grounded_feature(feature="f", query="q")
  assert logs[-1]["error_code"] == "down" and logs[-1]["stage"] == "generate"


@pytest.mark.asyncio
async def test_run_grounded_feature_stream(grounded, logs, monkeypatch):
  prov = FakeProvider(streams=[(["a", "b"], {"finish_reason": "length", "prompt_tokens": 1, "tool_calls": [1]}),
                               (["c"], {"finish_reason": "stop", "prompt_tokens": 2, "model": "m2"})])
  monkeypatch.setattr(runner, "resolve_provider", lambda **kw: prov)
  out = await _collect(runner.run_grounded_feature_stream(feature="f", query="q"))
  assert out == ["a", "b", "c"]
  log = logs[-1]
  assert log["output"] == "abc" and log["continuations"] == 1 and log["finish_reason"] == "stop"
  assert log["prompt_tokens"] == 3 and "tool_calls" not in log


@pytest.mark.asyncio
async def test_run_grounded_feature_stream_refusal_and_failure(grounded, logs, monkeypatch):
  grounded.prompt = {"allowed_sources": []}
  monkeypatch.setattr(runner, "resolve_provider", lambda **kw: FakeProvider())
  with pytest.raises(RuntimeError, match="fuentes"):
    await _collect(runner.run_grounded_feature_stream(feature="f", query="q"))
  grounded.prompt = {"allowed_sources": ["knowledge"]}

  class Broken(FakeProvider):
    async def complete_stream(self, *a, **k):
      yield "x"
      raise ValueError("mid-stream")

  monkeypatch.setattr(runner, "resolve_provider", lambda **kw: Broken())
  with pytest.raises(ValueError):
    await _collect(runner.run_grounded_feature_stream(feature="f", query="q"))
  assert logs[-1]["error_code"] == "ValueError" and logs[-1]["streamed"]


# --- chat helpers ----------------------------------------------------------------


def test_flag_and_format_rule(monkeypatch):
  monkeypatch.setenv("X_FLAG", " Yes ")
  assert runner._flag("X_FLAG", "false")
  monkeypatch.delenv("X_FLAG")
  assert not runner._flag("X_FLAG", "off")
  assert 'extension="pdf"' in runner._format_rule_for_intent("generic_report", ".PDF")
  assert "CONVERSACIONAL" in runner._format_rule_for_intent("chat")


@pytest.mark.asyncio
async def test_system_prompts(monkeypatch):
  seen = []

  async def get_prompt(f):
    seen.append(f)
    if f == "boom":
      raise KeyError(f)
    return {"system": "TEMPLATE"} if f == "generic_plan" else {}

  monkeypatch.setattr(runner, "get_prompt", get_prompt)
  assert await runner._build_base_system_prompt("generic_plan") == "TEMPLATE" + runner._UNTRUSTED_SUFFIX
  assert "QA" in await runner._build_base_system_prompt("chat", "boom")
  assert "QA" in await runner._build_base_system_prompt("chat", None)
  assert seen == ["generic_plan", "boom", "chat"]
  full = await runner._build_chat_system_prompt("generic_plan", None, None)
  assert full.startswith("TEMPLATE") and 'extension="docx"' in full
  # every system prompt, template or default, tells the model how to treat external content
  for intent, feature in (("generic_plan", None), ("chat", "boom"), ("chat", None)):
    assert "DATOS_EXTERNOS" in await runner._build_base_system_prompt(intent, feature)
    assert "DATOS_EXTERNOS" in await runner._build_chat_system_prompt(intent, feature)


def test_assemble_multimodal_message():
  assert runner._assemble_multimodal_message("t", None).content == "t"
  msg = runner._assemble_multimodal_message("t", [{"data": "data:image/jpeg;base64,AA"}, {"dataUrl": "BB", "type": "image/gif"}, {}])
  urls = [p["image_url"]["url"] for p in msg.content[1:]]
  assert urls == ["data:image/jpeg;base64,AA", "data:image/gif;base64,BB", "data:image/png;base64,"]


@pytest.mark.asyncio
async def test_fast_provider_resolver_caches_and_falls_back(monkeypatch):
  main = FakeProvider()
  calls = []

  def resolve(**kw):
    calls.append(kw)
    raise ValueError("no fast tier")

  monkeypatch.setattr(runner, "resolve_provider", resolve)
  cfg = runner.AgenticChatConfig(query="q")
  r = runner._FastProviderResolver(cfg, main)
  assert await r.get() is main and await r.get() is main
  assert len(calls) == 1 and calls[0]["tier"] == "fast" and cfg.run_info["fast_model"] == "fake-model"


def test_supports_agent():
  assert runner._supports_agent(FakeProvider(tools=True))
  assert not runner._supports_agent(FakeProvider(tools="raise"))
  assert not runner._supports_agent(SimpleNamespace())


# --- agentic chat --------------------------------------------------------------


@pytest.fixture
def chat(monkeypatch, logs):
  state = SimpleNamespace(provider=FakeProvider(), fast=FakeProvider(), budget=100000,
                          bundle=ContextBundle(query="q", chunks=[_chunk(1)], used_sources=["knowledge"]),
                          uploads=[], condensed=[], pruned=[])

  def resolve(**kw):
    return state.fast if kw.get("tier") == "fast" else state.provider

  async def assemble(query, sources, user_id=None):
    return state.bundle

  async def get_prompt(f):
    return {"system": "BASE"}

  async def condense(text, target_budget, provider, feature_goal):
    state.condensed.append((target_budget, provider))
    return "CONDENSED"

  async def prune(msgs, **kw):
    state.pruned.append(kw)
    return msgs[-1:]

  class Store:
    def __init__(self, cid, uid):
      self.cid = cid

  monkeypatch.setattr(runner, "resolve_provider", resolve)
  monkeypatch.setattr(runner, "assemble_context", assemble)
  monkeypatch.setattr(runner, "chunks_from_documents", lambda ids: state.uploads)
  monkeypatch.setattr(runner, "get_prompt", get_prompt)
  monkeypatch.setattr(runner, "calculate_input_budget", lambda *a: state.budget)
  monkeypatch.setattr(runner, "map_reduce_condense_context", condense)
  monkeypatch.setattr(runner, "prune_or_summarize_history", prune)
  monkeypatch.setattr(runner, "ChatSessionSummaryStore", Store)
  monkeypatch.setenv("AI_AGENT_MODE", "false")
  monkeypatch.setenv("AI_SECTION_GENERATION", "false")
  return state


@pytest.mark.asyncio
async def test_prepare_chat_full_context(chat):
  chat.uploads = [_chunk(5, "up")]
  cfg = runner.AgenticChatConfig(
    query="q", intent="template_mutation", sources=["knowledge"], document_ids=["d"],
    attached_docs=[{"filename": "a.txt", "content": "ATT"}, {"filename": "empty"}],
    template_content="TPL", history=[{"role": "user", "content": "h1"}, {"role": "assistant", "content": "h2"}],
    conversation_id="conv", images=[{"data": "AA"}], template_extension="xlsx",
  )
  prep = await runner._prepare_chat(cfg)
  assert prep.used_sources == ["knowledge", "uploads", "chat_attachments"]
  docs = prep.messages[1].content
  assert "Formato XLSX" in docs and "PLANTILLA CORPORATIVA:\nTPL" in docs and "ATT" in docs and "up" in docs
  assert prep.messages[-1].role == "user" and isinstance(prep.messages[-1].content, list)
  assert chat.pruned and chat.pruned[0]["store"].cid == "conv" and chat.pruned[0]["fast_provider"] is chat.fast
  assert cfg.run_info["provider"] == "fake" and cfg.run_info["stage"] == "history"
  assert not chat.condensed


@pytest.mark.asyncio
async def test_prepare_chat_condenses_oversized_docs(chat, monkeypatch):
  chat.bundle = ContextBundle(query="q", chunks=[_chunk(1, "x" * 50000)], used_sources=["knowledge"])
  chat.budget = 2000
  cfg = runner.AgenticChatConfig(query="q", sources=["knowledge"])
  prep = await runner._prepare_chat(cfg)
  assert prep.context_docs_text == "CONDENSED" and cfg.run_info["context_condensed"]
  assert chat.condensed[0][1] is chat.fast
  assert len(prep.messages) == 3  # system, docs, query (no history)


@pytest.mark.asyncio
async def test_plain_route_with_continuation_and_truncation(chat, logs):
  chat.provider = FakeProvider(streams=[(['<artifact title="x" extension="md">'], {"finish_reason": "length", "prompt_tokens": 1}),
                                        (["more"], {"finish_reason": "length", "prompt_tokens": 1}),
                                        (["again"], {"finish_reason": "length"}),
                                        (["last"], {"finish_reason": "length"})])
  cfg = runner.AgenticChatConfig(query="q", intent="chat")
  items = await _collect(runner.run_agentic_chat_stream(cfg))
  texts = [i for i in items if isinstance(i, str)]
  assert texts[0] == '<artifact title="x" extension="md">' and texts[-1].startswith("\n</artifact>")
  usage = [i for i in items if isinstance(i, AgentEvent) and i.type == "usage"][0]
  assert usage.data["route"] == "plain" and usage.data["finish_reason"] == "length"
  assert cfg.run_info["truncated"] and len(logs) == 1 and logs[0]["truncated"] is True


@pytest.mark.asyncio
async def test_agent_route_translates_events(chat, logs, monkeypatch):
  chat.provider = FakeProvider(tools=True)
  monkeypatch.setenv("AI_AGENT_MODE", "true")

  async def fake_agent(messages, provider, ctx, max_iters, max_tokens):
    ctx.artifacts.append({})
    for ev in [
      AgentEvent(type="status", data={"message": "s"}),
      AgentEvent(type="delta", data={"text": "hi"}),
      AgentEvent(type="artifact_start", data={"title": "T", "extension": "md"}),
      AgentEvent(type="artifact_delta", data={"text": "body"}),
      AgentEvent(type="artifact_end", data={}),
      AgentEvent(type="usage", data={"prompt_tokens": 4, "iterations": 2}),
      AgentEvent(type="done", data={}),
      AgentEvent(type="delta", data={"text": "never"}),
    ]:
      yield ev

  monkeypatch.setattr(runner, "run_agent", fake_agent)
  cfg = runner.AgenticChatConfig(query="q")
  items = await _collect(runner.run_agentic_chat_stream(cfg))
  texts = "".join(i for i in items if isinstance(i, str))
  assert texts == 'hi\n<artifact title="T" extension="md">\nbody\n</artifact>\n'
  usage = [i for i in items if isinstance(i, AgentEvent) and i.type == "usage"][0]
  assert usage.data["route"] == "agent" and usage.data["iterations"] == 2 and "duration_ms" in usage.data
  assert logs[0]["agent_mode"] and logs[0]["artifacts_created"] == 1 and logs[0]["route"] == "agent"


@pytest.mark.asyncio
async def test_agent_mode_unsupported_falls_back_to_plain(chat, logs, monkeypatch):
  monkeypatch.setenv("AI_AGENT_MODE", "true")
  chat.provider = FakeProvider(streams=[(["ok"], {"finish_reason": "stop"})])
  cfg = runner.AgenticChatConfig(query="q")
  await _collect(runner.run_agentic_chat_stream(cfg))
  assert cfg.run_info["agent_unsupported"] and cfg.run_info["route"] == "plain"


@pytest.mark.asyncio
async def test_sections_route(chat, logs, monkeypatch):
  monkeypatch.setenv("AI_SECTION_GENERATION", "true")
  monkeypatch.setattr(runner, "is_section_generation_candidate", lambda i, q: True)
  plan = SimpleNamespace(title="Doc", extension="md", chat_intro="", sections=[1, 2])

  async def fake_plan(**kw):
    kw["usage_sink"]["prompt_tokens"] = 7
    assert kw["provider"] is chat.fast
    return plan

  async def fake_sections(**kw):
    kw["usage_sink"]["failed_sections"] = ["B"]
    yield "part1"
    yield AgentEvent(type="status", data={})

  monkeypatch.setattr(runner, "plan_document", fake_plan)
  monkeypatch.setattr(runner, "generate_sections_stream", fake_sections)
  cfg = runner.AgenticChatConfig(query="q", intent="generic_report")
  items = await _collect(runner.run_agentic_chat_stream(cfg))
  usage = [i for i in items if isinstance(i, AgentEvent) and i.type == "usage"][0]
  assert usage.data["route"] == "sections" and usage.data["prompt_tokens"] == 7
  assert logs[0]["sections"] == 2 and logs[0]["failed_sections"] == ["B"] and logs[0]["output"] == "part1"


@pytest.mark.asyncio
async def test_section_plan_failure_falls_back_and_is_logged(chat, logs, monkeypatch):
  monkeypatch.setenv("AI_SECTION_GENERATION", "true")
  monkeypatch.setattr(runner, "is_section_generation_candidate", lambda i, q: True)

  async def no_plan(**kw):
    return None

  monkeypatch.setattr(runner, "plan_document", no_plan)
  chat.provider = FakeProvider(streams=[(["ok"], {"finish_reason": "stop"})])
  cfg = runner.AgenticChatConfig(query="q", intent="generic_report")
  cfg.run_info.update(intent_rules=["r"], protocol="v2")
  await _collect(runner.run_agentic_chat_stream(cfg))
  assert logs[0]["section_plan_failed"] and logs[0]["intent_rules"] == ["r"] and logs[0]["protocol"] == "v2"


@pytest.mark.asyncio
async def test_chat_failure_and_cancellation_are_logged_once(chat, logs, monkeypatch):
  def broken(**kw):
    raise ValueError("no provider")

  monkeypatch.setattr(runner, "resolve_provider", broken)
  cfg = runner.AgenticChatConfig(query="q")
  with pytest.raises(ValueError):
    await _collect(runner.run_agentic_chat_stream(cfg))
  assert logs[-1]["error_code"] == "ValueError" and logs[-1]["stage"] == "context"
  assert logs[-1]["sources_used"] == []
  runner._log_chat(cfg, None)  # already logged -> no duplicate
  assert len(logs) == 1

  monkeypatch.setattr(runner, "resolve_provider", lambda **kw: FakeProvider(streams=[(["a", "b"], {})]))
  cfg = runner.AgenticChatConfig(query="q")
  gen = runner.run_agentic_chat_stream(cfg)
  async for item in gen:
    if isinstance(item, str):
      break
  await gen.aclose()
  assert logs[-1]["error_code"] == "cancelled" and logs[-1]["stage"] == "generate"


# --- edge cases of logs, budgets, routing and timing ---------------------------------


def _ticks(monkeypatch, *values):
  """Make `runner.time.perf_counter()` return the given values in order, then the last one forever."""
  queue = list(values)
  monkeypatch.setattr(runner, "time", SimpleNamespace(perf_counter=lambda: queue.pop(0) if len(queue) > 1 else queue[0]))


# --- continuation and citations -------------------------------------------

def test_continuation_prompt_quotes_the_last_800_characters():
  prompt = runner._continuation_prompt("a" * 500 + "b" * 800)
  assert '"""' + "b" * 800 + '"""' in prompt


def test_citations_are_numbered_from_one():
  citations = runner._citations([_chunk(1), _chunk(2)])
  assert [(c["index"], c["id"], c["source_type"], c["title"]) for c in citations] == [
    (1, "c1", "knowledge", "T1"), (2, "c2", "knowledge", "T2"),
  ]


# --- grounded logs --------------------------------------------------------

@pytest.mark.asyncio
async def test_grounded_logs_say_it_was_not_a_refusal(grounded, logs, monkeypatch):
  monkeypatch.setattr(runner, "resolve_provider", lambda **kw: FakeProvider(completions=[_completion("hola")]))
  await runner.run_grounded_feature(feature="f", query="q")
  assert logs[-1]["refused"] is False and logs[-1]["route"] == "grounded" and logs[-1]["feature"] == "f"

  class Broken(FakeProvider):
    async def complete(self, *a, **k):
      raise AIError("down", "caído")

  monkeypatch.setattr(runner, "resolve_provider", lambda **kw: Broken())
  with pytest.raises(AIError):
    await runner.run_grounded_feature(feature="f", query="q")
  assert logs[-1]["refused"] is False and logs[-1]["stage"] == "generate" and "streamed" not in logs[-1]


@pytest.mark.asyncio
async def test_grounded_stream_logs(grounded, logs, monkeypatch):
  provider = FakeProvider(streams=[(["a"], {"finish_reason": "stop", "prompt_tokens": 4, "tool_calls": [1]})])
  monkeypatch.setattr(runner, "resolve_provider", lambda **kw: provider)
  await _collect(runner.run_grounded_feature_stream(feature="f", query="q"))
  log = logs[-1]
  assert log["streamed"] is True and log["refused"] is False and log["continuations"] == 0
  assert log["model"] == "fake-model" and log["finish_reason"] == "stop" and "tool_calls" not in log

  provider = FakeProvider(streams=[(["a"], {"finish_reason": "stop", "model": "served-model"})])
  monkeypatch.setattr(runner, "resolve_provider", lambda **kw: provider)
  await _collect(runner.run_grounded_feature_stream(feature="f", query="q"))
  assert logs[-1]["model"] == "served-model"

  class Broken(FakeProvider):
    async def complete_stream(self, *a, **k):
      raise ValueError("boom")
      yield

  monkeypatch.setattr(runner, "resolve_provider", lambda **kw: Broken())
  with pytest.raises(ValueError):
    await _collect(runner.run_grounded_feature_stream(feature="f", query="q"))
  assert logs[-1]["refused"] is False and logs[-1]["streamed"] is True and logs[-1]["stage"] == "generate"


@pytest.mark.asyncio
async def test_document_feature_defaults_to_the_knowledge_source(monkeypatch):
  seen = []

  async def fake_run(**kwargs):
    seen.append(kwargs["sources"])
    return {}

  monkeypatch.setattr(runner, "run_grounded_feature", fake_run)
  await runner.run_document_feature(DocumentFeatureRequest("f", "q", ["d"]))
  await runner.run_document_feature(DocumentFeatureRequest("f", "q", ["d"], sources=["jira"]))
  await runner.run_document_feature(DocumentFeatureRequest("f", "q", ["d"], sources=[]))
  assert seen == [["knowledge"], ["jira"], ["knowledge"]]


# --- system prompts and context -------------------------------------------

@pytest.mark.asyncio
async def test_chat_system_prompt_defaults_to_docx(monkeypatch):
  async def no_template(feature):
    return {}

  monkeypatch.setattr(runner, "get_prompt", no_template)
  assert 'extension="docx"' in await runner._build_chat_system_prompt("generic_report", None, None)
  assert 'extension="pdf"' in await runner._build_chat_system_prompt("generic_report", None, "pdf")


@pytest.mark.asyncio
async def test_template_without_a_system_text_falls_back_to_the_default_prompt(monkeypatch):
  async def none_template(feature):
    return None

  monkeypatch.setattr(runner, "get_prompt", none_template)
  assert "QA" in await runner._build_base_system_prompt("chat")


def test_context_parts_are_numbered_and_attachments_without_content_are_dropped():
  bundle = SimpleNamespace(is_empty=True, used_sources=[], to_prompt_block=lambda: "")
  text, used = runner._collect_context(
    bundle, [_chunk(1, "uno"), _chunk(2, "dos")], [{"filename": "a.txt", "content": "ATT"}, {"filename": "vacio"}]
  )
  assert "[1] " in text and "[2] " in text and "ATT" in text and "vacio" not in text
  assert used == ["uploads", "chat_attachments"]
  assert runner._collect_context(None, [], None) == ("", [])


# --- budgets --------------------------------------------------------------

def _cfg(**kwargs):
  return runner.AgenticChatConfig(query="qq", **kwargs)


@pytest.mark.asyncio
async def test_budgets_split_the_input_window(monkeypatch):
  seen = []
  monkeypatch.setattr(runner, "count_tokens", lambda model, text: len(text))
  monkeypatch.setattr(runner, "calculate_input_budget", lambda provider_id, model, out: seen.append(model) or 100_000)
  provider = SimpleNamespace(id="x")
  cfg = _cfg(intent="template_mutation", template_content="tttt", images=[{}, {}])
  budgets = await runner._chat_budgets(cfg, provider, "sss")
  assert seen == ["gpt-4o"] and budgets.model == "gpt-4o"
  assert budgets.history_tokens == 6_000
  assert budgets.docs_tokens == 100_000 - (3 + 2 + 4 + 2 * runner.IMAGE_TOKEN_ESTIMATE) - 6_000

  chat_only = await runner._chat_budgets(_cfg(intent="chat", template_content="tttt"), SimpleNamespace(id="x", default_model="m"), "sss")
  assert chat_only.model == "m" and chat_only.docs_tokens == 100_000 - 5 - 6_000
  no_template = await runner._chat_budgets(_cfg(intent="template_mutation"), provider, "sss")
  assert no_template.docs_tokens == 100_000 - 5 - 6_000


@pytest.mark.asyncio
@pytest.mark.parametrize("input_budget,history", [(100_000, 6_000), (8_000, 2_000), (2_000, 1_000)])
async def test_history_budget_is_a_quarter_of_the_window_within_bounds(monkeypatch, input_budget, history):
  monkeypatch.setattr(runner, "count_tokens", lambda model, text: 0)
  monkeypatch.setattr(runner, "calculate_input_budget", lambda *a: input_budget)
  budgets = await runner._chat_budgets(_cfg(), SimpleNamespace(id="x", default_model="m"), "s")
  assert budgets.history_tokens == history
  assert budgets.docs_tokens == max(runner.DOCS_MIN_TOKENS, input_budget - history)


@pytest.mark.asyncio
async def test_documents_are_condensed_only_when_they_exceed_their_budget(monkeypatch):
  targets = []

  async def condense(text, target_budget, provider, feature_goal):
    targets.append(target_budget)
    return "CONDENSED"

  monkeypatch.setattr(runner, "count_tokens", lambda model, text: len(text))
  monkeypatch.setattr(runner, "chars_per_token", lambda model, text: 2.0)
  monkeypatch.setattr(runner, "map_reduce_condense_context", condense)
  fast = SimpleNamespace(get=lambda: _async(None))
  cfg = _cfg()
  budgets = runner._Budgets("m", 0, 0, 0, docs_tokens=10)
  assert await runner._condense_context(cfg, "x" * 10, budgets, fast) == "x" * 10
  assert await runner._condense_context(cfg, "", budgets, fast) == ""
  assert targets == [] and "context_condensed" not in cfg.run_info
  assert await runner._condense_context(cfg, "x" * 11, budgets, fast) == "CONDENSED"
  assert targets == [20] and cfg.run_info["context_condensed"] is True and cfg.run_info["stage"] == "condense"


async def _async(value):
  return value


def test_documents_message_sections():
  def message(intent, template="TPL", docs="DOCS"):
    return runner._documents_message(_cfg(intent=intent, template_content=template, template_extension="pdf"), docs)

  assert "PLANTILLA CORPORATIVA:\nTPL" in message("template_mutation")
  assert "PLANTILLA" not in message("chat")
  assert "PLANTILLA" not in message("template_mutation", template=None)
  assert "Formato PDF" in message("generic_plan") and "Formato" not in message("chat")
  assert message("chat", docs="") == ""


@pytest.mark.asyncio
async def test_history_scope_is_the_conversation_then_the_user(monkeypatch):
  seen = []

  async def prune(messages, **kwargs):
    seen.append((kwargs["scope"], kwargs["store"]))
    return messages

  class Store:
    def __init__(self, conversation_id, user_id):
      self.ids = (conversation_id, user_id)

  monkeypatch.setattr(runner, "prune_or_summarize_history", prune)
  monkeypatch.setattr(runner, "ChatSessionSummaryStore", Store)
  fast = SimpleNamespace(get=lambda: _async(None))
  budgets = runner._Budgets("m", 0, 0, 100, 100)
  history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
  await runner._prepare_history(_cfg(history=history, conversation_id="conv", user_id="u"), budgets, fast)
  await runner._prepare_history(_cfg(history=history, user_id="u"), budgets, fast)
  assert [scope for scope, _ in seen] == ["conv", "u"]
  assert seen[0][1].ids == ("conv", "u") and seen[1][1] is None
  assert await runner._prepare_history(_cfg(), budgets, fast) == []


@pytest.mark.asyncio
async def test_chat_prompt_defaults_to_docx_in_the_prepared_conversation(chat):
  prep = await runner._prepare_chat(_cfg(intent="generic_plan", template_extension=None))
  assert 'extension="docx"' in prep.sys_prompt


# --- chat log entry -------------------------------------------------------

def test_log_entry_flags_and_usage(logs):
  cfg = _cfg()
  cfg.run_info.update(model="info-model", provider="p")
  runner._log_chat(cfg, None, usage={"tool_calls": [1], "model": "served", "prompt_tokens": 3})
  entry = logs[-1]
  assert entry["refused"] is False and entry["streamed"] is True and entry["model"] == "served"
  assert entry["prompt_tokens"] == 3 and "tool_calls" not in entry
  cfg2 = _cfg()
  runner._log_chat(cfg2, None, usage={})
  assert logs[-1]["model"] == "unknown" and logs[-1]["provider"] == "unknown"
  cfg3 = _cfg()
  cfg3.run_info["model"] = "info-model"
  runner._log_chat(cfg3, None)
  assert logs[-1]["model"] == "info-model"


# --- routes ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_route_context_and_duration(chat, logs, monkeypatch):
  seen = {}

  async def fake_agent(messages, provider, ctx, max_iters, max_tokens):
    seen["documents"] = ctx.allowed_document_ids
    yield AgentEvent(type="usage", data={"prompt_tokens": 1})
    yield AgentEvent(type="done", data={})

  chat.provider = FakeProvider(tools=True)
  monkeypatch.setenv("AI_AGENT_MODE", "true")
  monkeypatch.setattr(runner, "run_agent", fake_agent)
  _ticks(monkeypatch, 10.0, 12.0)
  items = await _collect(runner.run_agentic_chat_stream(runner.AgenticChatConfig(query="q")))
  usage = next(i for i in items if isinstance(i, AgentEvent) and i.type == "usage")
  assert seen["documents"] == [] and usage.data["duration_ms"] == 2000.0


@pytest.mark.asyncio
async def test_sections_route_duration_and_failed_sections(chat, logs, monkeypatch):
  async def fake_sections(**kwargs):
    yield "texto"

  plan = SimpleNamespace(sections=[1, 2], title="T", extension="md", chat_intro="")

  async def fake_plan(**kwargs):
    return plan

  monkeypatch.setenv("AI_SECTION_GENERATION", "true")
  monkeypatch.setattr(runner, "is_section_generation_candidate", lambda intent, query: True)
  monkeypatch.setattr(runner, "plan_document", fake_plan)
  monkeypatch.setattr(runner, "generate_sections_stream", fake_sections)
  _ticks(monkeypatch, 10.0, 13.0)
  items = await _collect(runner.run_agentic_chat_stream(runner.AgenticChatConfig(query="q")))
  usage = next(i for i in items if isinstance(i, AgentEvent) and i.type == "usage")
  assert usage.data["duration_ms"] == 3000.0
  assert logs[-1]["failed_sections"] == [] and logs[-1]["sections"] == 2


def _plain_chat(chat, streams, monkeypatch):
  chat.provider = FakeProvider(streams=streams)
  monkeypatch.setattr(runner, "resolve_max_continuations", lambda intent: 1)


@pytest.mark.asyncio
async def test_plain_answer_is_truncated_when_the_model_stopped_on_length(chat, logs, monkeypatch):
  _plain_chat(chat, [(["uno"], {"finish_reason": "length"}), (["dos"], {"finish_reason": "length"})], monkeypatch)
  cfg = runner.AgenticChatConfig(query="q")
  await _collect(runner.run_agentic_chat_stream(cfg))
  assert cfg.run_info["truncated"] is True and logs[-1]["truncated"] is True


@pytest.mark.asyncio
async def test_plain_answer_is_truncated_when_an_artifact_is_left_open(chat, logs, monkeypatch):
  _plain_chat(chat, [(['<artifact title="a" extension="md">mitad'], {"finish_reason": "stop"}), ([], {})], monkeypatch)
  cfg = runner.AgenticChatConfig(query="q")
  await _collect(runner.run_agentic_chat_stream(cfg))
  assert cfg.run_info["truncated"] is True


@pytest.mark.asyncio
async def test_complete_plain_answer_is_not_truncated_and_keeps_its_usage(chat, logs, monkeypatch, caplog):
  _plain_chat(chat, [(["listo"], {"finish_reason": "stop", "prompt_tokens": 5, "tool_calls": [1]})], monkeypatch)
  cfg = runner.AgenticChatConfig(query="q")
  await _collect(runner.run_agentic_chat_stream(cfg))
  assert "truncated" not in cfg.run_info and logs[-1]["truncated"] is False
  assert logs[-1]["prompt_tokens"] == 5 and "tool_calls" not in logs[-1] and logs[-1]["continuations"] == 0


@pytest.mark.asyncio
async def test_truncation_warning_reports_the_continuations_made(chat, logs, monkeypatch, caplog):
  _plain_chat(chat, [(["uno"], {"finish_reason": "length"}), (["dos"], {"finish_reason": "length"})], monkeypatch)
  with caplog.at_level(logging.WARNING):
    await _collect(runner.run_agentic_chat_stream(runner.AgenticChatConfig(query="q")))
  assert any("after 1 continuation(s)" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_usage_event_of_the_plain_route_reports_its_continuations(chat, logs, monkeypatch):
  _plain_chat(chat, [(["uno"], {"finish_reason": "length"}), (["dos"], {"finish_reason": "stop"})], monkeypatch)
  items = await _collect(runner.run_agentic_chat_stream(runner.AgenticChatConfig(query="q")))
  usage = next(i for i in items if isinstance(i, AgentEvent) and i.type == "usage")
  assert usage.data["continuations"] == 1 and usage.data["finish_reason"] == "stop"


# --- routing --------------------------------------------------------------

@pytest.mark.parametrize("flag,candidate,expected", [
  ("true", True, True), ("false", True, False), ("true", False, False), ("false", False, False),
])
def test_sections_are_wanted_only_when_enabled_and_the_request_is_a_candidate(monkeypatch, flag, candidate, expected):
  monkeypatch.setenv("AI_SECTION_GENERATION", flag)
  monkeypatch.setattr(runner, "is_section_generation_candidate", lambda intent, query: candidate)
  assert runner._wants_sections(_cfg()) is expected


@pytest.mark.asyncio
async def test_agent_route_wins_over_section_planning(chat, logs, monkeypatch):
  planned = []

  async def fake_plan(**kwargs):
    planned.append(1)

  async def fake_agent(messages, provider, ctx, max_iters, max_tokens):
    yield AgentEvent(type="done", data={})

  chat.provider = FakeProvider(tools=True)
  monkeypatch.setenv("AI_AGENT_MODE", "true")
  monkeypatch.setenv("AI_SECTION_GENERATION", "true")
  monkeypatch.setattr(runner, "is_section_generation_candidate", lambda intent, query: True)
  monkeypatch.setattr(runner, "plan_document", fake_plan)
  monkeypatch.setattr(runner, "run_agent", fake_agent)
  cfg = runner.AgenticChatConfig(query="q")
  await _collect(runner.run_agentic_chat_stream(cfg))
  assert planned == [] and cfg.run_info["route"] == "agent"


@pytest.mark.asyncio
async def test_no_planning_when_sections_are_not_wanted(chat, logs, monkeypatch):
  planned = []

  async def fake_plan(**kwargs):
    planned.append(1)

  chat.provider = FakeProvider(streams=[(["ok"], {"finish_reason": "stop"})])
  monkeypatch.setattr(runner, "plan_document", fake_plan)
  await _collect(runner.run_agentic_chat_stream(runner.AgenticChatConfig(query="q")))
  assert planned == []


@pytest.mark.asyncio
async def test_failed_chat_run_is_logged_with_its_traceback(chat, logs, monkeypatch, caplog):
  class Broken(FakeProvider):
    async def complete_stream(self, *a, **k):
      raise ValueError("boom")
      yield

  chat.provider = Broken()
  with caplog.at_level(logging.WARNING), pytest.raises(ValueError):
    await _collect(runner.run_agentic_chat_stream(runner.AgenticChatConfig(query="q")))
  record = next(r for r in caplog.records if "Chat run failed" in r.getMessage())
  assert record.exc_info and logs[-1]["error_code"] == "ValueError"


# --- continuation limits and context trimming -----------------------------

@pytest.mark.asyncio
async def test_streamed_continuation_stops_when_the_text_does_not_grow():
  prov = FakeProvider(streams=[([""], {"finish_reason": "length"}), (["more"], {"finish_reason": "stop"})])
  out = await _collect(runner.continue_if_truncated(["start"], prov, [], finish_reason="length", max_continuations=5))
  assert out == [""] and len(prov.stream_calls) == 1


@pytest.mark.asyncio
async def test_completion_continues_at_most_the_allowed_number_of_times():
  prov = FakeProvider(completions=[_completion(letter, "length") for letter in "abcdef"])
  res = await runner.complete_with_continuation(prov, [], max_tokens=1, max_continuations=2)
  assert res.text == "abc" and len(prov.complete_calls) == 3
  prov = FakeProvider(completions=[_completion("a", "length"), _completion("b", "stop", prompt_tokens=5)])
  assert (await runner.complete_with_continuation(prov, [], max_tokens=1)).prompt_tokens == 5


class _Bundle:
  def __init__(self, count):
    self.chunks = list(range(count))

  def to_prompt_block(self):
    return "y" * (10 * len(self.chunks))


@pytest.mark.asyncio
async def test_bundle_is_trimmed_to_exactly_the_available_tokens(monkeypatch, caplog):
  models = []
  monkeypatch.setattr(runner, "count_tokens", lambda model, text: len(text))
  monkeypatch.setattr(runner, "calculate_input_budget", lambda pid, model, out: models.append(model) or 100)
  bundle = _Bundle(9)
  with caplog.at_level(logging.INFO):
    await runner._fit_bundle_to_budget(bundle, provider=SimpleNamespace(id="x"), max_output_tokens=10, fixed_texts=["x" * 30, ""])
  assert models == ["gpt-4o"] and len(bundle.chunks) == 7
  assert any("dropped 2 chunk(s)" in r.getMessage() for r in caplog.records)
  caplog.clear()
  with caplog.at_level(logging.INFO):
    await runner._fit_bundle_to_budget(bundle, provider=SimpleNamespace(id="x", default_model="m"), max_output_tokens=10, fixed_texts=["x" * 30])
  assert models[-1] == "m" and len(bundle.chunks) == 7 and not any("dropped" in r.getMessage() for r in caplog.records)


def test_refusal_answer_shape():
  assert runner._refusal("porque") == {"ok": False, "refused": True, "reason": "porque", "answer": None, "citations": []}


@pytest.mark.asyncio
async def test_plan_uses_docx_when_the_request_names_no_extension(chat, monkeypatch):
  seen = []

  async def fake_plan(**kwargs):
    seen.append(kwargs["template_extension"])

  monkeypatch.setattr(runner, "plan_document", fake_plan)
  prep = await runner._prepare_chat(runner.AgenticChatConfig(query="q"))
  await runner._plan_sections(runner.AgenticChatConfig(query="q", template_extension=None), prep)
  await runner._plan_sections(runner.AgenticChatConfig(query="q", template_extension="xlsx"), prep)
  assert seen == ["docx", "xlsx"]
