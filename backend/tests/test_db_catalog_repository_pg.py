"""AIModelCatalogRepository against a real PostgreSQL (skipped when TEST_DATABASE_URL is not set)."""

from __future__ import annotations

import pytest

from app.db.repositories.catalog_repository import AIModelCatalogRepository


@pytest.fixture
def repo(pg_session):
  return AIModelCatalogRepository(pg_session)


def model(mid, **extra):
  return {"id": mid, **extra}


def test_bulk_upsert_counts_models_and_skips_those_without_an_id(repo):
  assert repo.bulk_upsert([model("a"), {"name": "no id"}, model("")]) == 1
  assert [m["id"] for m in repo.list()] == ["a"]


def test_bulk_upsert_fills_defaults(repo):
  repo.bulk_upsert([model("a"), model("b", is_free=True)])
  a, b = repo.get("a"), repo.get("b")
  assert (a["provider"], a["task_type"], a["name"]) == ("groq", "chat_writing", "a")
  assert (a["is_free"], a["tier_type"]) == (False, "paid")
  assert (b["is_free"], b["tier_type"]) == (True, "free")
  assert "vram_required_mb" not in a and "required_features" not in a


def test_bulk_upsert_accepts_the_camel_case_and_short_field_names(repo):
  repo.bulk_upsert([
    model("a", vramRequiredMB=512, contextWindow="8k", downloadSize="1 GB", requiredFeatures=["gpu"]),
    model("b", tokens="32k", size="2 GB"),
    model("c", vram_required_mb=2048, context_window="4k", download_size="3 GB", required_features=["cpu"], tier="pro"),
  ])
  a, b, c = repo.get("a"), repo.get("b"), repo.get("c")
  assert (a["vram_required_mb"], a["context_window"], a["download_size"]) == (512, "8k", "1 GB")
  assert a["vram_formatted"] == "~512 MB VRAM" and a["required_features"] == ["gpu"]
  assert (b["context_window"], b["download_size"]) == ("32k", "2 GB")
  assert (c["vram_formatted"], c["required_features"], c["tier"]) == ("~2.0 GB VRAM", ["cpu"], "pro")


def test_bulk_upsert_updates_an_existing_model_in_place(repo):
  repo.bulk_upsert([model("a", provider="groq", name="Old", tier="x", vram_required_mb=100, required_features=["gpu"])])
  assert repo.bulk_upsert([model("a", provider="openai", name="New")]) == 1
  assert len(repo.list()) == 1
  updated = repo.get("a")
  assert (updated["provider"], updated["name"]) == ("openai", "New")
  assert "tier" not in updated and "vram_required_mb" not in updated and "required_features" not in updated


def test_get_finds_a_model_by_id_ignoring_surrounding_spaces(repo):
  repo.bulk_upsert([model("gpt-x", name="GPT X")])
  assert repo.get("  gpt-x  ")["name"] == "GPT X"
  assert repo.get("missing") is None


@pytest.mark.parametrize("lookup", ["ALIAS-ONE", "alias-one", "Model.GGUF", "TAG-1"])
def test_get_finds_a_model_by_alias_filename_or_tag_ignoring_case(repo, lookup):
  repo.bulk_upsert([
    model("target", aliases=["Alias-One"], filename="model.gguf", tag="tag-1"),
    model("other", aliases=["unrelated"], filename="other.gguf", tag="tag-2"),
  ])
  assert repo.get(lookup)["id"] == "target"


def test_get_does_not_match_a_model_with_no_aliases_filename_or_tag(repo):
  repo.bulk_upsert([model("a")])
  assert repo.get("") is None and repo.get("unknown") is None


def test_list_is_sorted_by_name_and_can_filter_by_task_type(repo):
  repo.bulk_upsert([
    model("1", name="Zeta", task_type="chat_writing"),
    model("2", name="Alpha", task_type="transcription"),
    model("3", name="Mid", task_type="chat_writing"),
  ])
  assert [m["name"] for m in repo.list()] == ["Alpha", "Mid", "Zeta"]
  assert [m["name"] for m in repo.list("chat_writing")] == ["Mid", "Zeta"]
  assert repo.list("nothing") == []


def test_delete_free_models_removes_only_builtin_and_local_ones(repo):
  repo.bulk_upsert([model("b", provider="builtin"), model("l", provider="local"), model("o", provider="openai")])
  assert repo.delete_free_models() == 2
  assert [m["id"] for m in repo.list()] == ["o"]


def test_replace_external_keeps_browser_models_and_swaps_the_rest(repo):
  repo.bulk_upsert([
    model("w", provider="webllm"), model("r", provider="browser_asr"),
    model("old", provider="openai"), model("loc", provider="local"),
  ])
  assert repo.replace_external([model("new", provider="anthropic")]) == 1
  assert sorted(m["id"] for m in repo.list()) == ["new", "r", "w"]


def test_the_stored_payload_keeps_accents_readable():
  from app.db.repositories.catalog_repository import _model_columns

  assert "Ñandú" in _model_columns({"name": "Ñandú"}, "a")["payload_json"]
