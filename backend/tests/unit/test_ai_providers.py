"""LLM provider layer: wire format, typed errors, fallbacks, prompt caching and stream usage."""

import json
from unittest.mock import MagicMock, patch

import litellm
import pytest

from app.ai.errors import AIError
from app.ai.providers import factory
from app.ai.providers.base import AIMessage, ToolCall
from app.ai.providers.implementations import (
  LiteLLMProvider,
  _handle_completion_error,
  apply_cache_breakpoints,
)
from app.ai.providers.registry import find_provider_spec


def _provider(provider_id="groq", model="m1", **kwargs):
  return LiteLLMProvider(find_provider_spec(provider_id), api_key="k", default_model=model, **kwargs)


def _settings(**overrides):
  base = {
    "provider": "groq",
    "model": "llama-3.3-70b-versatile",
    "groq_api_key": "k",
    "fallback_models": [],
    "fast_model": None,
    "ollama_base_url": None,
  }
  base.update(overrides)
  return base


class TestWireFormat:
  def test_plain_message_has_no_tool_fields(self):
    assert AIMessage(role="user", content="hola").to_litellm() == {"role": "user", "content": "hola"}

  def test_tool_calls_use_openai_format(self):
    msg = AIMessage(role="assistant", tool_calls=[ToolCall(id="c1", name="search_knowledge", arguments={"query": "x"})])
    tc = msg.to_litellm()["tool_calls"][0]
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "search_knowledge"
    assert json.loads(tc["function"]["arguments"]) == {"query": "x"}

  def test_tool_result_keeps_call_id(self):
    payload = AIMessage(role="tool", tool_call_id="c1", content="r").to_litellm()
    assert payload["tool_call_id"] == "c1" and "tool_calls" not in payload


class TestTypedErrors:
  def test_rate_limit_and_context_window_are_typed(self):
    rate = _handle_completion_error(litellm.RateLimitError("Rate limit reached", "groq", "llama"))
    ctx = _handle_completion_error(litellm.ContextWindowExceededError("Context window exceeded", "openai", "gpt-4"))
    assert isinstance(rate, AIError) and rate.code == "rate_limit"
    assert isinstance(ctx, AIError) and ctx.code == "context_window_exceeded"


class TestFallbacks:
  def setup_method(self):
    factory.clear_provider_cache()

  def test_user_fallbacks_reach_main_provider_only(self):
    with patch.object(factory, "get_ai_settings", return_value=_settings(fallback_models=["llama-3.1-8b-instant"])):
      main = factory.resolve_provider(user_id="u1")
      fast = factory.resolve_provider(user_id="u1", tier="fast")
    assert main.fallback_models == ["llama-3.1-8b-instant"]
    assert fast.fallback_models == []

  def test_fallbacks_ignored_when_request_targets_another_provider(self):
    with patch.object(factory, "get_ai_settings", return_value=_settings(fallback_models=["x"], gemini_api_key="g")):
      prov = factory.resolve_provider(provider_name="gemini", user_id="u1")
    assert prov.fallback_models == []

  def test_non_stream_uses_native_fallbacks_without_primary(self):
    kwargs = _provider(fallback_models=["m1", "m2"])._build_kwargs([AIMessage(role="user", content="hi")])
    assert kwargs["fallbacks"] == ["groq/m2"]

  @pytest.mark.asyncio
  async def test_stream_falls_back_before_first_chunk(self):
    prov = _provider(fallback_models=["m2"])

    async def _ok_stream():
      chunk = MagicMock(usage=None)
      chunk.choices = [MagicMock(delta=MagicMock(content="hola"))]
      yield chunk

    calls = []

    async def fake_acompletion(**kwargs):
      calls.append(kwargs["model"])
      assert "fallbacks" not in kwargs  # streaming handles fallbacks itself
      if kwargs["model"] == "groq/m1":
        raise RuntimeError("503 service unavailable")
      return _ok_stream()

    with patch("app.ai.providers.implementations.litellm.acompletion", side_effect=fake_acompletion):
      out = [c async for c in prov.complete_stream([AIMessage(role="user", content="q")])]
    assert out == ["hola"]
    assert calls == ["groq/m1", "groq/m2"]


class TestPromptCache:
  def test_breakpoints_on_context_and_end_of_history(self):
    wire = [
      {"role": "system", "content": "sys"},
      {"role": "system", "content": "docs"},
      {"role": "user", "content": "h1"},
      {"role": "assistant", "content": "h2"},
      {"role": "user", "content": "now"},
    ]
    assert apply_cache_breakpoints(wire) == 2
    assert wire[1]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert wire[3]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert wire[0]["content"] == "sys" and wire[4]["content"] == "now"

  def test_multimodal_parts_are_not_mutated(self):
    parts = [{"type": "text", "text": "hola"}, {"type": "image_url", "image_url": {"url": "data:x"}}]
    wire = [{"role": "system", "content": parts}]
    apply_cache_breakpoints(wire)
    assert "cache_control" not in parts[0]

  def test_only_claude_gets_explicit_breakpoints(self, monkeypatch):
    monkeypatch.setenv("AI_PROMPT_CACHE", "on")
    msgs = [AIMessage(role="system", content="s"), AIMessage(role="user", content="u")]
    assert isinstance(_provider("claude")._build_kwargs(msgs)["messages"][0]["content"], list)
    assert _provider("openai", "gpt-4o")._build_kwargs(msgs)["messages"][0]["content"] == "s"


class TestStreamUsage:
  @pytest.mark.asyncio
  async def test_usage_sink_collects_tokens_cache_and_ttft(self):
    async def _stream():
      c1 = MagicMock(usage=None)
      c1.choices = [MagicMock(delta=MagicMock(content="hola"))]
      yield c1
      c2 = MagicMock()
      c2.choices = []
      c2.usage = {"prompt_tokens": 100, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 80}}
      yield c2

    captured = {}

    async def fake_acompletion(**kwargs):
      captured.update(kwargs)
      return _stream()

    sink: dict = {}
    with patch("app.ai.providers.implementations.litellm.acompletion", side_effect=fake_acompletion):
      out = [c async for c in _provider("openai", "gpt-4o").complete_stream(
        [AIMessage(role="user", content="q")], usage_sink=sink
      )]

    assert out == ["hola"]
    assert captured["stream_options"] == {"include_usage": True}
    assert sink["prompt_tokens"] == 100 and sink["cached_tokens"] == 80
    assert sink["ttft_ms"] is not None and sink["fallback_used"] is False
