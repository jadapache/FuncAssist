"""Tests for template renderers, rubric evaluator, event serializer, document base and schemas."""

from __future__ import annotations

import asyncio
import io
import json

import openpyxl
import pytest
from docx import Document
from pydantic import ValidationError

from app.models.ai import AIModelInfo, ModelCatalogResponse
from app.schemas.agent_events import AgentEvent, AgentEventType, RunEventEnvelope, sse_event
from app.schemas.artifacts import (
  FunctionalImprovementArtifact,
  FunctionalInventoryArtifact,
  GherkinScenario,
  InventoryComponent,
  InventoryModule,
)
from app.schemas.user import UserBase, UserCreate, UserInDB, UserResponse
from app.services.documents.base import DocumentMetadata, IDocumentBuilder
from app.services.event_serializer import AgentRunEmitter, RunRegistry
from app.services.rubric_evaluator import RubricEvaluator
from app.services.template_renderer import DocxTemplateRenderer, XlsxTemplateRenderer


# --- DOCX template renderer ---------------------------------------------------

def _docx_template() -> bytes:
  doc = Document()
  p = doc.add_paragraph()
  p.add_run("Proyecto: {{pro")
  p.add_run("ject.name}} v{{version}}")
  doc.add_paragraph("Sin marcadores")
  doc.add_paragraph("{{unknown}} queda")
  doc.add_paragraph("Lista: {{tags}} | {{none}}")
  t = doc.add_table(rows=1, cols=1)
  t.rows[0].cells[0].text = "Autor {{author}}"
  doc.sections[0].header.paragraphs[0].text = "H {{project.name}}"
  doc.sections[0].footer.paragraphs[0].text = "F {{version}}"
  buf = io.BytesIO()
  doc.save(buf)
  return buf.getvalue()


DATA = {"project": {"name": "Atlas"}, "version": 2, "tags": ["a", "b"],
        "items": [{"x": 1}], "author": "Ana", "none": None}


@pytest.mark.parametrize("kind", ["bytes", "bytesio", "path"])
def test_docx_renderer_replaces_split_runs_tables_headers(kind, tmp_path):
  tpl = _docx_template()
  if kind == "bytesio":
    src = io.BytesIO(tpl)
  elif kind == "path":
    path = tmp_path / "t.docx"
    path.write_bytes(tpl)
    src = str(path)
  else:
    src = tpl
  out = Document(io.BytesIO(DocxTemplateRenderer.render(src, DATA)))
  texts = [p.text for p in out.paragraphs]
  assert texts[0] == "Proyecto: Atlas v2"
  assert texts[1] == "Sin marcadores"
  assert texts[2] == "{{unknown}} queda"
  assert texts[3] == "Lista: - a\n- b | "
  assert out.tables[0].rows[0].cells[0].text == "Autor Ana"
  assert out.sections[0].header.paragraphs[0].text == "H Atlas"
  assert out.sections[0].footer.paragraphs[0].text == "F 2"


def test_docx_flatten_and_runless_paragraph():
  flat = DocxTemplateRenderer._flatten_dict(DATA)
  assert "items" not in flat and flat["project.name"] == "Atlas" and flat["none"] == ""
  assert DocxTemplateRenderer._flatten_dict({"empty": []}) == {"empty": ""}

  doc = Document()
  p = doc.add_paragraph()
  DocxTemplateRenderer._apply_replacement_to_runs(p, "nuevo")
  assert p.text == "nuevo"


# --- XLSX template renderer ---------------------------------------------------

def _xlsx_template() -> bytes:
  wb = openpyxl.Workbook()
  ws = wb.active
  ws["A1"] = "Proyecto {{project.name}}"
  ws["A2"] = "=SUM(1,2)"
  ws["A3"] = 42
  ws["A4"] = "{{tags}} / {{missing}}"
  ws2 = wb.create_sheet("Dos")
  ws2["B2"] = "v{{version}}"
  buf = io.BytesIO()
  wb.save(buf)
  return buf.getvalue()


@pytest.mark.parametrize("kind", ["bytes", "bytesio", "path"])
def test_xlsx_renderer(kind, tmp_path):
  tpl = _xlsx_template()
  if kind == "bytesio":
    src = io.BytesIO(tpl)
  elif kind == "path":
    path = tmp_path / "t.xlsx"
    path.write_bytes(tpl)
    src = str(path)
  else:
    src = tpl
  out = openpyxl.load_workbook(io.BytesIO(XlsxTemplateRenderer.render(
    src, DATA, cell_coordinates={"C1": "Autor: {{author}}", "C2": 7})))
  ws = out.active
  assert ws["A1"].value == "Proyecto Atlas"
  assert ws["A2"].value == "=SUM(1,2)"
  assert ws["A3"].value == 42
  assert ws["A4"].value == "a, b / {{missing}}"
  assert ws["C1"].value == "Autor: Ana"
  assert ws["C2"].value == "7"
  assert out["Dos"]["B2"].value == "v2"


