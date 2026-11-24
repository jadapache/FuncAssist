"""app.ai.templates: DB-backed prompts/rubrics with fallback to seeded defaults."""

import pytest

import app.db.unit_of_work as uow_mod
from app.ai import templates
from app.ai.seeds import DEFAULT_PROMPTS, DEFAULT_RUBRICS


class FakeRepo:
  def __init__(self, store=None, fail=False):
    self.store = store if store is not None else {}
    self.fail = fail
    self.saved = []
    self.seeded = False

  def _check(self):
    if self.fail:
      raise RuntimeError("db down")

  async def seed_defaults(self, prompts, rubrics):
    self.seeded = True

  async def list_templates(self, ttype, tag=None):
    self._check()
    return [v for (t, _), v in sorted(self.store.items()) if t == ttype and (not tag or v.get("tag") == tag)]

  async def get_template(self, ttype, feature):
    self._check()
    return self.store.get((ttype, feature))

  async def save_template_update(self, template_type, feature, new_data, updated_by=None, change_summary=None):
    self._check()
    self.saved.append((template_type, feature, new_data, updated_by, change_summary))
    self.store[(template_type, feature)] = dict(new_data)
    return {**new_data, "saved": True}

  async def get_version_history(self, ttype, feature, limit=50):
    return [{"type": ttype, "feature": feature, "limit": limit}]


class FakeUoW:
  repo: FakeRepo = None

  async def __aenter__(self):
    self.ai_templates = FakeUoW.repo
    return self

  async def __aexit__(self, *a):
    return False

  async def commit(self):
    FakeUoW.repo._check()


@pytest.fixture
def repo(monkeypatch):
  r = FakeRepo()
  FakeUoW.repo = r
  monkeypatch.setattr(uow_mod, "AsyncUnitOfWork", FakeUoW)
  monkeypatch.setattr(templates, "_DB_SEEDED", True)
  return r


def any_feature(defaults):
  return sorted(defaults)[0]


@pytest.mark.asyncio
async def test_list_prompts_falls_back_to_defaults_when_db_empty(repo):
  items = await templates.list_prompts()
  assert [p["feature"] for p in items] == [DEFAULT_PROMPTS[f]["feature"] for f in sorted(DEFAULT_PROMPTS)]
  tag = next(p.get("tag") for p in items if p.get("tag"))
  tagged = await templates.list_prompts(tag=tag)
  assert tagged and all(p["tag"] == tag for p in tagged)


@pytest.mark.asyncio
async def test_list_rubrics_db_and_fallback(repo):
  rubrics = await templates.list_rubrics()
  assert len(rubrics) == len(DEFAULT_RUBRICS)
  tag = next((r.get("tag") for r in rubrics if r.get("tag")), None)
  if tag:
    assert all(r["tag"] == tag for r in await templates.list_rubrics(tag=tag))
  assert await templates.list_rubrics(tag="__none__") == []
  repo.store[("rubric", "x")] = {"feature": "x"}
  assert await templates.list_rubrics() == [{"feature": "x"}]
  repo.store[("prompt", "p")] = {"feature": "p"}
  assert await templates.list_prompts() == [{"feature": "p"}]


@pytest.mark.asyncio
async def test_list_survives_db_errors(repo):
  repo.fail = True
  assert len(await templates.list_prompts()) == len(DEFAULT_PROMPTS)
  assert len(await templates.list_rubrics()) == len(DEFAULT_RUBRICS)


@pytest.mark.asyncio
async def test_get_prompt_prefers_db_and_resolves_alias(repo):
  repo.store[("prompt", templates.DEFAULT_TRANSCRIPT_SUMMARY_FEATURE)] = {"system": "db"}
  assert await templates.get_prompt("transcript_summary") == {"system": "db"}
  repo.fail = True
  f = any_feature(DEFAULT_PROMPTS)
  assert await templates.get_prompt(f) == DEFAULT_PROMPTS[f]
  with pytest.raises(KeyError):
    await templates.get_prompt("nope")


