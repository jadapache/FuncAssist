"""Catalog-driven model selection, fast-tier recovery, retry policy, typed errors and streamed tool calls."""

from types import SimpleNamespace
from unittest.mock import patch

import litellm
import pytest

from app.ai import catalog
from app.ai.errors import AIError
from app.ai.providers import factory, implementations
from app.ai.providers.base import AIMessage
from app.ai.providers.implementations import LiteLLMProvider, _handle_completion_error
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


def _catalog(*entries):
  """Fake catalog: entries are (provider, model_id)."""
  return [SimpleNamespace(id=m, raw_id=m, provider=p, task_type="chat_writing") for p, m in entries]


class _FakeResponse:
  def __init__(self, text="ok", model="groq/m", finish_reason="stop"):
    self.choices = [SimpleNamespace(
      message=SimpleNamespace(content=text, tool_calls=None), finish_reason=finish_reason,
    )]
    self.usage = {"prompt_tokens": 3, "completion_tokens": 2}
    self.model = model

  def model_dump(self):
    return {}


class TestPickModel:
  def test_fast_tier_prefers_newest_undated_match(self):
    fake = _catalog(
      ("claude", "claude-3-5-haiku-20241022"),
      ("claude", "claude-haiku-4-5-20251001"),
      ("claude", "claude-haiku-4-5"),
      ("claude", "claude-sonnet-4-5"),
    )
    with patch.object(catalog, "load_local_catalog", return_value=fake):
      assert catalog.pick_model("claude", "fast") == "claude-haiku-4-5"
      assert catalog.pick_model("claude", "main") == "claude-sonnet-4-5"

  def test_pattern_order_wins_over_version(self):
    fake = _catalog(
      ("groq", "llama-3.1-8b-instant"),
      ("groq", "openai/gpt-oss-20b"),
      ("groq", "openai/gpt-oss-120b"),
    )
    with patch.object(catalog, "load_local_catalog", return_value=fake):
      assert catalog.pick_model("groq", "fast") == "openai/gpt-oss-20b"
      assert catalog.pick_model("groq", "main") == "openai/gpt-oss-120b"

  def test_excludes_preview_variants(self):
    fake = _catalog(
      ("gemini", "gemini-3-flash-preview"),
      ("gemini", "gemini-2.5-flash"),
      ("gemini", "gemini-2.5-flash-lite"),
    )
    with patch.object(catalog, "load_local_catalog", return_value=fake):
      assert catalog.pick_model("gemini", "fast") == "gemini-2.5-flash-lite"
      assert catalog.pick_model("gemini", "main") == "gemini-2.5-flash"

  def test_no_match_returns_none(self):
    with patch.object(catalog, "load_local_catalog", return_value=_catalog(("groq", "mixtral-8x7b"))):
      assert catalog.pick_model("groq", "fast", "llama-3.1-8b-instant") is None

  def test_empty_catalog_returns_registry_default(self):
    with patch.object(catalog, "load_local_catalog", return_value=[]):
      assert catalog.pick_model("groq", "fast", "openai/gpt-oss-20b") == "openai/gpt-oss-20b"


class TestFastTierResolution:
  def setup_method(self):
    factory.clear_provider_cache()

  def test_fast_tier_uses_main_model_when_catalog_has_no_fast_model(self):
    with patch.object(catalog, "load_local_catalog", return_value=_catalog(("groq", "llama-3.3-70b-versatile"))), \
         patch.object(factory, "get_ai_settings", return_value=_settings()):
      fast = factory.resolve_provider(user_id="u1", tier="fast")
    assert fast.default_model == "llama-3.3-70b-versatile"
    assert fast.not_found_fallback is None

  def test_fast_tier_picks_catalog_model_and_keeps_main_as_recovery(self):
    fake = _catalog(("groq", "llama-3.3-70b-versatile"), ("groq", "openai/gpt-oss-20b"))
    with patch.object(catalog, "load_local_catalog", return_value=fake), \
         patch.object(factory, "get_ai_settings", return_value=_settings()):
      fast = factory.resolve_provider(user_id="u1", tier="fast")
    assert fast.default_model == "openai/gpt-oss-20b"
    assert fast.not_found_fallback == "llama-3.3-70b-versatile"

  def test_configured_model_ignored_for_another_provider(self):
    fake = _catalog(("gemini", "gemini-2.5-flash"))
    with patch.object(catalog, "load_local_catalog", return_value=fake), \
         patch.object(factory, "get_ai_settings", return_value=_settings(gemini_api_key="g")):
      prov = factory.resolve_provider(provider_name="gemini", user_id="u1")
    assert prov.default_model == "gemini-2.5-flash"


