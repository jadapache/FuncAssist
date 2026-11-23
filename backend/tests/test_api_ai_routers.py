"""HTTP tests for the AI management/settings/templates routers, document templates, PM features and
the grounded-error middleware."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.ai.errors import AIError
from app.api.middleware.error_handlers import handle_grounded_errors
from app.api.routers import (
  ai_management,
  ai_settings,
  ai_templates,
  features_pm,
  templates,
)


def _client(*routers) -> TestClient:
  app = FastAPI()
  for r in routers:
    app.include_router(r, prefix="/api")
  return TestClient(app, base_url="https://testserver")


# --------------------------------------------------------------------------- middleware


class TestErrorHandlers:
  @pytest.mark.parametrize(
    "exc,status,detail",
    [
      (AIError(code="rate_limit", user_message="lento", retry_after=7), 429, "lento"),
      (AIError(code="auth_error", user_message="clave"), 401, "clave"),
      (AIError(code="other", user_message="boom"), 502, "boom"),
      (ValueError("malo"), 400, "malo"),
      (KeyError("falta"), 404, "'falta'"),
      (RuntimeError("caido"), 502, "caido"),
      (HTTPException(status_code=418, detail="tetera"), 418, "tetera"),
    ],
  )
  def test_async_and_sync_wrappers_map_exceptions(self, exc, status, detail):
    app = FastAPI()

    @app.get("/a")
    @handle_grounded_errors
    async def a():
      raise exc

    @app.get("/s")
    @handle_grounded_errors
    def s():
      raise exc

    c = TestClient(app, base_url="https://testserver")
    for path in ("/a", "/s"):
      r = c.get(path)
      assert r.status_code == status
      assert r.json()["detail"] == detail
      if status == 429:
        assert r.headers["retry-after"] == "7"

  def test_wrappers_pass_through_results(self):
    @handle_grounded_errors
    def s(x):
      return x * 2

    assert s(3) == 6


# --------------------------------------------------------------------------- ai_management


class _FakeProvider:
  def __init__(self, fail=False):
    self.fail = fail

  async def complete(self, messages, model, max_tokens):
    if self.fail:
      raise RuntimeError("sin red")
    return SimpleNamespace(text="OK")


class TestAIManagement:
  def test_no_provider_configured(self, monkeypatch):
    monkeypatch.setattr(ai_management, "get_ai_settings", lambda user_id=None: {})
    r = _client(ai_management.router).post("/api/ai/test-connection", json={})
    assert r.status_code == 200
    assert r.json()["ok"] is False and "proveedor" in r.json()["message"]

  def test_forbidden_browser_provider(self, monkeypatch):
    monkeypatch.setattr(ai_management, "get_ai_settings", lambda user_id=None: {})
    monkeypatch.setattr(ai_management, "FORBIDDEN_BACKEND_PROVIDERS", {"webllm"})
    r = _client(ai_management.router).post("/api/ai/test-connection", json={"provider": "WebLLM", "model": "x"})
    body = r.json()
    assert body["ok"] is False and body["provider"] == "webllm" and "WebLLM" in body["message"]

  def test_missing_model(self, monkeypatch):
    monkeypatch.setattr(ai_management, "get_ai_settings", lambda user_id=None: {"provider": "groq"})
    r = _client(ai_management.router).post("/api/ai/test-connection", json={})
    assert r.json() == {"ok": False, "message": "No hay un modelo especificado para el proveedor 'groq'."}

  def test_success_uses_first_api_key(self, monkeypatch):
    seen = {}
    monkeypatch.setattr(ai_management, "get_ai_settings", lambda user_id=None: {"provider": "groq", "model": "m1"})

    def resolve(**kw):
      seen.update(kw)
      return _FakeProvider()

    monkeypatch.setattr(ai_management, "resolve_provider", resolve)
    r = _client(ai_management.router).post(
      "/api/ai/test-connection", json={"openai_api_key": "sk-o", "ollama_base_url": "http://o"}
    )
    body = r.json()
    assert body["ok"] is True and body["response"] == "OK" and body["model"] == "m1"
    assert seen["api_key"] == "sk-o" and seen["base_url"] == "http://o" and seen["user_id"] == "test-user-id"

  def test_provider_failure_reported(self, monkeypatch):
    monkeypatch.setattr(ai_management, "get_ai_settings", lambda user_id=None: {})
    monkeypatch.setattr(ai_management, "resolve_provider", lambda **kw: _FakeProvider(fail=True))
    r = _client(ai_management.router).post("/api/ai/test-connection", json={"provider": "groq", "model": "m"})
    assert r.json()["ok"] is False and "sin red" in r.json()["message"]

  def test_ollama_models_requires_url(self, monkeypatch):
    monkeypatch.setattr(ai_management, "get_ai_settings", lambda user_id=None: {})
    r = _client(ai_management.router).get("/api/ai/ollama/models")
    assert r.json()["ok"] is False and r.json()["models"] == []

  def test_ollama_models_rejects_unsafe_url(self, monkeypatch):
    monkeypatch.setattr(ai_management, "get_ai_settings", lambda user_id=None: {})
    monkeypatch.setattr(ai_management, "validate_remote_endpoint_url", lambda u: (False, "privada"))
    r = _client(ai_management.router).get("/api/ai/ollama/models", params={"base_url": "http://10.0.0.1/"})
    assert r.json() == {"online": False, "models": [], "error": "privada"}

  def _patch_httpx(self, monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*a, **kw):
      kw["transport"] = httpx.MockTransport(handler)
      return real(*a, **kw)

    monkeypatch.setattr(ai_management.httpx, "AsyncClient", factory)

  def test_ollama_models_lists_names(self, monkeypatch):
    monkeypatch.setattr(ai_management, "get_ai_settings", lambda user_id=None: {"ollama_base_url": "https://ol.example/"})
    monkeypatch.setattr(ai_management, "validate_remote_endpoint_url", lambda u: (True, None))
    calls = []

    def handler(req):
      calls.append(str(req.url))
      return httpx.Response(200, json={"models": [{"name": "llama3"}, {"size": 1}, {"name": "qwen"}]})

    self._patch_httpx(monkeypatch, handler)
    r = _client(ai_management.router).get("/api/ai/ollama/models")
    assert r.json() == {"online": True, "models": ["llama3", "qwen"]}
    assert calls == ["https://ol.example/api/tags"]

  def test_ollama_models_http_error(self, monkeypatch):
    monkeypatch.setattr(ai_management, "get_ai_settings", lambda user_id=None: {})
    monkeypatch.setattr(ai_management, "validate_remote_endpoint_url", lambda u: (True, None))
    self._patch_httpx(monkeypatch, lambda req: httpx.Response(500))
    r = _client(ai_management.router).get("/api/ai/ollama/models", params={"base_url": "https://ol.example"})
    body = r.json()
    assert body["online"] is False and body["error"]


# --------------------------------------------------------------------------- ai_settings


class _Catalog:
  def __init__(self, data):
    self.data = data

  def model_dump(self):
    return dict(self.data)


class TestAISettingsCatalog:
  def test_catalog_refresh_error_is_reported(self, monkeypatch):
    monkeypatch.setattr(ai_settings, "sync_frontier_models_catalog", AsyncMock(return_value={"status": "error"}))
    get_cat = AsyncMock(return_value=_Catalog({"models": []}))
    monkeypatch.setattr(ai_settings, "get_model_catalog", get_cat)
    r = _client(ai_settings.router).get("/api/ai/models/catalog", params={"refresh": "true", "provider": "groq"})
    assert r.status_code == 200
    assert r.json()["models"] == [] and "LiteLLM" in r.json()["error"]
    get_cat.assert_awaited_with(refresh=True, provider="groq", task_type="all")

  def test_catalog_without_refresh(self, monkeypatch):
    sync = AsyncMock()
    monkeypatch.setattr(ai_settings, "sync_frontier_models_catalog", sync)
    monkeypatch.setattr(ai_settings, "get_model_catalog", AsyncMock(return_value=_Catalog({"models": ["a"]})))
    r = _client(ai_settings.router).get("/api/ai/models/catalog")
    assert r.json() == {"models": ["a"]}
    sync.assert_not_awaited()

  def test_sync_and_status(self, monkeypatch):
    monkeypatch.setattr(ai_settings, "sync_frontier_models_catalog", AsyncMock(return_value={"status": "ok"}))
    monkeypatch.setattr(ai_settings, "get_model_catalog", AsyncMock(return_value=_Catalog({"models": ["a"]})))
    monkeypatch.setattr(ai_settings, "get_frontier_sync_status", lambda: {"last": "now"})
    c = _client(ai_settings.router)
    assert c.post("/api/ai/models/sync").json() == {"sync": {"status": "ok"}, "catalog": {"models": ["a"]}}
    assert c.get("/api/ai/models/sync-status").json() == {"last": "now"}


@pytest.fixture
def settings_store(monkeypatch):
  store: dict = {}
  monkeypatch.setattr(ai_settings, "get_ai_settings", lambda user_id=None: dict(store))

  def save(uid, data):
    store.update(data)

  monkeypatch.setattr(ai_settings, "save_user_ai_settings", save)
  monkeypatch.setattr(ai_settings, "clear_provider_cache", lambda uid: None)
  monkeypatch.setattr(ai_settings, "catalog_chat_models", lambda pid: ["fast-1", "fb-1", "fb-2"])
  for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"):
    monkeypatch.delenv(k, raising=False)
  return store


class TestAISettings:
  def test_get_defaults(self, settings_store):
    body = _client(ai_settings.router).get("/api/ai/settings").json()
    assert body["provider"] is None and body["active_api_key_set"] is False
    assert body["transcription_cleanup"] == "rules" and body["user_id"] == "test-user-id"

  @pytest.mark.parametrize(
    "spec,config,expected",
    [
      (SimpleNamespace(id="ollama_remote", aliases=(), config_key=None, env_key=None), {"ollama_base_url": "u"}, True),
      (SimpleNamespace(id="groq", aliases=(), config_key="groq_api_key", env_key="GROQ_API_KEY"), {"groq_api_key": "k"}, True),
      (SimpleNamespace(id="x", aliases=(), config_key=None, env_key="X_KEY_FOR_TEST"), {}, True),
    ],
  )
  def test_active_key_detection(self, settings_store, monkeypatch, spec, config, expected):
    settings_store.update(config, provider="p")
    monkeypatch.setenv("X_KEY_FOR_TEST", "1")
    monkeypatch.setattr(ai_settings, "find_provider_spec", lambda p: spec)
    assert _client(ai_settings.router).get("/api/ai/settings").json()["active_api_key_set"] is expected

  def test_update_maps_inference_fields_and_normalizes(self, settings_store):
    r = _client(ai_settings.router).put(
      "/api/ai/settings",
      json={
        "inference_provider": "groq",
        "inference_model": "llama",
        "fallback_models": [" fb-1 ", "fb-1", ""],
        "fast_model": " fast-1 ",
        "transcription_fillers": [" Eh ", "eh", "mmm"],
        "transcription_vocabulary": "  Jira  ",
        "groq_api_key": "k",
      },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "groq" and body["model"] == "llama"
    assert body["fallback_models"] == ["fb-1"] and body["fast_model"] == "fast-1"
    assert body["transcription_fillers"] == ["eh", "mmm"] and body["transcription_vocabulary"] == "Jira"
    assert body["active_api_key_set"] is True

  def test_inference_fields_dropped_when_explicit_given(self, settings_store):
    _client(ai_settings.router).put(
      "/api/ai/settings",
      json={"provider": "groq", "inference_provider": "openai", "model": "a", "inference_model": "b"},
    )
    assert settings_store["provider"] == "groq" and settings_store["model"] == "a"
    assert "inference_provider" not in settings_store

  @pytest.mark.parametrize(
    "payload,fragment",
    [
      ({"model": "x.gguf"}, "GGUF"),
      ({"fallback_models": ["a.GGUF"]}, "respaldo no pueden"),
      ({"fallback_models": ["a", "b", "c", "d"]}, "máximo 3"),
      ({"fast_model": "f.gguf"}, "rápido no puede"),
      ({"transcription_fillers": ["x" * 41]}, "40 caracteres"),
      ({"provider": "groq", "fast_model": "nope"}, "no existe en el catálogo"),
      ({"provider": "groq", "fallback_models": ["nope"]}, "no disponibles"),
    ],
  )
  def test_update_validation_errors(self, settings_store, payload, fragment):
    r = _client(ai_settings.router).put("/api/ai/settings", json=payload)
    assert r.status_code == 400
    assert fragment in r.json()["detail"]
    assert settings_store == {}

  def test_update_rejects_invalid_literal(self, settings_store):
    r = _client(ai_settings.router).put("/api/ai/settings", json={"transcription_cleanup": "bogus"})
    assert r.status_code == 422

  def test_provider_change_prunes_stored_tier_models(self, settings_store, monkeypatch):
    settings_store.update(provider="openai", fast_model="gone", fallback_models=["fb-2", "gone"])
    r = _client(ai_settings.router).put("/api/ai/settings", json={"provider": "groq"})
    assert r.status_code == 200
    assert settings_store["fast_model"] == "" and settings_store["fallback_models"] == ["fb-2"]

  def test_catalog_failure_skips_validation(self, settings_store, monkeypatch):
    def boom(pid):
      raise RuntimeError("x")

    monkeypatch.setattr(ai_settings, "catalog_chat_models", boom)
    r = _client(ai_settings.router).put("/api/ai/settings", json={"provider": "groq", "fast_model": "anything"})
    assert r.status_code == 200 and settings_store["fast_model"] == "anything"

  def test_unknown_provider_skips_validation(self, settings_store):
    r = _client(ai_settings.router).put("/api/ai/settings", json={"provider": "nonexistent-prov", "fast_model": "z"})
    assert r.status_code == 200

  def test_ollama_url_validation(self, settings_store, monkeypatch):
    monkeypatch.setattr(ai_settings, "validate_remote_endpoint_url", lambda u: (False, "URL bloqueada"))
    r = _client(ai_settings.router).put(
      "/api/ai/settings", json={"provider": "ollama", "ollama_base_url": "http://127.0.0.1"}
    )
    assert r.status_code == 400 and r.json()["detail"] == "URL bloqueada"
    monkeypatch.setattr(ai_settings, "validate_remote_endpoint_url", lambda u: (True, None))
    r = _client(ai_settings.router).put(
      "/api/ai/settings", json={"provider": "ollama", "ollama_base_url": "https://ol.example"}
    )
    assert r.status_code == 200 and r.json()["ollama_base_url"] == "https://ol.example"

  def test_webllm_and_asr_catalog_checks(self, settings_store, monkeypatch):
    monkeypatch.setattr(ai_settings, "has_catalog_model", lambda m, p, t: False)
    c = _client(ai_settings.router)
    r = c.put("/api/ai/settings", json={"provider": "webllm", "model": "m"})
    assert r.status_code == 400 and "WebLLM" in r.json()["detail"]
    r = c.put("/api/ai/settings", json={"transcription_provider": "browser_asr", "transcription_model": "w"})
    assert r.status_code == 400 and "ASR" in r.json()["detail"]
    monkeypatch.setattr(ai_settings, "has_catalog_model", lambda m, p, t: True)
    r = c.put("/api/ai/settings", json={"transcription_provider": "browser_asr", "transcription_model": "w"})
    assert r.status_code == 200 and r.json()["transcription_model"] == "w"


# --------------------------------------------------------------------------- ai_templates


class TestAITemplates:
  @pytest.fixture(autouse=True)
  def fakes(self, monkeypatch):
    self.saved = []

    async def save_prompt(feature, data, updated_by=None, change_summary=None):
      if feature == "missing":
        raise KeyError("missing")
      self.saved.append((feature, data, updated_by, change_summary))
      return {"feature": feature, **data}

    async def getter(feature):
      if feature == "missing":
        raise KeyError(f"no {feature}")
      return {"feature": feature}

    monkeypatch.setattr(ai_templates, "save_prompt", save_prompt)
    monkeypatch.setattr(ai_templates, "save_rubric", save_prompt)
    for name in ("get_prompt", "reset_prompt", "get_rubric", "reset_rubric"):
      monkeypatch.setattr(ai_templates, name, getter)
    monkeypatch.setattr(ai_templates, "list_prompts", AsyncMock(return_value=[{"feature": "a"}]))
    monkeypatch.setattr(ai_templates, "list_rubrics", AsyncMock(return_value=[{"feature": "r"}]))
    monkeypatch.setattr(
      ai_templates, "get_template_history", AsyncMock(side_effect=lambda kind, f, limit: [{"kind": kind, "f": f, "limit": limit}])
    )
    monkeypatch.setattr(ai_templates, "list_logs", lambda limit: [{"i": i} for i in range(limit)])
    monkeypatch.setattr(ai_templates, "summarize_logs", lambda logs: {"count": len(logs)})
    self.c = _client(ai_templates.router)

  def test_lists(self):
    assert self.c.get("/api/ai/prompts", params={"tag": "qa"}).json() == {"prompts": [{"feature": "a"}]}
    assert self.c.get("/api/ai/rubrics").json() == {"rubrics": [{"feature": "r"}]}

  def test_create_prompt_sanitizes_feature(self):
    r = self.c.post("/api/ai/prompts", json={"feature": " Mi Feature! ", "system": "s", "updated_by": "ana"})
    assert r.status_code == 200
    assert r.json()["feature"] == "mi_feature"
    feature, data, by, summary = self.saved[-1]
    assert by == "ana" and "updated_by" not in data and "mi_feature" in summary


  def test_create_prompt_requires_feature(self):
    assert self.c.post("/api/ai/prompts", json={}).status_code == 422

  @pytest.mark.parametrize("kind", ["prompts", "rubrics"])
  def test_detail_reset_and_404(self, kind):
    assert self.c.get(f"/api/ai/{kind}/x").json() == {"feature": "x"}
    assert self.c.post(f"/api/ai/{kind}/x/reset").json() == {"feature": "x"}
    assert self.c.get(f"/api/ai/{kind}/missing").status_code == 404
    assert self.c.post(f"/api/ai/{kind}/missing/reset").status_code == 404

  def test_history(self):
    assert self.c.get("/api/ai/prompts/x/history", params={"limit": 5}).json() == {
      "history": [{"kind": "prompt", "f": "x", "limit": 5}]
    }
    assert self.c.get("/api/ai/rubrics/x/history").json()["history"][0]["kind"] == "rubric"
    assert self.c.get("/api/ai/prompts/x/history", params={"limit": 0}).status_code == 422

  def test_update_prompt_and_rubric(self):
    r = self.c.put("/api/ai/prompts/x", json={"system": "s", "change_summary": "c", "updated_by": "u"})
    assert r.json() == {"feature": "x", "system": "s"}
    assert self.saved[-1][2:] == ("u", "c")
    r = self.c.put("/api/ai/rubrics/x", json={"criteria": ["a"]})
    assert r.json() == {"feature": "x", "criteria": ["a"]}
    assert self.c.put("/api/ai/prompts/missing", json={}).status_code == 404
    assert self.c.put("/api/ai/rubrics/missing", json={"criteria": []}).status_code == 404
    assert self.c.put("/api/ai/rubrics/x", json={}).status_code == 422

  def test_logs(self):
    assert self.c.get("/api/ai/logs", params={"limit": 2}).json() == {"logs": [{"i": 0}, {"i": 1}]}
    assert self.c.get("/api/ai/logs/stats", params={"limit": 3}).json() == {"count": 3}


# --------------------------------------------------------------------------- templates


class TestTemplates:
  @pytest.fixture(autouse=True)
  def fakes(self, monkeypatch):
    monkeypatch.setattr(templates, "list_templates", AsyncMock(return_value=[{"id": "t1"}]))
    monkeypatch.setattr(
      templates, "get_template_detail", AsyncMock(side_effect=lambda tid: {"id": tid} if tid == "t1" else None)
    )
    self.save = AsyncMock(return_value={"id": "new"})
    monkeypatch.setattr(templates, "save_template_file", self.save)
    monkeypatch.setattr(
      templates,
      "update_template_metadata",
      AsyncMock(side_effect=lambda tid, **kw: {"id": tid, **kw} if tid == "t1" else None),
    )
    monkeypatch.setattr(templates, "delete_template", AsyncMock(side_effect=lambda tid: tid == "t1"))
    self.c = _client(templates.router)

  def test_list_and_detail(self):
    assert self.c.get("/api/templates").json() == {"templates": [{"id": "t1"}]}
    assert self.c.get("/api/templates/t1/content").json() == {"id": "t1"}
    assert self.c.get("/api/templates/zz/content").status_code == 404

  def test_upload(self):
    r = self.c.post(
      "/api/templates/upload", files={"file": ("plan.docx", b"bytes", "application/octet-stream")}, data={"title": "T"}
    )
    assert r.json() == {"template": {"id": "new"}}
    self.save.assert_awaited_once_with(filename="plan.docx", file_bytes=b"bytes", title="T", module="general")
    assert self.c.post("/api/templates/upload").status_code == 422

  def test_edit_and_delete(self):
    r = self.c.put("/api/templates/t1", json={"title": "N", "tags": ["a"]})
    assert r.json()["template"]["title"] == "N" and r.json()["template"]["tags"] == ["a"]
    assert self.c.put("/api/templates/zz", json={}).status_code == 404
    assert self.c.delete("/api/templates/t1").json() == {"ok": True, "template_id": "t1"}
    assert self.c.delete("/api/templates/zz").status_code == 404


# --------------------------------------------------------------------------- features_pm


class _Repo:
  def __init__(self):
    self.calls = []

  def __getattr__(self, name):
    async def rec(**kw):
      self.calls.append((name, kw))

    return rec


class TestFeaturesPM:
  @pytest.fixture(autouse=True)
  def repos(self):
    from app.api import deps

    self.repo = _Repo()
    app = FastAPI()
    app.include_router(features_pm.router, prefix="/api")
    for dep in (deps.get_standup_repository, deps.get_chat_repository, deps.get_prd_repository):
      app.dependency_overrides[dep] = lambda: self.repo
    self.c = TestClient(app, base_url="https://testserver")

  def test_standup_persists_markdown(self, monkeypatch):
    monkeypatch.setattr(features_pm, "generate_standup", AsyncMock(return_value={"markdown": "# S", "date": "2026-01-01"}))
    r = self.c.post("/api/features/standup", json={"sources": ["jira"]})
    assert r.json()["markdown"] == "# S"
    name, kw = self.repo.calls[0]
    assert name == "create_standup" and kw["title"] == "Standup 2026-01-01" and kw["sources"] == ["jira"]

  def test_standup_without_markdown_not_saved(self, monkeypatch):
    monkeypatch.setattr(features_pm, "generate_standup", AsyncMock(return_value={"error": "x"}))
    assert self.c.post("/api/features/standup").json() == {"error": "x"}
    assert self.repo.calls == []

  def test_standup_ai_error(self, monkeypatch):
    monkeypatch.setattr(
      features_pm, "generate_standup", AsyncMock(side_effect=AIError(code="rate_limit", user_message="espera"))
    )
    r = self.c.post("/api/features/standup")
    assert r.status_code == 429 and r.json()["detail"] == "espera"

  def test_ask_saves_both_messages(self, monkeypatch):
    run = AsyncMock(return_value={"markdown": "resp", "context_sources": ["a"]})
    monkeypatch.setattr(features_pm, "run_grounded_feature", run)
    r = self.c.post("/api/features/ask", json={"query": "¿qué?"})
    assert r.json()["markdown"] == "resp"
    assert [kw["role"] for _, kw in self.repo.calls] == ["user", "assistant"]
    assert self.repo.calls[1][1]["context_sources"] == ["a"]
    assert run.await_args.kwargs["feature"] == "ask_product"


  def test_prd_checker(self, monkeypatch):
    monkeypatch.setattr(features_pm, "review_prd", AsyncMock(return_value={"markdown": "ok"}))
    assert self.c.post("/api/features/prd-checker", json={"query": "q"}).status_code == 400
    r = self.c.post("/api/features/prd-checker", json={"query": "q", "document_ids": ["d"]})
    assert r.json() == {"markdown": "ok"}
    assert self.repo.calls[0][0] == "create_prd_review"
    assert self.c.post("/api/features/prd-checker", json={"query": ""}).status_code == 422

  def test_change_impact(self, monkeypatch):
    an = AsyncMock(return_value={"markdown": "impact"})
    monkeypatch.setattr(features_pm, "analyze_change_impact", an)
    assert self.c.post("/api/features/change-impact", json={"query": "q"}).status_code == 400
    r = self.c.post("/api/features/change-impact", json={"query": "q", "sources": ["jira"]})
    assert r.json() == {"markdown": "impact"}
    assert an.await_args.kwargs["sources"] == ["jira"]
