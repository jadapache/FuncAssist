"""Edge cases of the LiteLLM provider: retries, error messages, cache breakpoints, streaming and the factory."""

import logging
from dataclasses import replace
from types import SimpleNamespace

import litellm
import pytest

from app.ai import catalog
from app.ai.errors import AIError
from app.ai.providers import factory, implementations as impl
from app.ai.providers.base import AIMessage
from app.ai.providers.implementations import LiteLLMProvider
from app.ai.providers.registry import ProviderSpec, find_provider_spec
from tests.test_ai_providers import FakeStream, StatusErr, _chunk, _resp, _settings


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
  monkeypatch.setattr(catalog, "load_local_catalog", lambda *a, **k: [])
  monkeypatch.delenv("AI_PROMPT_CACHE", raising=False)
  factory.clear_provider_cache()
  yield
  factory.clear_provider_cache()


# --- retries --------------------------------------------------------------

def test_litellm_types_keeps_only_exception_classes():
  assert impl._litellm_types("completion_cost", "Router", "NotFoundError", "no_such_name") == (litellm.NotFoundError,)


async def _failing_call(calls):
  calls.append(1)
  raise StatusErr(status_code=503)


@pytest.mark.asyncio
async def test_backoff_doubles_up_to_its_cap(monkeypatch):
  delays = []

  async def fake_sleep(delay):
    delays.append(delay)

  monkeypatch.setattr(impl.asyncio, "sleep", fake_sleep)
  calls = []
  with pytest.raises(StatusErr):
    await impl._with_retries(lambda: _failing_call(calls), retries=6, label="m")
  assert delays == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0] and len(calls) == 7


@pytest.mark.asyncio
async def test_no_sleep_when_the_backoff_is_zero_and_attempts_are_logged(monkeypatch, caplog):
  slept = []

  async def fake_sleep(delay):
    slept.append(delay)

  monkeypatch.setattr(impl.asyncio, "sleep", fake_sleep)
  monkeypatch.setattr(impl, "_RETRY_BACKOFF_S", 0.0)
  calls = []
  with caplog.at_level(logging.WARNING), pytest.raises(StatusErr):
    await impl._with_retries(lambda: _failing_call(calls), retries=2, label="m")
  assert slept == [] and len(calls) == 3
  assert [("attempt 1/2" in r.getMessage()) for r in caplog.records] == [True, False]
  assert any("attempt 2/2" in r.getMessage() for r in caplog.records)


def test_provider_unavailable_starts_at_status_500():
  assert impl._is_provider_unavailable(StatusErr(), 500) is True
  assert impl._is_provider_unavailable(StatusErr(), 499) is False
  assert impl._is_provider_unavailable(StatusErr(), None) is False


# --- error messages -------------------------------------------------------

def test_quota_numbers_need_both_values():
  assert impl._quota_numbers("Limit 100") is None
  assert impl._quota_numbers("Requested 5") is None
  assert impl._quota_numbers("Limit 100, Requested 200") == ("100", "200")


def test_rate_limit_messages_name_the_wait_and_the_quota():
  tpm = impl._handle_completion_error(StatusErr("try again in 2.5s. Limit 6000, Requested 7000", status_code=429))
  assert tpm.retry_after == 2.5
  assert tpm.user_message == "Límite de tasa de tokens por minuto (TPM) alcanzado (7000 solicitados, límite 6000). Espera 2.5s."
  plain = impl._handle_completion_error(StatusErr("slow down", status_code=429))
  assert plain.retry_after is None and "espera unos segundos" in plain.user_message
  otpm = impl._handle_completion_error(StatusErr("OTPM try again in 3s", status_code=429))
  assert otpm.user_message.startswith("Límite de tokens de salida") and "Espera 3s" in otpm.user_message


# --- cache breakpoints ----------------------------------------------------

def test_only_the_last_valid_text_part_gets_the_cache_marker():
  original = [
    {"type": "text", "text": "a"}, {"type": "image_url", "text": "ignored"}, {"type": "text", "text": ""}, "raw",
  ]
  message = {"role": "user", "content": original}
  assert impl._mark_cacheable(message) is True
  parts = message["content"]
  assert parts[0]["cache_control"] == {"type": "ephemeral"}
  assert all("cache_control" not in p for p in parts[1:3])
  assert "cache_control" not in original[0]


