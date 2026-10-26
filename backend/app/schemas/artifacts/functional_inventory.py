"""Structured Pydantic schema for Functional Inventory artifacts."""

from __future__ import annotations

from typing import List, Literal
from pydantic import BaseModel, Field


class InventoryComponent(BaseModel):
    """Component entry within a system module."""

    component_id: str
    name: str
    description: str
    dependencies: List[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    coverage_level: float = 0.0


class InventoryModule(BaseModel):
    """Functional module containing grouped components."""

    module_id: str
    name: str
    description: str
    components: List[InventoryComponent] = Field(default_factory=list)


class FunctionalInventoryArtifact(BaseModel):
    """Verified functional inventory specification."""

    artifact_id: str
    title: str
    project_name: str
    version: str = "1.0.0"
    modules: List[InventoryModule] = Field(default_factory=list)
    overall_coverage: float = 0.0
    identified_risks: List[str] = Field(default_factory=list)

    @property
    def total_components(self) -> int:
        return sum(len(m.components) for m in self.modules)

    def to_markdown(self) -> str:
        sections = [
            f"# {self.title} - {self.project_name} (v{self.version})",
            f"**Total de Módulos:** {len(self.modules)} | **Total Componentes:** {self.total_components} | **Cobertura Global:** {self.overall_coverage * 100:.1f}%",
        ]
        for mod in self.modules:
            mod_lines = [f"## Módulo: {mod.name}", mod.description, "| ID | Componente | Riesgo | Cobertura | Dependencias |", "| --- | --- | --- | --- | --- |"]
            for comp in mod.components:
                deps = ", ".join(comp.dependencies) or "Ninguna"
                mod_lines.append(f"| {comp.component_id} | {comp.name} | {comp.risk_level.upper()} | {comp.coverage_level * 100:.0f}% | {deps} |")
            sections.append("\n".join(mod_lines))

        if self.identified_risks:
            sections.append("## Riesgos Identificados\n" + "\n".join(f"- {r}" for r in self.identified_risks))
        return "\n\n".join(sections)
