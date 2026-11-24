"""Tests for features_doc and features_qa routers (+ grounded error mapping)."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.errors import AIError
from app.api.deps import get_test_plan_repository
from app.api.routers import features_doc, features_qa


class FakePlanRepo:
  def __init__(self):
    self.created = []

  async def create_test_plan(self, **kw):
    self.created.append(kw)


@pytest.fixture
def plans():
  return FakePlanRepo()


@pytest.fixture
def client(plans):
  app = FastAPI()
  app.include_router(features_doc.router, prefix="/api")
  app.include_router(features_qa.router, prefix="/api")
  app.dependency_overrides[get_test_plan_repository] = lambda: plans
  return TestClient(app, base_url="https://testserver")


@pytest.mark.parametrize("path,fn", [
  ("mejoras", "generate_mejoras_report"),
  ("inventario", "generate_inventario_report"),
  ("levantamiento", "generate_levantamiento_report"),
])
def test_doc_features_pass_through(client, monkeypatch, path, fn):
  mock = AsyncMock(return_value={"markdown": f"# {path}"})
  monkeypatch.setattr(features_doc, fn, mock)
  r = client.post(f"/api/features/{path}", json={"query": "q", "sources": ["jira"], "chat_context": "c"})
  assert r.status_code == 200 and r.json() == {"markdown": f"# {path}"}
  mock.assert_awaited_once_with(query="q", sources=["jira"], document_ids=[], chat_context="c")


def test_doc_feature_validation(client):
  assert client.post("/api/features/mejoras", json={"query": ""}).status_code == 422


@pytest.mark.parametrize("exc,status", [
  (AIError(code="rate_limit", user_message="slow", retry_after=7), 429),
  (AIError(code="auth_error", user_message="key"), 401),
  (AIError(code="other", user_message="x"), 502),
  (ValueError("bad"), 400),
  (KeyError("missing"), 404),
  (RuntimeError("boom"), 502),
])
def test_doc_feature_error_mapping(client, monkeypatch, exc, status):
  monkeypatch.setattr(features_doc, "generate_mejoras_report", AsyncMock(side_effect=exc))
  r = client.post("/api/features/mejoras", json={"query": "q"})
  assert r.status_code == status
  if status == 429:
    assert r.headers["retry-after"] == "7"


def test_qa_feature_stores_plan(client, monkeypatch, plans):
  run = AsyncMock(return_value={"markdown": "# plan"})
  monkeypatch.setattr(features_qa, "run_grounded_feature", run)
  r = client.post("/api/features/qa/regression", json={"query": "q"})
  assert r.status_code == 200 and r.json() == {"markdown": "# plan"}
  assert run.await_args.kwargs["sources"] == ["jira", "github", "gitlab", "knowledge"]
  assert plans.created == [{"feature_name": "regression", "content": "# plan", "test_type": "regression"}]


def test_qa_feature_no_markdown_not_stored(client, monkeypatch, plans):
  monkeypatch.setattr(features_qa, "run_grounded_feature", AsyncMock(return_value={"other": 1}))
  r = client.post("/api/features/qa/api_qa", json={"query": "q", "sources": ["knowledge"]})
  assert r.status_code == 200 and plans.created == []






def test_sync_wrapper_error_mapping():
  from fastapi import HTTPException
  from app.api.middleware.error_handlers import handle_grounded_errors

  def make(exc):
    @handle_grounded_errors
    def f():
      raise exc
    return f

  cases = [
    (HTTPException(status_code=418), 418),
    (AIError(code="rate_limit", user_message="x", retry_after=3), 429),
    (AIError(code="auth_error", user_message="x"), 401),
    (ValueError("v"), 400), (KeyError("k"), 404), (RuntimeError("r"), 502),
  ]
  for exc, status in cases:
    with pytest.raises(HTTPException) as ei:
      make(exc)()
    assert ei.value.status_code == status

  @handle_grounded_errors
  def ok():
    return 1
  assert ok() == 1