@pytest.mark.asyncio
async def test_get_rubric_db_default_and_unknown(repo):
  repo.store[("rubric", "r1")] = {"criteria": ["a"]}
  assert await templates.get_rubric("r1") == {"criteria": ["a"]}
  f = any_feature(DEFAULT_RUBRICS)
  assert await templates.get_rubric(f) == DEFAULT_RUBRICS[f]
  repo.fail = True
  assert await templates.get_rubric(f) == DEFAULT_RUBRICS[f]
  with pytest.raises(KeyError):
    await templates.get_rubric("nope")


def test_rubric_to_text():
  assert templates.rubric_to_text({"criteria": ["a", "b"]}) == "- a\n- b"
  assert templates.rubric_to_text({}) == ""


@pytest.mark.asyncio
async def test_history(repo):
  assert await templates.get_template_history("prompt", "f", limit=3) == [{"type": "prompt", "feature": "f", "limit": 3}]


@pytest.mark.asyncio
async def test_save_prompt_existing_bumps_version(repo):
  repo.store[("prompt", "f")] = {"version": 2, "system": "old", "x": 1}
  res = await templates.save_prompt("f", {"system": "new"}, updated_by="u")
  assert res["version"] == 3 and res["system"] == "new" and res["x"] == 1 and res["saved"]
  assert repo.saved[0][4] == "Updated prompt for f" and repo.saved[0][3] == "u"


@pytest.mark.asyncio
async def test_save_prompt_new_feature_and_db_failure(repo):
  res = await templates.save_prompt("brand_new", {"system": "s"}, change_summary="c")
  assert res["version"] == 1 and res["allowed_sources"] == ["knowledge"]
  assert res["user_template"] == "{query}\n\n{context}"
  assert repo.saved[-1][4] == "c"
  repo.fail = True
  res = await templates.save_prompt("other_new", {"version": 5})
  assert res["version"] == 5 and "saved" not in res


@pytest.mark.asyncio
async def test_save_rubric(repo):
  f = any_feature(DEFAULT_RUBRICS)
  res = await templates.save_rubric(f, {"criteria": ["z"]})
  assert res["criteria"] == ["z"] and res["version"] == int(DEFAULT_RUBRICS[f].get("version") or 1) + 1
  repo.fail = True
  res = await templates.save_rubric(f, {"criteria": ["y"]})
  assert res["criteria"] == ["y"] and "saved" not in res
  with pytest.raises(KeyError):
    await templates.save_rubric("missing", {})


@pytest.mark.asyncio
async def test_reset_prompt_and_rubric(repo):
  fp, fr = any_feature(DEFAULT_PROMPTS), any_feature(DEFAULT_RUBRICS)
  repo.store[("prompt", fp)] = {"version": 7}
  res = await templates.reset_prompt(fp, updated_by="a")
  assert res["version"] == 8 and repo.saved[-1][4] == "Reset prompt to factory default"
  res = await templates.reset_rubric(fr)
  assert repo.saved[-1][4] == "Reset rubric to factory default" and res["saved"]
  with pytest.raises(KeyError):
    await templates.reset_prompt("nope")
  with pytest.raises(KeyError):
    await templates.reset_rubric("nope")
  repo.fail = True
  assert "saved" not in await templates.reset_prompt(fp)
  assert "saved" not in await templates.reset_rubric(fr)


def test_seeding_sync_path_runs_once(monkeypatch):
  r = FakeRepo()
  FakeUoW.repo = r
  monkeypatch.setattr(uow_mod, "AsyncUnitOfWork", FakeUoW)
  monkeypatch.setattr(templates, "_DB_SEEDED", False)
  templates.ensure_ai_files()
  assert r.seeded and templates._DB_SEEDED is True
  r.seeded = False
  templates.ensure_ai_templates_seeded()
  assert r.seeded is False




def test_seeding_failure_is_swallowed(monkeypatch):
  class Boom:
    def __init__(self):
      raise RuntimeError("no db")
  monkeypatch.setattr(uow_mod, "AsyncUnitOfWork", Boom)
  monkeypatch.setattr(templates, "_DB_SEEDED", False)
  templates.ensure_ai_templates_seeded()
  assert templates._DB_SEEDED is False
