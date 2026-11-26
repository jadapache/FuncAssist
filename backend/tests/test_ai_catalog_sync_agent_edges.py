"""Edge cases of the model catalog, provider registry, templates, agent loop, section generation and frontier sync."""

import asyncio
import json
import logging
from types import SimpleNamespace

import pytest

from app.ai import agent, catalog, frontier_sync as fs, section_generator as sg, templates
from app.ai.providers import registry
from app.ai.providers.base import AIMessage, ToolCall
from app.ai.tools.registry import Tool, ToolContext
from tests.test_ai_agent import ScriptedProvider, _collect
from tests.test_ai_section_generator import PLAN_JSON, _Prov


def model(id, provider="openai", task="chat_writing", raw_id="", output=None):
  return SimpleNamespace(id=id, raw_id=raw_id, provider=provider, task_type=task, max_output_tokens=output)


# --- catalog --------------------------------------------------------------

def test_catalog_items_that_are_not_dicts_are_skipped():
  assert catalog._filter_catalog_items([5, "x", ["id"], None]) == []


def test_catalog_cache_expires_exactly_at_the_ttl(monkeypatch):
  loads = []
  monkeypatch.setattr(catalog, "_ensure_catalog_seeded", lambda: None)
  monkeypatch.setattr(catalog, "_load_frontier_from_db", lambda: loads.append(1) or [])
  monkeypatch.setattr(catalog, "_catalog_cache", ["cached"])
  monkeypatch.setattr(catalog, "_catalog_cache_ts", 100.0)
  monkeypatch.setattr(catalog.time, "monotonic", lambda: 100.0 + catalog._CACHE_TTL_SECONDS - 0.5)
  assert catalog.load_local_catalog() == ["cached"] and loads == []
  monkeypatch.setattr(catalog.time, "monotonic", lambda: 100.0 + catalog._CACHE_TTL_SECONDS)
  assert catalog.load_local_catalog() == [] and loads == [1]


def test_browser_providers_are_aliased_per_task_type(monkeypatch):
  monkeypatch.setattr(catalog, "load_local_catalog", lambda refresh=False: [
    model("asr-1", "browser_asr", "transcription"), model("llm-1", "webllm", "chat_writing"),
  ])
  assert catalog.has_catalog_model("asr-1", "local", "transcription")
  assert catalog.has_catalog_model("asr-1", "BUILTIN", "Transcription")
  assert not catalog.has_catalog_model("asr-1", "local", "chat_writing")
  assert catalog.has_catalog_model("llm-1", "local", "chat_writing")
  assert not catalog.has_catalog_model("llm-1", "local", "transcription")


def test_catalog_model_matches_by_id_or_raw_id(monkeypatch):
  monkeypatch.setattr(catalog, "load_local_catalog", lambda refresh=False: [model("short", raw_id="vendor/long")])
  assert catalog.has_catalog_model("short", "openai", "chat_writing")
  assert catalog.has_catalog_model("vendor/long", "openai", "chat_writing")
  assert not catalog.has_catalog_model("other", "openai", "chat_writing")


def test_catalog_model_ids_prefer_the_raw_id(monkeypatch):
  monkeypatch.setattr(catalog, "load_local_catalog", lambda refresh=False: [model("i", raw_id="r"), model("j")])
  assert catalog.catalog_chat_models("OpenAI") == ["r", "j"]


def test_shorter_id_wins_among_equal_versions():
  assert catalog._version_key("gpt-5") > catalog._version_key("gpt-5-turbo")
  assert catalog._version_key("gpt-5") > catalog._version_key("gpt-4")
  assert catalog._version_key("gpt-5") > catalog._version_key("gpt-5-2025-01-01")


def test_newest_transcription_and_diarization_models_are_picked(monkeypatch):
  monkeypatch.setattr(catalog, "segment_transcription_models", lambda p: ["whisper-a-v2", "whisper-a-v3"])
  assert catalog.pick_transcription_model("x") == "whisper-a-v3"
  monkeypatch.setattr(catalog, "catalog_transcription_models", lambda p: ["diarize-v1", "diarize-v2", "whisper"])
  assert catalog.pick_diarization_model("x") == ("diarize-v2", True)


