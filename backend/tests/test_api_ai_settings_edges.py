"""Edge cases of the AI settings endpoints: catalog validation, limits and refresh defaults."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routers import ai_settings as router
from app.api.routers.ai_settings import AISettingsUpdate


def _spec():
  return SimpleNamespace(name="Spec", id="spec")


def _data_and_current(**kwargs):
  return dict(kwargs.get("data", {})), dict(kwargs.get("current", {}))


# --- fast model -----------------------------------------------------------

@pytest.mark.parametrize("changed,current_fast,available,expected", [
  (True, "gone", {"ok"}, ""),
  (True, "ok", {"ok"}, None),
  (False, "gone", {"ok"}, None),
  (True, None, {"ok"}, None),
])
def test_stored_fast_model_is_cleared_only_when_the_provider_changed_and_lacks_it(changed, current_fast, available, expected):
  data = {}
  router._check_fast_model(data, {"fast_model": current_fast}, available, _spec(), changed)
  assert data.get("fast_model") == expected


def test_sent_fast_model_must_exist_in_the_catalog():
  router._check_fast_model({"fast_model": "ok"}, {}, {"ok"}, _spec(), False)
  with pytest.raises(HTTPException) as err:
    router._check_fast_model({"fast_model": "nope"}, {}, {"ok"}, _spec(), False)
  assert err.value.status_code == 400 and "Spec" in err.value.detail


def test_stored_fallbacks_are_filtered_when_the_provider_changed():
  data = {}
  router._check_fallback_models(data, {"fallback_models": ["a", "gone"]}, {"a"}, _spec(), True)
  assert data["fallback_models"] == ["a"]
  untouched = {}
  router._check_fallback_models(untouched, {"fallback_models": ["a", "gone"]}, {"a"}, _spec(), False)
  assert untouched == {}


def test_provider_change_is_detected_against_the_stored_provider(monkeypatch):
  monkeypatch.setattr(router, "catalog_chat_models", lambda provider: ["gpt-1"])
  # Same provider as stored: the stored fast model is kept even though it is not in the catalog.
  same = {"provider": "openai"}
  router._validate_tier_models_against_catalog(same, {"provider": "openai", "fast_model": "old"})
  assert "fast_model" not in same
  # Different provider: cleared.
  changed = {"provider": "openai"}
  router._validate_tier_models_against_catalog(changed, {"provider": "groq", "fast_model": "old"})
  assert changed["fast_model"] == ""
  # No provider in the payload: nothing is cleared.
  none_sent = {}
  router._validate_tier_models_against_catalog(none_sent, {"provider": "openai", "fast_model": "old"})
  assert none_sent == {}


# --- limits ---------------------------------------------------------------

def test_fallback_limit_is_three_models():
  data = {"fallback_models": ["a", "b", "c"]}
  router._normalize_fallback_models(data)
  assert data["fallback_models"] == ["a", "b", "c"]
  with pytest.raises(HTTPException) as err:
    router._normalize_fallback_models({"fallback_models": ["a", "b", "c", "d"]})
  assert err.value.status_code == 400


def test_filler_limit_is_forty_characters():
  data = {"transcription_fillers": ["x" * 40, " Eh "]}
  router._normalize_transcription_settings(data)
  assert data["transcription_fillers"] == ["x" * 40, "eh"]
  with pytest.raises(HTTPException):
    router._normalize_transcription_settings({"transcription_fillers": ["x" * 41]})


# --- active key -----------------------------------------------------------

def test_active_key_for_a_spec_with_only_an_environment_variable(monkeypatch):
  spec = SimpleNamespace(id="x", aliases=(), config_key=None, env_key="X_API_KEY")
  monkeypatch.setattr(router, "find_provider_spec", lambda name: spec)
  monkeypatch.delenv("X_API_KEY", raising=False)
  assert router._active_key_set({"provider": "x"}) is False
  monkeypatch.setenv("X_API_KEY", "v")
  assert router._active_key_set({"provider": "x"}) is True
  spec.env_key = None
  assert router._active_key_set({"provider": "x"}) is False


# --- refresh defaults -----------------------------------------------------

@pytest.mark.asyncio
async def test_catalog_endpoint_refreshes_only_when_asked(monkeypatch):
  syncs, loads = [], []

  async def fake_sync(force_remote):
    syncs.append(force_remote)
    return {"status": "ok"}

  async def fake_catalog(refresh=False, provider="all", task_type="all"):
    loads.append(refresh)
    return SimpleNamespace(model_dump=lambda: {})

  monkeypatch.setattr(router, "sync_frontier_models_catalog", fake_sync)
  monkeypatch.setattr(router, "get_model_catalog", fake_catalog)
  await router.ai_models_catalog()
  assert syncs == [] and loads == [False]
  await router.ai_models_catalog(refresh=True)
  assert syncs == [True] and loads == [False, True]


@pytest.mark.asyncio
async def test_sync_endpoint_forces_a_remote_refresh_by_default(monkeypatch):
  syncs, loads = [], []

  async def fake_sync(force_remote):
    syncs.append(force_remote)
    return {"status": "ok"}

  async def fake_catalog(refresh=False, provider="all", task_type="all"):
    loads.append(refresh)
    return SimpleNamespace(model_dump=lambda: {"models": []})

  monkeypatch.setattr(router, "sync_frontier_models_catalog", fake_sync)
  monkeypatch.setattr(router, "get_model_catalog", fake_catalog)
  result = await router.sync_ai_models_catalog(current_user={"id": "u"})
  assert syncs == [True] and loads == [True] and result == {"sync": {"status": "ok"}, "catalog": {"models": []}}


# --- full endpoints -------------------------------------------------------


@pytest.fixture
def settings_env(monkeypatch):
  state = SimpleNamespace(stored={}, saved=[], cleared=[], catalog=["gpt-1"], endpoint=(True, None), has_model=True)
  monkeypatch.setattr(router, "get_ai_settings", lambda user_id=None: state.stored)
  monkeypatch.setattr(router, "save_user_ai_settings", lambda uid, data: state.saved.append((uid, dict(data))))
  monkeypatch.setattr(router, "clear_provider_cache", lambda uid: state.cleared.append(uid))
  monkeypatch.setattr(router, "catalog_chat_models", lambda provider: state.catalog)
  monkeypatch.setattr(router, "validate_remote_endpoint_url", lambda url: state.endpoint)
  monkeypatch.setattr(router, "has_catalog_model", lambda model, provider, task: state.has_model)
  for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY"):
    monkeypatch.delenv(name, raising=False)
  return state


async def _put(**fields):
  return await router.update_ai_settings(body=AISettingsUpdate(**fields), current_user={"id": "u"})


@pytest.mark.asyncio
async def test_only_the_fields_that_were_sent_are_saved(settings_env):
  await _put(model="gpt-1")
  assert settings_env.saved == [("u", {"model": "gpt-1"})] and settings_env.cleared == ["u"]


@pytest.mark.asyncio
async def test_gguf_models_are_rejected_but_missing_ones_are_fine(settings_env):
  await _put()
  for field, value in (("model", "x.GGUF"), ("fast_model", "y.gguf")):
    with pytest.raises(HTTPException) as err:
      await _put(**{field: value})
    assert err.value.status_code == 400
  with pytest.raises(HTTPException):
    await _put(fallback_models=["a.gguf"])


@pytest.mark.asyncio
async def test_remote_ollama_endpoint_is_validated_only_for_ollama_providers(settings_env):
  settings_env.endpoint = (False, "URL no permitida")
  await _put()
  await _put(provider="groq", ollama_base_url="http://10.0.0.1")
  await _put(provider="ollama_remote")
  with pytest.raises(HTTPException) as err:
    await _put(provider="ollama_remote", ollama_base_url="http://10.0.0.1")
  assert err.value.detail == "URL no permitida"
  settings_env.endpoint = (True, None)
  await _put(provider="ollama", ollama_base_url="https://ollama.example.com")


@pytest.mark.asyncio
async def test_browser_models_must_exist_in_the_catalog(settings_env):
  settings_env.has_model = False
  await _put()
  await _put(provider="openai", model="gpt-1")
  await _put(provider="webllm")
  await _put(model="gpt-1")
  await _put(transcription_model="x")
  with pytest.raises(HTTPException) as err:
    await _put(provider="webllm", model="missing")
  assert "WebLLM" in err.value.detail
  with pytest.raises(HTTPException) as err:
    await _put(transcription_provider="browser_asr", transcription_model="missing")
  assert "ASR" in err.value.detail
  settings_env.has_model = True
  await _put(provider="webllm", model="present")


@pytest.mark.asyncio
async def test_catalog_validation_uses_the_stored_provider_when_none_is_sent(settings_env):
  settings_env.stored = {"provider": "openai"}
  with pytest.raises(HTTPException):
    await _put(fast_model="not-in-catalog")
  await _put(fast_model="gpt-1")


def test_provider_for_validation_prefers_the_payload(monkeypatch):
  seen = []
  monkeypatch.setattr(router, "catalog_chat_models", lambda provider: seen.append(provider) or ["m"])
  router._validate_tier_models_against_catalog({"provider": "groq", "fast_model": "m"}, {"provider": "openai"})
  router._validate_tier_models_against_catalog({"fast_model": "m"}, {"provider": "openai"})
  assert seen == ["groq", "openai"]
  router._validate_tier_models_against_catalog({"fast_model": "m"}, {})
  assert seen == ["groq", "openai"]


@pytest.mark.asyncio
async def test_settings_report_values_defaults_and_key_flags(settings_env, monkeypatch):
  settings_env.stored = {
    "provider": "groq", "model": "", "fast_model": "f", "fallback_models": ["a"], "transcription_cleanup": "llm",
    "groq_api_key": "k", "ollama_base_url": "https://o",
  }
  monkeypatch.setenv("OPENAI_API_KEY", "env")
  result = await router.get_settings_endpoint(current_user={"id": "u"})
  assert (result["provider"], result["model"], result["fast_model"]) == ("groq", None, "f")
  assert result["fallback_models"] == ["a"] and result["transcription_cleanup"] == "llm"
  assert result["transcription_diarization"] == "auto" and result["transcription_fillers"] == []
  assert result["transcription_vocabulary"] == "" and result["transcription_browser_diarization"] == "off"
  assert result["groq_api_key_set"] is True and result["transcription_groq_api_key_set"] is True
  assert result["openai_api_key_set"] is True and result["transcription_openai_api_key_set"] is True
  assert result["claude_api_key_set"] is False and result["gemini_api_key_set"] is False
  assert result["ollama_base_url"] == "https://o" and result["active_api_key_set"] is True and result["user_id"] == "u"


@pytest.mark.asyncio
async def test_empty_settings_report_nothing_configured(settings_env):
  result = await router.get_settings_endpoint(current_user={"id": "u"})
  assert result["provider"] is None and result["fast_model"] is None and result["active_api_key_set"] is False
  assert not any(result[name] for name in result if name.endswith("_api_key_set"))


def test_active_key_depends_on_the_provider_kind(monkeypatch):
  assert router._active_key_set({}) is False
  assert router._active_key_set({"provider": "unknown-provider"}) is False
  assert router._active_key_set({"provider": "groq", "groq_api_key": "k"}) is True
  assert router._active_key_set({"provider": "groq"}) is False
  by_alias = SimpleNamespace(id="x", aliases=("ollama",), config_key="x_key", env_key=None)
  by_id = SimpleNamespace(id="ollama_remote", aliases=(), config_key="x_key", env_key=None)
  plain = SimpleNamespace(id="x", aliases=(), config_key="x_key", env_key=None)
  for spec, expected in ((by_alias, True), (by_id, True), (plain, False)):
    monkeypatch.setattr(router, "find_provider_spec", lambda name, spec=spec: spec)
    assert router._active_key_set({"provider": "x", "ollama_base_url": "https://o"}) is expected
  with_env = SimpleNamespace(id="x", aliases=(), config_key="x_key", env_key="X_ENV_KEY")
  monkeypatch.setattr(router, "find_provider_spec", lambda name: with_env)
  monkeypatch.delenv("X_ENV_KEY", raising=False)
  assert router._active_key_set({"provider": "x"}) is False
  monkeypatch.setenv("X_ENV_KEY", "v")
  assert router._active_key_set({"provider": "x"}) is True
  assert router._active_key_set({"provider": "x", "x_key": "stored"}) is True


@pytest.mark.asyncio
async def test_refresh_reports_a_sync_failure_only_when_it_failed(monkeypatch):
  async def failing_sync(force_remote):
    return {"status": "error"}

  async def ok_sync(force_remote):
    return {"status": "success"}

  async def fake_catalog(refresh=False, provider="all", task_type="all"):
    return SimpleNamespace(model_dump=lambda: {"models": []})

  monkeypatch.setattr(router, "get_model_catalog", fake_catalog)
  monkeypatch.setattr(router, "sync_frontier_models_catalog", failing_sync)
  assert "LiteLLM" in (await router.ai_models_catalog(refresh=True))["error"]
  monkeypatch.setattr(router, "sync_frontier_models_catalog", ok_sync)
  assert "error" not in await router.ai_models_catalog(refresh=True)
