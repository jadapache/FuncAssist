"""Chat persistence: session commit semantics, duplicate-free messages, history source and migration."""

import asyncio
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import database
from app.db.models import Base, ChatMessageModel, ChatSessionModel
from app.db.repositories.history_repository import ChatRepository


# ---------------------------------------------------------------- get_db commit semantics

@pytest.fixture
def async_session():
  session = MagicMock()
  session.commit = AsyncMock()
  session.rollback = AsyncMock()

  @asynccontextmanager
  async def _factory():
    yield session

  with patch.object(database, "_async_session_override", None), \
       patch.object(database, "get_async_engine"), \
       patch.object(database, "_async_session_factory", _factory):
    yield session


class TestSessionCommit:
  @pytest.mark.asyncio
  async def test_commits_on_success(self, async_session):
    async with database.get_db():
      pass
    async_session.commit.assert_awaited_once()
    async_session.rollback.assert_not_awaited()

  @pytest.mark.asyncio
  @pytest.mark.parametrize("exc", [ValueError("boom"), asyncio.CancelledError()])
  async def test_rolls_back_on_error_or_cancellation(self, async_session, exc):
    with pytest.raises(type(exc)):
      async with database.get_db():
        raise exc
    async_session.commit.assert_not_awaited()
    async_session.rollback.assert_awaited_once()

  @pytest.mark.asyncio
  async def test_failed_commit_rolls_back_and_raises(self, async_session):
    async_session.commit.side_effect = RuntimeError("constraint")
    with pytest.raises(RuntimeError):
      async with database.get_db():
        pass
    async_session.rollback.assert_awaited_once()

  def test_sync_session_commits_and_rolls_back(self):
    session = MagicMock()

    @contextmanager
    def _factory():
      yield session

    with patch.object(database, "_sync_session_override", None), \
         patch.object(database, "get_sync_engine"), \
         patch.object(database, "_sync_session_factory", _factory):
      with database.get_sync_db():
        pass
      with pytest.raises(KeyError):
        with database.get_sync_db():
          raise KeyError("x")
    assert session.commit.call_count == 1
    session.rollback.assert_called_once()


# ---------------------------------------------------------------- duplicate-free messages

class _AsyncAdapter:
  """Minimal AsyncSession facade over a sync SQLite session (aiosqlite is not installed)."""

  def __init__(self, session: Session):
    self._s = session

  def add(self, obj):
    self._s.add(obj)

  async def get(self, model, ident):
    return self._s.get(model, ident)

  async def execute(self, stmt):
    return self._s.execute(stmt)

  async def flush(self):
    self._s.flush()

  async def refresh(self, obj):
    self._s.refresh(obj)


@pytest.fixture
def repo():
  engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
  Base.metadata.create_all(engine, tables=[ChatSessionModel.__table__, ChatMessageModel.__table__])
  with Session(engine) as session:
    session.add(ChatSessionModel(id="c1", user_id="u1", title="t"))
    session.flush()
    yield ChatRepository(_AsyncAdapter(session))


async def _contents(repo, session_id="c1", user_id="u1"):
  return [m["content"] for m in await repo.get_session_messages(session_id, limit=0, user_id=user_id)]


async def _autosave(repo, messages):
  from app.api.drafts import SaveDraftRequest, save_draft

  with patch("app.api.drafts.save_draft_session", return_value={}):  # never write draft files to disk
    await save_draft(SaveDraftRequest(id="c1", messages=messages), current_user={"id": "u1"}, chat_repo=repo)


