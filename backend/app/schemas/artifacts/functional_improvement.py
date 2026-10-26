"""Structured Pydantic schema for Functional Improvement artifacts."""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class GherkinScenario(BaseModel):
    """BDD / Gherkin acceptance test scenario."""

    title: str
    given: List[str] = Field(default_factory=list)
    when: List[str] = Field(default_factory=list)
    then: List[str] = Field(default_factory=list)

    def to_gherkin_text(self) -> str:
        lines = [f"Escenario: {self.title}"]
        for g in self.given:
            lines.append(f"  Dado {g}")
        for w in self.when:
            lines.append(f"  Cuando {w}")
        for t in self.then:
            lines.append(f"  Entonces {t}")
        return "\n".join(lines)


class FunctionalImprovementArtifact(BaseModel):
    """Verified functional improvement specification."""

    artifact_id: str
    title: str
    problem_statement: str
    business_objective: str
    actors: List[str] = Field(default_factory=list)
    main_flow: List[str] = Field(default_factory=list)
    alternate_flows: List[str] = Field(default_factory=list)
    acceptance_criteria: List[GherkinScenario] = Field(default_factory=list)
    impacted_systems: List[str] = Field(default_factory=list)
    assumptions_and_risks: List[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        sections = [
            f"# {self.title}",
            f"## Planteamiento del Problema\n{self.problem_statement}",
            f"## Objetivo de Negocio\n{self.business_objective}",
            "## Actores Involucrados\n" + "\n".join(f"- {a}" for a in self.actors),
            "## Flujo Principal\n" + "\n".join(f"{i + 1}. {step}" for i, step in enumerate(self.main_flow)),
        ]
        if self.alternate_flows:
            sections.append("## Flujos Alternos\n" + "\n".join(f"- {f}" for f in self.alternate_flows))
        if self.acceptance_criteria:
            criteria_str = "\n\n".join(c.to_gherkin_text() for c in self.acceptance_criteria)
            sections.append(f"## Criterios de Aceptación (Gherkin)\n```gherkin\n{criteria_str}\n```")
        if self.impacted_systems:
            sections.append("## Sistemas Impactados\n" + "\n".join(f"- {s}" for s in self.impacted_systems))
        return "\n\n".join(sections)