def test_breakpoint_targets():
  def role(r):
    return {"role": r, "content": "x"}

  assert impl._breakpoint_targets([role("system"), role("system"), role("user")]) == [1]
  assert impl._breakpoint_targets([role("system"), role("user"), role("assistant"), role("user")]) == [0, 2]
  assert impl._breakpoint_targets([role("user"), role("system"), role("user")]) == [1]
  assert impl._breakpoint_targets([role("user"), role("tool"), role("user")]) == []
  assert impl._breakpoint_targets([]) == []


# --- tool-call deltas and stream closing ----------------------------------

def test_empty_ids_and_names_do_not_overwrite_earlier_fragments():
  parts = {}
  impl._accumulate_tool_deltas(parts, [{"index": 0, "id": "c1", "function": {"name": "fn", "arguments": "{"}}])
  impl._accumulate_tool_deltas(parts, [{"index": 0, "id": "", "function": {"name": "", "arguments": "}"}}])
  impl._accumulate_tool_deltas(parts, [{"index": 0, "id": 5, "function": {"name": 7}}])
  assert parts[0] == {"id": "c1", "name": "fn", "arguments": "{}"}


def test_dict_arguments_keep_non_ascii_text():
  parts = {}
  impl._accumulate_tool_deltas(parts, [{"index": 0, "function": {"name": "f", "arguments": {"q": "ñandú"}}}])
  assert parts[0]["arguments"] == '{"q": "ñandú"}'


@pytest.mark.asyncio
async def test_non_callable_closer_is_skipped_and_the_inner_stream_is_closed():
  closed = []

  class Inner:
    async def aclose(self):
      closed.append("inner")

  response = SimpleNamespace(aclose="not callable", completion_stream=Inner())
  await impl._close_stream(response)
  assert closed == ["inner"]


# --- streaming attempt ----------------------------------------------------

def test_stream_cost_passes_zero_for_missing_completion_tokens(monkeypatch):
  seen = []
  monkeypatch.setattr(impl.litellm, "cost_per_token", lambda **kw: seen.append(kw) or (1.0, 2.0))
  assert impl._stream_cost("m", 5, 7) == 3.0
  assert impl._stream_cost("m", 5, None) == 3.0
  assert impl._stream_cost("m", 0, 5) == 3.0
  assert impl._stream_cost("m", None, 5) is None
  assert [(k["prompt_tokens"], k["completion_tokens"]) for k in seen] == [(5, 7), (5, 0), (0, 5)]


def test_stream_attempt_tracks_text_tool_calls_and_timing(monkeypatch):
  attempt = impl._StreamAttempt(t0=100.0)
  monkeypatch.setattr(impl, "time", SimpleNamespace(perf_counter=lambda: 100.5))
  assert attempt.consume(_chunk("")) is None and attempt.started is False
  assert attempt.consume(_chunk(None)) is None and attempt.started is False
  assert attempt.consume(_chunk("hola")) == "hola"
  assert attempt.started is True and attempt.ttft_ms == 500.0
  monkeypatch.setattr(impl, "time", SimpleNamespace(perf_counter=lambda: 102.0))
  assert attempt.consume(_chunk("otra")) == "otra" and attempt.ttft_ms == 500.0
  assert attempt.usage_record("wire", "model", "model")["duration_ms"] == 2000.0


def test_stream_attempt_ignores_non_string_and_empty_finish_reasons():
  attempt = impl._StreamAttempt()
  attempt.consume(_chunk(finish="stop"))
  attempt.consume(_chunk(finish=5))
  attempt.consume(_chunk(finish=""))
  assert attempt.finish_reason == "stop"


def test_tool_call_deltas_mark_the_attempt_as_started():
  attempt = impl._StreamAttempt()
  delta = [SimpleNamespace(index=0, id="c", function=SimpleNamespace(name="f", arguments="{}"))]
  assert attempt.consume(_chunk(tool_calls=delta)) is None
  assert attempt.started is True and attempt.tool_parts[0]["name"] == "f"


# --- kwargs ---------------------------------------------------------------

def test_default_temperature_rules():
  assert impl._wants_default_temperature("openai", "gpt", {}, {}) is True
  assert impl._wants_default_temperature("gemini", "other", {}, {}) is False
  assert impl._wants_default_temperature("openai", "gemini/x", {}, {}) is False
  assert impl._wants_default_temperature("openai", "gpt", {"temperature": 1}, {}) is False
  assert impl._wants_default_temperature("openai", "gpt", {}, {"temperature": 1}) is False


