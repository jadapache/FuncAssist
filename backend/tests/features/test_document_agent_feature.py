"""
Comprehensive feature test suite for Document Agent & Chat.
Covers:
1. Intent classification and prompt routing.
2. Document operations and validation against canonical document state.
3. Run lifecycle, cancellation, and event serialization.
4. Declarative artifact exports and rubric evaluations.
"""

from __future__ import annotations

import io
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.document_agent import (
  router,
  classify_prompt_intent,
  AgenticPromptRequest,
  _try_parse_structured_artifact,
  _evaluate_artifacts_rubric,
)
from app.core.document_agent.schema import (
  CanonicalDocumentState,
  DocumentSection,
  InsertImageOperation,
  TargetLocator,
  AssetLocator,
)
from app.core.document_agent.validator import DocumentOperationValidator
from app.services.event_serializer import AgentRunEmitter, run_registry
from app.schemas.artifacts import FunctionalImprovementArtifact, GherkinScenario


@pytest.fixture
def client() -> TestClient:
  app = FastAPI()
  app.include_router(router, prefix="/api")
  return TestClient(app)


class TestDocumentAgentIntents:
  """Intent detection and slash command parsing."""

  def test_slash_command_classification(self):
    assert classify_prompt_intent("/plan Pruebas de regresión") == "generic_plan"
    assert classify_prompt_intent("/informe Hallazgos de QA") == "generic_report"
    assert classify_prompt_intent("/report Estado del sprint") == "generic_report"
    assert classify_prompt_intent("/pregunta Cuántos casos fallaron") == "ask_product"
    assert classify_prompt_intent("/ask Detalles del servicio de autenticación") == "ask_product"

  def test_conversational_and_template_intents(self):
    assert classify_prompt_intent("¿Cómo estructurar una prueba de carga?") == "chat"
    assert classify_prompt_intent("Genera el documento de mejora para login") == "template_mutation"
    assert classify_prompt_intent("Completa la plantilla con los hallazgos") == "template_mutation"
    # Prompt descriptivo sin palabras clave pero con template corporativo activo:
    assert classify_prompt_intent("De acuerdo a las transcripciones de los embargos", template_id="tmpl-inventario") == "template_mutation"
    # Si es pregunta directa, preserva modo chat aun con template activo:
    assert classify_prompt_intent("¿Qué campos requiere este formulario?", template_id="tmpl-inventario") == "chat"

  def test_explicit_mode_override(self):
    assert classify_prompt_intent("texto", mode="plan") == "generic_plan"
    assert classify_prompt_intent("texto", mode="report") == "generic_report"
    assert classify_prompt_intent("texto", mode="chat") == "chat"
    assert classify_prompt_intent("texto", mode="template") == "template_mutation"


class TestDocumentAgentOperations:
  """Canonical document state and operation validation."""

  def test_validate_operation_targeting_existing_section(self):
    state = CanonicalDocumentState(
      document_id="doc_101",
      title="Plan de Pruebas",
      sections=[DocumentSection(id="sec_1", title="Observaciones Complementarias", preview_text="...")],
      tags_present=["OBSERVACIONES"],
    )
    op = InsertImageOperation(
      target=TargetLocator(section_title="Observaciones", position="inside_end"),
      asset=AssetLocator(asset_id="img_01", url="http://localhost:8000/assets/img_01.png"),
    )
    valid, msg = DocumentOperationValidator.validate(op, state, available_asset_ids=["img_01"])
    assert valid is True
    assert "Matched section" in msg

  def test_validate_operation_rejects_missing_target(self):
    state = CanonicalDocumentState(
      document_id="doc_102",
      title="Plan de Pruebas",
      sections=[DocumentSection(id="sec_1", title="Alcance", preview_text="...")],
    )
    op = InsertImageOperation(
      target=TargetLocator(section_title="Seccion Inexistente", position="inside_end"),
      asset=AssetLocator(asset_id="img_01", url="http://localhost:8000/assets/img_01.png"),
    )
    valid, msg = DocumentOperationValidator.validate(op, state, available_asset_ids=["img_01"])
    assert valid is False
    assert "Target not found" in msg


class TestDocumentAgentLifecycle:
  """Request aliases, run registry, cancellation, and events."""

  def test_agentic_prompt_request_aliases(self):
    req = AgenticPromptRequest(query="test", runId="run-123", conversationId="conv-456")
    assert req.run_id == "run-123"
    assert req.conversation_id == "conv-456"

  def test_cancel_nonexistent_run_returns_404(self, client: TestClient):
    resp = client.post("/api/doc-agent/runs/nonexistent-run-xyz/cancel")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()

  def test_cancel_active_run_via_api(self, client: TestClient):
    emitter = AgentRunEmitter(run_id="run-active-test-01", conversation_id="conv-01")
    run_registry.register(emitter)
    try:
      resp = client.post("/api/doc-agent/runs/run-active-test-01/cancel")
      assert resp.status_code == 200
      data = resp.json()
      assert data["status"] in ("cancelling", "cancelled")
      assert emitter.is_cancelled is True
    finally:
      run_registry.unregister("run-active-test-01")


class TestDeclarativeArtifactsAndExport:
  """Structured artifacts and evaluation."""

  def test_structured_artifact_parsing(self):
    json_payload = (
      '{\n'
      '  "artifact_id": "art-101",\n'
      '  "title": "Optimización Login",\n'
      '  "problem_statement": "El login actual tiene latencia alta y bloqueos",\n'
      '  "business_objective": "Reducir el tiempo de respuesta a menos de 200ms",\n'
      '  "actors": ["Usuario"],\n'
      '  "main_flow": ["Paso 1", "Paso 2", "Paso 3"],\n'
      '  "alternate_flows": ["Error de red"],\n'
      '  "acceptance_criteria": []\n'
      '}'
    )
    parsed = _try_parse_structured_artifact(json_payload, "Test")
    assert isinstance(parsed, FunctionalImprovementArtifact)
    assert parsed.title == "Optimización Login"

  def test_evaluate_artifacts_rubric(self):
    art = FunctionalImprovementArtifact(
      artifact_id="art-test",
      title="Validación Biométrica",
      problem_statement="El sistema actual carece de doble factor biométrico en sedes críticas.",
      business_objective="Garantizar la identidad y autenticación estricta del personal.",
      actors=["Médico", "Enfermera"],
      main_flow=["Ingresar cédula", "Capturar huella", "Confirmar acceso"],
      alternate_flows=["Falla en sensor biométrico"],
      acceptance_criteria=[
        GherkinScenario(
          title="Huella válida",
          given=["un médico registrado"],
          when=["coloca su dedo en el lector"],
          then=["se autoriza el ingreso al sistema"],
        )
      ],
    )
    art_dict = {"title": art.title, "content": art.model_dump_json(), "extension": "docx"}
    score, feedback = _evaluate_artifacts_rubric([art_dict])
    assert score >= 75.0
    assert "aprobados" in feedback.lower()
