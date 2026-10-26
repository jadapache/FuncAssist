"""Deterministic Rubric Evaluator enforcing quality gates before artifact rendering."""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field

from app.schemas.artifacts.functional_improvement import FunctionalImprovementArtifact
from app.schemas.artifacts.functional_inventory import FunctionalInventoryArtifact


class CriterionEvaluation(BaseModel):
    """Evaluation result for an individual rubric criterion."""

    criterion_name: str
    max_weight: float
    awarded_weight: float
    passed: bool
    feedback: str


class RubricEvaluationResult(BaseModel):
    """Overall outcome of a rubric assessment."""

    artifact_id: str
    score: float
    threshold: float
    approved: bool
    evaluations: List[CriterionEvaluation] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)


class RubricEvaluator:
    """Evaluates generated artifacts against deterministic business criteria."""

    @classmethod
    def evaluate_improvement(
        cls, artifact: FunctionalImprovementArtifact, threshold: float = 75.0
    ) -> RubricEvaluationResult:
        evals = [
            cls._check_problem_objective(artifact),
            cls._check_actors(artifact),
            cls._check_main_flow(artifact),
            cls._check_alternate_flows(artifact),
            cls._check_acceptance_criteria(artifact),
        ]
        return cls._build_result(artifact.artifact_id, evals, threshold)

    @classmethod
    def evaluate_inventory(
        cls, artifact: FunctionalInventoryArtifact, threshold: float = 75.0
    ) -> RubricEvaluationResult:
        evals = [
            cls._check_modules_components(artifact),
            cls._check_component_details(artifact),
            cls._check_risks(artifact),
            cls._check_coverage(artifact),
        ]
        return cls._build_result(artifact.artifact_id, evals, threshold)

    @staticmethod
    def _build_result(
        artifact_id: str, evaluations: List[CriterionEvaluation], threshold: float
    ) -> RubricEvaluationResult:
        score = sum(e.awarded_weight for e in evaluations)
        missing = [e.feedback for e in evaluations if not e.passed]
        return RubricEvaluationResult(
            artifact_id=artifact_id,
            score=round(score, 1),
            threshold=threshold,
            approved=score >= threshold,
            evaluations=evaluations,
            missing_requirements=missing,
        )

    @staticmethod
    def _check_problem_objective(art: FunctionalImprovementArtifact) -> CriterionEvaluation:
        has_prob = len(art.problem_statement.strip()) >= 20
        has_obj = len(art.business_objective.strip()) >= 15
        passed = has_prob and has_obj
        return CriterionEvaluation(
            criterion_name="Claridad de Problema y Objetivo",
            max_weight=20.0,
            awarded_weight=20.0 if passed else 0.0,
            passed=passed,
            feedback="El problema y objetivo de negocio deben describirse con detalle suficiente." if not passed else "Cumplido",
        )

    @staticmethod
    def _check_actors(art: FunctionalImprovementArtifact) -> CriterionEvaluation:
        passed = len(art.actors) >= 1
        return CriterionEvaluation(
            criterion_name="Actores Identificados",
            max_weight=10.0,
            awarded_weight=10.0 if passed else 0.0,
            passed=passed,
            feedback="Debe definirse al menos un actor o rol funcional involucrado." if not passed else "Cumplido",
        )

    @staticmethod
    def _check_main_flow(art: FunctionalImprovementArtifact) -> CriterionEvaluation:
        passed = len(art.main_flow) >= 3
        return CriterionEvaluation(
            criterion_name="Completitud del Flujo Principal",
            max_weight=25.0,
            awarded_weight=25.0 if passed else 0.0,
            passed=passed,
            feedback="El flujo principal debe contener al menos 3 pasos secuenciales claros." if not passed else "Cumplido",
        )

    @staticmethod
    def _check_alternate_flows(art: FunctionalImprovementArtifact) -> CriterionEvaluation:
        passed = len(art.alternate_flows) >= 1
        return CriterionEvaluation(
            criterion_name="Manejo de Flujos Alternos y Casos Borde",
            max_weight=15.0,
            awarded_weight=15.0 if passed else 0.0,
            passed=passed,
            feedback="Debe especificarse al menos un flujo alterno o excepción." if not passed else "Cumplido",
        )

    @staticmethod
    def _check_acceptance_criteria(art: FunctionalImprovementArtifact) -> CriterionEvaluation:
        has_criteria = len(art.acceptance_criteria) >= 1
        valid_bdd = all(
            len(c.given) >= 1 and len(c.when) >= 1 and len(c.then) >= 1
            for c in art.acceptance_criteria
        )
        passed = has_criteria and valid_bdd
        return CriterionEvaluation(
            criterion_name="Criterios de Aceptación Gherkin",
            max_weight=30.0,
            awarded_weight=30.0 if passed else 0.0,
            passed=passed,
            feedback="Debe incluir al menos un escenario Gherkin con cláusulas Dado/Cuando/Entonces completas." if not passed else "Cumplido",
        )

    @staticmethod
    def _check_modules_components(art: FunctionalInventoryArtifact) -> CriterionEvaluation:
        passed = len(art.modules) >= 1 and art.total_components >= 1
        return CriterionEvaluation(
            criterion_name="Estructura de Módulos y Componentes",
            max_weight=40.0,
            awarded_weight=40.0 if passed else 0.0,
            passed=passed,
            feedback="Debe registrar al menos un módulo con componentes clasificados." if not passed else "Cumplido",
        )

    @staticmethod
    def _check_component_details(art: FunctionalInventoryArtifact) -> CriterionEvaluation:
        passed = all(
            len(c.name.strip()) > 0 and len(c.description.strip()) > 0
            for m in art.modules for c in m.components
        ) if art.total_components > 0 else False
        return CriterionEvaluation(
            criterion_name="Detalle de Componentes y Dependencias",
            max_weight=25.0,
            awarded_weight=25.0 if passed else 0.0,
            passed=passed,
            feedback="Todos los componentes deben contar con nombre y descripción válidos." if not passed else "Cumplido",
        )

    @staticmethod
    def _check_risks(art: FunctionalInventoryArtifact) -> CriterionEvaluation:
        passed = len(art.identified_risks) >= 1
        return CriterionEvaluation(
            criterion_name="Matriz de Riesgos Identificados",
            max_weight=20.0,
            awarded_weight=20.0 if passed else 0.0,
            passed=passed,
            feedback="Debe enumerarse al menos un riesgo operativo o técnico detectado." if not passed else "Cumplido",
        )

    @staticmethod
    def _check_coverage(art: FunctionalInventoryArtifact) -> CriterionEvaluation:
        passed = 0.0 <= art.overall_coverage <= 1.0
        return CriterionEvaluation(
            criterion_name="Métrica de Cobertura Global",
            max_weight=15.0,
            awarded_weight=15.0 if passed else 0.0,
            passed=passed,
            feedback="El porcentaje de cobertura debe ser un valor válido entre 0.0 y 1.0." if not passed else "Cumplido",
        )
