from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.features.transcription.cleanup import (
  CleanupStats,
  RuleCleaner,
  accept_llm_text,
  apply_llm,
  apply_rules,
  filter_hallucinations,
  group_turns,
  strip_pause_markers,
)


@pytest.fixture
def cleaner():
  return RuleCleaner("es")


class TestRuleCleaner:
  @pytest.mark.parametrize(
    "raw, expected",
    [
      ("Eh, bueno, revisemos el el inventario, ¿no?", "Revisemos el inventario."),
      ("Mmm, no sé.", "No sé."),
      ("Esto lo- lo resolvemos mañana.", "Esto lo resolvemos mañana."),
      ("O sea, el sistema valida la cita.", "El sistema valida la cita."),
      ("Bueno, o sea, empezamos.", "Empezamos."),
      ("Funciona, ¿verdad? Sí.", "Funciona. Sí."),
      ("Listo. Bueno, sigamos con el punto dos.", "Listo. Sigamos con el punto dos."),
      ("Em, en el en el módulo de citas.", "En el módulo de citas."),
    ],
  )
  def test_removes_fillers_and_markers(self, cleaner, raw, expected):
    text, removed = cleaner.clean(raw)
    assert text == expected
    assert removed > 0

  @pytest.mark.parametrize(
    "raw",
    [
      "Este documento define el alcance.",
      "La propuesta está bueno, pero falta detalle.",
      "Entonces el sistema valida la orden.",
      "Padres e hijos comparten la cuenta.",
      "Pues sí, lo revisamos el lunes.",
    ],
  )
  def test_keeps_words_with_meaning(self, cleaner, raw):
    text, _ = cleaner.clean(raw)
    assert text == raw

  def test_extra_user_fillers(self):
    text, removed = RuleCleaner("es", ["en plan"]).clean("Lo hacemos en plan rápido.")
    assert text == "Lo hacemos rápido."
    assert removed == 1


class TestPauseMarkers:
  def test_strips_ellipses_and_tags(self):
    text, tags = strip_pause_markers("[música] Hola… [risas] equipo (aplausos)...")
    assert text == "Hola equipo"
    assert tags == ["risas"]

  def test_unknown_brackets_are_kept(self):
    text, tags = strip_pause_markers("El módulo (versión 2) está listo")
    assert text == "El módulo (versión 2) está listo"
    assert tags == []


class TestApplyRules:
  def test_keeps_raw_and_cleans_text(self):
    segments, stats = apply_rules([{"id": "s1", "text_raw": "Eh... bueno, hola"}], mode="rules")
    assert segments[0]["text_raw"] == "Eh... bueno, hola"
    assert segments[0]["text"] == "Hola"
    assert stats.fillers_removed >= 2

  def test_off_mode_only_strips_markup(self):
    segments, stats = apply_rules([{"id": "s1", "text_raw": "Eh, hola [música]"}], mode="off")
    assert segments[0]["text"] == "Eh, hola"
    assert stats.fillers_removed == 0


class TestHallucinations:
  def test_filters_known_phrases_low_confidence_loops_and_repeats(self):
    segments = [
      {"text_raw": "Hola equipo", "speaker_id": "S1", "start": 0.0, "end": 1.0},
      {"text_raw": "Subtítulos realizados por la comunidad de Amara.org", "speaker_id": "S1"},
      {"text_raw": "ruido", "speaker_id": "S1", "_metrics": {"no_speech_prob": 0.9, "avg_logprob": -1.5}},
      {"text_raw": "sí sí sí sí", "speaker_id": "S1", "_metrics": {"compression_ratio": 2.6}},
      {"text_raw": "Hola equipo", "speaker_id": "S1", "start": 1.0, "end": 2.0},
    ]
    kept, removed = filter_hallucinations(segments)
    assert [s["text_raw"] for s in kept] == ["Hola equipo"]
    assert kept[0]["end"] == 2.0
    assert removed == 4

  def test_meeting_sentence_starting_like_a_known_phrase_is_kept(self):
    text = "Gracias por ver esto conmigo y luego decidimos el plan de pruebas"
    kept, removed = filter_hallucinations([{"text_raw": text}])
    assert removed == 0 and kept[0]["text_raw"] == text


class TestTurns:
  def test_pause_below_gap_does_not_split_turn(self):
    segments = [
      {"id": "a", "speaker_id": "S1", "speaker": "Ana", "start": 0.0, "end": 2.0, "text": "Primero."},
      {"id": "b", "speaker_id": "S1", "speaker": "Ana", "start": 8.0, "end": 9.0, "text": "Después."},
      {"id": "c", "speaker_id": "S2", "speaker": "Luis", "start": 9.5, "end": 10.0, "text": "Vale."},
      {"id": "d", "speaker_id": "S2", "speaker": "Luis", "start": 30.0, "end": 31.0, "text": "Otra cosa."},
    ]
    turns = group_turns(segments, gap_s=8.0)
    assert [(t["speaker"], t["text"]) for t in turns] == [
      ("Ana", "Primero. Después."),
      ("Luis", "Vale."),
      ("Luis", "Otra cosa."),
    ]
    assert turns[0]["segment_ids"] == ["a", "b"]


class TestLlmCleanup:
  def test_accept_rules(self):
    raw = "Eh, bueno, revisemos el el inventario"
    assert accept_llm_text(raw, "Revisemos el inventario.")
    assert not accept_llm_text(raw, "Revisemos el inventario completo.")
    assert not accept_llm_text(raw, "Inventario.")

  @pytest.mark.asyncio
  async def test_apply_llm_rejects_invented_words(self):
    class FakeProvider:
      async def complete(self, messages, max_tokens=0):
        payload = [
          {"id": "s1", "text": "Revisemos el inventario."},
          {"id": "s2", "text": "Aprobamos el presupuesto millonario."},
        ]
        return SimpleNamespace(text=json.dumps(payload))

    segments, stats = apply_rules(
      [
        {"id": "s1", "text_raw": "Eh, revisemos el el inventario"},
        {"id": "s2", "text_raw": "Aprobamos el presupuesto"},
      ],
      mode="rules",
    )
    result = await apply_llm(segments, FakeProvider(), stats)
    assert result[0]["text"] == "Revisemos el inventario."
    assert result[1]["text"] == "Aprobamos el presupuesto"
    assert stats.llm_segments == 1 and stats.llm_rejected == 1

  @pytest.mark.asyncio
  async def test_apply_llm_failure_keeps_rules_text(self):
    class FailingProvider:
      async def complete(self, messages, max_tokens=0):
        raise RuntimeError("boom")

    segments, stats = apply_rules([{"id": "s1", "text_raw": "Eh, hola"}], mode="rules")
    result = await apply_llm(segments, FailingProvider(), CleanupStats())
    assert result[0]["text"] == "Hola"