def test_xlsx_renderer_without_coordinates_and_flatten():
  out = openpyxl.load_workbook(io.BytesIO(XlsxTemplateRenderer.render(_xlsx_template(), {})))
  assert out.active["A1"].value == "Proyecto {{project.name}}"
  flat = XlsxTemplateRenderer._flatten_dict({"a": {"b": None}, "l": [{"x": 1}], "e": []})
  assert flat == {"a.b": "", "e": ""}


# --- Artifacts + rubric evaluator ---------------------------------------------

def _good_improvement(**over):
  base = dict(
    artifact_id="imp-1",
    title="Mejora de pagos",
    problem_statement="Los pagos fallan intermitentemente en horas pico.",
    business_objective="Reducir fallas al 1 por ciento",
    actors=["Cliente"],
    main_flow=["Ingresa", "Paga", "Confirma"],
    alternate_flows=["Tarjeta rechazada"],
    acceptance_criteria=[GherkinScenario(title="Pago ok", given=["saldo"], when=["paga"], then=["confirma"])],
    impacted_systems=["Pasarela"],
  )
  base.update(over)
  return FunctionalImprovementArtifact(**base)


def test_improvement_rubric_full_score_and_markdown():
  art = _good_improvement()
  res = RubricEvaluator.evaluate_improvement(art)
  assert res.score == 100.0 and res.approved and res.missing_requirements == []
  md = art.to_markdown()
  assert md.startswith("# Mejora de pagos")
  assert "1. Ingresa\n2. Paga\n3. Confirma" in md
  assert "## Flujos Alternos\n- Tarjeta rechazada" in md
  assert "```gherkin\nEscenario: Pago ok\n  Dado saldo\n  Cuando paga\n  Entonces confirma\n```" in md
  assert "## Sistemas Impactados\n- Pasarela" in md




def _inventory(**over):
  base = dict(
    artifact_id="inv-1", title="Inventario", project_name="Atlas",
    modules=[InventoryModule(module_id="m1", name="Auth", description="Autenticación", components=[
      InventoryComponent(component_id="c1", name="Login", description="Form", dependencies=["DB", "IdP"],
                         risk_level="high", coverage_level=0.8),
      InventoryComponent(component_id="c2", name="Logout", description="Btn"),
    ])],
    overall_coverage=0.5, identified_risks=["Sin MFA"],
  )
  base.update(over)
  return FunctionalInventoryArtifact(**base)


def test_inventory_rubric_and_markdown():
  art = _inventory()
  assert art.total_components == 2
  res = RubricEvaluator.evaluate_inventory(art)
  assert res.score == 100.0 and res.approved
  md = art.to_markdown()
  assert md.startswith("# Inventario - Atlas (v1.0.0)")
  assert "**Total de Módulos:** 1 | **Total Componentes:** 2 | **Cobertura Global:** 50.0%" in md
  assert "| c1 | Login | HIGH | 80% | DB, IdP |" in md
  assert "| c2 | Logout | MEDIUM | 0% | Ninguna |" in md
  assert "## Riesgos Identificados\n- Sin MFA" in md




def test_inventory_invalid_risk_level():
  with pytest.raises(ValidationError):
    InventoryComponent(component_id="c", name="n", description="d", risk_level="extreme")


# --- Event serializer ---------------------------------------------------------

def test_emitter_builds_sequenced_events():
  em = AgentRunEmitter("run-1", "conv-1")
  events = [
    em.started("chat", "gpt", "hola"),
    em.step_started("s1", "Buscar", "d"),
    em.step_completed("s1", "Buscar"),
    em.step_failed("s2", "Falla", "err"),
    em.message_delta("abc"),
    em.source_found("src", "Doc", "knowledge", "snip"),
    em.artifact_created("a1", "T", "c"),
    em.artifact_updated("a1", "T", "c2", extension="xlsx"),
    em.interaction_required("i1", "¿Seguro?", [{"label": "Sí", "value": "y"}], required=False),
    em.completed("fin", [{"id": "a1"}], ["src"]),
    em.failed("E1", "Error", "trace"),
    em.cancelled("explicit"),
  ]
  assert [e.sequence for e in events] == list(range(1, 13))
  assert [e.type for e in events] == [
    AgentEventType.RUN_STARTED, AgentEventType.RUN_STEP_STARTED, AgentEventType.RUN_STEP_COMPLETED,
    AgentEventType.RUN_STEP_FAILED, AgentEventType.MESSAGE_DELTA, AgentEventType.SOURCE_FOUND,
    AgentEventType.ARTIFACT_CREATED, AgentEventType.ARTIFACT_UPDATED, AgentEventType.INTERACTION_REQUIRED,
    AgentEventType.RUN_COMPLETED, AgentEventType.RUN_FAILED, AgentEventType.RUN_CANCELLED,
  ]
  assert all(e.run_id == "run-1" and e.conversation_id == "conv-1" for e in events)
  assert events[1].data.status.value == "in_progress"
  assert events[8].data.options[0].label == "Sí" and events[8].data.required is False
  assert events[7].data.extension == "xlsx"
  assert events[11].data.reason == "explicit"

  start_pkt = json.loads(events[0].to_sse_packet()[len("data: "):])
  assert start_pkt["intent"] == "chat" and start_pkt["sequence"] == 1
  delta_pkt = json.loads(events[4].to_sse_packet()[len("data: "):])
  assert delta_pkt["text"] == "abc"


