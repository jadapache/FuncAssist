"""Small AI helpers: budget, DLP, endpoint security, errors, policies, intent classifier, summary store."""

import asyncio
import socket
from types import SimpleNamespace

import pytest

from app.ai import budget, endpoint_security, history_store, intent_classifier
from app.ai.dlp import enforce_cloud_policy, is_confidential, sanitize_text
from app.ai.errors import AIError
from app.ai.policies import resolve_feature_max_tokens, resolve_intent_max_tokens, resolve_max_continuations


# --- budget ---------------------------------------------------------------

def test_count_tokens_falls_back_to_chars(monkeypatch):
  def boom(**kw):
    raise RuntimeError("no tokenizer")
  monkeypatch.setattr(budget, "token_counter", boom)
  assert budget.count_tokens("m", "a" * 40) == 10
  assert budget.count_tokens("m", [{"content": "a" * 8}, {"content": "b" * 8}]) == 4
  assert budget.count_tokens("m", "") == 1


def test_count_tokens_uses_tokenizer(monkeypatch):
  monkeypatch.setattr(budget, "token_counter", lambda **kw: 7 if "text" in kw else 9)
  assert budget.count_tokens("m", "hola") == 7
  assert budget.count_tokens("m", [{"role": "user", "content": "x"}]) == 9


def test_chars_per_token(monkeypatch):
  assert budget.chars_per_token("m", "") == budget.DEFAULT_CHARS_PER_TOKEN
  monkeypatch.setattr(budget, "count_tokens", lambda m, s: 5)
  assert budget.chars_per_token("m", "x" * 20) == 4.0
  monkeypatch.setattr(budget, "count_tokens", lambda m, s: 100)
  assert budget.chars_per_token("m", "xx") == 1.0


def test_model_info_tries_prefixed_name(monkeypatch):
  seen = []

  def info(name):
    seen.append(name)
    if name == "groq/llama":
      return {"max_input_tokens": 1234}
    raise ValueError("unknown")

  monkeypatch.setattr(budget.litellm, "get_model_info", info)
  assert budget._model_info("groq", "llama") == {"max_input_tokens": 1234}
  assert seen == ["llama", "groq/llama"]
  seen.clear()
  assert budget._model_info("nonexistent-provider", "x") is None
  assert seen == ["x"]


def test_context_window_sources(monkeypatch):
  cat = [SimpleNamespace(id="cat-model", raw_id="Raw-M", context_length=50_000),
         SimpleNamespace(id="nolen", raw_id="", context_length=None)]
  monkeypatch.setattr(budget, "load_local_catalog", lambda: cat)
  monkeypatch.setattr(budget, "_model_info", lambda p, m: None)
  assert budget.context_window("openai", "CAT-MODEL") == 50_000
  assert budget.context_window("openai", "raw-m") == 50_000
  assert budget.context_window("openai", "nolen") == 128_000
  assert budget.context_window("weird", "nolen") == 16_384
  monkeypatch.setattr(budget, "_model_info", lambda p, m: {"max_input_tokens": None, "max_tokens": 777})
  assert budget.context_window("openai", "other") == 777

  def bad():
    raise RuntimeError("catalog broken")

  monkeypatch.setattr(budget, "load_local_catalog", bad)
  assert budget.context_window("openai", "other") == 777


def test_max_output_sources(monkeypatch):
  monkeypatch.setattr(budget, "_model_info", lambda p, m: {"max_output_tokens": 321})
  assert budget.max_output("openai", "m") == 321
  monkeypatch.setattr(budget, "_model_info", lambda p, m: None)
  monkeypatch.setattr(budget, "find_provider_spec", lambda p: SimpleNamespace(default_max_tokens=999))
  assert budget.max_output("x", "m") == 999
  monkeypatch.setattr(budget, "find_provider_spec", lambda p: None)
  assert budget.max_output("groq", "m") == 4096
  assert budget.max_output("zzz", "m") == 8192


