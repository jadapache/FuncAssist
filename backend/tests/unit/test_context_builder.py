"""Unit tests for Hierarchical Memory and Context Builder."""

import pytest
from app.context.memory import ProjectKnowledge, ConversationMemory
from app.context.models import ContextChunk, SourceType
from app.context.builder import (
    ContextBudget,
    ContextBuilder,
    BuildContextParams,
    deduplicate_chunks,
    estimate_tokens,
    truncate_to_budget,
)


def test_project_knowledge_formatting() -> None:
    proj = ProjectKnowledge(
        project_id="proj-1",
        name="Portal Pacientes",
        guidelines=["Usar tipografía corporativa", "Validar accesibilidad"],
        glossary={"HC": "Historia Clínica", "ADM": "Admisión Hospitalaria"},
        architecture_rules=["No emitir bloques monolíticos"],
    )
    block = proj.to_context_block()
    assert "Directrices del Proyecto:" in block
    assert "Usar tipografía corporativa" in block
    assert "Glosario de Dominio:" in block
    assert "HC: Historia Clínica" in block
    assert "Reglas de Arquitectura:" in block


def test_conversation_memory_formatting() -> None:
    conv = ConversationMemory(
        conversation_id="conv-1",
        goal="Generar informe de mejoras para admisiones",
        compacted_summary="El usuario solicitó agregar campos de firma digital",
        active_references=["REQ-01", "REQ-02"],
    )
    block = conv.to_context_block()
    assert "Objetivo de la Conversación:" in block
    assert "Generar informe de mejoras para admisiones" in block
    assert "Resumen de Interacciones Previas:" in block
    assert "Referencias Activas: REQ-01, REQ-02" in block


def test_deduplicate_chunks() -> None:
    c1 = ContextChunk(id="c1", source_type=SourceType.KNOWLEDGE, source_label="Doc1", title="Title1", text="Text 1")
    c2 = ContextChunk(id="c1", source_type=SourceType.KNOWLEDGE, source_label="Doc1", title="Title1 Dup", text="Text 1 dup")
    c3 = ContextChunk(id="c2", source_type=SourceType.KNOWLEDGE, source_label="Doc2", title="Title2", text="Text 2")

    deduped = deduplicate_chunks([c1, c2, c3])
    assert len(deduped) == 2
    assert deduped[0].id == "c1"
    assert deduped[1].id == "c2"


def test_truncate_to_budget() -> None:
    text = "A" * 500
    truncated = truncate_to_budget(text, max_tokens=50)  # 50 tokens ~ 200 chars
    assert len(truncated) <= 250
    assert "Truncado" in truncated


def test_context_builder_within_budget() -> None:
    proj = ProjectKnowledge(project_id="p1", guidelines=["G1", "G2"])
    conv = ConversationMemory(conversation_id="c1", goal="Goal")
    chunks = [
        ContextChunk(id="k1", source_type=SourceType.KNOWLEDGE, source_label="L1", title="T1", text="Chunk text 1"),
        ContextChunk(id="k2", source_type=SourceType.KNOWLEDGE, source_label="L2", title="T2", text="Chunk text 2"),
    ]

    params = BuildContextParams(
        system_prompt="Eres un asistente experto.",
        project=proj,
        conversation=conv,
        rag_chunks=chunks,
        query="Explica el flujo de admisión",
    )

    result = ContextBuilder.build(params)
    assert result.estimated_total_tokens > 0
    assert len(result.truncated_sections) == 0

    full_prompt = result.assemble_prompt()
    assert "Eres un asistente experto." in full_prompt
    assert "Directrices del Proyecto:" in full_prompt
    assert "Contexto RAG Relevante:" in full_prompt
    assert "Explica el flujo de admisión" in full_prompt


def test_context_builder_truncates_excess_rag() -> None:
    # Huge RAG chunks exceeding rag_reserve
    huge_text = "Dato relevante de historia clínica. " * 300
    chunks = [
        ContextChunk(id="k1", source_type=SourceType.KNOWLEDGE, source_label="L1", title="T1", text=huge_text),
        ContextChunk(id="k2", source_type=SourceType.KNOWLEDGE, source_label="L2", title="T2", text=huge_text),
    ]

    budget = ContextBudget(rag_reserve=100)  # Strict small reserve
    params = BuildContextParams(
        system_prompt="Sistema",
        rag_chunks=chunks,
        query="Pregunta",
        budget=budget,
    )

    result = ContextBuilder.build(params)
    assert "rag_context" in result.truncated_sections