def test_model_names_for_openai_style_specs():
  assert LiteLLMProvider("openai")._format_model_name("openai/gpt-x") == "gpt-x"
  custom = LiteLLMProvider(ProviderSpec(id="custom", name="Custom", litellm_prefix=""))
  assert custom._format_model_name("openai/gpt-x") == "gpt-x"
  assert custom._format_model_name("plain") == "plain"


def test_kwargs_defaults_do_not_stream_and_keep_fallbacks():
  provider = LiteLLMProvider("claude", api_key="k", default_model="c1", fallback_models=["c2"])
  kwargs = provider._build_kwargs([AIMessage(role="user", content="u")])
  assert "stream" not in kwargs and "stream_options" not in kwargs
  assert kwargs["num_retries"] == 0 and kwargs["fallbacks"] == ["anthropic/c2"]


def _first_content(provider, **kwargs):
  messages = [AIMessage(role="system", content="s"), AIMessage(role="user", content="u")]
  return provider._build_kwargs(messages, **kwargs)["messages"][0]["content"]


def test_explicit_cache_breakpoints_only_for_providers_that_need_and_support_them(monkeypatch):
  claude = find_provider_spec("claude")
  assert isinstance(_first_content(LiteLLMProvider(claude, api_key="k"), ), list)
  assert isinstance(_first_content(LiteLLMProvider(replace(claude, supports_prompt_cache=False), api_key="k")), str)
  assert isinstance(_first_content(LiteLLMProvider("openai", api_key="k")), str)
  monkeypatch.setenv("AI_PROMPT_CACHE", "off")
  assert isinstance(_first_content(LiteLLMProvider(claude, api_key="k")), str)


def test_stream_usage_is_requested_only_when_streaming_with_a_supporting_provider():
  messages = [AIMessage(role="user", content="u")]
  assert LiteLLMProvider("openai", api_key="k")._build_kwargs(messages, stream=True)["stream_options"] == {"include_usage": True}
  assert "stream_options" not in LiteLLMProvider("openai", api_key="k")._build_kwargs(messages)
  assert "stream_options" not in LiteLLMProvider("zzz", api_key="k")._build_kwargs(messages, stream=True)
  custom = LiteLLMProvider("openai", api_key="k")._build_kwargs(messages, stream=True, stream_options={"x": 1})
  assert custom["stream_options"] == {"x": 1}


# --- completion flow ------------------------------------------------------

@pytest.mark.asyncio
async def test_model_not_found_retries_with_the_fallback_only_when_it_applies(monkeypatch):
  calls = []

  def provider_with(fallback, code="model_not_found"):
    provider = LiteLLMProvider("groq", api_key="k", default_model="a", not_found_fallback=fallback)

    async def fake_once(messages, chosen_raw, max_tokens, fallbacks, extra):
      calls.append(chosen_raw)
      if chosen_raw == "a":
        raise AIError(code, "x")
      return "ok"

    monkeypatch.setattr(provider, "_complete_once", fake_once)
    return provider

  assert await provider_with("b").complete([]) == "ok" and calls == ["a", "b"]
  for provider, kwargs in ((provider_with("b"), {"model": "a"}), (provider_with(None), {}), (provider_with("b", "auth_error"), {})):
    calls.clear()
    with pytest.raises(AIError):
      await provider.complete([], **kwargs)
    assert calls == ["a"]


def test_missing_model_fallback_is_queued_only_for_a_missing_model_the_caller_did_not_choose():
  provider = LiteLLMProvider("groq", api_key="k", default_model="a", not_found_fallback="b")
  missing, other = AIError("model_not_found", "x"), AIError("timeout", "x")

  def queued(error, requested=None, tried=("a",)):
    models = list(tried)
    provider._queue_not_found_fallback(models, 1, error, requested)
    return models

  assert queued(missing) == ["a", "b"]
  assert queued(other) == ["a"]
  assert queued(missing, requested="a") == ["a"]
  assert queued(missing, tried=("a", "b")) == ["a", "b"]
  provider.not_found_fallback = None
  assert queued(missing) == ["a"]


@pytest.mark.asyncio
async def test_completion_reports_its_duration_in_milliseconds(monkeypatch):
  async def fake_acompletion(**kwargs):
    return _resp()

  ticks = iter([1.0, 1.5])
  monkeypatch.setattr(impl.litellm, "acompletion", fake_acompletion)
  monkeypatch.setattr(impl, "_completion_cost", lambda response: None)
  monkeypatch.setattr(impl, "time", SimpleNamespace(perf_counter=lambda: next(ticks)))
  completion = await LiteLLMProvider("groq", api_key="k").complete([AIMessage(role="user", content="hi")])
  assert completion.duration_ms == 500.0


