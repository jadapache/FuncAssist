"""Unit tests for the async SQLAlchemy repositories (chat/history, templates, orgs, MCP, users...).

Most queries are simple equality filters that the in-memory FakeAsyncSession understands.
Statements it cannot evaluate (UPDATE, multi-column selects with .first(), coalesce ordering)
are exercised against a small recording stub defined here.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy.sql.dml import Update

from app.db.models import (
  AITemplateModel,
  AITemplateVersionModel,
  ChatMessageModel,
  ChatSessionModel,
  CorporateTemplateModel,
  UserModel,
)
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.corporate_template_repository import CorporateTemplateRepository
from app.db.repositories.history_repository import (
  ChatRepository,
  PRDRepository,
  StandupRepository,
  TestPlanRepository,
)
from app.db.repositories.mcp_server_repository import McpServerRepository
from app.db.repositories.organization_repository import OrganizationRepository
from app.db.repositories.template_repository import AITemplateRepository
from app.db.repositories.user_repository import UserRepository
from tests.fake_session import GLOBAL_FAKE_STORAGE, FakeAsyncSession

pytestmark = pytest.mark.asyncio


class GettableFakeSession(FakeAsyncSession):
  """FakeAsyncSession plus AsyncSession.get(), used by ChatRepository.save_message."""

  async def get(self, model_cls: Any, pk: Any) -> Any:
    return self.storage.tables.get(model_cls, {}).get(pk)


class _Row(tuple):
  pass


class _StubResult:
  def __init__(self, first: Any = None, rowcount: int = 0, items: list | None = None):
    self._first = first
    self.rowcount = rowcount
    self._items = items or []

  def first(self) -> Any:
    return self._first

  def scalars(self):
    items = self._items

    class _S:
      def all(self_inner):
        return list(items)

    return _S()


class RecordingSession:
  """Records executed statements and returns queued results."""

  def __init__(self, results: list[_StubResult]):
    self.results = list(results)
    self.statements: list[Any] = []
    self.flushed = 0

  async def execute(self, stmt: Any) -> _StubResult:
    self.statements.append(stmt)
    return self.results.pop(0)

  async def flush(self) -> None:
    self.flushed += 1


def _sql(stmt: Any) -> str:
  return str(stmt.compile(compile_kwargs={"literal_binds": False}))


@pytest.fixture
def session() -> GettableFakeSession:
  return GettableFakeSession(GLOBAL_FAKE_STORAGE)


# ---------------------------------------------------------------------------
# BaseRepository
# ---------------------------------------------------------------------------


async def test_base_repository_get_list_delete(session):
  repo = BaseRepository(session, UserModel)
  session.add(UserModel(id="u1", username="ana"))
  session.add(UserModel(id="u2", username="bob"))

  assert (await repo.get_by_id("u1")).username == "ana"
  assert await repo.get_by_id("missing") is None
  assert {u.id for u in await repo.list()} == {"u1", "u2"}
  assert len(await repo.list(limit=1)) == 1

  assert await repo.delete("u1") is True
  assert await repo.get_by_id("u1") is None
  assert await repo.delete("u1") is False


# ---------------------------------------------------------------------------
# ChatRepository
# ---------------------------------------------------------------------------


async def test_save_session_creates_with_defaults(session):
  repo = ChatRepository(session)
  out = await repo.save_session({"user_id": "u1"})
  assert out["id"]
  stored = GLOBAL_FAKE_STORAGE.tables[ChatSessionModel][out["id"]]
  assert stored.title == "Nueva conversación"
  assert stored.feature_slug == "general"
  assert stored.artifacts_json == "[]"
  assert stored.user_id == "u1"


async def test_save_session_partial_update_preserves_document_and_artifacts(session):
  repo = ChatRepository(session)
  await repo.save_session({
    "id": "s1",
    "name": "Original",
    "specification": "login",
    "documentContent": "# doc",
    "artifacts": [{"id": "a1"}],
    "activeArtifactId": "a1",
  })
  stored = GLOBAL_FAKE_STORAGE.tables[ChatSessionModel]["s1"]
  assert stored.feature_slug == "login"
  assert stored.active_artifact_id == "a1"

  # Update without document/artifacts must not wipe them; user_id is backfilled once.
  await repo.save_session({"id": "s1", "title": "Renamed", "user_id": "u9"})
  assert stored.title == "Renamed"
  assert stored.document_content == "# doc"
  assert json.loads(stored.artifacts_json) == [{"id": "a1"}]
  assert stored.user_id == "u9"
  assert stored.active_artifact_id == "a1"

  # Explicit document/artifacts replace, and existing owner is not overwritten.
  await repo.save_session({
    "id": "s1", "document_content": "new", "artifacts": [], "user_id": "other",
    "active_artifact_id": "a2",
  })
  assert stored.document_content == "new"
  assert stored.artifacts_json == "[]"
  assert stored.user_id == "u9"
  assert stored.active_artifact_id == "a2"


async def test_get_session_includes_messages_and_respects_owner(session):
  repo = ChatRepository(session)
  await repo.save_session({"id": "s1", "user_id": "u1"})
  await repo.save_message("s1", "user", "hola", user_id="u1")

  got = await repo.get_session("s1", user_id="u1")
  assert got is not None
  assert [m["content"] for m in got["messages"]] == ["hola"]
  assert await repo.get_session("s1", user_id="intruder") is None
  assert await repo.get_session("nope") is None


async def test_get_session_artifacts_variants(session):
  repo = ChatRepository(session)
  assert await repo.get_session_artifacts("missing") == []

  session.add(ChatSessionModel(id="ok", user_id="u1", title="t", artifacts_json=json.dumps([{"id": 1}, "junk"])))
  session.add(ChatSessionModel(id="bad", title="t", artifacts_json="{not json"))
  session.add(ChatSessionModel(id="dict", title="t", artifacts_json=json.dumps({"id": 1})))
  session.add(ChatSessionModel(id="empty", title="t", artifacts_json=""))

  assert await repo.get_session_artifacts("ok", user_id="u1") == [{"id": 1}]
  assert await repo.get_session_artifacts("ok", user_id="u2") == []
  assert await repo.get_session_artifacts("bad") == []
  assert await repo.get_session_artifacts("dict") == []
  assert await repo.get_session_artifacts("empty") == []


async def test_delete_session_removes_session_and_messages(session):
  repo = ChatRepository(session)
  await repo.save_session({"id": "s1", "user_id": "u1"})
  await repo.save_message("s1", "user", "a", user_id="u1")
  await repo.save_message("s2", "user", "b", user_id="u1")

  assert await repo.delete_session("s1", user_id="u1") is True
  assert "s1" not in GLOBAL_FAKE_STORAGE.tables[ChatSessionModel]
  remaining = [m.session_id for m in GLOBAL_FAKE_STORAGE.tables[ChatMessageModel].values()]
  assert remaining == ["s2"]


async def test_clear_session_only_removes_messages(session):
  repo = ChatRepository(session)
  await repo.save_session({"id": "s1"})
  await repo.save_message("s1", "user", "a")
  assert await repo.clear_session("s1") is True
  assert GLOBAL_FAKE_STORAGE.tables[ChatMessageModel] == {}
  assert "s1" in GLOBAL_FAKE_STORAGE.tables[ChatSessionModel]


async def test_save_message_serializes_and_touches_session(session):
  repo = ChatRepository(session)
  await repo.save_session({"id": "s1"})
  before = GLOBAL_FAKE_STORAGE.tables[ChatSessionModel]["s1"].updated_at
  msg = await repo.save_message(
    "s1", "assistant", "resp",
    context_sources=[{"id": "c1"}],
    attachments=[{"name": "f.txt"}],
    user_id="u1",
  )
  stored = GLOBAL_FAKE_STORAGE.tables[ChatMessageModel][msg["id"]]
  assert json.loads(stored.context_sources_json) == [{"id": "c1"}]
  assert json.loads(stored.attachments_json) == [{"name": "f.txt"}]
  after = GLOBAL_FAKE_STORAGE.tables[ChatSessionModel]["s1"].updated_at
  assert after is not None and after is not before


async def test_save_message_is_idempotent_by_id(session):
  repo = ChatRepository(session)
  first = await repo.save_message("s1", "user", "v1", id="m1", user_id="u1")
  assert first["id"] == "m1"

  # Same id/session/user: update in place.
  await repo.save_message(
    "s1", "user", "v2", id="m1", user_id="u1",
    context_sources=[{"x": 1}], attachments=[{"y": 2}],
  )
  msgs = GLOBAL_FAKE_STORAGE.tables[ChatMessageModel]
  assert list(msgs) == ["m1"]
  assert msgs["m1"].content == "v2"
  assert json.loads(msgs["m1"].context_sources_json) == [{"x": 1}]
  assert json.loads(msgs["m1"].attachments_json) == [{"y": 2}]

  # Identical resave: no change branch.
  again = await repo.save_message("s1", "user", "v2", id="m1", user_id="u1")
  assert again["content"] == "v2"






async def test_get_user_sessions_builds_filtered_ordered_query():
  rows = [ChatSessionModel(id="s1", title="t", feature_slug="f")]
  stub = RecordingSession([_StubResult(items=rows)])
  out = await ChatRepository(stub).get_user_sessions(user_id="u1", feature_slug="f", limit=5)
  assert [s["id"] for s in out] == ["s1"]
  sql = _sql(stub.statements[0])
  assert "coalesce(chat_sessions.updated_at, chat_sessions.created_at) DESC" in sql
  assert "chat_sessions.user_id = " in sql and "chat_sessions.feature_slug = " in sql
  assert "LIMIT" in sql

  stub2 = RecordingSession([_StubResult(items=[])])
  assert await ChatRepository(stub2).get_user_sessions(limit=0) == []
  sql2 = _sql(stub2.statements[0])
  assert "LIMIT" not in sql2 and "WHERE" not in sql2


async def test_get_history_summary():
  stub = RecordingSession([_StubResult(first=_Row(("k1", "summary")))])
  assert await ChatRepository(stub).get_history_summary("s1", user_id="u1") == ("k1", "summary")
  assert "chat_sessions.user_id" in _sql(stub.statements[0])

  for first in (None, _Row((None, "x")), _Row(("k", ""))):
    stub = RecordingSession([_StubResult(first=first)])
    assert await ChatRepository(stub).get_history_summary("s1") is None


async def test_save_history_summary_updates_without_bumping_updated_at():
  stub = RecordingSession([_StubResult(rowcount=1)])
  assert await ChatRepository(stub).save_history_summary("s1", "key", "sum", user_id="u1") is True
  stmt = stub.statements[0]
  assert isinstance(stmt, Update)
  sql = _sql(stmt)
  assert "history_summary=" in sql and "history_summary_key=" in sql
  # updated_at is assigned to itself so onupdate does not fire.
  assert "updated_at=chat_sessions.updated_at" in sql
  assert "chat_sessions.user_id = " in sql
  assert stub.flushed == 1

  stub = RecordingSession([_StubResult(rowcount=0)])
  assert await ChatRepository(stub).save_history_summary("missing", "k", "s") is False


# ---------------------------------------------------------------------------
# Standup / PRD / TestPlan
# ---------------------------------------------------------------------------


async def test_standup_repository(session):
  repo = StandupRepository(session)
  a = await repo.create_standup("t1", "c1", sources=["jira"], user_id="u1")
  await repo.create_standup("t2", "c2", user_id="u2")
  assert a["title"] == "t1"
  assert a["sources"] == ["jira"]
  mine = await repo.get_all_standups(user_id="u1")
  assert [s["title"] for s in mine] == ["t1"]
  assert len(await repo.get_all_standups(limit=0)) == 2


async def test_prd_repository(session):
  repo = PRDRepository(session)
  r = await repo.create_prd_review("PRD", "body", score=80, risk_level="LOW", user_id="u1")
  assert r["score"] == 80 and r["risk_level"] == "LOW"
  await repo.create_prd_review("Other", "x", user_id="u2")
  assert [x["prd_title"] for x in await repo.get_all_prd_reviews(user_id="u1")] == ["PRD"]
  assert len(await repo.get_all_prd_reviews(limit=0)) == 2


async def test_test_plan_repository(session):
  repo = TestPlanRepository(session)
  p = await repo.create_test_plan("Login", "steps", test_type="e2e", user_id="u1")
  assert p["feature_name"] == "Login" and p["test_type"] == "e2e"
  await repo.create_test_plan("Other", "x")
  assert [x["feature_name"] for x in await repo.get_all_test_plans(user_id="u1")] == ["Login"]
  assert len(await repo.get_all_test_plans(limit=1)) == 1
  assert len(await repo.get_all_test_plans(limit=0)) == 2


# ---------------------------------------------------------------------------
# AITemplateRepository
# ---------------------------------------------------------------------------


async def test_template_create_update_and_history(session):
  repo = AITemplateRepository(session)
  assert await repo.get_template("prompt", "chat") is None

  created = await repo.save_template_update(
    "prompt", "chat", {"system": "S1", "tag": "core", "id": "ignored", "version": 3}, updated_by="ana"
  )
  assert created["version"] == 3
  tmpl = GLOBAL_FAKE_STORAGE.tables[AITemplateModel]["prompt:chat"]
  payload = json.loads(tmpl.payload_json)
  assert payload == {"system": "S1", "tag": "core"}
  assert tmpl.updated_by == "ana"

  updated = await repo.save_template_update("prompt", "chat", {"user": "U"}, change_summary="add user")
  assert updated["version"] == 4
  merged = json.loads(tmpl.payload_json)
  assert merged["system"] == "S1" and merged["user"] == "U"
  assert tmpl.tag == "core"

  await repo.save_template_update("prompt", "chat", {"tag": "new"})
  assert tmpl.tag == "new"

  history = await repo.get_version_history("prompt", "chat")
  assert [v["version"] for v in history] == [5, 4, 3]
  assert history[1]["change_summary"] == "add user"
  assert history[2]["change_summary"] == "Created prompt for chat"
  assert len(await repo.get_version_history("prompt", "chat", limit=1)) == 1
  assert len(await repo.get_version_history("prompt", "chat", limit=0)) == 3

  got = await repo.get_template("prompt", "chat")
  assert got["feature"] == "chat"


async def test_template_list_by_type_and_tag(session):
  repo = AITemplateRepository(session)
  await repo.save_template_update("prompt", "b", {"tag": "x"})
  await repo.save_template_update("prompt", "a", {"tag": "y"})
  await repo.save_template_update("rubric", "c", {})
  assert [t["feature"] for t in await repo.list_templates("prompt")] == ["a", "b"]
  assert [t["feature"] for t in await repo.list_templates("prompt", tag="x")] == ["b"]


async def test_template_seed_defaults_skips_existing_and_removes_obsolete(session):
  repo = AITemplateRepository(session)
  await repo.save_template_update("prompt", "chat", {"system": "custom"})
  session.add(AITemplateModel(id="prompt:transcript_summary", template_type="prompt", feature="transcript_summary", version=1, payload_json="{}"))
  session.add(AITemplateModel(id="rubric:transcript_summary", template_type="rubric", feature="transcript_summary", version=1, payload_json="{}"))

  await repo.seed_defaults(
    {"chat": {"system": "default"}, "prd": {"system": "P", "version": 2, "tag": "t", "updated_by": "x"}},
    {"prd": {"criteria": ["a"]}},
  )
  tables = GLOBAL_FAKE_STORAGE.tables[AITemplateModel]
  assert "prompt:transcript_summary" not in tables
  assert "rubric:transcript_summary" not in tables
  assert json.loads(tables["prompt:chat"].payload_json) == {"system": "custom"}
  assert tables["prompt:prd"].version == 2 and tables["prompt:prd"].updated_by == "system"
  assert json.loads(tables["prompt:prd"].payload_json) == {"system": "P", "tag": "t"}
  assert tables["rubric:prd"].template_type == "rubric"
  seeds = [v for v in GLOBAL_FAKE_STORAGE.tables[AITemplateVersionModel].values() if v.change_summary == "Initial system seed"]
  assert {v.template_id for v in seeds} == {"prompt:prd", "rubric:prd"}


# ---------------------------------------------------------------------------
# OrganizationRepository
# ---------------------------------------------------------------------------


async def test_organization_repository_crud(session):
  repo = OrganizationRepository(session)
  org = await repo.create_organization("Acme", "acme")
  assert (await repo.get_by_id(org["id"]))["slug"] == "acme"
  assert (await repo.get_by_slug("acme"))["name"] == "Acme"
  assert await repo.get_by_id("x") is None
  assert await repo.get_by_slug("x") is None

  m = await repo.add_member(org["id"], "u1")
  assert m["role"] == "member"
  await repo.add_member(org["id"], "u2", role="admin")
  assert {x["user_id"] for x in await repo.list_members(org["id"])} == {"u1", "u2"}
  assert (await repo.get_member(org["id"], "u2"))["role"] == "admin"
  assert await repo.get_member(org["id"], "nobody") is None

  assert (await repo.update_member_role(org["id"], "u1", "owner"))["role"] == "owner"
  assert await repo.update_member_role(org["id"], "nobody", "owner") is None

  assert await repo.remove_member(org["id"], "u1") is True
  assert await repo.remove_member(org["id"], "u1") is False
  assert [x["user_id"] for x in await repo.list_members(org["id"])] == ["u2"]


# ---------------------------------------------------------------------------
# McpServerRepository
# ---------------------------------------------------------------------------


async def test_mcp_server_repository_crud(session):
  repo = McpServerRepository(session)
  tool = {"name": "snapshot", "read_only": True, "approved": True, "fingerprint": "f1"}
  s = await repo.create("u1", "  srv  ", " http://x/sse ", description=" d ", tools=[tool])
  assert s["name"] == "srv" and s["endpoint_url"] == "http://x/sse" and s["description"] == "d"
  assert s["status"] == "configured" and s["allowed_tools"] == ["snapshot"]
  assert s["tools"][0]["fingerprint"] == "f1" and s["tools"][0]["read_only"] is True

  bare = await repo.create("u1", "b", "http://y")
  assert bare["description"] == "" and bare["allowed_tools"] == [] and bare["tools"] == []

  assert (await repo.get_by_id(s["id"], user_id="u1"))["id"] == s["id"]
  assert await repo.get_by_id(s["id"], user_id="u2") is None
  assert (await repo.get_by_id(s["id"]))["id"] == s["id"]
  assert len(await repo.list_by_user("u1")) == 2
  assert await repo.list_by_user("u2") == []
  assert {x["id"] for x in await repo.list_all()} == {s["id"], bare["id"]}

  upd = await repo.update(s["id"], "u1", {
    "name": " n2 ", "description": " d2 ", "endpoint_url": " http://z ",
    "transport_type": "http", "auth_type": "bearer",
    "tools": [{"name": "b", "approved": True, "fingerprint": "x"}, {"name": "c"}, "legacy"],
    "status": None,
  })
  assert upd["name"] == "n2" and upd["description"] == "d2" and upd["endpoint_url"] == "http://z"
  assert upd["transport_type"] == "http" and upd["auth_type"] == "bearer" and upd["status"] == "configured"
  # only tools an administrator approved (with a pinned fingerprint) count as allowed
  assert upd["allowed_tools"] == ["b"]
  assert [t["name"] for t in upd["tools"]] == ["b", "c", "legacy"]
  assert await repo.update(s["id"], "u2", {"name": "hack"}) is None

  assert (await repo.update_status(s["id"], "u1", "connected"))["status"] == "connected"

  # administrators manage every server regardless of who registered it
  assert (await repo.update(s["id"], None, {"name": "by-admin"}))["name"] == "by-admin"
  assert (await repo.update_status(s["id"], None, "error"))["status"] == "error"
  assert await repo.update("missing", None, {"name": "x"}) is None

  assert await repo.delete(s["id"], "u2") is False
  assert await repo.delete(s["id"], "u1") is True
  assert await repo.delete(bare["id"]) is True
  assert await repo.get_by_id(s["id"]) is None
  assert await repo.list_all() == []


async def test_mcp_server_legacy_tool_names_authorize_nothing(session):
  repo = McpServerRepository(session)
  s = await repo.create("u1", "old", "http://x", tools=["a", "b"])  # bare names, as stored before tool approvals existed
  assert s["allowed_tools"] == []
  assert [(t["name"], t["approved"]) for t in s["tools"]] == [("a", False), ("b", False)]


# ---------------------------------------------------------------------------
# CorporateTemplateRepository
# ---------------------------------------------------------------------------


async def test_corporate_template_repository(session):
  repo = CorporateTemplateRepository(session)
  with pytest.raises(ValueError):
    await repo.upsert({"title": "no id"})

  created = await repo.upsert({"id": "t1", "title": "Zeta", "tags": ["a"], "custom_content": "X"})
  assert created["filename"] == "t1.docx" and created["stored_filename"] == "t1.docx"
  assert created["file_type"] == "docx" and created["module"] == "general" and created["file_size"] == 0
  assert created["tags"] == ["a"] and created["custom_content"] == "X"

  await repo.upsert({"id": "t2", "title": "Alpha"})
  assert [t["title"] for t in await repo.list()] == ["Alpha", "Zeta"]

  # Update keeps custom_content when not provided.
  updated = await repo.upsert({"id": "t1", "filename": "f.pdf", "file_type": "pdf", "file_size": "12", "module": "qa"})
  assert updated["title"] == "Plantilla Corporativa"
  assert updated["file_size"] == 12 and updated["module"] == "qa" and updated["stored_filename"] == "f.pdf"
  assert updated["custom_content"] == "X"
  updated = await repo.upsert({"id": "t1", "custom_content": "Y"})
  assert updated["custom_content"] == "Y"

  assert (await repo.get("t1"))["id"] == "t1"
  assert await repo.get("nope") is None
  assert await repo.delete("t1") is True
  assert await repo.delete("t1") is False
  assert "t1" not in GLOBAL_FAKE_STORAGE.tables[CorporateTemplateModel]


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------


async def test_user_repository_bootstrap_and_updates(session):
  repo = UserRepository(session)
  first = await repo.create_user_with_password("root", "h", "s", role="user", status="pending")
  assert first["role"] == "admin" and first["status"] == "approved"
  second = await repo.create_user_with_password("bob", "h", "s")
  assert second["role"] == "user" and second["status"] == "pending"
  assert await repo.count() == 2

  assert [u["username"] for u in await repo.get_pending_users()] == ["bob"]
  assert [u["username"] for u in await repo.get_approved_users()] == ["root"]

  assert (await repo.update_user_status(second["id"], "approved"))["status"] == "approved"
  assert await repo.update_user_status("missing", "approved") is None

  upd = await repo.update(second["id"], {"full_name": "Bob B", "not_a_column": 1})
  assert upd["full_name"] == "Bob B"
  assert not hasattr(GLOBAL_FAKE_STORAGE.tables[UserModel][second["id"]], "not_a_column")
  assert (await repo.update(second["id"], {}))["id"] == second["id"]
  assert await repo.update("missing", {"x": 1}) is None

  assert (await repo.get_by_username("bob"))["id"] == second["id"]
  assert await repo.delete(second["id"]) is True
  assert await repo.delete(second["id"]) is False
