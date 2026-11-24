"""Provider layer: LiteLLM provider, error mapping, retries, streaming, factory and registry."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import litellm
import pytest

from app.ai import catalog
from app.ai.errors import AIError
from app.ai.providers import factory, implementations as impl
from app.ai.providers.base import AIMessage, AIProvider, ToolCall
from app.ai.providers.implementations import LiteLLMProvider
from app.ai.providers.registry import ProviderSpec, find_provider_spec, resolve_model_max_tokens


@pytest.fixture(autouse=True)
def _no_catalog(monkeypatch):
  monkeypatch.setattr(catalog, "load_local_catalog", lambda *a, **k: [])
  monkeypatch.setattr(impl, "_RETRY_BACKOFF_S", 0.0)
  factory.clear_provider_cache()
  yield
  factory.clear_provider_cache()


class StatusErr(Exception):
  def __init__(self, msg="boom", status_code=None, response=None):
    super().__init__(msg)
    if status_code is not None:
      self.status_code = status_code
    if response is not None:
      self.response = response


def _resp(text="ok", tool_calls=None, model="groq/m", usage=None, finish="stop"):
  choice = SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=tool_calls), finish_reason=finish)
  return SimpleNamespace(choices=[choice], usage=usage, model=model, model_dump=lambda: {"x": 1})


# ---------- base ----------

def test_aimessage_to_litellm_includes_tool_fields_only_when_set():
  plain = AIMessage(role="user", content="hi").to_litellm()
  assert plain == {"role": "user", "content": "hi"}
  m = AIMessage(role="assistant", content="", tool_calls=[ToolCall(id="c1", name="f", arguments={"a": "ñ"})])
  out = m.to_litellm()
  assert out["tool_calls"][0]["function"] == {"name": "f", "arguments": '{"a": "ñ"}'}
  assert AIMessage(role="tool", content="r", tool_call_id="c1").to_litellm()["tool_call_id"] == "c1"


def test_base_provider_supports_tools_default_false():
  class P(AIProvider):
    async def complete(self, messages, **kw):
      return await super().complete(messages)

    async def complete_stream(self, messages, **kw):
      return await super().complete_stream(messages)

  p = P()
  assert p.supports_tools() is False
  with pytest.raises(NotImplementedError):
    asyncio.run(p.complete([]))
  with pytest.raises(NotImplementedError):
    asyncio.run(p.complete_stream([]))


# ---------- registry ----------

def test_find_provider_spec_aliases_and_forbidden():
  assert find_provider_spec("GROQ").id == "groq"
  assert find_provider_spec("anthropic").id == "claude"
  assert find_provider_spec("local") is None
  assert find_provider_spec("") is None
  assert find_provider_spec("nope") is None




def test_resolve_model_max_tokens_catalog_and_defaults(monkeypatch):
  entry = SimpleNamespace(provider="groq", id="m1", raw_id="vendor/m1", max_output_tokens=1000)
  monkeypatch.setattr(catalog, "load_local_catalog", lambda *a, **k: [entry])
  assert resolve_model_max_tokens("groq", "m1") == 1000
  assert resolve_model_max_tokens("groq", "x/m1", requested_max=5000) == 1000
  assert resolve_model_max_tokens("groq", "m1", requested_max=0) == 1
  # unknown model -> spec default
  assert resolve_model_max_tokens("groq", "other") == 4096
  # unknown provider: requested or stream defaults
  assert resolve_model_max_tokens("zzz", "m", requested_max=77) == 77
  assert resolve_model_max_tokens("zzz", "m", is_stream=True) == 8192
  assert resolve_model_max_tokens("zzz", "m") == 4096


def test_resolve_model_max_tokens_catalog_failure_is_ignored(monkeypatch):
  def boom(*a, **k):
    raise RuntimeError("db down")
  monkeypatch.setattr(catalog, "load_local_catalog", boom)
  assert resolve_model_max_tokens("claude", "", requested_max=100) == 100


# ---------- error classification ----------

def test_status_code_extraction():
  assert impl._status_code(StatusErr(status_code="429")) == 429
  assert impl._status_code(StatusErr(response=SimpleNamespace(status_code=503))) == 503
  assert impl._status_code(StatusErr(status_code="abc")) is None
  assert impl._status_code(StatusErr()) is None


def test_is_retryable_error():
  assert impl.is_retryable_error(AIError("auth_error", "x")) is False
  assert impl.is_retryable_error(AIError("timeout", "x", original_error=TimeoutError())) is True
  assert impl.is_retryable_error(litellm.NotFoundError("nf", "m", "groq")) is False
  assert impl.is_retryable_error(litellm.RateLimitError("rl", "groq", "m")) is True
  assert impl.is_retryable_error(StatusErr(status_code=500)) is True
  assert impl.is_retryable_error(StatusErr(status_code=408)) is True
  assert impl.is_retryable_error(StatusErr(status_code=404)) is False
  assert impl.is_retryable_error(StatusErr(status_code=302)) is False
  assert impl.is_retryable_error(ConnectionError()) is True
  assert impl.is_retryable_error(ValueError()) is False




@pytest.mark.parametrize("err,code", [
  (StatusErr(status_code=413), "context_window_exceeded"),
  (StatusErr(status_code=404), "model_not_found"),
  (TimeoutError(), "timeout"),
  (StatusErr(status_code=408), "timeout"),
  (StatusErr(status_code=401), "auth_error"),
  (StatusErr(status_code=403), "auth_error"),
  (StatusErr("bad thing", status_code=400), "bad_request"),
  (StatusErr(status_code=503), "provider_unavailable"),
])
def test_handle_completion_error_codes(err, code):
  out = impl._handle_completion_error(err)
  assert isinstance(out, AIError) and out.code == code and out.original_error is err


def test_handle_completion_error_passthrough():
  e = AIError("x", "y")
  assert impl._handle_completion_error(e) is e
  plain = ValueError("nope")
  assert impl._handle_completion_error(plain) is plain


def test_handle_max_tokens_exceeded():
  out = impl._handle_completion_error(StatusErr("please reduce max_tokens: Limit 100, Requested 200", status_code=400))
  assert out.code == "max_tokens_exceeded" and "200" in out.user_message and "100" in out.user_message
  out2 = impl._handle_completion_error(StatusErr("reduce max_tokens", status_code=422))
  assert "solicitada" in out2.user_message


def test_rate_limit_variants():
  otpm = impl._handle_completion_error(StatusErr("OTPM exceeded Limit 10 Requested 20 try again in 1.5s", status_code=429))
  assert otpm.code == "rate_limit" and otpm.retry_after == 1.5 and "(20 solicitados, límite 10)" in otpm.user_message
  otpm2 = impl._handle_completion_error(StatusErr("output tokens per minute", status_code=429))
  assert "OTPM" in otpm2.user_message and otpm2.retry_after is None
  itpm = impl._handle_completion_error(StatusErr("ITPM Limit 5 Requested 9", status_code=429))
  assert "(9 tokens)" in itpm.user_message
  itpm2 = impl._handle_completion_error(StatusErr("input tokens per minute", status_code=429))
  assert "ITPM" in itpm2.user_message
  tpm = impl._handle_completion_error(StatusErr("Limit 5 Requested 9 try again in 2s", status_code=429))
  assert "TPM" in tpm.user_message and tpm.retry_after == 2.0
  rpm = impl._handle_completion_error(StatusErr("slow down", status_code=429))
  assert "unos segundos" in rpm.user_message


# ---------- retries ----------

@pytest.mark.asyncio
async def test_with_retries_retries_transient_then_succeeds():
  calls = []

  async def call():
    calls.append(1)
    if len(calls) < 3:
      raise StatusErr(status_code=503)
    return "done"

  assert await impl._with_retries(call, retries=2, label="m") == "done"
  assert len(calls) == 3




@pytest.mark.asyncio
async def test_with_retries_permanent_not_retried():
  calls = []

  async def call():
    calls.append(1)
    raise StatusErr(status_code=401)

  with pytest.raises(StatusErr):
    await impl._with_retries(call, retries=5, label="m")
  assert len(calls) == 1


# ---------- cache breakpoints & usage ----------

def test_apply_cache_breakpoints():
  assert impl.apply_cache_breakpoints([]) == 0
  msgs = [
    {"role": "system", "content": "sys"},
    {"role": "assistant", "content": [{"type": "image"}, {"type": "text", "text": "prev"}]},
    {"role": "user", "content": "now"},
  ]
  original_parts = msgs[1]["content"]
  assert impl.apply_cache_breakpoints(msgs) == 2
  assert msgs[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
  assert msgs[1]["content"][1]["cache_control"] == {"type": "ephemeral"}
  assert "cache_control" not in original_parts[1]  # caller's list not mutated


def test_mark_cacheable_edge_cases():
  assert impl._mark_cacheable({"content": "   "}) is False
  assert impl._mark_cacheable({"content": [{"type": "image"}]}) is False
  assert impl._mark_cacheable({"content": None}) is False


def test_usage_numbers():
  assert impl._usage_numbers(None) == (None, None, None)
  assert impl._usage_numbers({"prompt_tokens": 3, "completion_tokens": 4, "prompt_tokens_details": {"cached_tokens": 2}}) == (3, 4, 2)
  obj = SimpleNamespace(prompt_tokens=1, completion_tokens=2, prompt_tokens_details=None, cache_read_input_tokens=5)
  assert impl._usage_numbers(obj) == (1, 2, 5)
  assert impl._usage_numbers({"prompt_tokens": 1}) == (1, None, 0)




# ---------- tool argument helpers ----------

def test_parse_tool_arguments():
  assert impl._parse_tool_arguments({"a": 1}) == {"a": 1}
  assert impl._parse_tool_arguments("  ") == {}
  assert impl._parse_tool_arguments('{"a": 1}') == {"a": 1}
  assert impl._parse_tool_arguments("[1]") == {"value": [1]}
  assert impl._parse_tool_arguments("{bad") == {"raw": "{bad"}
  assert impl._parse_tool_arguments(None) == {}


def test_accumulate_and_finalize_tool_deltas():
  parts = {}
  impl._accumulate_tool_deltas(parts, [{"index": 0, "id": "c1", "function": {"name": "search", "arguments": '{"q":'}}])
  impl._accumulate_tool_deltas(parts, [SimpleNamespace(index=0, id=None, function=SimpleNamespace(name=None, arguments='"x"}'))])
  calls = impl._finalize_tool_calls(parts)
  assert [(c.id, c.name, c.arguments) for c in calls] == [("c1", "search", {"q": "x"})]
  # Missing index falls back to list position; dict args are serialized; nameless slots are dropped.
  p2 = {}
  impl._accumulate_tool_deltas(p2, [{"index": None}, {"function": {"name": "f", "arguments": {"k": 1}}}, {"index": 2}])
  calls2 = impl._finalize_tool_calls(p2)
  assert [(c.id, c.name, c.arguments) for c in calls2] == [("call_1", "f", {"k": 1})]


@pytest.mark.asyncio
async def test_close_stream_variants():
  await impl._close_stream(None)
  closed = []

  class Async:
    async def aclose(self):
      closed.append("a")

  await impl._close_stream(Async())

  class Sync:
    aclose = None
    completion_stream = SimpleNamespace(aclose=lambda: closed.append("s"))

  await impl._close_stream(Sync())

  class Bad:
    def aclose(self):
      raise RuntimeError("x")

  await impl._close_stream(Bad())
  assert closed == ["a", "s"]


# ---------- LiteLLMProvider basics ----------

def test_provider_init_variants():
  unknown = LiteLLMProvider("mystery", default_model="m", fallback_models=["m", "a", "a", ""], not_found_fallback="m")
  assert unknown.id == "mystery" and unknown.name == "Mystery"
  assert unknown.fallback_models == ["a"] and unknown.not_found_fallback is None
  by_name = LiteLLMProvider("google")
  assert by_name.id == "gemini" and by_name.default_model == "gemini-2.5-flash"


def test_format_model_name():
  oll = LiteLLMProvider("ollama_remote")
  assert oll._format_model_name("qwen") == "ollama_chat/qwen"
  assert oll._format_model_name("ollama/qwen") == "ollama/qwen"
  oa = LiteLLMProvider("openai")
  assert oa._format_model_name("openai/gpt-4o") == "gpt-4o"
  assert oa._format_model_name("gpt-4o") == "gpt-4o"
  gm = LiteLLMProvider("gemini")
  assert gm._format_model_name("gemini/x") == "gemini/x"
  assert gm._format_model_name("models/x") == "gemini/x"
  assert gm._format_model_name("x") == "gemini/x"
  cl = LiteLLMProvider("claude")
  assert cl._format_model_name("anthropic/c") == "anthropic/c"
  assert cl._format_model_name(" c ") == "anthropic/c"
  noprefix = LiteLLMProvider(ProviderSpec(id="raw", name="Raw", litellm_prefix="x"))
  noprefix.spec = ProviderSpec(id="raw", name="Raw", litellm_prefix="")
  assert noprefix._format_model_name("m") == "m"


def test_supports_tools(monkeypatch):
  p = LiteLLMProvider("groq", api_key="k")
  monkeypatch.setattr(impl.litellm, "supports_function_calling", lambda model: model == "groq/m")
  assert p.supports_tools("m") is True
  assert p.supports_tools("z") is False

  def boom(model):
    raise RuntimeError("unknown")
  monkeypatch.setattr(impl.litellm, "supports_function_calling", boom)
  assert p.supports_tools("m") is False
  no_tools = LiteLLMProvider(ProviderSpec(id="nt", name="NT", litellm_prefix="nt", supports_tools=False))
  assert no_tools.supports_tools("m") is False


def test_retries_env(monkeypatch):
  p = LiteLLMProvider("groq")
  monkeypatch.setenv("AI_NUM_RETRIES", "-3")
  assert p._retries() == 0
  monkeypatch.setenv("AI_NUM_RETRIES", "x")
  assert p._retries() == 2


def test_build_kwargs_claude_stream_with_cache_and_fallbacks():
  p = LiteLLMProvider("claude", api_key="k", base_url="https://b", default_model="c1", fallback_models=["c2"])
  msgs = [AIMessage(role="system", content="s"), AIMessage(role="assistant", content="a"), AIMessage(role="user", content="u")]
  kw = p._build_kwargs(msgs, stream=True, max_tokens=50)
  assert kw["model"] == "anthropic/c1" and kw["stream"] is True
  assert kw["fallbacks"] == ["anthropic/c2"]
  assert kw["temperature"] == 0.2 and kw["max_tokens"] == 50
  assert kw["api_key"] == "k" and kw["api_base"] == "https://b"
  assert kw["stream_options"] == {"include_usage": True}
  assert kw["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
  # streaming disables native fallbacks
  assert "fallbacks" not in p._build_kwargs(msgs, native_fallbacks=False)


def test_build_kwargs_gemini_no_temperature():
  g = LiteLLMProvider("gemini", api_key="k")
  assert "temperature" not in g._build_kwargs([AIMessage(role="user", content="hi")])


def test_build_kwargs_remote_ollama_goes_through_dlp():
  o = LiteLLMProvider("ollama_remote", base_url="https://o")
  assert o._is_on_premise() is False
  with patch.object(impl, "enforce_cloud_policy", side_effect=lambda msgs, name: msgs) as dlp:
    o._build_kwargs([AIMessage(role="user", content="hi")])
  dlp.assert_called_once()
  assert dlp.call_args.args[1] == "Ollama Remote"


def test_remote_ollama_blocks_confidential_content():
  o = LiteLLMProvider("ollama_remote", base_url="https://o")
  with pytest.raises(AIError) as exc:
    o._build_kwargs([AIMessage(role="user", content="Documento CONFIDENCIAL: plan de negocio")])
  assert exc.value.code == "confidential_data_blocked"


def test_remote_ollama_sanitizes_personal_data():
  o = LiteLLMProvider("ollama_remote", base_url="https://o")
  kwargs = o._build_kwargs([AIMessage(role="user", content="Escribe a luis@fcv.org")])
  assert "luis@fcv.org" not in str(kwargs["messages"])


def test_local_spec_skips_dlp():
  local = LiteLLMProvider("ollama_remote", base_url="https://o")
  local.spec = replace(local.spec, is_local=True)
  with patch.object(impl, "enforce_cloud_policy") as dlp:
    local._build_kwargs([AIMessage(role="user", content="hi")])
  dlp.assert_not_called()


# ---------- complete ----------

@pytest.mark.asyncio
async def test_complete_parses_tool_calls_usage_and_cost(monkeypatch):
  tcs = [
    SimpleNamespace(id="c1", function=SimpleNamespace(name="search", arguments='{"q": "x"}')),
    SimpleNamespace(id="c2", function=None, name="direct", arguments={"a": 1}),
  ]
  resp = _resp(text=None, tool_calls=tcs, model="groq/served", usage={"prompt_tokens": 5, "completion_tokens": 6})

  async def fake(**kw):
    return resp
  monkeypatch.setattr(impl.litellm, "acompletion", fake)
  monkeypatch.setattr(impl.litellm, "completion_cost", lambda completion_response: 0.25)
  p = LiteLLMProvider("groq", api_key="k", default_model="m")
  out = await p.complete([AIMessage(role="user", content="q")])
  assert out.text == "" and out.model == "served" and out.cost_usd == 0.25
  assert out.prompt_tokens == 5 and out.completion_tokens == 6 and out.cached_tokens == 0
  assert [(t.name, t.arguments) for t in out.tool_calls] == [("search", {"q": "x"}), ("direct", {"a": 1})]
  assert out.raw == {"x": 1} and out.finish_reason == "stop"


@pytest.mark.asyncio
async def test_complete_cost_failure_and_no_model(monkeypatch):
  resp = SimpleNamespace(choices=[], usage=None, model=None)
  resp_dict = {"choices": []}

  class R(dict):
    choices = []
    usage = None
    model = None

  async def fake(**kw):
    return R(resp_dict)
  monkeypatch.setattr(impl.litellm, "acompletion", fake)

  def boom(**kw):
    raise RuntimeError
  monkeypatch.setattr(impl.litellm, "completion_cost", boom)
  p = LiteLLMProvider("groq", api_key="k", default_model="plain")
  out = await p.complete([AIMessage(role="user", content="q")])
  assert out.text == "" and out.model == "plain" and out.cost_usd is None and out.raw == resp_dict




# ---------- streaming ----------

def _chunk(content=None, finish=None, usage=None, tool_calls=None, no_choice=False, no_delta=False):
  if no_choice:
    return SimpleNamespace(choices=[], usage=usage)
  delta = None if no_delta else SimpleNamespace(content=content, tool_calls=tool_calls)
  return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)], usage=usage)


class FakeStream:
  def __init__(self, chunks, fail_after=None):
    self.chunks = chunks
    self.fail_after = fail_after
    self.closed = False

  def __aiter__(self):
    return self._gen()

  async def _gen(self):
    for i, c in enumerate(self.chunks):
      if self.fail_after is not None and i == self.fail_after:
        raise StatusErr(status_code=503)
      yield c

  async def aclose(self):
    self.closed = True


@pytest.mark.asyncio
async def test_stream_yields_text_and_fills_usage(monkeypatch):
  stream = FakeStream([
    _chunk(no_choice=True),
    _chunk(no_delta=True),
    _chunk(content="Hola "),
    _chunk(tool_calls=[{"index": 0, "id": "t1", "function": {"name": "f", "arguments": "{}"}}]),
    _chunk(content="mundo", finish="stop"),
    _chunk(no_choice=True, usage={"prompt_tokens": 10, "completion_tokens": 2}),
  ])

  async def fake(**kw):
    assert kw["stream"] is True and "fallbacks" not in kw
    return stream
  monkeypatch.setattr(impl.litellm, "acompletion", fake)
  monkeypatch.setattr(impl.litellm, "cost_per_token", lambda **kw: (0.1, 0.2))
  p = LiteLLMProvider("groq", api_key="k", default_model="m")
  sink = {}
  out = [d async for d in p.complete_stream([AIMessage(role="user", content="q")], usage_sink=sink)]
  assert out == ["Hola ", "mundo"]
  assert sink["model"] == "m" and sink["fallback_used"] is False
  assert sink["prompt_tokens"] == 10 and sink["cost_usd"] == pytest.approx(0.3)
  assert sink["finish_reason"] == "stop" and sink["ttft_ms"] is not None
  assert [t.name for t in sink["tool_calls"]] == ["f"]
  assert stream.closed


@pytest.mark.asyncio
async def test_stream_cost_failure_gives_none(monkeypatch):
  async def fake(**kw):
    return FakeStream([_chunk(content="x", usage={"prompt_tokens": 1, "completion_tokens": 1})])
  monkeypatch.setattr(impl.litellm, "acompletion", fake)

  def boom(**kw):
    raise RuntimeError
  monkeypatch.setattr(impl.litellm, "cost_per_token", boom)
  sink = {}
  p = LiteLLMProvider("groq", api_key="k", default_model="m")
  assert [d async for d in p.complete_stream([AIMessage(role="user", content="q")], usage_sink=sink)] == ["x"]
  assert sink["cost_usd"] is None


@pytest.mark.asyncio
async def test_stream_falls_back_before_first_chunk(monkeypatch):
  monkeypatch.setenv("AI_NUM_RETRIES", "0")
  calls = []

  async def fake(**kw):
    calls.append(kw["model"])
    if kw["model"] == "groq/a":
      raise StatusErr(status_code=503)
    return FakeStream([_chunk(content="ok")])
  monkeypatch.setattr(impl.litellm, "acompletion", fake)
  p = LiteLLMProvider("groq", api_key="k", default_model="a", fallback_models=["b"])
  sink = {}
  assert [d async for d in p.complete_stream([AIMessage(role="user", content="q")], usage_sink=sink)] == ["ok"]
  assert calls == ["groq/a", "groq/b"] and sink["fallback_used"] is True and sink["prompt_tokens"] is None


@pytest.mark.asyncio
async def test_stream_not_found_uses_not_found_fallback(monkeypatch):
  calls = []

  async def fake(**kw):
    calls.append(kw["model"])
    if kw["model"] == "groq/fast":
      raise StatusErr(status_code=404)
    return FakeStream([_chunk(content="ok")])
  monkeypatch.setattr(impl.litellm, "acompletion", fake)
  p = LiteLLMProvider("groq", api_key="k", default_model="fast", not_found_fallback="main")
  assert [d async for d in p.complete_stream([AIMessage(role="user", content="q")])] == ["ok"]
  assert calls == ["groq/fast", "groq/main"]


@pytest.mark.asyncio
async def test_stream_all_fail_raises_last_error(monkeypatch):
  async def fake(**kw):
    raise StatusErr(status_code=401)
  monkeypatch.setattr(impl.litellm, "acompletion", fake)
  p = LiteLLMProvider("groq", api_key="k", default_model="a")
  with pytest.raises(AIError) as ei:
    [d async for d in p.complete_stream([AIMessage(role="user", content="q")], fallbacks=["b"])]
  assert ei.value.code == "auth_error"




# ---------- factory ----------

def _settings(**over):
  base = {
    "provider": "groq", "model": None, "groq_api_key": "gk", "fallback_models": ["f1"],
    "fast_model": None, "ollama_base_url": None,
  }
  base.update(over)
  return base


def test_normalize_fallbacks():
  assert factory._normalize_fallbacks("a, b,a,,c,d") == ["a", "b", "c"]
  assert factory._normalize_fallbacks(None) == []
  assert factory._normalize_fallbacks(["x", 3, " "]) == ["x"]


def test_get_ai_settings_from_user_and_env(monkeypatch):
  monkeypatch.setattr(factory, "load_user_ai_settings", lambda uid: {"provider": "claude", "groq_api_key": "g"})
  monkeypatch.setenv("AI_FALLBACK_MODELS", "x,y")
  s = factory.get_ai_settings("u")
  assert s["provider"] == "claude" and s["transcription_groq_api_key"] == "g" and s["fallback_models"] == ["x", "y"]
  monkeypatch.setattr(factory, "load_app_settings", lambda: {"ai": {"model": "mm"}})
  assert factory.get_ai_settings()["model"] == "mm"


def test_resolve_provider_main_tier_and_cache(monkeypatch):
  monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: _settings(model="mine"))
  p = factory.resolve_provider(user_id="u")
  assert p.default_model == "mine" and p.fallback_models == ["f1"] and p.api_key == "gk"
  assert factory.resolve_provider(user_id="u") is p
  factory.clear_provider_cache("u")
  assert factory.resolve_provider(user_id="u") is not p


def test_resolve_provider_fast_tier(monkeypatch):
  monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: _settings(model="main", fast_model="quick"))
  p = factory.resolve_provider(tier="fast")
  assert p.default_model == "quick" and p.not_found_fallback == "main" and p.fallback_models == []


def test_resolve_provider_errors(monkeypatch):
  monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: _settings(groq_api_key=""))
  monkeypatch.delenv("GROQ_API_KEY", raising=False)
  with pytest.raises(ValueError, match="no se ejecuta"):
    factory.resolve_provider("local")
  with pytest.raises(ValueError, match="GGUF"):
    factory.resolve_provider("groq", model_name="x.gguf")
  with pytest.raises(ValueError, match="No valid AI provider"):
    factory.resolve_provider("nope")
  with pytest.raises(ValueError, match="API key"):
    factory.resolve_provider("groq", model_name="m")


def test_resolve_provider_ollama(monkeypatch):
  monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: _settings(provider="ollama_remote"))
  with pytest.raises(ValueError, match="HTTPS"):
    factory.resolve_provider(model_name="q")
  monkeypatch.setattr(factory, "validate_remote_endpoint_url", lambda u: (False, "privada"))
  with pytest.raises(ValueError, match="privada"):
    factory.resolve_provider(model_name="q", base_url="https://10.0.0.1")
  monkeypatch.setattr(factory, "validate_remote_endpoint_url", lambda u: (True, None))
  p = factory.resolve_provider(model_name="q", base_url="https://ollama.example.com/")
  assert p.base_url == "https://ollama.example.com" and p.default_model == "q"
  assert factory.resolve_provider(model_name="q", base_url="https://ollama.example.com") is p
