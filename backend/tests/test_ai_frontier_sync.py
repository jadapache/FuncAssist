"""app.ai.frontier_sync: LiteLLM cost-map discovery, enrichment and persistence (no network)."""

import pytest

import app.db.unit_of_work as uow_mod
from app.ai import catalog, frontier_sync as fs


class FakeResp:
  def __init__(self, status, data):
    self.status_code = status
    self._data = data

  def json(self):
    return self._data


def fake_client(resp):
  class C:
    def __init__(self, *a, **k):
      pass

    async def __aenter__(self):
      return self

    async def __aexit__(self, *a):
      return False

    async def get(self, url):
      assert url == fs.LITELLM_REMOTE_URL
      return resp
  return C


@pytest.mark.asyncio
async def test_fetch_cost_map_success_updates_litellm(monkeypatch):
  data = {f"m{i}": {"mode": "chat"} for i in range(101)}
  monkeypatch.setattr(fs.httpx, "AsyncClient", fake_client(FakeResp(200, data)))
  store = {}
  monkeypatch.setattr(fs.litellm, "model_cost", store)
  got, src = await fs.fetch_litellm_cost_map()
  assert got is data and src == "remote_litellm" and "m5" in store


@pytest.mark.asyncio
@pytest.mark.parametrize("resp", [FakeResp(500, {}), FakeResp(200, {"a": {}}), FakeResp(200, [1])])
async def test_fetch_cost_map_rejects_bad_responses(monkeypatch, resp):
  monkeypatch.setattr(fs.httpx, "AsyncClient", fake_client(resp))
  with pytest.raises(RuntimeError):
    await fs.fetch_litellm_cost_map()


def test_format_context_window():
  assert fs._format_context_window(2_000_000) == "2M tokens"
  assert fs._format_context_window(1_500_000) == "1.5M tokens"
  assert fs._format_context_window(128_000) == "128k tokens"
  assert fs._format_context_window(512) == "512 tokens"


def test_find_litellm_entry_variants():
  e = {"x": 1}
  assert fs._find_litellm_entry({"anthropic/c3": e}, "c3", "claude") is e
  assert fs._find_litellm_entry({"google/g1": e}, "g1", "gemini") is e
  assert fs._find_litellm_entry({"openai/o1": e}, "o1", "openai") is e
  assert fs._find_litellm_entry({"groq/q": e}, "q", "groq") is e
  assert fs._find_litellm_entry({"vendor/deep/x": e}, "deep/x", "other") is e  # flexible suffix match
  assert fs._find_litellm_entry({"bad": "str", "y": e}, "z", "other") is None


def test_build_model_description():
  assert "diarización" in fs._build_model_description(None, "OpenAI", "gpt-diarize", "transcription", "")
  assert "diarización" not in fs._build_model_description(None, "OpenAI", "whisper", "transcription", "")
  d = fs._build_model_description(
    {"supports_reasoning": True, "supported_modalities": ["image"], "supports_function_calling": True,
     "supports_prompt_caching": True}, "P", "m", "chat_writing", "8k tokens")
  assert d == "Modelo P con ventana de 8k tokens, optimizado para razonamiento, visión multimodal, herramientas, prompt caching."
  assert fs._build_model_description(None, "P", "m", "chat_writing", "8k") == "Modelo P con ventana de 8k."


def test_discover_models_filters_and_maps_providers():
  cmap = {
    "anthropic/claude-x": {"mode": "chat"},
    "groq/whisper-large-v3": {"mode": "audio_transcription"},
    "gpt-4o": {"mode": "chat", "litellm_provider": "openai"},
    "embed": {"mode": "embedding"},
    "unknown/foo": {"mode": "chat"},
    "groq/": {"mode": "chat"},
    "bare": {"mode": "chat"},
    "notdict": "x",
    7: {"mode": "chat"},
  }
  got = fs._discover_litellm_models(cmap)
  assert set(got) == {"claude:claude-x", "groq:whisper-large-v3", "openai:gpt-4o"}
  assert got["groq:whisper-large-v3"]["task_type"] == "transcription"
  assert got["groq:whisper-large-v3"]["tier_type"] == "free"
  assert got["openai:gpt-4o"]["provider_name"] == "OpenAI"


class FakeSyncUoW:
  saved = None
  fail = False

  def __enter__(self):
    if FakeSyncUoW.fail:
      raise RuntimeError("db down")
    outer = self

    class Cat:
      def replace_external(self, items):
        FakeSyncUoW.saved = items
    self.model_catalog = Cat()
    return outer

  def __exit__(self, *a):
    return False

  def commit(self):
    pass