def test_emitter_cancellation_reason_defaults():
  em = AgentRunEmitter("r", "c")
  assert em.cancelled().data.reason == "Run cancelled by user"
  assert not em.is_cancelled
  em.request_cancellation("stop")
  assert em.is_cancelled and em._cancel_event.is_set()
  assert em.cancelled().data.reason == "stop"


def test_envelope_dict_data_packets():
  env = RunEventEnvelope(run_id="r", conversation_id="c", sequence=1,
                         type=AgentEventType.MESSAGE_DELTA, data={"delta": "x"})
  assert '"text": "x"' in env.to_sse_packet()
  assert AgentEvent(type="delta", data={"t": "ñ"}).to_sse() == 'event: delta\ndata: {"t": "ñ"}\n\n'
  assert sse_event("done", {}) == "event: done\ndata: {}\n\n"


def test_run_registry_lifecycle(monkeypatch):

  reg = RunRegistry()
  em = AgentRunEmitter("run-1", "conv-1")
  reg.register(em)
  assert reg.get("run-1") is em and reg.get("conv-1") is em
  assert reg.cancel_run("conv-1", "bye") is True and em.is_cancelled
  assert reg.cancel_run("nope") is False

  reg._recently_terminated["old"] = 0.0
  reg.unregister("run-1")
  assert reg.get("run-1") is None and reg.get("conv-1") is None
  assert "old" not in reg._recently_terminated  # expired entry purged
  assert reg.cancel_run("run-1") is True  # recently terminated
  assert reg.cancel_run("conv-1") is True
  reg.unregister("unknown")  # no-op

  no_conv = AgentRunEmitter("run-2", "")
  reg.register(no_conv)
  assert reg.get("run-2") is no_conv
  reg.unregister("run-2")
  assert "run-2" in reg._recently_terminated and "" not in reg._recently_terminated


# --- documents base -------------------------------------------------------------

def test_document_builder_interface():
  with pytest.raises(TypeError):
    IDocumentBuilder()

  class TxtBuilder(IDocumentBuilder):
    async def build(self, content, metadata=None):
      await super().build(content, metadata)
      return (metadata.title if metadata else "").encode() + content["body"].encode()

    def get_mime_type(self):
      super().get_mime_type()
      return "text/plain"

    def get_extension(self):
      super().get_extension()
      return "txt"

  b = TxtBuilder()
  meta = DocumentMetadata(title="T", tags=["x"])
  assert meta.author == "FuncAssist" and meta.module == "general" and meta.created_at == ""
  assert DocumentMetadata(title="o").tags == []
  assert asyncio.run(b.build({"body": "!"}, meta)) == b"T!"
  assert b.get_mime_type() == "text/plain" and b.get_extension() == "txt"


# --- schemas / models -----------------------------------------------------------

def test_user_schemas():
  u = UserBase(username="  ana123 ")
  assert u.username == "ana123" and u.role == "user" and u.status == "pending" and u.email == ""
  for bad in ["ab", "ana-123", "x" * 21]:
    with pytest.raises(ValidationError):
      UserBase(username=bad)
  assert UserCreate(username="bob1", password_hash="h").password_hash == "h"

  class Row:
    id = "1"
    username = "carl"
    email = "c@x"
    full_name = "Carl"
    role = "admin"
    status = "approved"
    created_at = "2024"
    password_hash = None
    password_salt = None

  assert UserInDB.model_validate(Row()).id == "1"
  resp = UserResponse.model_validate(Row())
  assert resp.role == "admin" and resp.created_at == "2024"


def test_ai_model_catalog():
  m = AIModelInfo(id="p/m", raw_id="m", name="M", provider="p", provider_name="P", description="d",
                  context_window="8k", context_length=8000, tier_type="free", pricing_label="Gratis",
                  rate_limits="none")
  assert m.task_type == "chat_writing" and m.is_free is False and m.badge is None
  cat = ModelCatalogResponse(updated_at="now", source="live", providers=["p"], models=[m])
  assert cat.models[0].id == "p/m" and cat.error is None
