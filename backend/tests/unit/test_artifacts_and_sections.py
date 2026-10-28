"""Unit tests for resilient artifact parsing, model max_tokens resolution, and section-by-section generation."""

import pytest
from app.ai.artifacts import extract_artifacts, artifacts_to_dict, LLMArtifact
from app.ai.providers.registry import resolve_model_max_tokens
from app.ai.section_generator import (
    is_section_generation_candidate,
    _parse_plan_json,
    _clean_json_response,
    DocumentPlan,
)


class TestTolerantArtifactsParser:
    def test_extract_normal_complete_artifact(self):
        raw = (
            "<chat>Aquí tienes el documento solicitado.</chat>\n"
            '<artifact title="Plan de QA" extension="docx">\n'
            "# 1. Alcance\n"
            "Contenido del plan de pruebas.\n"
            "</artifact>"
        )
        artifacts, clean = extract_artifacts(raw)
        assert len(artifacts) == 1
        assert artifacts[0].title == "Plan de QA"
        assert artifacts[0].extension == "docx"
        assert "# 1. Alcance" in artifacts[0].content
        assert clean == "Aquí tienes el documento solicitado."

    def test_extract_reversed_attributes(self):
        raw = (
            '<artifact extension="xlsx" title="Matriz de Casos">\n'
            "| ID | Caso |\n"
            "</artifact>"
        )
        artifacts, _ = extract_artifacts(raw)
        assert len(artifacts) == 1
        assert artifacts[0].title == "Matriz de Casos"
        assert artifacts[0].extension == "xlsx"

    def test_extract_truncated_unclosed_artifact(self):
        """Simulates LLM stopping mid-generation due to max_tokens."""
        raw = (
            "<chat>Generando el informe...</chat>\n"
            '<artifact title="Informe Tecnico" extension="docx">\n'
            "# 1. Resumen Ejecutivo\n"
            "El sistema presenta alta disponibilidad...\n"
            "# 2. Métricas de Rendimiento\n"
            "- Latencia promedio: 120ms\n"
            "- Tráfico estimado: 5000 req/s"
            # Notice: no </artifact>
        )
        artifacts, clean = extract_artifacts(raw)
        assert len(artifacts) == 1
        assert artifacts[0].title == "Informe Tecnico"
        assert artifacts[0].extension == "docx"
        assert "# 1. Resumen Ejecutivo" in artifacts[0].content
        assert "5000 req/s" in artifacts[0].content
        assert clean == "Generando el informe..."

    def test_extract_truncated_with_trailing_broken_tag(self):
        """Simulates LLM cut off right when starting closing tag."""
        raw = (
            '<artifact title="Especificacion" extension="md">\n'
            "Contenido de la especificacion.\n"
            "</art"
        )
        artifacts, _ = extract_artifacts(raw)
        assert len(artifacts) == 1
        assert artifacts[0].title == "Especificacion"
        assert "Contenido de la especificacion." in artifacts[0].content
        assert "</art" not in artifacts[0].content

    def test_extract_multiple_artifacts_with_last_truncated(self):
        raw = (
            '<artifact title="Doc 1" extension="md">Contenido 1</artifact>\n'
            '<artifact title="Doc 2" extension="docx">Contenido 2 truncado'
        )
        artifacts, _ = extract_artifacts(raw)
        assert len(artifacts) == 2
        assert artifacts[0].title == "Doc 1"
        assert artifacts[1].title == "Doc 2"
        assert artifacts[1].content == "Contenido 2 truncado"

    def test_extract_no_artifacts(self):
        raw = "Solo un mensaje conversacional sin artefactos."
        artifacts, clean = extract_artifacts(raw)
        assert len(artifacts) == 0
        assert clean == raw

    def test_artifacts_to_dict_serialization(self):
        arts = [LLMArtifact(title="T1", extension="docx", content="C1", index=0)]
        dicts = artifacts_to_dict(arts)
        assert len(dicts) == 1
        assert dicts[0] == {"index": 0, "title": "T1", "extension": "docx", "content": "C1"}


class TestModelMaxTokensResolution:
    def test_openai_gpt4o_family_cap(self):
        tokens = resolve_model_max_tokens("openai", "gpt-4o", requested_max=None)
        assert tokens == 16384

    def test_openai_gpt4o_mini_family_cap(self):
        tokens = resolve_model_max_tokens("openai", "gpt-4o-mini", requested_max=None)
        assert tokens == 16384

    def test_claude_sonnet_cap(self):
        tokens = resolve_model_max_tokens("claude", "claude-3-5-sonnet-20241022", requested_max=None)
        assert tokens == 8192

    def test_gemini_cap(self):
        tokens = resolve_model_max_tokens("gemini", "gemini-2.0-flash", requested_max=None)
        assert tokens == 8192

    def test_groq_ceiling_enforced(self):
        """Groq has a conservative rate limit default of 4096."""
        tokens = resolve_model_max_tokens("groq", "llama-3.3-70b-versatile", requested_max=None)
        assert tokens <= 4096

    def test_explicit_requested_max_constrained_by_model_limit(self):
        # Requesting 32000 on a model with 16384 limit will cap to 16384
        tokens = resolve_model_max_tokens("openai", "gpt-4o", requested_max=32000)
        assert tokens == 16384

        # Requesting lower (2000) will be respected
        tokens_lower = resolve_model_max_tokens("openai", "gpt-4o", requested_max=2000)
        assert tokens_lower == 2000


class TestSectionGenerator:
    def test_section_candidate_detection_by_intent(self):
        assert is_section_generation_candidate("generic_plan", "algo") is True
        assert is_section_generation_candidate("generic_report", "algo") is True
        assert is_section_generation_candidate("template_mutation", "algo") is True
        assert is_section_generation_candidate("chat", "¿Cómo estás?") is False

    def test_section_candidate_detection_by_query_keywords(self):
        assert is_section_generation_candidate("chat", "elabora un plan de pruebas para la API") is True
        assert is_section_generation_candidate("chat", "genera un informe detallado de rendimiento") is True
        assert is_section_generation_candidate("chat", "/plan pruebas de carga") is True
        assert is_section_generation_candidate("chat", "explícame qué es una prueba unitaria") is False

    def test_clean_and_parse_plan_json(self):
        json_str = """```json
        {
          "title": "Plan de Implementación",
          "extension": "docx",
          "chat_intro": "He organizado el plan en 3 secciones.",
          "sections": [
            {"title": "1. Objetivos", "instructions": "Definir alcance"},
            {"title": "2. Arquitectura", "instructions": "Diagramar componentes"},
            {"title": "3. Cronograma", "instructions": "Fases y entregables"}
          ]
        }
        ```"""
        plan = _parse_plan_json(json_str)
        assert plan is not None
        assert isinstance(plan, DocumentPlan)
        assert plan.title == "Plan de Implementación"
        assert plan.extension == "docx"
        assert len(plan.sections) == 3
        assert plan.sections[0].title == "1. Objetivos"

    def test_parse_invalid_plan_returns_none(self):
        plan = _parse_plan_json("No es un json")
        assert plan is None