def test_calculate_input_budget(monkeypatch):
  monkeypatch.setattr(budget, "context_window", lambda p, m: 100_000)
  monkeypatch.setattr(budget, "max_output", lambda p, m: 10_000)
  assert budget.calculate_input_budget("openai", "m") == 100_000 - 10_000 - 1_000
  assert budget.calculate_input_budget("openai", "m", reserved_output=90_000) == 50_000 - 1_000
  assert budget.calculate_input_budget("groq", "m", reserved_output=1) == 6_000 - 1_000
  monkeypatch.setattr(budget, "context_window", lambda p, m: 1_000)
  assert budget.calculate_input_budget("openai", "m") == 1_500


# --- DLP ------------------------------------------------------------------

def test_dlp_sanitizes_and_blocks():
  assert is_confidential("Documento CONFIDENCIAL") and not is_confidential(None)
  out = sanitize_text("mail a@b.com pwd: hunter2 key sk-abcdefghijklmnopqrstu cel 3001234567")
  assert "[EMAIL]" in out and "[SECRETO]" in out and "[TELEFONO]" in out and "hunter2" not in out
  msgs = [
    {"role": "system", "content": "confidencial template is fine"},
    {"role": "user", "content": [{"type": "text", "text": "a@b.com"}, {"type": "image_url"}]},
    {"role": "assistant", "content": None},
  ]
  res = enforce_cloud_policy(msgs, "OpenAI")
  assert res[1]["content"][0]["text"] == "[EMAIL]" and res[1]["content"][1] == {"type": "image_url"}
  assert res[2]["content"] is None
  with pytest.raises(AIError) as ei:
    enforce_cloud_policy([{"role": "user", "content": [{"type": "text", "text": "historia clínica"}]}], "Groq")
  assert ei.value.code == "confidential_data_blocked" and "Groq" in ei.value.user_message


# --- endpoint security ----------------------------------------------------

def test_private_host_detection(monkeypatch):
  assert endpoint_security.is_loopback_or_private_host("localhost")
  assert endpoint_security.is_loopback_or_private_host("svc.internal")
  assert endpoint_security.is_loopback_or_private_host("[::1]")
  assert endpoint_security.is_loopback_or_private_host("10.0.0.1")
  assert not endpoint_security.is_loopback_or_private_host("8.8.8.8")
  monkeypatch.setattr(socket, "getaddrinfo", lambda h, p: [(0, 0, 0, "", ("192.168.1.5", 0))])
  assert endpoint_security.is_loopback_or_private_host("evil.example")

  def fail(h, p):
    raise socket.gaierror("nope")

  monkeypatch.setattr(socket, "getaddrinfo", fail)
  assert not endpoint_security.is_loopback_or_private_host("unknown.example")


def test_validate_remote_endpoint_url(monkeypatch):
  monkeypatch.setattr(socket, "getaddrinfo", lambda h, p: [(0, 0, 0, "", ("93.184.216.34", 0))])
  v = endpoint_security.validate_remote_endpoint_url
  assert v("") == (False, "La URL del endpoint remoto es obligatoria.")
  assert v("http://example.com")[0] is False
  assert v("http://example.com", allow_http=True) == (True, None)
  assert v("https://example.com/v1") == (True, None)
  assert v("https://127.0.0.1")[0] is False
  assert v("https://")[0] is False
  assert v("https://[bad")[1] == "Formato de URL inválido."


# --- errors / policies ----------------------------------------------------

def test_ai_error_to_dict():
  orig = ValueError("x")
  err = AIError("rate_limited", "Espera", retry_after=2.5, original_error=orig)
  assert str(err) == "Espera" and err.original_error is orig
  assert err.to_dict() == {"code": "rate_limited", "message": "Espera", "retry_after": 2.5}


def test_policies():
  assert resolve_intent_max_tokens(None, 10) == 10
  assert resolve_intent_max_tokens(" Summary ") == 500
  assert resolve_intent_max_tokens("unknown", 11) == 11
  assert resolve_feature_max_tokens("reduce") == 1500
  assert resolve_feature_max_tokens(None) == 8192
  assert resolve_max_continuations("CHAT") == 1
  assert resolve_max_continuations(None) == 2


# --- intent classifier ----------------------------------------------------

class _Prov:
  default_model = "fast"

  def __init__(self, reply=None, exc=None, delay=0):
    self.reply, self.exc, self.delay, self.calls = reply, exc, delay, []

  async def complete(self, messages, **kw):
    self.calls.append((messages, kw))
    if self.delay:
      await asyncio.sleep(self.delay)
    if self.exc:
      raise self.exc
    return SimpleNamespace(text=self.reply)