class TestRetryPolicy:
  def test_litellm_internal_retries_are_disabled(self):
    assert _provider()._build_kwargs([AIMessage(role="user", content="hi")])["num_retries"] == 0

  @pytest.mark.asyncio
  async def test_model_not_found_retries_once_with_main_model(self):
    prov = _provider(model="fast-m", not_found_fallback="main-m")
    calls = []

    async def fake_acompletion(**kwargs):
      calls.append(kwargs["model"])
      if kwargs["model"] == "groq/fast-m":
        raise litellm.NotFoundError("The model fast-m does not exist", "fast-m", "groq")
      return _FakeResponse(model="groq/main-m")

    with patch("app.ai.providers.implementations.litellm.acompletion", side_effect=fake_acompletion):
      res = await prov.complete([AIMessage(role="user", content="q")])
    assert calls == ["groq/fast-m", "groq/main-m"]  # the missing model is never retried itself
    assert res.text == "ok" and res.model == "main-m"

  @pytest.mark.asyncio
  async def test_stream_model_not_found_falls_back_to_main_model(self):
    prov = _provider(model="fast-m", not_found_fallback="main-m")

    async def _ok_stream():
      yield SimpleNamespace(usage=None, choices=[SimpleNamespace(
        finish_reason="stop", delta=SimpleNamespace(content="hola", tool_calls=None),
      )])

    calls = []

    async def fake_acompletion(**kwargs):
      calls.append(kwargs["model"])
      if kwargs["model"] == "groq/fast-m":
        raise litellm.NotFoundError("The model fast-m does not exist", "fast-m", "groq")
      return _ok_stream()

    with patch("app.ai.providers.implementations.litellm.acompletion", side_effect=fake_acompletion):
      out = [c async for c in prov.complete_stream([AIMessage(role="user", content="q")])]
    assert out == ["hola"]
    assert calls == ["groq/fast-m", "groq/main-m"]

  @pytest.mark.asyncio
  async def test_permanent_errors_are_not_retried(self, monkeypatch):
    monkeypatch.setenv("AI_NUM_RETRIES", "3")
    calls = []

    async def fake_acompletion(**kwargs):
      calls.append(1)
      raise litellm.AuthenticationError("invalid api key", "groq", "m1")

    with patch("app.ai.providers.implementations.litellm.acompletion", side_effect=fake_acompletion):
      with pytest.raises(AIError) as exc_info:
        await _provider().complete([AIMessage(role="user", content="q")])
    assert exc_info.value.code == "auth_error"
    assert len(calls) == 1

  @pytest.mark.asyncio
  async def test_transient_errors_are_retried(self, monkeypatch):
    monkeypatch.setenv("AI_NUM_RETRIES", "2")
    monkeypatch.setattr(implementations, "_RETRY_BACKOFF_S", 0.0)
    calls = []

    async def fake_acompletion(**kwargs):
      calls.append(1)
      if len(calls) < 3:
        raise litellm.RateLimitError("Rate limit reached", "groq", "m1")
      return _FakeResponse()

    with patch("app.ai.providers.implementations.litellm.acompletion", side_effect=fake_acompletion):
      res = await _provider().complete([AIMessage(role="user", content="q")])
    assert res.text == "ok" and len(calls) == 3


class TestErrorTyping:
  def test_not_found_is_model_not_found(self):
    err = _handle_completion_error(litellm.NotFoundError("does not exist", "x", "groq"))
    assert isinstance(err, AIError) and err.code == "model_not_found"

  def test_status_code_drives_classification(self):
    class _Upstream(Exception):
      status_code = 503

    err = _handle_completion_error(_Upstream("upstream failure"))
    assert isinstance(err, AIError) and err.code == "provider_unavailable"

  def test_message_text_alone_does_not_classify(self):
    original = RuntimeError("author field missing in timeout table 429")
    assert _handle_completion_error(original) is original


class TestStreamToolCalls:
  @pytest.mark.asyncio
  async def test_tool_call_deltas_and_finish_reason_reach_the_sink(self):
    def _tc(index, tc_id=None, name=None, args=None):
      return SimpleNamespace(index=index, id=tc_id, function=SimpleNamespace(name=name, arguments=args))

    async def _stream():
      yield SimpleNamespace(usage=None, choices=[SimpleNamespace(
        finish_reason=None,
        delta=SimpleNamespace(content="Busco", tool_calls=[_tc(0, "c1", "search_knowledge", '{"que')]),
      )])
      yield SimpleNamespace(usage=None, choices=[SimpleNamespace(
        finish_reason="tool_calls",
        delta=SimpleNamespace(content=None, tool_calls=[_tc(0, args='ry": "x"}')]),
      )])

    async def fake_acompletion(**kwargs):
      return _stream()

    sink: dict = {}
    with patch("app.ai.providers.implementations.litellm.acompletion", side_effect=fake_acompletion):
      out = [c async for c in _provider().complete_stream([AIMessage(role="user", content="q")], usage_sink=sink)]
    assert out == ["Busco"]
    assert sink["finish_reason"] == "tool_calls"
    assert [(t.id, t.name, t.arguments) for t in sink["tool_calls"]] == [("c1", "search_knowledge", {"query": "x"})]
