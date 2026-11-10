"""
Comprehensive feature test suite for Templates & Prompt Management.
Covers:
1. Declarative DOCX and XLSX template rendering with variable interpolation.
2. Rubric evaluation scoring for functional artifacts.
3. Template and prompt listing, updating, history, and resetting.
"""

from __future__ import annotations

import io
import pytest
from docx import Document
import openpyxl

from app.services.template_renderer import DocxTemplateRenderer, XlsxTemplateRenderer
from app.schemas.artifacts import FunctionalImprovementArtifact, GherkinScenario
from app.services.rubric_evaluator import RubricEvaluator
from app.ai.templates import (
  list_prompts,
  list_rubrics,
  get_prompt,
  get_rubric,
  reset_prompt,
  reset_rubric,
  ensure_ai_templates_seeded,
)
from app.api.routers.ai_templates import TemplateUpdate, RubricUpdate, update_prompt, update_rubric


@pytest.fixture(autouse=True)
def seed_templates():
  ensure_ai_templates_seeded()


class TestTemplateRenderers:
  """DOCX and XLSX template rendering."""

  def test_docx_template_variable_substitution(self):
    doc = Document()
    doc.add_paragraph("Documento: {{artifact.title}}")
    p2 = doc.add_paragraph()
    p2.add_run("Problema: {{artifact.")
    p2.add_run("problem}}")

    buf = io.BytesIO()
    doc.save(buf)
    data = {"artifact": {"title": "Sistema de Turnos", "problem": "Demora en sala"}}

    rendered_bytes = DocxTemplateRenderer.render(buf.getvalue(), data)
    rendered_doc = Document(io.BytesIO(rendered_bytes))
    full_text = " ".join(p.text for p in rendered_doc.paragraphs)

    assert "Documento: Sistema de Turnos" in full_text
    assert "Problema: Demora en sala" in full_text

  def test_xlsx_template_renderer_preserves_formulas(self):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "Proyecto: {{artifact.project}}"
    ws["B1"] = "=SUM(10, 20)"

    buf = io.BytesIO()
    wb.save(buf)
    data = {"artifact": {"project": "FuncAssist"}}

    rendered_bytes = XlsxTemplateRenderer.render(buf.getvalue(), data)
    rendered_wb = openpyxl.load_workbook(io.BytesIO(rendered_bytes))
    assert rendered_wb.active["A1"].value == "Proyecto: FuncAssist"
    assert rendered_wb.active["B1"].value == "=SUM(10, 20)"


class TestRubricEvaluator:
  """Rubric evaluation and criteria scoring."""

  def test_valid_improvement_passes_rubric(self):
    scenario = GherkinScenario(
      title="Creación exitosa",
      given=["que el usuario es líder funcional"],
      when=["completa el formulario"],
      then=["el sistema emite el documento"],
    )
    art = FunctionalImprovementArtifact(
      artifact_id="art-imp-1",
      title="Automatización de Reportes",
      problem_statement="La generación manual de reportes toma más de 5 horas a la semana.",
      business_objective="Reducir el tiempo de elaboración a menos de 10 minutos mediante IA.",
      actors=["Líder Funcional"],
      main_flow=["Ingresar al módulo", "Adjuntar evidencias", "Hacer clic en Generar"],
      alternate_flows=["Error de conexión"],
      acceptance_criteria=[scenario],
      impacted_systems=["FuncAssist"],
    )

    result = RubricEvaluator.evaluate_improvement(art, threshold=75.0)
    assert result.approved is True
    assert result.score == 100.0

  def test_deficient_improvement_fails_rubric(self):
    art = FunctionalImprovementArtifact(
      artifact_id="art-bad",
      title="Mejora Incompleta",
      problem_statement="Corto",
      business_objective="Sin detalle",
      actors=[],
      main_flow=["Paso 1"],
      alternate_flows=[],
      acceptance_criteria=[],
    )
    result = RubricEvaluator.evaluate_improvement(art, threshold=75.0)
    assert result.approved is False
    assert result.score < 50.0


class TestTemplatesApi:
  """Prompts and rubrics CRUD and reset lifecycle."""

  @pytest.mark.asyncio
  async def test_list_and_get_prompts_and_rubrics(self):
    prompts = await list_prompts()
    assert len(prompts) > 0
    first_feature = prompts[0]["feature"]
    item = await get_prompt(first_feature)
    assert item is not None
    assert item["feature"] == first_feature

    rubrics = await list_rubrics()
    assert len(rubrics) > 0

  @pytest.mark.asyncio
  async def test_update_and_reset_prompt(self):
    from app.api.routers.ai_templates import reset_prompt_endpoint
    original = await get_prompt("standup")
    original_version = original.get("version", 1)

    body = TemplateUpdate(
      system="Custom standup system test prompt",
      user_template="Custom user template {query} {context} {rubric}",
      allowed_sources=["jira", "github", "knowledge"],
    )
    saved = await update_prompt("standup", body)
    assert saved["system"] == "Custom standup system test prompt"
    assert saved["version"] == original_version + 1

    # Reset
    reset_item = await reset_prompt_endpoint("standup")
    assert "system" in reset_item

  @pytest.mark.asyncio
  async def test_transcript_summary_templates_by_tag(self):
    prompts = await list_prompts(tag="transcript_summary")
    rubrics = await list_rubrics(tag="transcript_summary")

    expected_features = {
      "transcript_summary_standard_meeting",
      "transcript_summary_daily_standup",
      "transcript_summary_project_sync",
      "transcript_summary_retrospective",
      "transcript_summary_client_sales",
      "transcript_summary_psychiatric_session",
    }

    prompt_features = {p["feature"] for p in prompts}
    rubric_features = {r["feature"] for r in rubrics}

    assert expected_features.issubset(prompt_features)
    assert expected_features.issubset(rubric_features)

    # Legacy feature alias fallback
    legacy_prompt = await get_prompt("transcript_summary")
    assert legacy_prompt["feature"] == "transcript_summary_standard_meeting"

    legacy_rubric = await get_rubric("transcript_summary")
    assert legacy_rubric["feature"] == "transcript_summary_standard_meeting"

  def test_migration_script_executes_safely(self):
    from scripts.migrate_transcript_summary_templates import migrate_schema_and_templates
    migrate_schema_and_templates()

    from scripts.migrate_ai_models_catalog_id import migrate_ai_models_catalog
    migrate_ai_models_catalog()