@pytest.mark.asyncio
async def test_sync_enriches_prices_and_persists(monkeypatch):
  cmap = {
    "groq/llama-3.3-70b": {"mode": "chat", "max_input_tokens": 128000, "max_output_tokens": 32768,
                          "input_cost_per_token": 5e-7, "output_cost_per_token": 7e-7},
    "openai/gpt-4o": {"mode": "chat", "max_input_tokens": 1_000_000, "max_output_tokens": 16384,
                      "input_cost_per_token": 2.5e-6, "output_cost_per_token": 1e-5, "supports_vision": True},
    "deepseek/deepseek-free": {"mode": "chat", "max_tokens": 64000},
    "openai/whisper-1": {"mode": "audio_transcription", "input_cost_per_token": 1e-10},
    "openai/gpt-4o-transcribe": {"mode": "audio_transcription", "input_cost_per_token": 6e-6},
    "groq/whisper-large-v3": {"mode": "audio_transcription"},
    "openai/expensive-audio": {"mode": "audio_transcription", "input_cost_per_token": 5e-7},
    "openai/free-audio": {"mode": "audio_transcription"},
  }

  async def fake_fetch(timeout_seconds):
    return cmap, "remote_litellm"

  FakeSyncUoW.fail = False
  monkeypatch.setattr(fs, "fetch_litellm_cost_map", fake_fetch)
  monkeypatch.setattr(uow_mod, "SyncUnitOfWork", FakeSyncUoW)
  catalog._catalog_cache = ["stale"]
  res = await fs.sync_frontier_models_catalog(force_remote=True)
  assert res["status"] == "success" and res["models_count"] == 8 and res["source"] == "remote_litellm"
  assert catalog._catalog_cache is None
  by_id = {m["id"]: m for m in FakeSyncUoW.saved}
  groq = by_id["llama-3.3-70b"]
  assert groq["is_free"] and groq["pricing_prompt"] == 0.0 and "Gratuito en Groq Cloud" in groq["pricing_label"]
  assert groq["context_window"] == "128k tokens" and groq["max_output_tokens"] == 32768
  gpt = by_id["gpt-4o"]
  assert gpt["tier_type"] == "paid" and gpt["pricing_label"] == "$2.50 / 1M input • $10.00 / 1M output"
  assert gpt["context_window"] == "1M tokens" and "visión multimodal" in gpt["description"]
  free = by_id["deepseek-free"]
  assert free["is_free"] and free["pricing_label"] == "$0.00 (Gratuito)"
  assert by_id["whisper-1"]["pricing_label"] == "$0.000 por minuto de audio"
  assert by_id["gpt-4o-transcribe"]["pricing_label"] == "$6.00 / 1M tokens"
  assert by_id["expensive-audio"]["pricing_label"] == "$0.50 / 1M tokens"
  assert by_id["free-audio"]["pricing_label"] == "$0.00 (Gratuito en Groq Cloud)"
  assert fs.get_frontier_sync_status()["status"] == "success"


@pytest.mark.asyncio
async def test_sync_tolerates_db_failure_and_invalid_items(monkeypatch):
  async def fake_fetch(timeout_seconds):
    return {"openai/gpt-x": {"mode": "chat", "input_cost_per_token": 1e-6, "output_cost_per_token": 0}}, "s"

  monkeypatch.setattr(fs, "fetch_litellm_cost_map", fake_fetch)
  FakeSyncUoW.fail = True
  monkeypatch.setattr(uow_mod, "SyncUnitOfWork", FakeSyncUoW)
  orig = fs.AIModelInfo

  def picky(**kw):
    if kw["id"] == "never":
      raise ValueError("bad")
    return orig(**kw)
  monkeypatch.setattr(fs, "AIModelInfo", picky)
  res = await fs.sync_frontier_models_catalog()
  FakeSyncUoW.fail = False
  assert res["status"] == "success" and res["models_count"] == 1

  async def fetch_bad(timeout_seconds):
    return {"openai/never": {"mode": "chat"}}, "s"
  monkeypatch.setattr(fs, "fetch_litellm_cost_map", fetch_bad)
  monkeypatch.setattr(uow_mod, "SyncUnitOfWork", FakeSyncUoW)
  assert (await fs.sync_frontier_models_catalog())["models_count"] == 0


@pytest.mark.asyncio
async def test_sync_reports_fetch_error(monkeypatch):
  async def boom(timeout_seconds):
    raise RuntimeError("offline")
  monkeypatch.setattr(fs, "fetch_litellm_cost_map", boom)
  res = await fs.sync_frontier_models_catalog()
  assert res["status"] == "error" and res["error"] == "offline" and res["models_count"] == 0
  assert fs.get_frontier_sync_status() == res and fs.get_frontier_sync_status() is not res
