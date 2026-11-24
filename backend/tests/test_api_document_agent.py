"""HTTP + helper tests for app/api/document_agent.py (doc-agent router)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.errors import AIError
from app.ai.events import AgentEvent
from app.ai.stream_control import StreamStopped
from app.api import document_agent as da
from app.api.deps import get_chat_repository, get_streaming_chat_repository
from app.schemas.artifacts import FunctionalImprovementArtifact, FunctionalInventoryArtifact


class FakeRepo:
  def __init__(self, messages=None, artifacts=None, fail=False):
    self.messages = messages or []
    self.artifacts = artifacts or []
    self.fail = fail
    self.saved_messages: list[dict] = []
    self.saved_sessions: list[dict] = []

  async def get_session_messages(self, sid, limit=0, user_id=None):
    if self.fail:
      raise RuntimeError("db down")
    return self.messages

  async def get_session_artifacts(self, sid, user_id=None):
    if self.fail:
      raise RuntimeError("db down")
    return self.artifacts

  async def save_message(self, **kw):
    if self.fail:
      raise RuntimeError("db down")
    self.saved_messages.append(kw)

  async def save_session(self, data):
    self.saved_sessions.append(data)


@pytest.fixture
def repo():
  return FakeRepo()


@pytest.fixture
def client(repo):
  app = FastAPI()
  app.include_router(da.router, prefix="/api")
  app.dependency_overrides[get_chat_repository] = lambda: repo
  app.dependency_overrides[get_streaming_chat_repository] = lambda: repo
  return TestClient(app, base_url="https://testserver")


@pytest.fixture(autouse=True)
def no_template(monkeypatch):
  monkeypatch.setattr(da, "_load_active_template_info", AsyncMock(return_value=("", "docx")))
  monkeypatch.setattr(da, "classifier_enabled", lambda: False)


def _sse(body: str) -> list[tuple[str, dict]]:
  out = []
  for frame in body.split("\n\n"):
    name, data = "", None
    for line in frame.splitlines():
      if line.startswith("event:"):
        name = line[6:].strip()
      elif line.startswith("data:"):
        data = json.loads(line[5:].strip())
    if data is not None:
      out.append((name, data))
  return out


def _runner(*chunks, exc=None, route="plain"):
  async def run(cfg):
    cfg.run_info.update(route=route)
    for c in chunks:
      yield c
    if exc is not None:
      raise exc
  return run


# --------------------------------------------------------------------- pure helpers

class TestIntentHelpers:
  def test_follow_up_detection(self):
    assert da.is_artifact_follow_up("regenera el documento")
    assert da.is_artifact_follow_up("el documento está vacío")
    assert not da.is_artifact_follow_up("hola")
    assert not da.is_artifact_follow_up("")

  @pytest.mark.parametrize("arts,tid,has_doc,expected", [
    ([{"intent": "generic_plan"}], None, False, "generic_plan"),
    ([{"title": "x"}], "t1", False, "template_mutation"),
    ([{"title": "Plan de pruebas"}], None, False, "generic_plan"),
    ([{"title": "Otro"}], None, False, "generic_report"),
    ([], "t", True, "template_mutation"),
    ([], None, True, "generic_report"),
    (None, None, False, None),
  ])
  def test_infer_active_intent(self, arts, tid, has_doc, expected):
    assert da.infer_active_artifact_intent(arts, tid, has_doc) == expected

  @pytest.mark.parametrize("mode,expected", [
    ("plan", "generic_plan"), ("informe", "generic_report"), ("qa", "chat"),
    ("template", "template_mutation"), ("custom_x", "custom_x"),
  ])
  def test_mode_overrides(self, mode, expected):
    assert da.classify_prompt_intent("x", mode=mode) == expected

  @pytest.mark.parametrize("prompt,expected", [
    ("/plan algo", "generic_plan"), ("/informe x", "generic_report"),
    ("/plantilla x", "template_mutation"), ("/pregunta x", "ask_product"),
    ("/mejoras x", "mejoras"), ("¿qué es esto?", "chat"),
    ("genera un plan de trabajo", "generic_plan"), ("haz un reporte", "generic_report"),
    ("genera el documento ahora", "template_mutation"), ("hola", "chat"),
  ])
  def test_rules(self, prompt, expected):
    assert da.classify_prompt_intent(prompt) == expected

  def test_template_and_follow_up(self):
    assert da.classify_prompt_intent("hazme algo", template_id="t1") == "template_mutation"
    assert da.classify_prompt_intent("regenera", active_artifact_intent="generic_plan") == "generic_plan"
    assert da.classify_prompt_intent_by_rules("¿y esto?", active_artifact_intent="generic_plan") == ("chat", False)

  def test_needs_model_classification(self):
    assert not da.needs_model_classification("doc", True, None)
    assert da.needs_model_classification("hola", False, "generic_plan")
    assert da.needs_model_classification("el documento", False, None)
    assert not da.needs_model_classification("gracias", False, None)

  def test_strip_command(self):
    assert da._strip_command("/plan").startswith("Generar plan")
    assert da._strip_command("/informe").startswith("Generar informe")
    assert da._strip_command("/pregunta hola") == "hola"
    assert da._strip_command("libre") == "libre"

  @pytest.mark.xfail(strict=True, reason="BUG: '/plantilla' matches the '/plan' prefix first, leaving 'tilla abc'")
  def test_strip_plantilla_command(self):
    assert da._strip_command("/plantilla abc") == "abc"


class TestLoadTemplateInfo:
  @pytest.fixture(autouse=True)
  def restore(self, monkeypatch):
    # undo the module-level autouse patch for these tests
    monkeypatch.setattr(da, "_load_active_template_info", TestLoadTemplateInfo._orig)

  _orig = da._load_active_template_info

  async def _call(self, monkeypatch, templates, details, tid=None):
    import app.core.template_storage as ts
    monkeypatch.setattr(ts, "list_templates", AsyncMock(return_value=templates))
    monkeypatch.setattr(ts, "get_template_detail", AsyncMock(side_effect=lambda i: details.get(i)))
    return await da._load_active_template_info(tid)

  @pytest.mark.asyncio
  async def test_by_id(self, monkeypatch):
    res = await self._call(monkeypatch, [], {"t1": {"content": " C ", "filename": "a.XLSX"}}, "t1")
    assert res == ("C", "xlsx")

  @pytest.mark.asyncio
  async def test_candidates_by_module_and_fallback(self, monkeypatch):
    tmpls = [{"id": "a", "module": "otro"}, {"id": "b", "module": "Mejoras"}]
    res = await self._call(monkeypatch, tmpls, {"b": {"content": "B", "filename": "noext"}})
    assert res == ("B", "docx")
    res = await self._call(monkeypatch, [{"id": "a", "module": "x"}], {"a": {"content": "A", "filename": "f.docx"}})
    assert res == ("A", "docx")
    res = await self._call(monkeypatch, [{"id": "a"}], {"a": {"content": "  "}})
    assert res == ("", "docx")

  @pytest.mark.asyncio
  async def test_exception_swallowed(self, monkeypatch):
    import app.core.template_storage as ts
    monkeypatch.setattr(ts, "list_templates", AsyncMock(side_effect=RuntimeError("x")))
    assert await da._load_active_template_info(None) == ("", "docx")
    assert await da._load_active_template_content(None) == ""


class TestResolveIntentWithModel:
  def _req(self, **kw):
    return da.AgenticPromptRequest(query="mejora el documento", **kw)

  @pytest.mark.asyncio
  async def test_rules_only_when_disabled(self):
    intent, info = await da._resolve_intent(self._req(), "u", None)
    assert intent == "chat" and info == {"intent_source": "rules"}

  @pytest.mark.asyncio
  async def test_no_fast_provider(self, monkeypatch):
    monkeypatch.setattr(da, "classifier_enabled", lambda: True)
    def boom(**kw):
      raise ValueError("no provider")
    monkeypatch.setattr(da, "resolve_provider", boom)
    intent, info = await da._resolve_intent(self._req(), "u", None)
    assert intent == "chat" and info["intent_source"] == "rules"

  @pytest.mark.asyncio
  async def test_model_decides(self, monkeypatch):
    monkeypatch.setattr(da, "classifier_enabled", lambda: True)
    monkeypatch.setattr(da, "resolve_provider", lambda **kw: object())
    monkeypatch.setattr(da, "classify_intent_with_model",
                        AsyncMock(return_value=SimpleNamespace(intent="generic_report", cached=True)))
    intent, info = await da._resolve_intent(self._req(), "u", None)
    assert intent == "generic_report"
    assert info["intent_source"] == "model_cache" and info["intent_rules"] == "chat"
    assert "intent_classifier_ms" in info



class TestHistoryAndMerge:
  @pytest.mark.asyncio
  async def test_history_from_db(self):
    repo = FakeRepo(messages=[{"role": "user", "content": "a"}, {"role": "system", "content": "s"},
                              {"role": "assistant", "content": ""}])
    req = da.AgenticPromptRequest(query="x", conversationId="c1")
    assert await da._resolve_chat_history(req, repo, "u") == [{"role": "user", "content": "a"}]

  @pytest.mark.asyncio
  async def test_history_fallbacks(self):
    repo = FakeRepo(fail=True)
    req = da.AgenticPromptRequest(query="x", conversationId="c1",
                                  conversationHistory=[{"role": "user", "content": "h"}])
    assert await da._resolve_chat_history(req, repo, "u") == [{"role": "user", "content": "h"}]
    req = da.AgenticPromptRequest(query="x", chat_context="user: hi")
    assert await da._resolve_chat_history(req, repo, "u") == ["user: hi"]
    req = da.AgenticPromptRequest(query="x", chat_context=["a", "b"])
    assert await da._resolve_chat_history(req, repo, "u") == ["a", "b"]
    assert await da._resolve_chat_history(da.AgenticPromptRequest(query="x"), repo, "u") is None

  @pytest.mark.asyncio
  async def test_active_intent_load_failure(self):
    req = da.AgenticPromptRequest(query="x", conversationId="c1")
    assert await da._resolve_active_artifact_intent(req, FakeRepo(fail=True), "u") is None

  def test_merge(self):
    merged = da._merge_session_artifacts(
      [{"id": "keep", "title": "Plan", "content": "old"}],
      [{"id": "new", "title": " plan ", "content": "new"}, {"title": "Otro"}],
    )
    assert merged[0] == {"id": "keep", "title": " plan ", "content": "new"}
    assert merged[1] == {"title": "Otro"}


class TestFinalizeAndErrors:
  def _prepared(self, intent, truncated=False):
    cfg = SimpleNamespace(run_info={"truncated": truncated})
    return da._PreparedRun(cfg=cfg, intent=intent, query_text="q", sources=["knowledge"], template_ext="docx")

  def test_fallback_artifact_for_generative(self):
    out = da._finalize_answer("contenido largo", self._prepared("generic_plan"))
    assert out.artifacts and out.artifacts[0]["intent"] == "generic_plan"
    assert "panel de artefactos" in out.assistant_message
    out = da._finalize_answer("doc", self._prepared("template_mutation"))
    assert out.is_template and "corporativo" in out.assistant_message
    out = da._finalize_answer("doc", self._prepared("generic_report"))
    assert out.artifacts[0]["title"]

  def test_chat_and_truncation(self):
    out = da._finalize_answer("hola", self._prepared("chat", truncated=True))
    assert out.artifacts == [] and out.assistant_message.startswith("hola")
    assert da.TRUNCATION_NOTICE in out.assistant_message

  def test_format_errors(self):
    assert da._format_stream_error(AIError(code="x", user_message="msg")) == "msg"
    assert da._format_stream_error(ValueError("bad cfg")) == "bad cfg"
    assert "inesperado" in da._format_stream_error(RuntimeError("boom"))
    assert da._error_code(RuntimeError()) == "run_exception"

  def test_log_failure_once(self):
    cfg = SimpleNamespace(run_info={}, feature="f", intent="chat", conversation_id="c", provider=None, model=None)
    with patch.object(da, "log_ai_call") as log:
      da._log_request_failure(cfg, RuntimeError("x"), streamed=True)
      da._log_request_failure(cfg, RuntimeError("x"), streamed=True)
    assert log.call_count == 1 and cfg.run_info["logged"] is True

  @pytest.mark.asyncio
  async def test_persist_failure_is_swallowed(self):
    req = da.AgenticPromptRequest(query="x")
    out = da._finalize_answer("hola", self._prepared("chat"))
    await da._persist_turn(FakeRepo(fail=True), req=req, user_id="u", conv_id="c", user_text="x",
                           prepared=self._prepared("chat"), outcome=out, full_content="hola")


class TestRubricAndExportHelpers:
  def test_parse_structured(self):
    assert da._try_parse_structured_artifact("plain text", "t") is None
    assert da._try_parse_structured_artifact("[1]", "t") is None
    assert da._try_parse_structured_artifact("{bad json}", "t") is None
    assert da._try_parse_structured_artifact('{"other": 1}', "t") is None
    assert da._try_parse_structured_artifact('```json\n{"other": 1}\n```', "t") is None
    assert da._try_parse_structured_artifact("```json nope```", "t") is None

  def test_rubric_scores(self, monkeypatch):
    assert da._evaluate_artifacts_rubric([]) == (100.0, "Sin artefactos estructurados")
    imp = FunctionalImprovementArtifact.model_construct()
    inv = FunctionalInventoryArtifact.model_construct()
    seq = iter([imp, inv, None, None])
    monkeypatch.setattr(da, "_try_parse_structured_artifact", lambda c, t: next(seq))
    res = SimpleNamespace(score=40.0, approved=False, missing_requirements=["falta X"])
    monkeypatch.setattr(da.RubricEvaluator, "evaluate_improvement", staticmethod(lambda a: res))
    monkeypatch.setattr(da.RubricEvaluator, "evaluate_inventory", staticmethod(lambda a: res))
    score, fb = da._evaluate_artifacts_rubric(
      [{"content": "x"}, {"content": "y"}, {"content": "z" * 60}, {"content": "short"}])
    assert score == round((40 + 40 + 85 + 50) / 4, 1)
    assert fb == "falta X; falta X"

  def test_resolve_export_data(self):
    assert da._resolve_export_data("", {"a": 1}, "T") == {"a": 1, "title": "T"}
    assert da._resolve_export_data('{"b": 2}', None, "T") == {"b": 2, "title": "T"}
    assert da._resolve_export_data("{nope}", None, "T")["markdown"] == "{nope}"


# --------------------------------------------------------------------- endpoints

class TestSimpleEndpoints:
  def test_fixtures(self, client, monkeypatch):
    monkeypatch.setattr(da, "list_templates", AsyncMock(return_value=[
      {"id": "1", "title": "A", "filename": "a.xlsx"}, {"id": "2", "title": "B", "filename": "b.docx", "tags": ["x"]}]))
    r = client.get("/api/doc-agent/fixtures")
    assert r.status_code == 200
    fx = r.json()["fixtures"]
    assert fx[0]["kind"] == "spreadsheet" and fx[1]["kind"] == "document" and fx[1]["tags"] == ["x"]

  def test_parse_attachment(self, client, monkeypatch):
    r = client.post("/api/doc-agent/parse-attachment", files={"file": ("a.txt", b"hola mundo", "text/plain")})
    assert r.status_code == 200 and r.json()["content"].strip() == "hola mundo"
    r = client.post("/api/doc-agent/parse-attachment", files={"file": ("a.txt", b"", "text/plain")})
    assert r.status_code == 400
    monkeypatch.setattr(da, "extract_text", lambda **kw: (_ for _ in ()).throw(RuntimeError("bad")))
    r = client.post("/api/doc-agent/parse-attachment", files={"file": ("a.pdf", b"x", "application/pdf")})
    assert r.status_code == 400 and "bad" in r.json()["detail"]

  def test_validate(self, client, monkeypatch):
    assert client.post("/api/doc-agent/validate", json={}).status_code == 400
    monkeypatch.setattr(da.DocumentOperationValidator, "validate", staticmethod(lambda op, st: (True, type(op).__name__)))
    state = {"documentId": "d"}
    tgt = {"sectionTitle": "S"}
    cases = {
      "insert_image": {"operation": "insert_image", "target": tgt, "asset": {"assetId": "a"}},
      "insert_text": {"operation": "insert_text", "target": tgt, "content": "c"},
      "replace_content": {"operation": "replace_content", "target": tgt, "newContent": "n"},
      "other": {"operation": "weird"},
    }
    for key, op in cases.items():
      r = client.post("/api/doc-agent/validate", json={"state": state, "operation": op})
      assert r.status_code == 200, (key, r.text)
      assert r.json()["valid"] is True
    assert r.json()["message"] == "dict"

  def test_cancel_endpoints(self, client, monkeypatch):
    monkeypatch.setattr(da.run_registry, "cancel_run", lambda rid, reason: rid == "ok")
    assert client.post("/api/doc-agent/runs/ok/cancel").json() == {"status": "cancelled", "run_id": "ok"}
    assert client.post("/api/doc-agent/runs/no/cancel").status_code == 404
    assert client.post("/api/doc-agent/sessions/ok/cancel").json()["session_id"] == "ok"
    assert client.post("/api/doc-agent/sessions/no/cancel").status_code == 404


class TestExports:
  def test_docx_default_and_levantamiento(self, client, monkeypatch):
    monkeypatch.setattr(da, "create_mejoras_docx", lambda text, title: b"MEJ")
    monkeypatch.setattr(da, "create_levantamiento_docx", lambda text, title: b"LEV")
    r = client.post("/api/doc-agent/export-docx", json={"markdown": "# x", "title": "Mi doc!"})
    assert r.status_code == 200 and r.content == b"MEJ"
    assert 'filename="Mi_doc_.docx"' in r.headers["content-disposition"]
    r = client.post("/api/doc-agent/export-docx", json={"markdown": "# x", "title": "Levantamiento"})
    assert r.content == b"LEV"

  def test_docx_template(self, client, monkeypatch, tmp_path):
    p = tmp_path / "t.docx"
    monkeypatch.setattr(da, "get_template_file_path", lambda tid: p)
    monkeypatch.setattr(da.DocxTemplateRenderer, "render", staticmethod(lambda path, data: b"TPL:" + data["title"].encode()))
    r = client.post("/api/doc-agent/export-docx", json={"templateId": "t", "title": "T", "artifactData": {"k": 1}})
    assert r.content == b"TPL:T"

  def test_docx_error(self, client, monkeypatch):
    monkeypatch.setattr(da, "create_mejoras_docx", lambda text, title: (_ for _ in ()).throw(RuntimeError("kaboom")))
    r = client.post("/api/doc-agent/export-docx", json={"markdown": "x"})
    assert r.status_code == 500 and "kaboom" in r.json()["detail"]

  def test_xlsx_variants(self, client, monkeypatch, tmp_path):
    monkeypatch.setattr(da, "create_inventario_xlsx", lambda **kw: b"INV")
    monkeypatch.setattr(da, "create_qa_matrix_xlsx", lambda **kw: b"QA")
    r = client.post("/api/doc-agent/export-xlsx", json={"title": "Inventario"})
    assert r.status_code == 200 and r.content == b"INV"
    r = client.post("/api/doc-agent/export-xlsx", json={"title": "Matriz", "rows": [{"a": 1}]})
    assert r.content == b"QA"
    p = tmp_path / "t.xlsx"
    monkeypatch.setattr(da, "get_template_file_path", lambda tid: p)
    monkeypatch.setattr(da.XlsxTemplateRenderer, "render", staticmethod(lambda path, data: json.dumps(data["rows"]).encode()))
    r = client.post("/api/doc-agent/export-xlsx", json={"templateId": "t", "rows": [{"a": 1}]})
    assert json.loads(r.content) == [{"a": 1}]

  def test_xlsx_error(self, client, monkeypatch):
    monkeypatch.setattr(da, "create_qa_matrix_xlsx", lambda **kw: (_ for _ in ()).throw(RuntimeError("bad")))
    r = client.post("/api/doc-agent/export-xlsx", json={"title": "Matriz"})
    assert r.status_code == 500 and "bad" in r.json()["detail"]


class TestAgenticPromptFastHandlers:
  def test_image_insertion(self, client):
    r = client.post("/api/doc-agent/agentic-prompt",
                    json={"query": "incluye en las observaciones estas imágenes", "attachedAssetIds": ["a1", "a2"]})
    assert r.status_code == 200
    body = r.json()
    assert body["intentDetected"] == "insert_asset_in_section"
    assert len(body["operations"]) == 2 and "2 imagen" in body["answer"]

  def test_correction_pepito_and_generic(self, client):
    r = client.post("/api/doc-agent/agentic-prompt", json={"query": "Corregir, Pepito no es líder"})
    assert r.json()["intentDetected"] == "correct_document_content"
    assert "Pepito" in r.json()["assistantMessage"]
    r = client.post("/api/doc-agent/agentic-prompt", json={"query": "cambia el alcance"})
    assert "Solución" in r.json()["assistantMessage"]

  def test_responsables(self, client):
    r = client.post("/api/doc-agent/agentic-prompt", json={"query": "agrega al doctor Pepito Perez usuario funcional"})
    assert r.json()["intentDetected"] == "add_responsables"
    assert "Usuario Funcional" in r.json()["answer"]
    r = client.post("/api/doc-agent/agentic-prompt", json={"query": "agrega participantes"})
    assert "Participante Asignado" in r.json()["answer"]

  def test_stream_fast_path_v1_and_v2(self, client):
    r = client.post("/api/doc-agent/agentic-prompt-stream", json={"query": "agrega participantes"})
    ev = _sse(r.text)
    assert ev[0][1]["type"] == "full" and ev[0][1]["data"]["intentDetected"] == "add_responsables"
    r = client.post("/api/doc-agent/agentic-prompt-stream?protocol=v2", json={"query": "agrega participantes"})
    assert _sse(r.text)[0][0] == "done"


class TestAgenticPromptLLM:
  def test_rejects_local_providers(self, client):
    from app.ai.providers.registry import FORBIDDEN_BACKEND_PROVIDERS
    bad = next(iter(FORBIDDEN_BACKEND_PROVIDERS))
    r = client.post("/api/doc-agent/agentic-prompt", json={"query": "hola", "provider": bad})
    assert r.status_code == 400
    r = client.post("/api/doc-agent/agentic-prompt", json={"query": "hola", "model": "x.GGUF"})
    assert r.status_code == 400 and "GGUF" in r.json()["detail"]

  def test_chat_answer_persisted(self, client, repo):
    with patch.object(da, "run_agentic_chat_stream", _runner(AgentEvent(type="status", data={}), "Hola ", "mundo")):
      r = client.post("/api/doc-agent/agentic-prompt",
                      json={"query": "hola", "conversationId": "c1", "chat_context": ["user: a"]})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Hola mundo" and body["intentDetected"] == "chat"
    assert body["documentUpdates"] is None
    assert [m["role"] for m in repo.saved_messages] == ["user", "assistant"]
    assert "artifacts" not in repo.saved_sessions[0]

  def test_template_answer_stores_document(self, client, repo):
    repo.artifacts = [{"id": "old", "title": "Documento", "intent": "template_mutation"}]
    with patch.object(da, "run_agentic_chat_stream", _runner("# contenido")):
      r = client.post("/api/doc-agent/agentic-prompt",
                      json={"query": "regenera", "conversationId": "c1", "templateId": "t"})
    body = r.json()
    assert body["intentDetected"] == "template_mutation" and body["requiresDocumentMutation"] is True
    assert body["documentUpdates"] == "# contenido"
    sess = repo.saved_sessions[0]
    assert sess["document_content"] == "# contenido" and sess["artifacts"][0]["id"] == "old"

  def test_runner_failure_returns_502(self, client):
    with patch.object(da, "run_agentic_chat_stream", _runner(exc=AIError(code="x", user_message="falló"))), \
         patch.object(da, "log_ai_call"):
      r = client.post("/api/doc-agent/agentic-prompt", json={"query": "hola"})
    assert r.status_code == 502 and r.json()["detail"] == "falló"


class TestStreamV1:
  def test_full_v1_flow_with_events_and_artifacts(self, client, repo):
    events = [
      AgentEvent(type="tool_call", data={"id": "1", "name": "search"}),
      AgentEvent(type="tool_result", data={"id": "1", "name": "search"}),
      AgentEvent(type="plan", data={"sections": ["A", "B"]}),
      AgentEvent(type="status", data={"stage": "section", "section_index": 0, "section_title": "A"}),
      AgentEvent(type="status", data={"stage": "section", "section_index": 1, "section_title": "B", "pending": True}),
      AgentEvent(type="usage", data={}),
    ]
    run = _runner(*events, '<chat>Listo</chat>\n<artifact title="Plan" extension="docx"># Plan\n</artifact>')
    with patch.object(da, "run_agentic_chat_stream", run):
      r = client.post("/api/doc-agent/agentic-prompt-stream",
                      json={"query": "genera un plan de pruebas", "runId": "run-x", "conversationId": "c9"})
    assert r.status_code == 200
    packets = [d for _, d in _sse(r.text)]
    types = [p.get("type") for p in packets]
    assert "intent" in types and "token" in types and types[-1] == "done"
    full = next(p for p in packets if p.get("type") == "full")["data"]
    assert full["run_id"] == "run-x" and full["conversation_id"] == "c9"
    assert full["artifacts"][0]["title"] == "Plan" and full["rubric_score"] is not None
    assert repo.saved_sessions and repo.saved_sessions[0]["artifacts"][0]["intent"] == "generic_plan"

  def test_empty_response(self, client):
    with patch.object(da, "run_agentic_chat_stream", _runner("  ")):
      r = client.post("/api/doc-agent/agentic-prompt-stream", json={"query": "hola"})
    assert any(d.get("type") == "error" and "no generó" in d["message"] for _, d in _sse(r.text))
    with patch.object(da, "run_agentic_chat_stream", _runner("")):
      r = client.post("/api/doc-agent/agentic-prompt-stream?protocol=v2", json={"query": "hola"})
    errs = [d for n, d in _sse(r.text) if n == "error"]
    assert errs[0]["code"] == "empty_response"

  def test_exception_v1(self, client):
    with patch.object(da, "run_agentic_chat_stream", _runner("a", exc=RuntimeError("x"))), \
         patch.object(da, "log_ai_call") as log:
      r = client.post("/api/doc-agent/agentic-prompt-stream", json={"query": "hola"})
    errs = [d for _, d in _sse(r.text) if d.get("type") == "error"]
    assert errs and "inesperado" in errs[0]["message"]
    log.assert_called_once()

  def test_cancelled_v1_and_v2(self, client):
    with patch.object(da, "run_agentic_chat_stream", _runner("a", exc=StreamStopped("cancelled"))):
      r = client.post("/api/doc-agent/agentic-prompt-stream", json={"query": "hola"})
    assert r.status_code == 200 and "error" not in [d.get("type") for _, d in _sse(r.text)]
    with patch.object(da, "run_agentic_chat_stream", _runner("a", exc=StreamStopped("cancelled"))):
      r = client.post("/api/doc-agent/agentic-prompt-stream?protocol=v2", json={"query": "hola"})
    errs = [d for n, d in _sse(r.text) if n == "error"]
    assert errs[0]["code"] == "cancelled"
    with patch.object(da, "run_agentic_chat_stream", _runner("a", exc=StreamStopped("disconnected"))):
      r = client.post("/api/doc-agent/agentic-prompt-stream?protocol=v2", json={"query": "hola"})
    assert not [n for n, _ in _sse(r.text) if n == "error"]


class TestShouldStop:
  """Drive the stream generator directly to exercise the cancellation poll."""

  @pytest.mark.asyncio
  async def test_cancel_and_disconnect(self, monkeypatch):
    captured = {}

    def fake_iter(gen, should_stop, poll_s):
      captured["should_stop"] = should_stop

      async def it():
        yield "hola"
      return it()

    monkeypatch.setattr(da, "iterate_until_stopped", fake_iter)
    monkeypatch.setattr(da, "run_agentic_chat_stream", _runner("hola"))
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=True))
    req = da.AgenticPromptRequest(query="hola", runId="r-stop")
    resp = await da.handle_agentic_prompt_stream(request, req, current_user={"id": "u"},
                                                 chat_repo=FakeRepo(), protocol="v2")
    agen = resp.body_iterator
    first = await agen.__anext__()
    assert "classify" in first
    await agen.__anext__()  # forces iterate_until_stopped
    should_stop = captured["should_stop"]
    assert await should_stop() == "disconnected"
    assert await should_stop() == "cancelled"  # emitter now cancelled
    async for _ in agen:
      pass