def test_configured_diarization_model_is_kept_only_when_it_is_a_diarizer(monkeypatch):
  monkeypatch.setattr(catalog, "catalog_transcription_models", lambda p: ["diarize-v1", "diarize-v2", "whisper"])
  assert catalog.pick_diarization_model("x", "diarize-v1") == ("diarize-v1", True)
  assert catalog.pick_diarization_model("x", "whisper") == ("diarize-v2", True)


@pytest.mark.asyncio
async def test_model_catalog_does_not_refresh_by_default(monkeypatch):
  seen = []
  monkeypatch.setattr(catalog, "load_local_catalog", lambda refresh=False: seen.append(refresh) or [])
  await catalog.get_model_catalog()
  await catalog.get_model_catalog(refresh=True)
  assert seen == [False, True]


# --- provider registry ----------------------------------------------------

def test_max_tokens_default_depends_on_streaming():
  assert registry.resolve_model_max_tokens("unknown-provider", "m") == 4096
  assert registry.resolve_model_max_tokens("unknown-provider", "m", is_stream=True) == 8192


def test_catalog_output_limit_matching(monkeypatch):
  entries = [
    model("a-id", "openai", output=111, raw_id="a-raw"),
    model("c", "openai", output=222),
    model("zero", "openai", output=0),
    model("other-provider", "groq", output=999),
  ]
  monkeypatch.setattr("app.ai.catalog.load_local_catalog", lambda refresh=False: entries)
  assert registry._catalog_output_limit("openai", "a-id") == 111
  assert registry._catalog_output_limit("openai", "a-raw") == 111
  assert registry._catalog_output_limit("openai", "vendor/a/c") == 222
  assert registry._catalog_output_limit("openai", "zero") is None
  assert registry._catalog_output_limit("openai", "other-provider") is None
  assert registry._catalog_output_limit("openai", "unknown") is None


# --- templates ------------------------------------------------------------

@pytest.fixture
def captured_saves(monkeypatch):
  saved = []

  async def fake_save(kind, feature, data, updated_by, summary):
    saved.append((kind, feature, data, updated_by, summary))
    return data

  monkeypatch.setattr(templates, "ensure_ai_templates_seeded", lambda: None)
  monkeypatch.setattr(templates, "_save_template", fake_save)
  return saved


@pytest.mark.asyncio
@pytest.mark.parametrize("current,expected", [({"version": 5}, 6), ({}, 2), ({"version": 0}, 2)])
async def test_next_version_after_save_and_reset(monkeypatch, captured_saves, current, expected):
  async def current_template(*args):
    return dict(current)

  monkeypatch.setattr(templates, "get_prompt", current_template)
  monkeypatch.setattr(templates, "get_rubric", current_template)
  monkeypatch.setattr(templates, "_get_template", lambda kind, feature: current_template())
  feature = next(iter(templates.DEFAULT_RUBRICS))
  await templates.save_prompt("p", {"system": "s"})
  await templates.save_rubric(feature, {})
  await templates.reset_rubric(feature)
  assert [entry[2]["version"] for entry in captured_saves] == [expected] * 3


@pytest.mark.asyncio
async def test_rubric_change_summary_defaults_and_passes_through(monkeypatch, captured_saves):
  async def current(*args):
    return {"version": 1}

  monkeypatch.setattr(templates, "get_rubric", current)
  await templates.save_rubric("r", {}, updated_by="ana")
  await templates.save_rubric("r", {}, change_summary="mi cambio")
  assert [(e[3], e[4]) for e in captured_saves] == [("ana", "Updated rubric for r"), (None, "mi cambio")]


@pytest.mark.asyncio
async def test_transcript_summary_alias_resolves_to_the_standard_meeting_prompt(monkeypatch):
  monkeypatch.setattr(templates, "ensure_ai_templates_seeded", lambda: None)
  monkeypatch.setattr(templates, "DEFAULT_PROMPTS", {templates.DEFAULT_TRANSCRIPT_SUMMARY_FEATURE: {"x": 1}, "other": {"y": 2}})
  assert await templates.get_prompt("transcript_summary") == {"x": 1}
  assert await templates.get_prompt("other") == {"y": 2}
  with pytest.raises(KeyError):
    await templates.get_prompt("missing")


# --- agent ----------------------------------------------------------------

def _tool(name, external=False, handler=None):
  async def default(args, ctx):
    return "done"
  return Tool(name, "", {}, handler or default, read_only=not external, external_effect=external)


