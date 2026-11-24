"""Summarizer tests: formatting, budgets, condensation, summary parsing and the LLM call paths."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.features.transcription import summarizer
from app.features.transcription.summarizer import (
  condense_transcript_lines,
  format_timestamp,
  format_transcript_for_llm,
  format_transcript_lines,
  parse_summary_markdown_or_json,
  resolve_transcript_character_budget,
)


def _seg(start, end, text, speaker="Ana"):
  return {"start": start, "end": end, "speaker": speaker, "speaker_id": speaker, "text": text, "text_raw": text}


# --- formatting ---------------------------------------------------------------------------------


@pytest.mark.parametrize("seconds,expected", [(0, "00:00"), (59.9, "00:59"), (61, "01:01"), (3725, "62:05")])
def test_format_timestamp(seconds, expected):
  assert format_timestamp(seconds) == expected


def test_format_transcript_lines_groups_turns(monkeypatch):
  monkeypatch.setattr(
    summarizer, "group_turns",
    lambda segs, gap: [{"start": 5, "speaker": "Ana", "text": "hola"}, {"start": 70, "speaker": "Luis", "text": "adiós"}],
  )
  assert format_transcript_lines([_seg(0, 1, "x")], gap_s=2.0) == ["[00:05] Ana: hola", "[01:10] Luis: adiós"]
  assert format_transcript_for_llm([_seg(0, 1, "x")]) == "[00:05] Ana: hola\n[01:10] Luis: adiós"


def test_format_transcript_lines_uses_configured_gap_by_default(monkeypatch):
  seen = {}
  monkeypatch.setattr(summarizer.config, "turn_gap_s", lambda: 7.5)

  def fake_group(segs, gap):
    seen["gap"] = gap
    return []

  monkeypatch.setattr(summarizer, "group_turns", fake_group)
  format_transcript_lines([])
  assert seen["gap"] == 7.5


@pytest.mark.parametrize(
  "provider,budget",
  [("gemini", 1_000_000), ("Google", 1_000_000), ("openai", 300_000), ("claude", 300_000),
   ("groq", 20_000), ("ollama", 15_000), ("", 15_000), (None, 15_000)],
)
def test_character_budget_per_provider(provider, budget):
  assert resolve_transcript_character_budget(provider) == budget


# --- head/tail condensation ---------------------------------------------------------------------


def test_condense_empty_and_fits():
  assert condense_transcript_lines([], 100) == ""
  assert condense_transcript_lines(["a", "b"], 100) == "a\nb"


def test_condense_keeps_head_tail_and_samples_middle():
  lines = [f"line-{i:03d} " + "x" * 20 for i in range(200)]
  out = condense_transcript_lines(lines, 1500)
  assert out.startswith("line-000")
  assert out.rstrip().endswith(lines[-1])
  assert out.count("...\n") == 2  # middle + tail markers


def test_condense_truncates_single_huge_line_head_and_tail():
  lines = ["A" * 1000, "B" * 1000]
  out = condense_transcript_lines(lines, 100)
  assert out.startswith("A" * 30)
  assert out.endswith("B" * 30)


# --- summary parsing ----------------------------------------------------------------------------


def test_parse_json_codeblock():
  payload = {
    "summary": "Resumen", "key_insights": ["k"], "participants": ["Ana"], "topics": ["t"],
    "decisions": ["d"], "requirements": ["r"], "action_items": ["a"],
  }
  result = parse_summary_markdown_or_json("texto\n```json\n" + json.dumps(payload) + "\n```")
  assert result.summary_text == "Resumen"
  assert result.participants == ["Ana"]
  assert result.action_items == ["a"]


def test_parse_json_accepts_summary_text_key():
  result = parse_summary_markdown_or_json('```\n{"summary_text": "S"}\n```')
  assert result.summary_text == "S"
  assert result.key_insights == []


def test_parse_invalid_json_falls_back_to_markdown():
  result = parse_summary_markdown_or_json("```json\n{not json}\n```\nalgo")
  assert result.summary_text is not None
  assert result.participants  # defaults filled


def test_parse_markdown_sections():
  text = "\n".join([
    "Resumen de la reunión.",
    "## Participantes", "- Ana", "- Luis",
    "## Temas tratados", "- Arquitectura",
    "## Decisiones", "- Usar Postgres",
    "## Requerimientos", "* Exportar a Excel",
    "## Compromisos", "• Enviar acta",
    "## Puntos clave", "- Hay riesgo de plazo",
  ])
  r = parse_summary_markdown_or_json(text)
  assert r.participants == ["Ana", "Luis"]
  assert r.topics == ["Arquitectura"]
  assert r.decisions == ["Usar Postgres"]
  assert r.requirements == ["Exportar a Excel"]
  assert r.action_items == ["Enviar acta"]
  assert r.key_insights == ["Hay riesgo de plazo"]
  assert r.summary_text.startswith("Resumen de la reunión.")


def test_parse_bullets_before_any_header_become_key_insights():
  r = parse_summary_markdown_or_json("- primer punto\n- segundo punto")
  assert r.key_insights == ["primer punto", "segundo punto"]


def test_parse_without_structure_uses_defaults():
  r = parse_summary_markdown_or_json("Solo un párrafo.")
  assert r.summary_text == "Solo un párrafo."
  assert r.participants == ["Participante 1", "Participante 2"]
  assert r.key_insights and r.topics and r.decisions and r.requirements and r.action_items


def test_parse_empty_text():
  assert parse_summary_markdown_or_json("").summary_text is None


def test_parse_topics_fill_key_insights_when_missing():
  r = parse_summary_markdown_or_json("## Temas\n- Uno\n## Decisiones\n- Dos")
  assert r.key_insights == ["Uno", "Dos"]


# --- _fit_transcript ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fit_transcript_returns_whole_text_when_it_fits():
  assert await summarizer._fit_transcript(["a", "b"], 100, "T", None) == "a\nb"


@pytest.mark.asyncio
async def test_fit_transcript_uses_map_reduce(monkeypatch):
  monkeypatch.setattr(summarizer, "resolve_provider", lambda **kw: SimpleNamespace(tier=kw.get("tier")))
  captured = {}

  async def fake_mr(text, max_chars, provider, feature_goal):
    captured.update(provider=provider, goal=feature_goal)
    return "condensado"

  monkeypatch.setattr(summarizer, "map_reduce_condense_context", fake_mr)
  out = await summarizer._fit_transcript(["x" * 50, "y" * 50], 60, "Kickoff", "u1")
  assert out == "condensado"
  assert captured["provider"].tier == "fast"
  assert "Kickoff" in captured["goal"]


@pytest.mark.parametrize("failure", ["raises", "too_long", "empty"])
@pytest.mark.asyncio
async def test_fit_transcript_falls_back_to_head_tail(monkeypatch, failure):
  monkeypatch.setattr(summarizer, "resolve_provider", lambda **kw: object())

  async def fake_mr(text, max_chars, provider, feature_goal):
    if failure == "raises":
      raise RuntimeError("boom")
    return "z" * (max_chars + 1) if failure == "too_long" else ""

  monkeypatch.setattr(summarizer, "map_reduce_condense_context", fake_mr)
  lines = [f"linea {i} " + "q" * 30 for i in range(40)]
  out = await summarizer._fit_transcript(lines, 400, "T", None)
  assert out.startswith("linea 0")
  assert "z" * 10 not in out


# --- summarize_transcript -----------------------------------------------------------------------


class FakeProvider:
  id = "openai"

  def __init__(self, text="Resumen\n## Participantes\n- Ana\n- Participante 2", error=None):
    self.text, self.error, self.messages, self.max_tokens = text, error, None, None

  async def complete(self, messages, max_tokens=None):
    self.messages, self.max_tokens = messages, max_tokens
    if self.error:
      raise self.error
    return SimpleNamespace(text=self.text)


@pytest.fixture
def llm(monkeypatch):
  provider = FakeProvider()
  monkeypatch.setattr(summarizer, "resolve_provider", lambda **kw: provider)

  async def get_prompt(feature):
    return {"system": "SYS", "user_template": "T={title}|{transcript}|{rubric}", "title": f"Plantilla {feature}"}

  async def get_rubric(feature):
    return {"r": 1}

  monkeypatch.setattr(summarizer, "get_prompt", get_prompt)
  monkeypatch.setattr(summarizer, "get_rubric", get_rubric)
  monkeypatch.setattr(summarizer, "rubric_to_text", lambda cfg: "RUBRICA")
  monkeypatch.setattr(summarizer, "format_transcript_lines", lambda segs: ["[00:00] Ana: hola"])
  return provider


@pytest.mark.asyncio
async def test_summarize_empty_segments_skips_llm():
  res = await summarizer.summarize_transcript([], feature="transcript_summary")
  assert res.summary_text == "No se detectaron diálogos en la grabación."
  assert res.template_id == "transcript_summary_standard_meeting"
  assert res.participants == []


@pytest.mark.asyncio
async def test_summarize_builds_prompt_and_filters_generic_participants(llm):
  res = await summarizer.summarize_transcript([_seg(0, 1, "hola")], title="Kickoff", feature="custom_feature")
  assert [m.role for m in llm.messages] == ["system", "user"]
  assert llm.messages[0].content == "SYS"
  assert llm.messages[1].content == "T=Kickoff|[00:00] Ana: hola|RUBRICA"
  assert res.template_id == "custom_feature"
  assert res.template_name == "Plantilla custom_feature"
  assert res.participants == ["Ana"]  # "Participante 2" is dropped


@pytest.mark.asyncio
async def test_summarize_default_feature_when_blank(llm):
  res = await summarizer.summarize_transcript([_seg(0, 1, "hola")], feature="")
  assert res.template_id == "transcript_summary_standard_meeting"


@pytest.mark.asyncio
async def test_summarize_tolerates_rubric_failure(llm, monkeypatch):
  async def broken(feature):
    raise RuntimeError("no rubric")

  monkeypatch.setattr(summarizer, "get_rubric", broken)
  await summarizer.summarize_transcript([_seg(0, 1, "hola")])
  assert llm.messages[1].content.endswith("|")


@pytest.mark.asyncio
async def test_summarize_provider_resolution_failure_is_400(monkeypatch):
  def boom(**kw):
    raise RuntimeError("sin clave")

  monkeypatch.setattr(summarizer, "resolve_provider", boom)
  with pytest.raises(HTTPException) as exc:
    await summarizer.summarize_transcript([_seg(0, 1, "hola")])
  assert exc.value.status_code == 400
  assert "sin clave" in exc.value.detail


@pytest.mark.parametrize("error,status", [(ValueError("mala entrada"), 400), (RuntimeError("caído"), 500)])
@pytest.mark.asyncio
async def test_summarize_llm_failure_status(llm, error, status):
  llm.error = error
  with pytest.raises(HTTPException) as exc:
    await summarizer.summarize_transcript([_seg(0, 1, "hola")])
  assert exc.value.status_code == status
  assert "Error al generar resumen" in exc.value.detail


@pytest.mark.xfail(strict=True, reason="Bug: numbered bullets ('1. x') do not match the bullet regex in summarizer.py")
def test_parse_numbered_bullets():
  r = parse_summary_markdown_or_json("## Decisiones\n1. Usar Postgres\n2. Migrar")
  assert r.decisions == ["Usar Postgres", "Migrar"]
