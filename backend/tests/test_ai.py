"""AI layer: catalog-driven model choice, LiteLLM recovery and dependencies, WebLLM settings."""

import importlib
from types import SimpleNamespace
from unittest.mock import patch

import litellm
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.ai import catalog
from app.ai.providers import factory
from app.ai.providers.base import AIMessage
from app.ai.providers.implementations import LiteLLMProvider
from app.ai.providers.registry import find_provider_spec
from app.features.transcription import whisper_cloud


def _catalog(*entries):
  """Fake catalog: entries are (provider, model_id, task_type)."""
  return [SimpleNamespace(id=m, raw_id=m, provider=p, task_type=t) for p, m, t in entries]


def test_models_are_chosen_from_the_catalog():
  fake = _catalog(
    ("groq", "llama-3.3-70b-versatile", "chat_writing"),
    ("groq", "openai/gpt-oss-20b", "chat_writing"),
    ("openai", "whisper-1", "transcription"),
    ("openai", "gpt-4o-transcribe", "transcription"),
    ("openai", "gpt-4o-transcribe-diarize", "transcription"),
  )
  settings = {
    "provider": "groq", "model": "llama-3.3-70b-versatile", "groq_api_key": "k", "openai_api_key": "o",
    "fallback_models": [], "fast_model": None, "ollama_base_url": None,
    "transcription_provider": "openai", "transcription_model": "gpt-4o-transcribe",
  }
  factory.clear_provider_cache()
  with patch.object(catalog, "load_local_catalog", return_value=fake), \
       patch.object(factory, "get_ai_settings", return_value=settings), \
       patch.object(whisper_cloud, "get_ai_settings", lambda user_id=None: settings):
    fast = factory.resolve_provider(user_id="u1", tier="fast")
    speech = whisper_cloud.resolve_speech_target("u1")
    diarize = whisper_cloud.resolve_diarization_target("u1", True)

  # Fast tier: catalog model, with the main model as recovery when it disappears.
  assert fast.default_model == "openai/gpt-oss-20b"
  assert fast.not_found_fallback == "llama-3.3-70b-versatile"
  # Transcription: a text-only model is replaced by a catalog model with timestamped segments.
  assert speech.provider == "openai" and speech.model == "whisper-1"
  assert diarize is not None and diarize.model == "gpt-4o-transcribe-diarize"


@pytest.mark.asyncio
async def test_litellm_missing_model_recovers_with_main_model():
  prov = LiteLLMProvider(find_provider_spec("groq"), api_key="k", default_model="fast-m", not_found_fallback="main-m")
  calls = []

  async def fake_acompletion(**kwargs):
    calls.append(kwargs["model"])
    if kwargs["model"] == "groq/fast-m":
      raise litellm.NotFoundError("The model fast-m does not exist", "fast-m", "groq")
    choice = SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None), finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage={}, model="groq/main-m", model_dump=lambda: {})

  with patch("app.ai.providers.implementations.litellm.acompletion", side_effect=fake_acompletion):
    res = await prov.complete([AIMessage(role="user", content="q")])
  assert calls == ["groq/fast-m", "groq/main-m"]  # the missing model is not retried itself
  assert res.text == "ok" and res.model == "main-m"
  # LiteLLM's own retries are off: transient errors are retried by the provider, permanent ones never.
  assert prov._build_kwargs([AIMessage(role="user", content="hi")])["num_retries"] == 0


def test_litellm_tool_calling_dependencies_are_installed():
  # LiteLLM imports this module whenever `tools` are passed (agent mode). It needs the `mcp` package,
  # which LiteLLM does not declare: without it every tool call fails as "provider unavailable".
  importlib.import_module("litellm.responses.mcp.chat_completions_handler")


def test_webllm_model_is_validated_against_the_catalog():
  client = TestClient(main_module.app)
  fake = _catalog(("webllm", "Llama-3.2-1B-Instruct-q4f16_1-MLC", "chat_writing"))
  with patch.object(catalog, "load_local_catalog", return_value=fake):
    ok = client.put("/api/ai/settings", json={"provider": "webllm", "model": "Llama-3.2-1B-Instruct-q4f16_1-MLC"})
    unknown = client.put("/api/ai/settings", json={"provider": "webllm", "model": "not-a-browser-model"})
  assert ok.status_code == 200, ok.text
  assert ok.json()["model"] == "Llama-3.2-1B-Instruct-q4f16_1-MLC"
  assert unknown.status_code == 400 and "WebLLM" in unknown.json()["detail"]