# --- factory --------------------------------------------------------------

def test_transcription_keys_prefer_their_own_value():
  assert factory._api_keys({"transcription_openai_api_key": "t", "openai_api_key": "g"})["transcription_openai_api_key"] == "t"
  assert factory._api_keys({"openai_api_key": "g"})["transcription_openai_api_key"] == "g"
  assert factory._api_keys({"transcription_groq_api_key": "t", "groq_api_key": "g"})["transcription_groq_api_key"] == "t"


def test_stored_settings_win_over_environment(monkeypatch):
  monkeypatch.setattr(factory, "load_user_ai_settings", lambda uid: {"provider": "stored"})
  monkeypatch.setenv("AI_PROVIDER", "env")
  monkeypatch.setenv("AI_MODEL", "env-model")
  monkeypatch.delenv("AI_FAST_MODEL", raising=False)
  settings = factory.get_ai_settings("u")
  assert (settings["provider"], settings["model"], settings["fast_model"]) == ("stored", "env-model", None)


@pytest.mark.parametrize("spec_id,aliases,expected", [
  ("ollama_remote", (), True), ("x", ("ollama",), True), ("x", (), False),
])
def test_ollama_detection(spec_id, aliases, expected):
  assert factory._is_ollama(SimpleNamespace(id=spec_id, aliases=aliases)) is expected


def test_main_model_precedence(monkeypatch):
  monkeypatch.setattr(factory, "pick_model", lambda provider, tier, default: "picked")
  spec = SimpleNamespace(id="x", default_model="default", fast_model="fast")
  choose = lambda **kw: factory._choose_model(spec, {}, "main", None, kw.get("main"), kw.get("user", ""), True)[0]
  assert choose(main="main", user="user") == "main"
  assert choose(user="user") == "user"
  assert choose() == "picked"
  monkeypatch.setattr(factory, "pick_model", lambda provider, tier, default: None)
  assert choose() == "default"


def test_api_key_comes_from_the_request_then_settings_then_environment(monkeypatch):
  monkeypatch.setenv("GROQ_API_KEY", "from-env")
  monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: _settings(groq_api_key="from-settings"))
  assert factory.resolve_provider("groq", model_name="m", api_key="from-request").api_key == "from-request"
  assert factory.resolve_provider("groq", model_name="m").api_key == "from-settings"
  # No built-in provider declares an environment variable of its own, so a custom spec stands in.
  spec = ProviderSpec(id="envp", name="Env Provider", litellm_prefix="envp", env_key="ENVP_KEY", config_key="envp_key")
  monkeypatch.setattr(factory, "find_provider_spec", lambda name: spec)
  monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: _settings(provider="envp"))
  monkeypatch.setenv("ENVP_KEY", "envp-from-env")
  assert factory.resolve_provider("envp", model_name="m2").api_key == "envp-from-env"
  monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: _settings(provider="envp", envp_key="envp-stored"))
  assert factory.resolve_provider("envp", model_name="m3").api_key == "envp-stored"
  monkeypatch.delenv("ENVP_KEY")
  monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: _settings(provider="envp"))
  with pytest.raises(ValueError, match=r"\(ENVP_KEY\) is missing"):
    factory.resolve_provider("envp", model_name="m4")


def test_user_settings_apply_only_to_the_configured_provider(monkeypatch):
  monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: _settings(model="groq-model", openai_api_key="k"))
  assert factory.resolve_provider("groq").default_model == "groq-model"
  other = factory.resolve_provider("openai", api_key="k")
  assert other.default_model != "groq-model" and other.fallback_models != ["f1"]


@pytest.mark.asyncio
async def test_streaming_leaves_fallbacks_to_the_provider_itself(monkeypatch):
  seen = []

  async def fake_acompletion(**kwargs):
    seen.append(kwargs)
    return FakeStream([_chunk("hi")])

  monkeypatch.setattr(impl.litellm, "acompletion", fake_acompletion)
  provider = LiteLLMProvider("groq", api_key="k", default_model="a", fallback_models=["b"])
  assert [t async for t in provider.complete_stream([AIMessage(role="user", content="u")])] == ["hi"]
  assert "fallbacks" not in seen[0] and seen[0]["stream"] is True
