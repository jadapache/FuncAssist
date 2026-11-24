"""app.ai.catalog: DB-backed catalog loading, filtering and model picking."""


import pytest

import app.db.unit_of_work as uow_mod
from app.ai import catalog


def item(mid, provider="openai", task="chat_writing", **kw):
  return {
    "id": mid, "raw_id": mid, "name": mid, "provider": provider, "provider_name": provider,
    "description": "d", "context_window": "8k", "context_length": 8192, "task_type": task,
    "tier_type": "paid", "pricing_label": "", "rate_limits": "x", **kw,
  }


class FakeSyncUoW:
  items = []
  fail = False
  upserted = None

  def __enter__(self):
    if FakeSyncUoW.fail:
      raise RuntimeError("db down")

    class Cat:
      def bulk_upsert(self, models):
        FakeSyncUoW.upserted = models

      def list(self):
        return FakeSyncUoW.items
    self.model_catalog = Cat()
    return self

  def __exit__(self, *a):
    return False

  def commit(self):
    pass


@pytest.fixture
def db(monkeypatch):
  FakeSyncUoW.items, FakeSyncUoW.fail, FakeSyncUoW.upserted = [], False, None
  monkeypatch.setattr(uow_mod, "SyncUnitOfWork", FakeSyncUoW)
  monkeypatch.setattr(catalog, "_catalog_cache", None)
  monkeypatch.setattr(catalog, "_catalog_cache_ts", 0.0)
  return FakeSyncUoW


def test_load_seeds_filters_and_caches(db):
  db.items = [item("gpt-4o"), item("m.gguf"), item("x", provider="local"), {"no": "id"}, "junk",
              {"id": "invalid"}]
  models = catalog.load_local_catalog()
  assert [m.id for m in models] == ["gpt-4o"]
  assert db.upserted is catalog.KNOWN_BROWSER_MODELS
  db.items = []
  assert catalog.load_local_catalog() is models  # cached
  assert catalog.load_local_catalog(refresh=True) == []


def test_load_when_db_fails_or_returns_non_list(db):
  db.fail = True
  assert catalog.load_local_catalog(refresh=True) == []
  db.fail = False
  db.items = {"not": "a list"}
  assert catalog.load_local_catalog(refresh=True) == []




def test_pick_model_tiers_and_fallbacks(db):
  db.items = [item(m, provider="groq") for m in
              ("llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-guard-4", "llama-3.1-8b-instant")]
  assert catalog.pick_model("groq", "main") == "openai/gpt-oss-120b"
  assert catalog.pick_model("groq", "fast") == "openai/gpt-oss-20b"
  # No catalog models for provider: registry default is the last resort.
  assert catalog.pick_model("claude", "main", registry_default="rd") == "rd"
  assert catalog.pick_model("claude") is None
  # Models exist but none match the tier patterns.
  db.items = [item("weird-model", provider="deepseek")]
  catalog.load_local_catalog(refresh=True)
  assert catalog.pick_model("deepseek", "main", registry_default="weird-model") == "weird-model"
  assert catalog.pick_model("deepseek", "main", registry_default="other") is None


def test_pick_model_openrouter_skips_variants(db):
  db.items = [item(m, provider="openrouter") for m in (
    "meta-llama/llama-3.3-70b-instruct:free", "meta-llama/llama-3.3-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct:free", "meta-llama/llama-3.1-8b-instruct", "other/model",
  )]
  assert catalog.pick_model("openrouter", "main") == "meta-llama/llama-3.3-70b-instruct"
  assert catalog.pick_model("openrouter", "fast") == "meta-llama/llama-3.1-8b-instruct"


def test_pick_model_deepseek_chat(db):
  db.items = [item(m, provider="deepseek") for m in ("deepseek-reasoner", "deepseek-chat")]
  assert catalog.pick_model("deepseek", "main") == "deepseek-chat"
  assert catalog.pick_model("deepseek", "fast") == "deepseek-chat"


def test_pick_model_prefers_newest_undated(db):
  db.items = [item(m, provider="claude") for m in
              ("claude-3-5-sonnet-20241022", "claude-sonnet-4-5", "claude-sonnet-4", "claude-3-5-haiku")]
  assert catalog.pick_model("claude", "main") == "claude-sonnet-4-5"
  assert catalog.pick_model("claude", "fast") == "claude-3-5-haiku"


def test_pick_model_catalog_error(monkeypatch):
  monkeypatch.setattr(catalog, "catalog_chat_models", lambda p: (_ for _ in ()).throw(RuntimeError("x")))
  assert catalog.pick_model("openai", registry_default="d") == "d"


def test_transcription_pickers(db):
  db.items = [item(m, task="transcription") for m in
              ("whisper-1", "gpt-4o-transcribe", "gpt-4o-transcribe-diarize", "whisper-realtime")]
  assert catalog.segment_transcription_models("openai") == ["whisper-1"]
  assert catalog.pick_transcription_model("openai", "whisper-1") == "whisper-1"
  assert catalog.pick_transcription_model("openai", "gpt-4o-transcribe") == "whisper-1"
  assert catalog.pick_transcription_model("groq") is None
  assert catalog.pick_diarization_model("openai") == ("gpt-4o-transcribe-diarize", True)
  assert catalog.pick_diarization_model("openai", "gpt-4o-transcribe-diarize") == ("gpt-4o-transcribe-diarize", True)
  assert catalog.pick_diarization_model("groq", "cfg") == (None, False)
  db.items = [item("whisper-large-v3", provider="groq", task="transcription"),
              item("whisper-large-v3-turbo", provider="groq", task="transcription")]
  catalog.load_local_catalog(refresh=True)
  assert catalog.pick_transcription_model("groq") == "whisper-large-v3"
  assert catalog.pick_diarization_model("groq") == (None, True)
  assert catalog.supports_transcript_segments("whisper-large-v3")
  assert not catalog.supports_transcript_segments("gpt-4o-transcribe")


def test_transcription_pickers_catalog_error(monkeypatch):
  def boom(p):
    raise RuntimeError("x")
  monkeypatch.setattr(catalog, "segment_transcription_models", boom)
  monkeypatch.setattr(catalog, "catalog_transcription_models", boom)
  assert catalog.pick_transcription_model("openai") is None
  assert catalog.pick_diarization_model("openai") == (None, False)


@pytest.mark.asyncio
async def test_get_model_catalog_filters(db):
  db.items = [item("a"), item("b", provider="groq"), item("c", task="transcription")]
  res = await catalog.get_model_catalog(refresh=True, provider="openai", task_type="chat_writing")
  assert [m.id for m in res.models] == ["a"] and res.providers == ["groq", "openai"] and res.error is None
  res = await catalog.get_model_catalog()
  assert len(res.models) == 3
  db.items = []
  res = await catalog.get_model_catalog(refresh=True)
  assert res.models == [] and res.error
