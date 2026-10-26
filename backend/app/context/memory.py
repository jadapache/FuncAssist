"""Hierarchical memory models for Project, Conversation, and Turn context."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProjectKnowledge(BaseModel):
    """Domain guidelines, glossary, and corporate rules for a project."""

    project_id: str
    name: str = ""
    guidelines: List[str] = Field(default_factory=list)
    glossary: Dict[str, str] = Field(default_factory=dict)
    architecture_rules: List[str] = Field(default_factory=list)

    def to_context_block(self) -> str:
        parts: List[str] = []
        if self.guidelines:
            parts.append("Directrices del Proyecto:\n" + "\n".join(f"- {g}" for g in self.guidelines))
        if self.glossary:
            glossary_lines = [f"- {term}: {definition}" for term, definition in self.glossary.items()]
            parts.append("Glosario de Dominio:\n" + "\n".join(glossary_lines))
        if self.architecture_rules:
            parts.append("Reglas de Arquitectura:\n" + "\n".join(f"- {r}" for r in self.architecture_rules))
        return "\n\n".join(parts)


class ConversationMemory(BaseModel):
    """Compacted goal, active references, and windowed history for a conversation."""

    conversation_id: str
    project_id: Optional[str] = None
    goal: Optional[str] = None
    compacted_summary: Optional[str] = None
    active_references: List[str] = Field(default_factory=list)
    recent_messages: List[Dict[str, str]] = Field(default_factory=list)

    def to_context_block(self) -> str:
        parts: List[str] = []
        if self.goal:
            parts.append(f"Objetivo de la Conversación: {self.goal}")
        if self.compacted_summary:
            parts.append(f"Resumen de Interacciones Previas: {self.compacted_summary}")
        if self.active_references:
            parts.append("Referencias Activas: " + ", ".join(self.active_references))
        return "\n\n".join(parts)


class HierarchicalContext(BaseModel):
    """Aggregated three-tier memory structure."""

    project: Optional[ProjectKnowledge] = None
    conversation: Optional[ConversationMemory] = None
    turn_query: str = ""
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)
