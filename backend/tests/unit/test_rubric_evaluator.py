"""Unit tests for Artifact Schemas and Rubric Evaluator."""

import pytest
from app.schemas.artifacts import (
    FunctionalImprovementArtifact,
    GherkinScenario,
    FunctionalInventoryArtifact,
    InventoryComponent,
    InventoryModule,
)
from app.services.rubric_evaluator import RubricEvaluator


def test_valid_functional_improvement_passes_rubric() -> None:
    scenario = GherkinScenario(
        title="Creación exitosa de solicitud",
        given=["que el usuario es líder funcional"],
        when=["completa el formulario de mejora"],
        then=["el sistema emite el documento con ID único"],
    )
    art = FunctionalImprovementArtifact(
        artifact_id="art-imp-1",
        title="Automatización de Reportes",
        problem_statement="La generación manual de reportes toma más de 5 horas a la semana.",
        business_objective="Reducir el tiempo de elaboración a menos de 10 minutos mediante IA.",
        actors=["Líder Funcional", "Auditor de Calidad"],
        main_flow=["Ingresar al módulo", "Adjuntar evidencias", "Hacer clic en Generar"],
        alternate_flows=["Si falta adjunto, notificar al usuario"],
        acceptance_criteria=[scenario],
        impacted_systems=["ERP", "FuncAssist"],
    )

    result = RubricEvaluator.evaluate_improvement(art, threshold=75.0)
    assert result.approved is True
    assert result.score == 100.0
    assert len(result.missing_requirements) == 0

    md = art.to_markdown()
    assert "# Automatización de Reportes" in md
    assert "Escenario: Creación exitosa de solicitud" in md


def test_deficient_functional_improvement_fails_rubric() -> None:
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
    assert len(result.missing_requirements) > 0


def test_valid_functional_inventory_passes_rubric() -> None:
    comp = InventoryComponent(
        component_id="C-01",
        name="Motor de Validación",
        description="Evalúa reglas de negocio hospitalarias",
        dependencies=["PostgreSQL", "LiteLLM"],
        risk_level="high",
        coverage_level=0.85,
    )
    mod = InventoryModule(
        module_id="M-01",
        name="Módulo Clínico",
        description="Gestión integral de admisiones",
        components=[comp],
    )
    inv = FunctionalInventoryArtifact(
        artifact_id="inv-1",
        title="Inventario de Aplicaciones",
        project_name="FuncAssist",
        version="2.0.0",
        modules=[mod],
        overall_coverage=0.85,
        identified_risks=["Falta de documentación en módulos legados"],
    )

    result = RubricEvaluator.evaluate_inventory(inv, threshold=75.0)
    assert result.approved is True
    assert result.score == 100.0

    md = inv.to_markdown()
    assert "Módulo Clínico" in md
    assert "Motor de Validación" in md