class TestMessageDeduplication:
  @pytest.mark.asyncio
  async def test_same_id_is_upserted(self, repo):
    await repo.save_message(session_id="c1", role="assistant", content="He elaborado...", user_id="u1", id="a1")
    await repo.save_message(session_id="c1", role="assistant", content="Texto visible", user_id="u1", id="a1")
    assert await _contents(repo) == ["Texto visible"]

  @pytest.mark.asyncio
  async def test_foreign_id_is_never_overwritten(self, repo):
    await repo.save_message(session_id="c1", role="user", content="mío", user_id="u1", id="m1")
    await repo.save_message(session_id="c2", role="user", content="ajeno", user_id="u2", id="m1")
    assert await _contents(repo) == ["mío"]
    assert await _contents(repo, "c2", "u2") == ["ajeno"]

  @pytest.mark.asyncio
  async def test_agent_and_autosave_produce_one_turn(self, repo):
    await _autosave(repo, [{"id": "u-1", "role": "user", "content": "genera un plan"}])
    await repo.save_message(session_id="c1", role="user", content="genera un plan", user_id="u1", id="u-1")
    await repo.save_message(session_id="c1", role="assistant", content="He elaborado el documento.", user_id="u1", id="a-1")
    await _autosave(repo, [
      {"id": "u-1", "role": "user", "content": "genera un plan"},
      {"id": "a-1", "role": "assistant", "content": "Listo: plan en el panel."},
    ])
    assert await _contents(repo) == ["genera un plan", "Listo: plan en el panel."]

  @pytest.mark.asyncio
  async def test_repeated_short_answers_are_kept(self, repo):
    await _autosave(repo, [
      {"id": "u-1", "role": "user", "content": "sí"},
      {"id": "a-1", "role": "assistant", "content": "¿Continúo?"},
      {"id": "u-2", "role": "user", "content": "sí"},
    ])
    assert await _contents(repo) == ["sí", "¿Continúo?", "sí"]


# ---------------------------------------------------------------- history source

class TestHistorySource:
  @pytest.mark.asyncio
  async def test_prefers_persisted_messages_then_client_context(self):
    from app.api.document_agent import AgenticPromptRequest, _resolve_chat_history

    chat_repo = MagicMock()
    chat_repo.get_session_messages = AsyncMock(return_value=[
      {"role": "user", "content": "a"},
      {"role": "assistant", "content": "b"},
    ])
    req = AgenticPromptRequest(query="q", conversationId="c1", chat_context=["user: viejo"])
    assert await _resolve_chat_history(req, chat_repo, "u1") == [
      {"role": "user", "content": "a"},
      {"role": "assistant", "content": "b"},
    ]
    chat_repo.get_session_messages.assert_awaited_once_with("c1", limit=0, user_id="u1")

    chat_repo.get_session_messages = AsyncMock(return_value=[])
    assert await _resolve_chat_history(req, chat_repo, "u1") == ["user: viejo"]


# ---------------------------------------------------------------- schema migration

class TestSummaryColumnsMigration:
  @staticmethod
  def _patched(engine):
    @contextmanager
    def _db():
      with Session(engine) as s:
        yield s
    return patch("app.core.chat_history_migration.get_sync_db", _db)

  def test_idempotent_apply_and_rollback(self):
    from app.core.chat_history_migration import (
      migrate_chat_history_summary_if_needed,
      rollback_chat_history_summary,
    )

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
      conn.execute(text("CREATE TABLE chat_sessions (id VARCHAR(36) PRIMARY KEY, title VARCHAR)"))
      conn.execute(text("INSERT INTO chat_sessions (id, title) VALUES ('s1', 't')"))

    with self._patched(engine):
      assert len(migrate_chat_history_summary_if_needed()) == 3
      assert migrate_chat_history_summary_if_needed() == []
      with engine.connect() as conn:
        assert conn.execute(text("SELECT title FROM chat_sessions")).scalar() == "t"
      assert len(rollback_chat_history_summary()) == 3
    assert "history_summary" not in {c["name"] for c in inspect(engine).get_columns("chat_sessions")}

  def test_missing_table_is_noop(self):
    from app.core.chat_history_migration import migrate_chat_history_summary_if_needed

    with self._patched(create_engine("sqlite://")):
      assert migrate_chat_history_summary_if_needed() == []
