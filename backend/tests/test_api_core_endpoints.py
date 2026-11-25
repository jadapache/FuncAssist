"""HTTP tests for settings, user, drafts, history, knowledge and auth endpoints, plus the auth deps."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import auth, deps, drafts, history, knowledge, settings as settings_api, user


class Recorder:
  """Repository double: records calls and returns canned values per method name."""

  def __init__(self, **returns):
    self.calls: list[tuple[str, tuple, dict]] = []
    self.returns = returns

  def __getattr__(self, name):
    if name.startswith("__"):
      raise AttributeError(name)

    async def method(*args, **kwargs):
      self.calls.append((name, args, kwargs))
      val = self.returns.get(name)
      if isinstance(val, Exception):
        raise val
      return val(*args, **kwargs) if callable(val) else val

    return method

  def names(self):
    return [c[0] for c in self.calls]


def _client(router, overrides=None, prefix="/api") -> TestClient:
  app = FastAPI(version="9.9.9")
  app.include_router(router, prefix=prefix)
  def _provider(val):
    # No default args: FastAPI would treat them as query params and deep-copy the value.
    return lambda: val

  for dep, val in (overrides or {}).items():
    app.dependency_overrides[dep] = _provider(val)
  return TestClient(app, base_url="https://testserver")


# --------------------------------------------------------------------------- settings


class TestSettingsAPI:
  @pytest.fixture(autouse=True)
  def fakes(self, monkeypatch):
    store = {"theme": "dark"}
    monkeypatch.setattr(settings_api, "load_app_settings", lambda: dict(store))

    def save(payload):
      store.update(payload)
      return dict(store)

    monkeypatch.setattr(settings_api, "save_app_settings", save)
    monkeypatch.setattr(settings_api, "get_jira_oauth_public", lambda: {"provider": "jira"})
    monkeypatch.setattr(settings_api, "save_jira_oauth_config", lambda **kw: {"provider": "jira", **kw})
    self.c = _client(settings_api.router)

  def test_get_and_update(self):
    assert self.c.get("/api/settings").json() == {"theme": "dark", "version": "9.9.9"}
    r = self.c.put("/api/settings", json={"theme": "light", "selected_repos": ["a/b"]})
    assert r.json() == {"theme": "light", "selected_repos": ["a/b"]}

  def test_oauth_endpoints(self):
    assert self.c.get("/api/settings/jira-oauth").json() == {"provider": "jira"}
    r = self.c.put("/api/settings/jira-oauth", json={"client_id": "cid", "client_secret": "s"})
    body = r.json()
    assert body["provider"] == "jira" and body["client_id"] == "cid" and body["client_secret"] == "s"
    assert self.c.put("/api/settings/jira-oauth", json={"client_id": ""}).status_code == 422

  @pytest.mark.parametrize("kind", ["github", "gitlab"])
  def test_github_and_gitlab_have_no_oauth_settings(self, kind):
    assert self.c.get(f"/api/settings/{kind}-oauth").status_code == 404
    assert self.c.put(f"/api/settings/{kind}-oauth", json={"client_id": "cid"}).status_code in (404, 405)

  def test_health(self, monkeypatch):
    monkeypatch.setenv("APP_BUILD_ID", "b42")
    c = _client(settings_api.health_router, prefix="")
    for path in ("/health", "/api/health", "/api/health/ready"):
      assert c.get(path).json() == {"status": "ok", "app": "FuncAssist", "version": "9.9.9", "build": "b42"}
    monkeypatch.delenv("APP_BUILD_ID")
    monkeypatch.delenv("APP_VERSION", raising=False)
    assert c.get("/health").json()["build"] is None


# --------------------------------------------------------------------------- user


class TestUserAPI:
  @pytest.fixture(autouse=True)
  def fakes(self, monkeypatch, tmp_path):
    self.prefs: dict = {}
    monkeypatch.setattr(user, "get_user_preferences", lambda uid: dict(self.prefs))
    monkeypatch.setattr(user, "save_user_preferences", lambda uid, p: self.prefs.update(p))
    monkeypatch.setattr(user, "USER_DOCUMENTS_DIR", tmp_path)
    self.tmp = tmp_path
    self.c = _client(user.router)

  def test_profile_defaults_to_current_user(self):
    assert self.c.get("/api/user/profile").json() == {
      "display_name": "Usuario", "user_role": "admin", "documents_path": str(self.tmp),
    }

  def test_update_profile(self):
    r = self.c.put("/api/user/profile", json={"display_name": " Ana ", "user_role": "qa", "documents_path": " /d "})
    assert r.json() == {"display_name": "Ana", "user_role": "qa", "documents_path": "/d"}
    assert self.prefs == {"display_name": "Ana", "user_role": "qa", "documents_path": "/d"}

  def test_update_noop_and_validation(self):
    assert self.c.put("/api/user/profile", json={}).json()["display_name"] == "Usuario"
    assert self.prefs == {}
    assert self.c.put("/api/user/profile", json={"user_role": "boss"}).status_code == 422

  def test_setup(self):
    r = self.c.post("/api/user/setup", json={"display_name": " Bo ", "user_role": "dev", "documents_path": " /x "})
    assert r.status_code == 200 and r.json()["user_role"] == "dev"
    assert self.prefs == {"display_name": "Bo", "user_role": "dev", "documents_path": "/x"}
    self.prefs.clear()
    self.c.post("/api/user/setup", json={"display_name": "Bo", "user_role": "dev"})
    assert "documents_path" not in self.prefs
    assert self.c.post("/api/user/setup", json={"display_name": "", "user_role": "dev"}).status_code == 422


# --------------------------------------------------------------------------- drafts


class TestDraftsAPI:
  @pytest.fixture(autouse=True)
  def fakes(self, monkeypatch):
    self.saved_files = []
    monkeypatch.setattr(drafts, "save_draft_session", lambda p: self.saved_files.append(p) or {"id": p.get("id")})
    monkeypatch.setattr(drafts, "list_generated_drafts", lambda specification=None, user_id=None: [{"spec": specification, "u": user_id}])
    monkeypatch.setattr(drafts, "get_generated_draft", lambda did: {"id": did} if did == "d1" else None)
    self.deleted = []
    monkeypatch.setattr(drafts, "delete_generated_draft", lambda did: self.deleted.append(did) or True)

  def _c(self, repo):
    return _client(drafts.router, {deps.get_chat_repository: repo})

  def test_save_dedupes_messages(self):
    existing = [
      {"id": "m1", "role": "user", "content": "hola"},
      {"role": "assistant", "content": "ok"},
    ]
    repo = Recorder(get_session_messages=existing)
    r = self._c(repo).post(
      "/api/drafts/save",
      json={
        "id": "s1",
        "messages": [
          {"content": "   "},
          {"id": "m1", "role": "user", "content": "hola"},  # unchanged by id
          {"role": "assistant", "content": "ok"},  # content duplicate
          {"id": "m1", "role": "user", "content": "hola editado"},  # changed -> saved
          {"role": "user", "content": "nuevo"},
          {"role": "user", "content": "nuevo"},  # dedup within the same payload
        ],
      },
    )
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["draft"] == {"id": "s1"}
    saves = [c[2] for c in repo.calls if c[0] == "save_message"]
    assert [(s["content"], s["id"]) for s in saves] == [("hola editado", "m1"), ("nuevo", None)]
    assert repo.calls[0][0] == "save_session" and repo.calls[0][1][0]["user_id"] == "test-user-id"
    assert self.saved_files[0]["user_id"] == "test-user-id"

  def test_save_without_id_uses_default_session(self):
    repo = Recorder(get_session_messages=[])
    self._c(repo).post("/api/drafts/save", json={"messages": [{"content": "x"}]})
    assert repo.calls[-1][2]["session_id"] == "default"

  def test_save_failure_returns_500(self):
    repo = Recorder(save_session=RuntimeError("db caída"))
    r = self._c(repo).post("/api/drafts/save", json={})
    assert r.status_code == 500 and "db caída" in r.json()["detail"]

  def test_list_get_delete(self):
    repo = Recorder()
    c = self._c(repo)
    assert c.get("/api/drafts/list", params={"specification": "S"}).json() == {
      "ok": True, "drafts": [{"spec": "S", "u": "test-user-id"}]
    }
    assert c.get("/api/drafts/d1").json() == {"ok": True, "draft": {"id": "d1"}}
    assert c.get("/api/drafts/zz").status_code == 404
    assert c.delete("/api/drafts/d1").json()["ok"] is True
    assert repo.calls[0][:2] == ("delete_session", ("d1",)) and self.deleted == ["d1"]


# --------------------------------------------------------------------------- history


class TestHistoryAPI:
  def _c(self, repo):
    return _client(
      history.router,
      {
        deps.get_chat_repository: repo,
        deps.get_user_repository: repo,
        deps.get_standup_repository: repo,
        deps.get_prd_repository: repo,
        deps.get_test_plan_repository: repo,
      },
    )

  def test_users(self):
    repo = Recorder(get_approved_users=[{"id": "1", "username": "ana", "full_name": "Ana"}, {"id": "2", "username": "bo"}])
    assert self._c(repo).get("/api/users").json() == {
      "users": [
        {"id": "1", "username": "ana", "display_name": "Ana", "role": "user"},
        {"id": "2", "username": "bo", "display_name": "bo", "role": "user"},
      ]
    }

  @pytest.mark.parametrize("ret", [[], RuntimeError("x")])
  def test_users_empty_or_error(self, ret):
    assert self._c(Recorder(get_approved_users=ret)).get("/api/users").json() == {"users": []}

  def test_db_settings(self, monkeypatch):
    store = {"a": 1}
    monkeypatch.setattr(history, "load_app_settings", lambda: dict(store))
    monkeypatch.setattr(history, "save_app_settings", lambda s: store.update(s))
    c = self._c(Recorder())
    assert c.get("/api/db/settings").json() == {"settings": {"a": 1}}
    assert c.post("/api/db/settings", json={"key": "b", "value": [1]}).json() == {"ok": True, "key": "b", "value": [1]}
    assert store == {"a": 1, "b": [1]}
    assert c.post("/api/db/settings", json={"key": "", "value": 1}).status_code == 422

  def test_chat_sessions(self):
    repo = Recorder(
      get_user_sessions=[{"id": "s"}], save_session=lambda d: d, get_session=lambda sid, user_id: {"id": sid}
    )
    c = self._c(repo)
    assert c.get("/api/chat/sessions", params={"feature_slug": "qa", "limit": 3}).json() == {"sessions": [{"id": "s"}]}
    assert repo.calls[-1][2] == {"user_id": "test-user-id", "feature_slug": "qa", "limit": 3}
    r = c.post("/api/chat/sessions", json={"title": "T"})
    assert r.json() == {"ok": True, "session": {"title": "T", "feature_slug": "general", "documentContent": "", "user_id": "test-user-id"}}
    assert c.get("/api/chat/sessions/s9").json() == {"session": {"id": "s9"}}
    assert c.delete("/api/chat/sessions/s9").json() == {"ok": True, "session_id": "s9"}

  def test_chat_history(self):
    repo = Recorder(get_session_messages=[{"c": 1}], save_message=lambda **kw: kw)
    c = self._c(repo)
    assert c.get("/api/chat/history/s1").json() == {"session_id": "s1", "messages": [{"c": 1}]}
    r = c.post("/api/chat/history/s1", json={"role": "user", "content": "hola"})
    assert r.json()["message"]["content"] == "hola" and r.json()["message"]["session_id"] == "s1"
    assert c.post("/api/chat/history/s1", json={"role": "robot", "content": "x"}).status_code == 422
    assert c.delete("/api/chat/history/s1").json() == {"ok": True, "session_id": "s1"}
    assert repo.calls[-1][0] == "clear_session"

  def test_feature_history(self):
    repo = Recorder(get_all_standups=[1], get_all_prd_reviews=[2], get_all_test_plans=[3])
    c = self._c(repo)
    assert c.get("/api/history/standups").json() == {"standups": [1]}
    assert c.get("/api/history/prd-reviews", params={"limit": 5}).json() == {"prd_reviews": [2]}
    assert c.get("/api/history/test-plans").json() == {"test_plans": [3]}
    assert repo.calls[1][2] == {"limit": 5, "user_id": "test-user-id"}


# --------------------------------------------------------------------------- knowledge


class TestKnowledgeAPI:
  @pytest.fixture(autouse=True)
  def fakes(self, monkeypatch, tmp_path):
    def ingest(filename, raw, tags):
      if filename.startswith("bad"):
        raise ValueError("formato no soportado")
      return {"filename": filename, "size": len(raw), "tags": tags}

    monkeypatch.setattr(knowledge, "ingest_document", ingest)
    monkeypatch.setattr(knowledge, "list_documents", lambda: [{"id": "k1"}])
    monkeypatch.setattr(knowledge, "delete_document", lambda did: did == "k1")
    monkeypatch.setattr(knowledge, "get_knowledge_base_dir", lambda: tmp_path)
    monkeypatch.setattr(knowledge, "verify_integrity", lambda: {"ok": True})
    monkeypatch.setattr(knowledge, "rebuild_fts_index", lambda: 12)
    monkeypatch.setattr(knowledge, "export_to_json", lambda: (tmp_path / "m.json", tmp_path / "c.json"))
    self.status = {"host": "db", "is_postgres": True, "connected": True, "engine": "postgresql", "doc_count": 2}
    monkeypatch.setattr(knowledge, "get_db_status", lambda: dict(self.status))
    self.tmp = tmp_path
    self.c = _client(knowledge.router)

  def test_list_and_delete(self):
    assert self.c.get("/api/knowledge/documents").json() == {"documents": [{"id": "k1"}]}
    assert self.c.delete("/api/knowledge/documents/k1").json() == {"ok": True}
    assert self.c.delete("/api/knowledge/documents/zz").status_code == 404

  def test_upload_single(self):
    r = self.c.post("/api/knowledge/documents", files={"file": ("a.md", b"abc")}, data={"tags": "x, ,y"})
    assert r.json() == {"document": {"filename": "a.md", "size": 3, "tags": ["x", "y"]}}
    assert self.c.post("/api/knowledge/documents", files={"file": ("a.md", b"")}).status_code == 400
    r = self.c.post("/api/knowledge/documents", files={"file": ("bad.bin", b"x")})
    assert r.status_code == 400 and r.json()["detail"] == "formato no soportado"

  def test_upload_batch(self):
    r = self.c.post(
      "/api/knowledge/documents/batch",
      files=[("files", ("a.md", b"1")), ("files", ("e.md", b"")), ("files", ("bad.x", b"2"))],
    )
    body = r.json()
    assert [d["filename"] for d in body["documents"]] == ["a.md"]
    assert body["errors"] == ["e.md: empty", "bad.x: formato no soportado"]
    r = self.c.post("/api/knowledge/documents/batch", files=[("files", ("e.md", b""))])
    assert r.status_code == 400 and r.json()["detail"] == "e.md: empty"

  def test_retrieve(self, monkeypatch):
    am = AsyncMock(return_value=SimpleNamespace(model_dump=lambda: {"chunks": []}))
    monkeypatch.setattr(knowledge, "assemble_context", am)
    assert self.c.post("/api/knowledge/retrieve", json={"query": "q"}).json() == {"chunks": []}
    am.assert_awaited_once_with(query="q", sources=["knowledge"], top_k=8)
    assert self.c.post("/api/knowledge/retrieve", json={"query": ""}).status_code == 422

  def test_status_and_path(self):
    assert self.c.get("/api/knowledge/db-status").json()["host"] == "db"
    p = self.c.get("/api/knowledge/path").json()
    assert p["configured_path"] == "db" and p["resolved_path"] == str(self.tmp) and p["doc_count"] == 2
    assert p["chunk_count"] == 0 and p["is_custom"] is True
    put = self.c.put("/api/knowledge/path", json={"path": "/x"}).json()
    assert put["ok"] is True and "DATABASE_URL" in put["message"]

  @pytest.mark.parametrize("method,path", [("get", "/db-status"), ("get", "/path"), ("put", "/path")])
  def test_status_errors_are_500(self, monkeypatch, method, path):
    def boom():
      raise RuntimeError("secret detail")

    monkeypatch.setattr(knowledge, "get_db_status", boom)
    r = getattr(self.c, method)(f"/api/knowledge{path}", **({"json": {}} if method == "put" else {}))
    assert r.status_code == 500 and "secret detail" not in r.json()["detail"]

  def test_admin(self):
    assert self.c.get("/api/knowledge/admin/integrity").json() == {"ok": True}
    assert self.c.post("/api/knowledge/admin/rebuild-index").json() == {"ok": True, "chunks_reindexed": 12}
    r = self.c.post("/api/knowledge/admin/export-json").json()
    assert r["manifest_path"] == str(self.tmp / "m.json") and r["chunks_path"] == str(self.tmp / "c.json")


# --------------------------------------------------------------------------- auth endpoints


STRONG = "Password123!"


class TestAuthEndpoints:
  def _c(self, repo):
    return _client(auth.router, {deps.get_user_repository: repo})

  def _register(self, repo, **over):
    body = {"username": "alice", "password": STRONG, "email": "a@x.io", "full_name": "Alice"}
    body.update(over)
    return self._c(repo).post("/api/auth/register", json=body)

  @pytest.mark.parametrize(
    "over,fragment",
    [
      ({"full_name": "   "}, "nombre completo es requerido"),
      ({"email": "bad-email"}, "correo"),
      ({"password": "weakpassword"}, "contraseña"),
      ({"username": " ab "}, "entre 3 y 20"),
    ],
  )
  def test_register_validation(self, over, fragment):
    r = self._register(Recorder(get_by_username=None), **over)
    assert r.status_code == 400 and fragment in r.json()["detail"]


  def test_register_duplicate(self):
    r = self._register(Recorder(get_by_username={"id": "1"}))
    assert r.status_code == 400 and "alice" in r.json()["detail"]

  def test_register_pending_and_approved(self):
    def create(**kw):
      return {"id": "u1", "username": kw["username"], "status": "pending", "password_hash": "h", "password_salt": "s"}

    r = self._register(Recorder(get_by_username=None, create_user_with_password=create))
    assert r.json()["status"] == "pending" and "password_hash" not in r.json()["user"]
    assert "funcassist_session" not in r.cookies

    def create_ok(**kw):
      return {"id": "u1", "username": kw["username"], "status": "approved", "role": "admin"}

    r = self._register(Recorder(get_by_username=None, create_user_with_password=create_ok))
    assert r.json()["status"] == "approved" and "funcassist_session" in r.cookies

  def _user(self, **over):
    from app.core.security import hash_password

    h, s = hash_password(STRONG)
    u = {"id": "u1", "username": "alice", "password_hash": h, "password_salt": s, "status": "approved", "role": "qa"}
    u.update(over)
    return u

  def test_login_flows(self):
    c = self._c(Recorder(get_by_username=None))
    assert c.post("/api/auth/login", json={"username": "x", "password": "y"}).status_code == 401

    c = self._c(Recorder(get_by_username=self._user()))
    assert c.post("/api/auth/login", json={"username": "alice", "password": "wrong"}).status_code == 401
    r = c.post("/api/auth/login", json={"username": "alice", "password": STRONG})
    assert r.status_code == 200 and r.json()["user"]["role"] == "qa" and "funcassist_session" in r.cookies

    for st, frag in (("pending", "pendiente"), ("rejected", "rechazada")):
      c = self._c(Recorder(get_by_username=self._user(status=st)))
      r = c.post("/api/auth/login", json={"username": "alice", "password": STRONG})
      assert r.status_code == 403 and frag in r.json()["detail"]

  def test_login_backfills_missing_hash(self):
    repo = Recorder(get_by_username={"id": "u1", "username": "alice", "status": "approved"})
    r = self._c(repo).post("/api/auth/login", json={"username": "alice", "password": "anything"})
    assert r.status_code == 200
    upd = [c for c in repo.calls if c[0] == "update"][0]
    assert upd[1][0] == "u1" and set(upd[1][1]) == {"password_hash", "password_salt"}

  def test_logout_and_me(self):
    c = self._c(Recorder())
    r = c.post("/api/auth/logout")
    assert r.status_code == 204
    assert c.get("/api/auth/me").json() == {"user": {"id": "test-user-id", "username": "Usuario", "role": "admin", "status": "approved", "full_name": None}}

  def test_update_me(self):
    repo = Recorder(update=lambda uid, upd: {"id": uid, "password_hash": "x", **upd})
    c = self._c(repo)
    r = c.put("/api/auth/me", json={"full_name": " Ana ", "email": "a@b.co", "password": STRONG})
    u = r.json()["user"]
    assert u["full_name"] == "Ana" and u["email"] == "a@b.co" and "password_hash" not in u
    assert set(repo.calls[0][1][1]) == {"full_name", "email", "password_hash", "password_salt"}

    for body, frag in (
      ({"full_name": "x" * 81}, "80"),
      ({"email": "nope"}, "correo"),
      ({"password": "short"}, "contraseña"),
    ):
      r = c.put("/api/auth/me", json=body)
      assert r.status_code == 400 and frag in r.json()["detail"]

    repo2 = Recorder()
    r = self._c(repo2).put("/api/auth/me", json={"full_name": "  ", "email": " "})
    assert r.json()["user"]["id"] == "test-user-id" and repo2.calls == []

  def test_update_me_repo_returns_none_keeps_user(self):
    r = self._c(Recorder(update=None)).put("/api/auth/me", json={"full_name": "Z"})
    assert r.json()["user"]["username"] == "Usuario"

  def test_access_requests(self):
    repo = Recorder(
      get_pending_users=[{"id": "p", "password_salt": "s"}],
      get_by_id=lambda uid: {"id": uid} if uid == "p" else None,
      update_user_status=lambda uid, st: {"id": uid, "status": st, "password_hash": "h"},
    )
    c = self._c(repo)
    assert c.get("/api/auth/access-requests").json() == {"requests": [{"id": "p"}]}
    for action, st in (("approve", "approved"), ("reject", "rejected")):
      r = c.post(f"/api/auth/access-requests/p/{action}")
      assert r.json() == {"status": st, "user": {"id": "p", "status": st}}
      assert c.post(f"/api/auth/access-requests/zz/{action}").status_code == 404


# --------------------------------------------------------------------------- deps


def _req(cookie=None):
  from app.core.settings import get_settings

  cookies = {get_settings().session_cookie_name: cookie} if cookie is not None else {}
  return SimpleNamespace(cookies=cookies)


class TestDeps:
  @pytest.mark.asyncio
  async def test_no_cookie(self):
    with pytest.raises(HTTPException) as ei:
      await deps.get_current_user(_req(), Recorder())
    assert ei.value.status_code == 401

  @pytest.mark.asyncio
  async def test_invalid_token(self, monkeypatch):
    monkeypatch.setattr(deps, "decode_access_token", lambda t: None)
    with pytest.raises(HTTPException) as ei:
      await deps.get_current_user(_req(" tok "), Recorder())
    assert ei.value.status_code == 401 and "inválido" in ei.value.detail

  @pytest.mark.asyncio
  @pytest.mark.parametrize(
    "ret,status",
    [(RuntimeError("db"), 503), (None, 404), ({"status": "pending"}, 403)],
  )
  async def test_user_lookup_failures(self, monkeypatch, ret, status):
    monkeypatch.setattr(deps, "decode_access_token", lambda t: {"username": "a"})
    with pytest.raises(HTTPException) as ei:
      await deps.get_current_user(_req("t"), Recorder(get_by_username=ret))
    assert ei.value.status_code == status

  @pytest.mark.asyncio
  async def test_success_strips_secrets_and_admin_check(self, monkeypatch):
    seen = []
    monkeypatch.setattr(deps, "decode_access_token", lambda t: seen.append(t) or {"username": "a"})
    repo = Recorder(get_by_username={"id": "1", "status": "approved", "role": "qa", "password_hash": "h", "password_salt": "s"})
    u = await deps.get_current_user(_req(" tok "), repo)
    assert u == {"id": "1", "status": "approved", "role": "qa"} and seen == ["tok"]
    with pytest.raises(HTTPException) as ei:
      await deps.get_current_admin_user(u)
    assert ei.value.status_code == 403
    assert await deps.get_current_admin_user({"role": "admin"}) == {"role": "admin"}

  @pytest.mark.asyncio
  async def test_repository_providers(self):
    from app.db import repositories as r

    s = object()
    pairs = [
      (deps.get_user_repository, r.UserRepository),
      (deps.get_mcp_server_repository, r.McpServerRepository),
      (deps.get_organization_repository, r.OrganizationRepository),
      (deps.get_integration_repository, r.IntegrationRepository),
      (deps.get_secret_repository, r.UserSecretRepository),
      (deps.get_settings_repository, r.SettingsRepository),
      (deps.get_chat_repository, r.ChatRepository),
      (deps.get_streaming_chat_repository, r.ChatRepository),
      (deps.get_standup_repository, r.StandupRepository),
      (deps.get_prd_repository, r.PRDRepository),
      (deps.get_test_plan_repository, r.TestPlanRepository),
      (deps.get_ai_template_repository, r.AITemplateRepository),
      (deps.get_transcription_repository, r.TranscriptionRepository),
      (deps.get_corporate_template_repository, r.CorporateTemplateRepository),
    ]
    for fn, cls in pairs:
      assert isinstance(fn(s), cls)

  @pytest.mark.asyncio
  async def test_session_generators(self):
    agen = deps.get_db_session()
    sess = await agen.__anext__()
    assert sess is not None
    await agen.aclose()
    gen = deps.get_sync_db_session()
    assert next(gen) is not None
    gen.close()