@pytest.mark.asyncio
async def test_external_tool_runs_by_default_when_nothing_untrusted_is_known(monkeypatch):
  tool = _tool("send", external=True)
  monkeypatch.setattr(agent, "get_tool", {"send": tool}.get)
  _, text, is_error = await agent._exec_tool(ToolCall(id="1", name="send"), ToolContext())
  assert (text, is_error) == ("done", False)


@pytest.mark.asyncio
async def test_failing_tool_is_logged_with_its_traceback(monkeypatch, caplog):
  async def boom(args, ctx):
    raise RuntimeError("kaput")

  monkeypatch.setattr(agent, "get_tool", {"t": _tool("t", handler=boom)}.get)
  with caplog.at_level(logging.WARNING):
    _, text, is_error = await agent._exec_tool(ToolCall(id="1", name="t"), ToolContext())
  assert is_error and "kaput" in text
  assert any("Tool t failed" in r.getMessage() and r.exc_info for r in caplog.records)


def test_usage_totals_start_from_zero_for_missing_keys():
  stats = agent._RunStats()
  stats.absorb({})
  assert (stats.prompt_tokens, stats.completion_tokens, stats.cached_tokens, stats.cost_usd) == (0, 0, 0, 0.0)


@pytest.mark.asyncio
async def test_agent_always_runs_at_least_one_turn_and_ends_with_done():
  provider = ScriptedProvider([(["hola"], {})])
  events = await _collect(agent.run_agent([AIMessage(role="user", content="x")], provider, ToolContext(), max_iters=0))
  assert len(provider.calls) == 1
  assert events[-1].type == "done" and events[-1].data == {"ok": True}


# --- section generation ---------------------------------------------------

@pytest.mark.parametrize("text,expected", [
  ('{"a": 1}', '{"a": 1}'),
  ('antes {"a": 1} despues', '{"a": 1}'),
  ("abc}", "abc}"),
  ("{abc", "{abc"),
  ("}{", "}{"),
])
def test_clean_json_response(text, expected):
  assert sg._clean_json_response(text) == expected


@pytest.mark.parametrize("payload", [
  '{"extension": "md", "sections": [{"title": "a"}]}',
  '{"title": "t", "sections": [{"title": "a"}]}',
  '{"title": "t", "extension": "md", "sections": []}',
])
def test_plan_needs_title_extension_and_sections(payload):
  assert sg._parse_plan_json(payload) is None


@pytest.mark.asyncio
async def test_planning_failures_are_logged_with_tracebacks(caplog):
  provider = _Prov([RuntimeError("one"), RuntimeError("two")])
  with caplog.at_level(logging.WARNING):
    assert await sg.plan_document("q", "ctx", provider=provider) is None
  assert any("Document planning with" in r.getMessage() and r.exc_info for r in caplog.records)
  assert any("planning retry" in r.getMessage() and r.exc_info for r in caplog.records)


@pytest.mark.asyncio
async def test_invalid_retry_is_logged_and_a_valid_one_is_not(caplog):
  with caplog.at_level(logging.WARNING):
    assert await sg.plan_document("q", "ctx", provider=_Prov(["nope", "still nope"])) is None
  assert any("retry from" in r.getMessage() for r in caplog.records)
  caplog.clear()
  with caplog.at_level(logging.WARNING):
    assert await sg.plan_document("q", "ctx", provider=_Prov(["nope", PLAN_JSON])) is not None
  assert not any("retry from" in r.getMessage() for r in caplog.records)


def _plan(*titles):
  return sg.DocumentPlan("Doc", "docx", "", [sg.PlanSection(t) for t in titles])


class _SectionProvider:
  default_model = "m"

  def __init__(self, behaviour):
    self.behaviour = behaviour

  async def complete(self, messages, max_tokens=None):
    return await self.behaviour(messages[-1].content)


async def _drain(plan, provider, **kwargs):
  return [item async for item in sg.generate_sections_stream(plan, "sys", "ctx", provider, **kwargs)]


@pytest.mark.asyncio
async def test_status_events_count_sections_from_one():
  async def ok(prompt):
    return SimpleNamespace(text="cuerpo")

  items = await _drain(_plan("A", "B"), _SectionProvider(ok))
  messages = [i.data["message"] for i in items if getattr(i, "type", "") == "status"]
  assert messages == ["Sección 1/2 lista", "Sección 2/2 lista"]