def test_classifier_env(monkeypatch):
  monkeypatch.setenv("AI_LLM_INTENT_CLASSIFIER", "off")
  assert not intent_classifier.classifier_enabled()
  monkeypatch.setenv("AI_LLM_INTENT_CLASSIFIER", "on")
  assert intent_classifier.classifier_enabled()
  monkeypatch.setenv("AI_INTENT_CLASSIFIER_TIMEOUT_S", "0.1")
  assert intent_classifier._timeout_s() == 0.5
  monkeypatch.setenv("AI_INTENT_CLASSIFIER_TIMEOUT_S", "abc")
  assert intent_classifier._timeout_s() == 4.0


def test_parse_label():
  p = intent_classifier.parse_label
  assert p("informe", active_intent=None, has_template=False) == "generic_report"
  assert p("SEGUIMIENTO", active_intent="generic_plan", has_template=False) == "generic_plan"
  assert p("SEGUIMIENTO", active_intent=None, has_template=False) is None
  assert p("PLANTILLA", active_intent=None, has_template=False) is None
  assert p("PLANTILLA", active_intent=None, has_template=True) == "template_mutation"
  assert p("???", active_intent=None, has_template=False) is None


def test_system_prompt_options():
  s = intent_classifier._system_prompt("generic_plan", True)
  assert "PLANTILLA" in s and "SEGUIMIENTO" in s
  s = intent_classifier._system_prompt(None, False)
  assert "PLANTILLA" not in s and "SEGUIMIENTO" not in s


@pytest.mark.asyncio
async def test_classify_caches_and_handles_failures(monkeypatch):
  intent_classifier.clear_cache()
  prov = _Prov(reply="PLAN")
  first = await intent_classifier.classify_intent_with_model("haz un plan", provider=prov)
  second = await intent_classifier.classify_intent_with_model("  HAZ UN PLAN ", provider=prov)
  assert first.intent == "generic_plan" and not first.cached
  assert second.cached and len(prov.calls) == 1
  assert prov.calls[0][1]["max_tokens"] == 800

  assert await intent_classifier.classify_intent_with_model("x", provider=_Prov(reply="nada")) is None
  assert await intent_classifier.classify_intent_with_model("y", provider=_Prov(exc=RuntimeError("down"))) is None
  monkeypatch.setattr(intent_classifier, "_timeout_s", lambda: 0.01)
  assert await intent_classifier.classify_intent_with_model("z", provider=_Prov(reply="CHAT", delay=1)) is None

  monkeypatch.setattr(intent_classifier, "_CACHE_MAX", 2)
  intent_classifier.clear_cache()
  for q in ("a", "b", "c"):
    await intent_classifier.classify_intent_with_model(q, provider=_Prov(reply="CHAT"))
  assert len(intent_classifier._cache) == 2
  intent_classifier.clear_cache()


# --- summary store --------------------------------------------------------

class _FakeUow:
  saved: list = []
  committed = 0
  result = True

  async def __aenter__(self):
    class Chat:
      async def get_history_summary(self, sid, user_id=None):
        return ("k", f"{sid}:{user_id}")

      async def save_history_summary(self, sid, key, summary, user_id=None):
        _FakeUow.saved.append((sid, key, summary, user_id))
        return _FakeUow.result

    self.chat = Chat()
    return self

  async def __aexit__(self, *a):
    return False

  async def commit(self):
    _FakeUow.committed += 1


@pytest.mark.asyncio
async def test_summary_store(monkeypatch):
  monkeypatch.setattr(history_store, "AsyncUnitOfWork", _FakeUow)
  _FakeUow.saved, _FakeUow.committed, _FakeUow.result = [], 0, True
  store = history_store.ChatSessionSummaryStore("s1", user_id="u1")
  assert await store.load() == ("k", "s1:u1")
  await store.save("2:abc", "sum")
  assert _FakeUow.saved == [("s1", "2:abc", "sum", "u1")] and _FakeUow.committed == 1
  _FakeUow.result = False
  await store.save("3:abc", "sum")
  assert _FakeUow.committed == 1
