"""Core helpers: exceptions, redis, RLS context, index refresher, migrations, OAuth config, validator."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import exceptions as exc_mod


# ---------------------------------------------------------------- exceptions

@pytest.mark.parametrize(
  "exc, status, detail",
  [
    (exc_mod.BaseApplicationException(), 500, "Internal server error"),
    (exc_mod.BaseApplicationException("boom", 418, {"X": "1"}), 418, "boom"),
    (exc_mod.FeatureNotFoundError("User"), 404, "User not found"),
    (exc_mod.FeatureNotFoundError("User", "u1"), 404, "User 'u1' not found"),
    (exc_mod.MissingContextError("org"), 400, "Missing org"),
    (exc_mod.MissingContextError("org", "no header"), 400, "Missing org: no header"),
    (exc_mod.ValidationError("name", "too long"), 422, "Validation failed for 'name': too long"),
    (exc_mod.IntegrationError("Jira"), 502, "Jira integration failed"),
    (exc_mod.IntegrationError("Jira", "401"), 502, "Jira integration failed: 401"),
    (exc_mod.AIProviderError("openai", "down"), 502, "openai provider error: down"),
    (exc_mod.AIProviderError("openai", "no key", is_config_error=True), 400, "openai provider error: no key"),
    (exc_mod.DuplicateResourceError("Tpl"), 409, "Tpl already exists"),
    (exc_mod.DuplicateResourceError("Tpl", "a"), 409, "Tpl 'a' already exists"),
    (exc_mod.OperationNotAllowedError("del"), 403, "Operation 'del' not allowed"),
    (exc_mod.OperationNotAllowedError("del", "locked"), 403, "Operation 'del' not allowed: locked"),
    (exc_mod.StorageError("write"), 500, "Storage operation 'write' failed"),
    (exc_mod.StorageError("write", "disk"), 500, "Storage operation 'write' failed: disk"),
    (exc_mod.AudioAnalysisError("bad"), 422, "Audio analysis failed: bad"),
    (exc_mod.AudioAnalysisError("bad", "a.mp3"), 422, "File 'a.mp3': Audio analysis failed: bad"),
    (exc_mod.FFmpegError("fail"), 422, "FFmpeg error: fail"),
    (exc_mod.FFmpegError("fail", "err", 2), 422, "FFmpeg error: fail (exit code: 2)"),
    (exc_mod.ChunkingError("x"), 422, "Chunking failed: x"),
    (exc_mod.ChunkingError("x", 0), 422, "Chunk 0: Chunking failed: x"),
    (exc_mod.TranscriptionError("t"), 422, "Transcription error: t"),
    (exc_mod.TranscriptionError("t", 3), 422, "Chunk 3: Transcription error: t"),
  ],
)
def test_exception_status_and_detail(exc, status, detail):
  assert exc.status_code == status
  assert exc.detail == detail


def test_exception_extra_attributes():
  e = exc_mod.FFmpegError("fail", "stderr-text", 1, headers={"A": "b"})
  assert e.stderr == "stderr-text" and e.returncode == 1 and e.headers == {"A": "b"}
  assert exc_mod.TranscriptionError("t", 5).chunk_index == 5


# ---------------------------------------------------------------- redis

@pytest.fixture
def redis_mod(monkeypatch):
  from app.core import redis as mod
  monkeypatch.setattr(mod, "_redis_client", None)
  yield mod
  mod._redis_client = None


def test_redis_requires_url(redis_mod, monkeypatch):
  monkeypatch.setattr(redis_mod, "get_settings", lambda: SimpleNamespace(valkey_url="  "))
  with pytest.raises(RuntimeError, match="VALKEY_URL"):
    redis_mod.get_redis_client()


def test_redis_client_is_cached(redis_mod, monkeypatch):
  calls = []
  fake = object()
  monkeypatch.setattr(redis_mod, "get_settings", lambda: SimpleNamespace(valkey_url=" redis://h:1/0 "))
  monkeypatch.setattr(redis_mod.aioredis, "from_url", lambda url, **kw: calls.append((url, kw)) or fake)
  assert redis_mod.get_redis_client() is fake
  assert redis_mod.get_redis_client() is fake
  assert calls == [("redis://h:1/0", {"encoding": "utf-8", "decode_responses": True})]


@pytest.mark.asyncio
async def test_redis_init_and_close(redis_mod, monkeypatch):
  client = MagicMock()
  client.ping = AsyncMock(return_value=True)
  client.aclose = AsyncMock()
  monkeypatch.setattr(redis_mod, "_redis_client", client)
  await redis_mod.init_redis()
  client.ping.assert_awaited_once()

  client.ping = AsyncMock(side_effect=ConnectionError("refused"))
  monkeypatch.setattr(redis_mod, "get_settings", lambda: SimpleNamespace(valkey_url="redis://x"))
  with pytest.raises(RuntimeError, match="Could not connect to Valkey cache at redis://x: refused"):
    await redis_mod.init_redis()

  await redis_mod.close_redis_client()
  client.aclose.assert_awaited_once()
  assert redis_mod._redis_client is None
  await redis_mod.close_redis_client()  # no-op when already closed


# ---------------------------------------------------------------- rls

def test_rls_context_sets_and_resets():
  from app.core.rls_context import reset_rls_context, set_rls_context
  s = MagicMock()
  set_rls_context(s)  # nothing to do
  assert s.execute.call_count == 0
  set_rls_context(s, user_id="u", org_id="o")
  params = [c.args[1] for c in s.execute.call_args_list]
  assert params == [{"uid": "u"}, {"oid": "o"}]
  set_rls_context(s, org_id="o2")
  assert s.execute.call_args.args[1] == {"oid": "o2"}

  bad = MagicMock()
  bad.execute.side_effect = RuntimeError("not pg")
  set_rls_context(bad, user_id="u")  # swallowed
  reset_rls_context(bad)  # swallowed
  reset_rls_context(s)
  assert "RESET app.current_org_id" in str(s.execute.call_args.args[0])


# ---------------------------------------------------------------- index refresher

@pytest.mark.asyncio
async def test_frontier_refresh_throttles_and_swallows(monkeypatch):
  from app.core import index_refresher as ir
  import app.ai.frontier_sync as fs

  calls = []

  async def fake_sync(force_remote=False):
    calls.append(force_remote)
    return {"status": "ok", "models_count": 3}

  monkeypatch.setattr(fs, "sync_frontier_models_catalog", fake_sync)
  monkeypatch.setattr(ir, "_last_frontier_sync_ts", 0.0)
  monkeypatch.setattr(ir.time, "monotonic", lambda: 10_000.0)
  await ir._refresh_frontier_models_catalog()
  await ir._refresh_frontier_models_catalog()  # throttled
  assert calls == [False]
  await ir._refresh_frontier_models_catalog(force=True)
  assert calls == [False, True]

  async def failing(force_remote=False):
    raise RuntimeError("down")

  monkeypatch.setattr(fs, "sync_frontier_models_catalog", failing)
  await ir._refresh_frontier_models_catalog(force=True)  # must not raise


@pytest.mark.asyncio
async def test_run_index_refresher_loop(monkeypatch):
  from app.core import index_refresher as ir

  refresh_calls = []

  async def fake_refresh(force=False):
    refresh_calls.append(force)
    if len(refresh_calls) == 2:
      raise ValueError("iteration error")

  sleeps = []
  real_sleep = asyncio.sleep

  async def fake_sleep(sec):
    sleeps.append(sec)
    if len(sleeps) >= 5:
      raise asyncio.CancelledError()
    await real_sleep(0)

  monkeypatch.setattr(ir, "_refresh_frontier_models_catalog", fake_refresh)
  monkeypatch.setattr(ir.asyncio, "sleep", fake_sleep)
  await ir.run_index_refresher()
  await real_sleep(0)
  assert ir.REFRESH_INTERVAL_SECONDS in sleeps and 3 in sleeps
  assert len(refresh_calls) >= 2


# ---------------------------------------------------------------- schema migrations

class FakeInspector:
  def __init__(self, has_table=True, columns=()):
    self._has = has_table
    self._cols = columns

  def has_table(self, name):
    return self._has

  def get_columns(self, name):
    return [{"name": c} for c in self._cols]


def _session(dialect="postgresql", lock_fails=False, fail_on=None):
  s = MagicMock()
  s.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
  executed = []

  def execute(stmt, *a):
    sql = str(stmt)
    executed.append(sql)
    if lock_fails and "advisory" in sql:
      raise RuntimeError("no lock")
    if fail_on and fail_on in sql:
      raise RuntimeError("ddl failed")

  s.execute.side_effect = execute
  s.executed = executed
  return s


def _patch_db(monkeypatch, mod, session, inspector=None):
  @contextmanager
  def db():
    yield session
  monkeypatch.setattr(mod, "get_sync_db", db)
  if inspector is not None:
    monkeypatch.setattr(mod, "inspect", lambda bind: inspector)


def test_chat_history_migration_adds_missing_columns_pg(monkeypatch):
  from app.core import chat_history_migration as m
  s = _session()
  _patch_db(monkeypatch, m, s, FakeInspector(columns=["history_summary"]))
  assert m.migrate_chat_history_summary_if_needed() == ["history_summary_key", "history_summary_updated_at"]
  assert any("ADD COLUMN IF NOT EXISTS history_summary_key VARCHAR(80)" in q for q in s.executed)
  s.commit.assert_called_once()
  s.rollback.assert_called_once()  # releases advisory lock


def test_chat_history_migration_generic_dialect_and_noop(monkeypatch):
  from app.core import chat_history_migration as m
  s = _session(dialect="sqlite")
  _patch_db(monkeypatch, m, s, FakeInspector(columns=[]))
  assert len(m.migrate_chat_history_summary_if_needed()) == 3
  assert any("ADD COLUMN history_summary_updated_at TIMESTAMP;" in q for q in s.executed)
  s.rollback.assert_not_called()

  s2 = _session(lock_fails=True)
  _patch_db(monkeypatch, m, s2, FakeInspector(columns=list(m.COLUMNS)))
  assert m.migrate_chat_history_summary_if_needed() == []
  s2.rollback.assert_not_called()

  s3 = _session()
  _patch_db(monkeypatch, m, s3, FakeInspector(has_table=False))
  assert m.migrate_chat_history_summary_if_needed() == []
  s3.commit.assert_not_called()


def test_chat_history_migration_failure_raises(monkeypatch):
  from app.core import chat_history_migration as m
  s = _session(fail_on="ALTER TABLE")
  _patch_db(monkeypatch, m, s, FakeInspector(columns=[]))
  with pytest.raises(RuntimeError, match="Chat history summary migration failed: ddl failed"):
    m.migrate_chat_history_summary_if_needed()


def test_chat_history_rollback(monkeypatch):
  from app.core import chat_history_migration as m
  s = _session()
  _patch_db(monkeypatch, m, s, FakeInspector(columns=["history_summary", "other"]))
  assert m.rollback_chat_history_summary() == ["history_summary"]
  _patch_db(monkeypatch, m, _session(), FakeInspector(has_table=False))
  assert m.rollback_chat_history_summary() == []


def test_transcription_migration(monkeypatch):
  from app.core import transcription_migration as m
  s = _session()
  _patch_db(monkeypatch, m, s, FakeInspector(columns=["user_id", "progress_json"]))
  assert m.migrate_transcriptions_if_needed() == ["error_code", "started_at", "finished_at"]
  assert any(m.INDEX_NAME in q for q in s.executed)
  s.rollback.assert_called_once()

  s2 = _session(dialect="sqlite")
  _patch_db(monkeypatch, m, s2, FakeInspector(columns=[]))
  assert len(m.migrate_transcriptions_if_needed()) == 5
  assert not any(m.INDEX_NAME in q for q in s2.executed)

  s3 = _session(lock_fails=True)
  _patch_db(monkeypatch, m, s3, FakeInspector(has_table=False))
  assert m.migrate_transcriptions_if_needed() == []

  s4 = _session(fail_on="CREATE INDEX")
  _patch_db(monkeypatch, m, s4, FakeInspector(columns=list(m.COLUMNS)))
  with pytest.raises(RuntimeError, match="Transcription schema migration failed"):
    m.migrate_transcriptions_if_needed()


def test_integration_migration(monkeypatch):
  from app.core import integration_migration as m
  s = _session()
  bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), _run_ddl_visitor=lambda *a, **k: None)
  s.get_bind.return_value = bind
  created = []
  monkeypatch.setattr(m.Base.metadata, "create_all", lambda b, tables: created.append([t.name for t in tables]))
  _patch_db(monkeypatch, m, s)
  m.migrate_integrations_schema_if_needed()
  assert created == [["user_integrations", "mcp_servers"]]
  assert any("uq_user_integrations_user_provider" in q for q in s.executed)
  s.commit.assert_called_once()
  s.rollback.assert_called_once()

  s2 = _session(lock_fails=True)  # no _run_ddl_visitor attribute on bind
  _patch_db(monkeypatch, m, s2)
  m.migrate_integrations_schema_if_needed()
  s2.rollback.assert_not_called()

  s3 = _session(fail_on="ai_models_catalog")
  _patch_db(monkeypatch, m, s3)
  with pytest.raises(RuntimeError, match="integrations schema migration failed"):
    m.migrate_integrations_schema_if_needed()


# ---------------------------------------------------------------- path migration

def _patch_paths(monkeypatch, tmp_path):
  from app.core import migration as m
  old = tmp_path / "local"
  new = tmp_path / "userdata"
  sentinel = tmp_path / "settings" / ".migrated_v2"
  monkeypatch.setattr(m, "OLD_LOCAL_DIR", old)
  monkeypatch.setattr(m, "USER_DATA_DIR", new)
  monkeypatch.setattr(m, "SENTINEL_FILE", sentinel)
  return m, old, new, sentinel


def test_path_migration_without_legacy_dir(monkeypatch, tmp_path):
  m, old, new, sentinel = _patch_paths(monkeypatch, tmp_path)
  m.migrate_paths_if_needed()
  assert sentinel.read_text(encoding="utf-8") == "done"
  assert not new.exists()


def test_path_migration_copies_and_merges(monkeypatch, tmp_path):
  m, old, new, sentinel = _patch_paths(monkeypatch, tmp_path)
  (old / "settings").mkdir(parents=True)
  (old / "settings" / "a.json").write_text("A")
  (old / "history" / "sub").mkdir(parents=True)
  (old / "history" / "sub" / "h.json").write_text("H-old")
  (old / "history" / "keep.json").write_text("old")
  (new / "history").mkdir(parents=True)
  (new / "history" / "keep.json").write_text("new")

  m.migrate_paths_if_needed()
  assert (new / "settings" / "a.json").read_text() == "A"
  assert (new / "history" / "sub" / "h.json").read_text() == "H-old"
  assert (new / "history" / "keep.json").read_text() == "new"  # never overwritten
  assert sentinel.exists()

  # Sentinel short-circuits a second run.
  (old / "templates").mkdir()
  m.migrate_paths_if_needed()
  assert not (new / "templates").exists()


def test_path_migration_copy_errors_are_logged(monkeypatch, tmp_path):
  m, old, new, sentinel = _patch_paths(monkeypatch, tmp_path)
  (old / "ai").mkdir(parents=True)
  (old / "knowledge").mkdir(parents=True)
  (old / "knowledge" / "k.txt").write_text("k")
  (new / "knowledge").mkdir(parents=True)

  def boom(*a, **k):
    raise OSError("denied")

  monkeypatch.setattr(m.shutil, "copytree", boom)
  monkeypatch.setattr(m.shutil, "copy2", boom)
  m.migrate_paths_if_needed()
  assert sentinel.exists()
  assert not (new / "ai").exists()
  assert not (new / "knowledge" / "k.txt").exists()


def test_json_history_aliases():
  from app.core import json_history as jh
  assert jh.JsonChatRepository is jh.ChatRepository
  assert jh.JsonTestPlanRepository is jh.TestPlanRepository
  assert set(jh.__all__) >= {"JsonPRDRepository", "StandupRepository"}


# ---------------------------------------------------------------- integration_config

@pytest.fixture
def oauth_env(monkeypatch):
  from app.core import integration_config as ic
  store: dict = {}
  settings = SimpleNamespace(jira_client_id="", jira_client_secret="", jira_redirect_uri="")
  monkeypatch.setattr(ic, "get_settings", lambda: settings)
  monkeypatch.setattr(ic, "load_app_settings", lambda: dict(store))
  monkeypatch.setattr(ic, "save_app_settings", lambda patch: store.update(patch))
  return ic, store, settings


def test_oauth_config_defaults_env_and_local(oauth_env):
  ic, store, settings = oauth_env
  cfg = ic.get_jira_oauth_config()
  assert cfg["configured"] is False and cfg["source"] == "none"
  assert cfg["redirect_uri"].endswith("/jira/callback")

  settings.jira_client_id, settings.jira_client_secret = "envid", "envsec"
  jira = ic.get_jira_oauth_config()
  assert jira["configured"] and jira["source"] == "env" and jira["client_id"] == "envid"

  store["jira_oauth"] = {"client_id": " localid ", "client_secret": "s"}
  jira = ic.get_jira_oauth_config()
  assert jira["client_id"] == "localid" and jira["source"] == "local"


def test_only_jira_has_oauth_config(oauth_env):
  ic, _, _ = oauth_env
  for name in ("get_github_oauth_config", "get_gitlab_oauth_config", "save_github_oauth_config",
               "save_gitlab_oauth_config", "get_github_oauth_public", "get_gitlab_oauth_public"):
    assert not hasattr(ic, name)


def test_oauth_public_masks_and_save(oauth_env):
  ic, store, settings = oauth_env
  pub = ic.save_jira_oauth_config(client_id=" abcdefghijkl ", client_secret=" sec ", redirect_uri=" http://r ")
  assert store["jira_oauth"] == {"client_id": "abcdefghijkl", "client_secret": "sec", "redirect_uri": "http://r"}
  assert pub["client_id"] == "abcdefgh…" and pub["client_secret_set"] and pub["configured"]
  assert pub["scopes"] and "scope_guide" in pub

  # Blank secret keeps existing one.
  ic.save_jira_oauth_config(client_id="short", client_secret="  ")
  assert store["jira_oauth"]["client_secret"] == "sec"
  assert ic.get_jira_oauth_public()["client_id"] == "short"


# ---------------------------------------------------------------- document agent validator

from app.core.document_agent import schema as ds  # noqa: E402
from app.core.document_agent.validator import DocumentOperationValidator as V, ValidationError as DVError  # noqa: E402


def _state(**kw):
  base = dict(
    document_id="d", sections=[ds.DocumentSection(id="s1", title="Observaciónes Generales")],
    tags_present=["{{FECHA}}"], tables_summary=[],
  )
  base.update(kw)
  return ds.CanonicalDocumentState(**base)


def T(**kw):
  return ds.TargetLocator(**kw)


def test_validator_resolve_target():
  st = _state()
  assert V.resolve_target(T(section_title="observaciones"), st)[0] is True
  ok, msg = V.resolve_target(T(tag="{{fecha}}"), st)
  assert ok and "FECHA" in msg
  ok, msg = V.resolve_target(T(section_title="Nope", tag="X", anchor_text="abc"), st)
  assert not ok and "section: Nope" in msg and "tag: X" in msg and "anchor: 'abc'" in msg
  assert V.resolve_target(T(), st) == (False, "Target not found in document: Unknown target locator")
  sheet = _state(kind="spreadsheet")
  assert V.resolve_target(T(cell_range="A1:B2"), sheet)[0]
  blank = ds.CanonicalDocumentState(document_id="b")
  assert V.resolve_target(T(section_title="x"), blank) == (True, "Document is currently blank; appending to root.")
  assert DVError("m", field="f").field == "f"


def test_validator_operations():
  st = _state()
  good, bad = T(section_title="Observaciones"), T(section_title="Missing")
  asset = ds.AssetLocator(asset_id="a1")

  assert V.validate(ds.InsertImageOperation(target=good, asset=asset), st, ["a1"])[0]
  assert not V.validate(ds.InsertImageOperation(target=bad, asset=asset), st)[0]
  assert V.validate(ds.InsertImageOperation(target=good, asset=ds.AssetLocator(asset_id="")), st) == (
    False, "Image operation missing both asset_id and url.")
  ok, msg = V.validate(ds.InsertImageOperation(target=good, asset=asset), st, ["other"])
  assert not ok and "not in available assets" in msg
  remote = ds.AssetLocator(asset_id="zz", url="https://img/x.png")
  assert V.validate(ds.InsertImageOperation(target=good, asset=remote), st, ["other"])[0]

  assert V.validate(ds.InsertTextOperation(target=good, content="  "), st) == (False, "Cannot insert empty text content.")
  assert not V.validate(ds.InsertTextOperation(target=bad, content="x"), st)[0]
  assert V.validate(ds.InsertTextOperation(target=good, content="x"), st)[0]

  assert V.validate(ds.ReplaceContentOperation(target=good, new_content="n"), st)[0]
  assert not V.validate(ds.ReplaceContentOperation(target=bad, new_content="n"), st)[0]

  assert V.validate(ds.UpdateTableOperation(target=T()), _state(kind="spreadsheet"))[0]
  assert not V.validate(ds.UpdateTableOperation(target=T()), st)[0]
  assert V.validate(ds.UpdateTableOperation(target=good), st)[0]

  assert V.validate(ds.CreateTableOperation(target=good, headers=[]), st) == (False, "Cannot create table without headers.")
  assert not V.validate(ds.CreateTableOperation(target=bad, headers=["h"]), st)[0]
  assert V.validate(ds.CreateTableOperation(target=good, headers=["h"]), st)[0]

  assert V.validate(ds.DeleteContentOperation(target=good), st)[0]
  assert not V.validate(ds.DeleteContentOperation(target=bad), st)[0]

  assert V.validate(ds.MoveContentOperation(source_target=good, destination_target=good), st)[0]
  assert "source target" in V.validate(ds.MoveContentOperation(source_target=bad, destination_target=good), st)[1]
  assert "destination target" in V.validate(ds.MoveContentOperation(source_target=good, destination_target=bad), st)[1]

  assert V.validate(ds.FindTextOperation(query="q"), st) == (True, "Operation 'find_text' validated.")