@pytest.mark.asyncio
async def test_zero_concurrency_still_generates():
  async def ok(prompt):
    return SimpleNamespace(text="cuerpo")

  items = await asyncio.wait_for(_drain(_plan("A"), _SectionProvider(ok), concurrency=0), timeout=5)
  assert any(isinstance(i, str) and "cuerpo" in i for i in items)


@pytest.mark.asyncio
async def test_a_section_is_retried_once_and_failures_are_logged(caplog):
  attempts = []

  async def flaky(prompt):
    attempts.append(1)
    if len(attempts) == 1:
      raise RuntimeError("blip")
    return SimpleNamespace(text="listo")

  with caplog.at_level(logging.WARNING):
    items = await _drain(_plan("A"), _SectionProvider(flaky))
  assert len(attempts) == 2 and any(isinstance(i, str) and "listo" in i for i in items)
  failure = next(r for r in caplog.records if "failed with" in r.getMessage())
  assert "attempt 1/2" in failure.getMessage() and failure.exc_info


@pytest.mark.asyncio
async def test_empty_section_bodies_are_retried_and_logged(caplog):
  replies = ["", "segundo intento"]

  async def reply(prompt):
    return SimpleNamespace(text=replies.pop(0))

  with caplog.at_level(logging.WARNING):
    items = await _drain(_plan("A"), _SectionProvider(reply))
  assert any(isinstance(i, str) and "segundo intento" in i for i in items)
  assert any("came back empty" in r.getMessage() and "attempt 1" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_pending_tasks_are_cancelled_only_when_the_consumer_stops_early(caplog):
  async def ok(prompt):
    return SimpleNamespace(text="cuerpo")

  with caplog.at_level(logging.INFO):
    await _drain(_plan("A", "B"), _SectionProvider(ok))
  assert not any("Cancelled" in r.getMessage() for r in caplog.records)

  async def slow(prompt):
    if "'A'" in prompt:
      return SimpleNamespace(text="rapido")
    await asyncio.sleep(30)

  stream = sg.generate_sections_stream(_plan("A", "B"), "sys", "ctx", _SectionProvider(slow))
  with caplog.at_level(logging.INFO):
    for _ in range(3):
      await stream.__anext__()
    await stream.aclose()
  assert any("Cancelled 1 pending section task(s)" in r.getMessage() for r in caplog.records)


# --- frontier sync --------------------------------------------------------

def _client_recording(kwargs_seen, data):
  class Client:
    def __init__(self, *args, **kwargs):
      kwargs_seen.append(kwargs)

    async def __aenter__(self):
      return self

    async def __aexit__(self, *exc):
      return False

    async def get(self, url):
      return SimpleNamespace(status_code=200, json=lambda: data)
  return Client


@pytest.mark.asyncio
async def test_cost_map_download_follows_redirects_and_needs_more_than_100_models(monkeypatch):
  seen = []
  monkeypatch.setattr(fs.httpx, "AsyncClient", _client_recording(seen, {f"m{i}": {} for i in range(101)}))
  monkeypatch.setattr(fs.litellm, "model_cost", object())  # no update(): the failure must be swallowed
  data, source = await fs.fetch_litellm_cost_map(timeout_seconds=3.0)
  assert source == "remote_litellm" and len(data) == 101
  assert seen == [{"timeout": 3.0, "follow_redirects": True}]
  monkeypatch.setattr(fs.httpx, "AsyncClient", _client_recording([], {f"m{i}": {} for i in range(100)}))
  with pytest.raises(RuntimeError):
    await fs.fetch_litellm_cost_map()


@pytest.mark.parametrize("tokens,label", [
  (999, "999 tokens"), (1000, "1k tokens"), (128_000, "128k tokens"), (1_000_000, "1M tokens"), (1_500_000, "1.5M tokens"),
])
def test_context_window_labels(tokens, label):
  assert fs._format_context_window(tokens) == label


def test_litellm_entry_lookup_by_provider_specific_keys():
  entry = {"mode": "chat"}
  assert fs._find_litellm_entry({"z": entry}, "x/y/z", "openai") is entry
  assert fs._find_litellm_entry({"anthropic/z": entry}, "x/y/z", "claude") is entry
  assert fs._find_litellm_entry({"anthropic/x/y/z": entry}, "x/y/z", "claude") is entry
  assert fs._find_litellm_entry({"openai/z": entry}, "x/y/z", "openai") is None
  assert fs._find_litellm_entry({"google/gem": entry}, "gem", "gemini") is entry
  assert fs._find_litellm_entry({"vendor/gem": entry}, "gem", "other") is entry


def test_capabilities_from_a_litellm_entry():
  assert fs._capabilities({"supports_vision": True}) == ["visión multimodal"]
  assert fs._capabilities({"supported_modalities": ["text", "image"]}) == ["visión multimodal"]
  assert fs._capabilities({"supported_modalities": ["text"]}) == []
  assert fs._capabilities({"supports_reasoning": 1, "supports_function_calling": 1, "supports_prompt_caching": 1}) == [
    "razonamiento", "herramientas", "prompt caching",
  ]


def test_provider_and_model_id_of_cost_map_keys():
  assert fs._provider_and_model_id("openai/gpt", {}) == ("openai", "gpt")
  assert fs._provider_and_model_id("openai/", {}) == (None, "")
  assert fs._provider_and_model_id("/gpt", {}) == (None, "gpt")
  assert fs._provider_and_model_id("gpt-x", {"litellm_provider": "Anthropic"}) == ("claude", "gpt-x")
  assert fs._provider_and_model_id("gpt-x", {}) == (None, "gpt-x")


def test_catalog_candidates_per_task_type_and_provider():
  chat = fs._catalog_candidate("openai", "gpt", "chat_writing")
  audio = fs._catalog_candidate("groq", "whisper", "transcription")
  unknown = fs._catalog_candidate("zzz", "m", "chat_writing")
  assert (chat["context_length"], chat["context_window"], chat["task_label"]) == (131072, "128k tokens", "Redacción y Chat")
  assert (audio["context_length"], audio["context_window"], audio["task_label"]) == (0, "Audio (hasta 25MB)", "Transcripción y Voz")
  assert (chat["is_free"], audio["is_free"], unknown["is_free"]) == (False, True, False)
  assert (chat["tier_type"], audio["tier_type"]) == ("paid", "free")


def test_positive_numbers_only():
  assert fs._positive_number(1) == 1
  assert fs._positive_number(0.5) == 0.5
  assert fs._positive_number(0) is None and fs._positive_number(-3) is None and fs._positive_number("5") is None


def _priced(provider="openai", task="chat_writing", prompt=0.0, completion=0.0):
  return {"provider": provider, "task_type": task, "pricing_prompt": prompt, "pricing_completion": completion}


def test_transcription_price_labels_switch_at_ten_cents():
  low, high = _priced(task="transcription", prompt=0.05), _priced(task="transcription", prompt=0.1)
  fs._apply_pricing_label(low)
  fs._apply_pricing_label(high)
  assert low["pricing_label"] == "$0.050 por minuto de audio"
  assert high["pricing_label"] == "$0.10 / 1M tokens"


def test_a_model_is_free_only_when_both_prices_are_zero():
  free, input_only, output_only = _priced(), _priced(prompt=1.0), _priced(completion=1.0)
  for item in (free, input_only, output_only):
    fs._apply_pricing_label(item)
  assert (free["is_free"], free["tier_type"], free["pricing_label"]) == (True, "free", "$0.00 (Gratuito)")
  for paid in (input_only, output_only):
    assert (paid["is_free"], paid["tier_type"]) == (False, "paid")


@pytest.mark.asyncio
async def test_sync_timeout_is_longer_when_a_remote_refresh_is_forced(monkeypatch):
  timeouts = []

  async def fake_fetch(timeout_seconds):
    timeouts.append(timeout_seconds)
    return {}, "s"

  monkeypatch.setattr(fs, "fetch_litellm_cost_map", fake_fetch)
  monkeypatch.setattr(fs, "_persist_external_models", lambda models: None)
  await fs.sync_frontier_models_catalog()
  await fs.sync_frontier_models_catalog(force_remote=True)
  assert timeouts == [5.0, 8.0]


def test_blank_title_or_extension_makes_the_plan_invalid():
  assert sg._parse_plan_json(json.dumps({"title": "", "extension": "md", "sections": [{"title": "a"}]})) is None
  assert sg._parse_plan_json(json.dumps({"title": "t", "extension": "", "sections": [{"title": "a"}]})) is None
  assert sg._parse_plan_json(json.dumps({"title": "t", "extension": "md", "sections": [{"title": "a"}]})) is not None
