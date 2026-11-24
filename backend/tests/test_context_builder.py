"""Deterministic context builder, token budgets and hierarchical memory blocks."""

from __future__ import annotations

from app.context.builder import (
  BuildContextParams,
  ContextBudget,
  ContextBuilder,
  deduplicate_chunks,
  estimate_tokens,
  truncate_to_budget,
)
from app.context.memory import ConversationMemory, HierarchicalContext, ProjectKnowledge
from app.context.models import ContextChunk, SourceType


def chunk(cid: str, text: str = "contenido", title: str = "T") -> ContextChunk:
  return ContextChunk(id=cid, source_type=SourceType.KNOWLEDGE, source_label="kb", title=title, text=text)


# ------------------------------------------------------------------ memory


def test_project_knowledge_block():
  assert ProjectKnowledge(project_id="p").to_context_block() == ""
  block = ProjectKnowledge(
    project_id="p", guidelines=["g1", "g2"], glossary={"API": "interfaz"}, architecture_rules=["r1"]
  ).to_context_block()
  assert "Directrices del Proyecto:\n- g1\n- g2" in block
  assert "Glosario de Dominio:\n- API: interfaz" in block
  assert block.endswith("Reglas de Arquitectura:\n- r1")


def test_conversation_memory_block_excludes_recent_messages():
  assert ConversationMemory(conversation_id="c").to_context_block() == ""
  block = ConversationMemory(
    conversation_id="c", goal="G", compacted_summary="S", active_references=["a", "b"],
    recent_messages=[{"role": "user", "content": "no debe aparecer"}],
  ).to_context_block()
  assert "Objetivo de la Conversación: G" in block and "Resumen de Interacciones Previas: S" in block
  assert "Referencias Activas: a, b" in block and "no debe aparecer" not in block


def test_hierarchical_context_defaults():
  ctx = HierarchicalContext()
  assert ctx.project is None and ctx.turn_query == "" and ctx.extra_metadata == {}


# ------------------------------------------------------------------ helpers


def test_estimate_tokens():
  assert estimate_tokens("") == 0
  assert estimate_tokens("abc") == 1
  assert estimate_tokens("x" * 40) == 10


def test_truncate_to_budget_variants():
  assert truncate_to_budget("", 5) == ""
  assert truncate_to_budget("corto", 5) == "corto"
  # no newline in the kept window -> hard cut with the short marker
  assert truncate_to_budget("a" * 100, 5) == "a" * 20 + " [... Truncado ...]"
  # a newline in the last 30% of the window -> cut at the line boundary
  text = "a" * 18 + "\n" + "b" * 50
  out = truncate_to_budget(text, 5)
  assert out == "a" * 18 + "\n[... Contenido truncado por límite de contexto ...]"
  # a newline too early in the window is ignored
  early = "a\n" + "b" * 100
  assert truncate_to_budget(early, 5).endswith(" [... Truncado ...]")


def test_deduplicate_chunks_by_id_and_prefix():
  a, a2 = chunk("1", "uno"), chunk("1", "otro texto")
  assert deduplicate_chunks([a, a2]) == [a]
  no_id1 = chunk("", "Hola   Mundo")
  no_id2 = chunk("", "hola mundo")
  assert deduplicate_chunks([no_id1, no_id2]) == [no_id1]
  assert deduplicate_chunks([]) == []


# ------------------------------------------------------------------ builder


def test_build_small_context_has_no_truncation():
  params = BuildContextParams(
    system_prompt="Eres un asistente.",
    project=ProjectKnowledge(project_id="p", guidelines=["g"]),
    conversation=ConversationMemory(conversation_id="c", goal="meta"),
    rag_chunks=[chunk("1", "texto uno", "Doc A"), chunk("2", "texto dos", "Doc B")],
    query="¿Qué hacer?",
  )
  result = ContextBuilder.build(params)
  assert result.truncated_sections == []
  assert result.rag_context.startswith("Contexto RAG Relevante:")
  assert "[1] Doc A (kb):\ntexto uno" in result.rag_context and "[2] Doc B (kb):" in result.rag_context
  assert result.turn_prompt == "Instrucción del Usuario:\n¿Qué hacer?"
  assert result.estimated_total_tokens > 0
  prompt = result.assemble_prompt()
  assert prompt.index("Eres un asistente.") < prompt.index("Directrices") < prompt.index("Objetivo") < prompt.index("Contexto RAG")


def test_build_empty_context_skips_blank_blocks():
  result = ContextBuilder.build(BuildContextParams(query="hola"))
  assert result.project_context == "" and result.conversation_context == "" and result.rag_context == ""
  assert result.assemble_prompt() == "Instrucción del Usuario:\nhola"


def test_build_truncates_every_oversized_section():
  budget = ContextBudget(system_reserve=10, project_reserve=10, history_reserve=10, rag_reserve=60, turn_reserve=10)
  params = BuildContextParams(
    system_prompt="s" * 500,
    project=ProjectKnowledge(project_id="p", guidelines=["g" * 200]),
    conversation=ConversationMemory(conversation_id="c", goal="o" * 300),
    rag_chunks=[chunk("1", "x" * 150, "A"), chunk("2", "y" * 150, "B")],
    query="q" * 300,
    budget=budget,
  )
  result = ContextBuilder.build(params)
  assert set(result.truncated_sections) == {
    "system_prompt", "project_context", "conversation_context", "rag_context", "turn_prompt",
  }
  assert len(result.system_prompt) < 100 and len(result.turn_prompt) < 100


