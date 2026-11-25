"""Quality score of the artifacts a run produced, from the rubric of their structured form."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Union

from app.schemas.artifacts import FunctionalImprovementArtifact, FunctionalInventoryArtifact
from app.services.rubric_evaluator import RubricEvaluator


def _try_parse_structured_artifact(
    content: str, title: str
) -> Optional[Union[FunctionalImprovementArtifact, FunctionalInventoryArtifact]]:
    json_str = _json_object_text(content)
    if not json_str:
        return None

    try:
        data = json.loads(json_str)
        data.setdefault("artifact_id", f"art-{uuid.uuid4().hex[:8]}")
        data.setdefault("title", title or "Documento")
        return _structured_artifact_from(data)
    except Exception:
        return None


def _json_object_text(content: str) -> Optional[str]:
    """The JSON object a model answer is, or the one inside its ```json fence."""
    trimmed = content.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        return trimmed
    match = re.search(r"```json\s*(\{.*?\})\s*```", trimmed, re.DOTALL) if "```json" in trimmed else None
    return match.group(1) if match else None


def _structured_artifact_from(
    data: Dict[str, Any],
) -> Optional[Union[FunctionalImprovementArtifact, FunctionalInventoryArtifact]]:
    if "problem_statement" in data or "acceptance_criteria" in data:
        return FunctionalImprovementArtifact(**data)
    if "modules" in data or "project_name" in data:
        return FunctionalInventoryArtifact(**data)
    return None


def evaluate_artifacts_rubric(art_dicts: List[Dict[str, Any]]) -> tuple[float, str]:
    if not art_dicts:
        return 100.0, "Sin artefactos estructurados"

    scores: List[float] = []
    feedbacks: List[str] = []
    for art in art_dicts:
        score, missing = _rubric_for_artifact(art)
        scores.append(score)
        feedbacks.extend(missing)

    avg_score = round(sum(scores) / len(scores), 1)
    feedback_str = "; ".join(feedbacks) if feedbacks else "Artefactos aprobados por rúbrica."
    return avg_score, feedback_str


def _rubric_for_artifact(art: Dict[str, Any]) -> tuple[float, List[str]]:
    """Rubric score of one artifact and what it is missing; free text only scores by its length."""
    content = art.get("content", "")
    parsed = _try_parse_structured_artifact(content, art.get("title", ""))
    if isinstance(parsed, FunctionalImprovementArtifact):
        res = RubricEvaluator.evaluate_improvement(parsed)
    elif isinstance(parsed, FunctionalInventoryArtifact):
        res = RubricEvaluator.evaluate_inventory(parsed)
    else:
        return (85.0 if len(content.strip()) >= 50 else 50.0), []
    return res.score, ([] if res.approved else res.missing_requirements)

