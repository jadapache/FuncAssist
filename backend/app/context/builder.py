"""Deterministic Context Builder with explicit token budgets and tier prioritization."""

from __future__ import annotations

import re
from typing import List, Optional
from pydantic import BaseModel, Field

from app.context.memory import ConversationMemory, ProjectKnowledge
from app.context.models import ContextChunk


class ContextBudget(BaseModel):
    """Token budget configuration across prompt segments."""

    total_budget: int = 4000
    system_reserve: int = 600
    project_reserve: int = 500
    rag_reserve: int = 1500
    history_reserve: int = 1000
    turn_reserve: int = 400


class BoundedContextResult(BaseModel):
    """Result of deterministic context building with applied truncations."""

    system_prompt: str
    project_context: str
    conversation_context: str
    rag_context: str
    turn_prompt: str
    estimated_total_tokens: int
    truncated_sections: List[str] = Field(default_factory=list)

    def assemble_prompt(self) -> str:
        blocks = [
            self.system_prompt,
            self.project_context,
            self.conversation_context,
            self.rag_context,
            self.turn_prompt,
        ]
        return "\n\n".join(b for b in blocks if b.strip())


class BuildContextParams(BaseModel):
    """Inputs for context assembly."""

    system_prompt: str = ""
    project: Optional[ProjectKnowledge] = None
    conversation: Optional[ConversationMemory] = None
    rag_chunks: List[ContextChunk] = Field(default_factory=list)
    query: str = ""
    budget: ContextBudget = Field(default_factory=ContextBudget)


def estimate_tokens(text: str) -> int:
    """Estimates token count using a standard 4 character-per-token heuristic."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def truncate_to_budget(text: str, max_tokens: int) -> str:
    """Truncates text cleanly to fit within the designated token budget."""
    if not text:
        return ""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_newline = truncated.rfind("\n")
    if last_newline > max_chars * 0.7:
        return truncated[:last_newline] + "\n[... Contenido truncado por límite de contexto ...]"
    return truncated + " [... Truncado ...]"


def deduplicate_chunks(chunks: List[ContextChunk]) -> List[ContextChunk]:
    """Removes duplicate context chunks by normalized ID or content prefix."""
    seen_ids = set()
    unique_chunks = []
    for chunk in chunks:
        norm_key = chunk.id or re.sub(r"\s+", "", chunk.text[:80].lower())
        if norm_key not in seen_ids:
            seen_ids.add(norm_key)
            unique_chunks.append(chunk)
    return unique_chunks


class ContextBuilder:
    """Orchestrates deterministic hierarchical context construction."""

    @classmethod
    def build(cls, params: BuildContextParams) -> BoundedContextResult:
        truncated: List[str] = []
        budget = params.budget

        system_part = cls._format_system(params.system_prompt, budget.system_reserve, truncated)
        project_part = cls._format_project(params.project, budget.project_reserve, truncated)
        conv_part = cls._format_conversation(params.conversation, budget.history_reserve, truncated)
        rag_part = cls._format_rag(params.rag_chunks, budget.rag_reserve, truncated)
        turn_part = cls._format_turn(params.query, budget.turn_reserve, truncated)

        total_tokens = sum(estimate_tokens(p) for p in [system_part, project_part, conv_part, rag_part, turn_part])

        return BoundedContextResult(
            system_prompt=system_part,
            project_context=project_part,
            conversation_context=conv_part,
            rag_context=rag_part,
            turn_prompt=turn_part,
            estimated_total_tokens=total_tokens,
            truncated_sections=truncated,
        )

    @staticmethod
    def _format_system(prompt: str, reserve: int, truncated: List[str]) -> str:
        if estimate_tokens(prompt) > reserve:
            truncated.append("system_prompt")
            return truncate_to_budget(prompt, reserve)
        return prompt

    @staticmethod
    def _format_project(project: Optional[ProjectKnowledge], reserve: int, truncated: List[str]) -> str:
        if not project:
            return ""
        raw_text = project.to_context_block()
        if estimate_tokens(raw_text) > reserve:
            truncated.append("project_context")
            return truncate_to_budget(raw_text, reserve)
        return raw_text

    @staticmethod
    def _format_conversation(conv: Optional[ConversationMemory], reserve: int, truncated: List[str]) -> str:
        if not conv:
            return ""
        raw_text = conv.to_context_block()
        if estimate_tokens(raw_text) > reserve:
            truncated.append("conversation_context")
            return truncate_to_budget(raw_text, reserve)
        return raw_text

    @classmethod
    def _format_rag(cls, chunks: List[ContextChunk], reserve: int, truncated: List[str]) -> str:
        unique_chunks = deduplicate_chunks(chunks)
        if not unique_chunks:
            return ""

        lines: List[str] = ["Contexto RAG Relevante:"]
        accumulated_tokens = estimate_tokens(lines[0])

        for idx, chunk in enumerate(unique_chunks, start=1):
            block = f"[{idx}] {chunk.title} ({chunk.source_label}):\n{chunk.text.strip()}"
            block_tokens = estimate_tokens(block)
            if accumulated_tokens + block_tokens > reserve:
                truncated.append("rag_context")
                remaining_tokens = reserve - accumulated_tokens
                if remaining_tokens > 50:
                    lines.append(truncate_to_budget(block, remaining_tokens))
                break
            lines.append(block)
            accumulated_tokens += block_tokens

        return "\n\n".join(lines)

    @staticmethod
    def _format_turn(query: str, reserve: int, truncated: List[str]) -> str:
        header = f"Instrucción del Usuario:\n{query}"
        if estimate_tokens(header) > reserve:
            truncated.append("turn_prompt")
            return truncate_to_budget(header, reserve)
        return header
