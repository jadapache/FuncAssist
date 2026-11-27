"""Boundary cases of the transcript text helpers: cleanup, summary parsing and condensing, and segment edits."""

import json
import logging
from types import SimpleNamespace

import pytest

from app.features.transcription import cleanup as cl
from app.features.transcription import segments as sg
from app.features.transcription import summarizer as sm

# --- cleanup --------------------------------------------------------------------------


def test_alternation_skips_blanks_longest_first_and_matches_any_spacing():
  assert cl._alternation(["", "  ", "bb", "a", "ccc", "a "]) == "ccc|bb|a"
  assert cl._alternation(["o sea"]) == r"o\s+sea"


def test_known_hallucinations_match_by_prefix_with_a_length_allowance():
  known = cl._is_known_hallucination
  assert known("") is False and known("Hola, buenos días") is False
  assert known("Subtítulos realizados por la comunidad de Amara.org") is True
  assert known("una frase muy larga que menciona amara.org en medio de la conversación") is True
  phrase = "gracias por ver el video"
  assert known(phrase + " " + "x" * 14) is True
  assert known(phrase + " " + "x" * 15) is False
  assert known("hola gracias por ver") is False


def test_segment_text_prefers_the_raw_text():
  assert cl._segment_text({"text_raw": "a", "text": "b"}) == "a"
  assert cl._segment_text({"text_raw": "", "text": "b"}) == "b"
  assert cl._segment_text({"text": "b"}) == "b"
  assert cl._segment_text({}) == ""


@pytest.mark.parametrize("metrics, expected", [
  ({}, False),
  ({"no_speech_prob": 0.7, "avg_logprob": -1.5}, True),
  ({"no_speech_prob": 0.6, "avg_logprob": -1.5}, False),
  ({"no_speech_prob": 0.7, "avg_logprob": -1.0}, False),
  ({"no_speech_prob": 0.7}, False),
  ({"avg_logprob": -2.0}, False),
  ({"no_speech_prob": 0.5, "avg_logprob": -2.0}, False),
  ({"no_speech_prob": 0.9, "avg_logprob": -0.5}, False),
  ({"compression_ratio": 2.5}, True),
  ({"compression_ratio": 2.4}, False),
  ({"no_speech_prob": 0.7, "avg_logprob": -1.5, "compression_ratio": 1.0}, True),
])
def test_a_segment_is_unreliable_by_whisper_confidence_or_looping(metrics, expected):
  assert cl._is_unreliable(metrics) is expected


def test_a_segment_repeats_the_previous_one_only_for_the_same_speaker_and_words():
  previous = {"text_raw": "Hola mundo", "speaker_id": "S1"}
  assert cl._repeats_previous(previous, {"text_raw": "hola, mundo!", "speaker_id": "S1"}) is True
  assert cl._repeats_previous(previous, {"text_raw": "hola otra vez", "speaker_id": "S1"}) is False
  assert cl._repeats_previous(previous, {"text_raw": "Hola mundo", "speaker_id": "S2"}) is False
  assert cl._repeats_previous({"text_raw": "", "speaker_id": "S1"}, {"text_raw": "", "speaker_id": "S1"}) is False


def _seg(text, end, speaker="S1", **extra):
  return {"text_raw": text, "start": 0.0, "end": end, "speaker_id": speaker, **extra}


def test_a_repeated_segment_extends_the_one_before_it_and_is_counted():
  segments = [_seg("uno", 1), _seg("dos", 2), _seg("tres", 5), _seg("tres", 9)]
  kept, removed = cl.filter_hallucinations(segments)
  assert [s["text_raw"] for s in kept] == ["uno", "dos", "tres"] and removed == 1
  assert [s["end"] for s in kept] == [1, 2, 9]


def test_a_repeat_that_ends_earlier_keeps_the_later_end():
  kept, removed = cl.filter_hallucinations([_seg("uno", 1), _seg("dos", 2), _seg("tres", 8), _seg("tres", 3)])
  assert kept[2]["end"] == 8 and removed == 1


def test_unreliable_and_known_segments_are_dropped_and_counted_separately():
  segments = [
    _seg("hola", 1),
    _seg("ruido", 2, _metrics={"compression_ratio": 3.0}),
    _seg("Gracias por ver el video", 3),
    _seg("seguimos", 4),
  ]
  kept, removed = cl.filter_hallucinations(segments)
  assert [s["text_raw"] for s in kept] == ["hola", "seguimos"] and removed == 2
  assert cl.filter_hallucinations([]) == ([], 0)


def test_the_llm_text_may_cut_at_most_forty_percent_of_the_raw_text():
  assert cl.accept_llm_text("aaaaaa bbb", "aaaaaa") is True
  assert cl.accept_llm_text("aaaaaa bbb", "bbb") is False
  assert cl.accept_llm_text("", "...") is True
  assert cl.accept_llm_text("aaa", "   ") is False
  assert cl.accept_llm_text("aaa bbb", "ccc") is False


def test_llm_replies_are_read_from_the_first_to_the_last_bracket():
  assert cl._parse_llm_items("no brackets at all") == {}
  assert cl._parse_llm_items("] before [") == {}
  assert cl._parse_llm_items('noise [{"id": "a", "text": " Hola "}, {"id": 5, "text": "x"}, {"id": "b"}, "x"] noise') == {"a": "Hola"}
  assert cl._parse_llm_items("[1, 2]") == {}
  assert cl._parse_llm_items("[not json]") == {}
  assert cl._parse_llm_items('{"id": "a"}') == {}


class _Provider:
  def __init__(self, reply="[]", fail=False):
    self.reply, self.fail, self.calls = reply, fail, []

  async def complete(self, messages, max_tokens):
    self.calls.append((messages, max_tokens))
    if self.fail:
      raise RuntimeError("down")
    return SimpleNamespace(text=self.reply)


@pytest.mark.asyncio
async def test_the_llm_receives_only_non_blank_segments_with_accents_intact():
  provider = _Provider(json.dumps([{"id": "s1", "text": "canción"}]))
  stats = cl.CleanupStats()
  segments = [{"id": "s1", "text_raw": "la canción", "text": "x"}, {"id": "s2", "text_raw": "  "}, {"id": "s3", "text_raw": None}]
  await cl.apply_llm(segments, provider, stats)
  messages, max_tokens = provider.calls[0]
  assert max_tokens == 4096 and json.loads(messages[1].content) == [{"id": "s1", "text": "la canción"}]
  assert "canción" in messages[1].content and "\\u" not in messages[1].content
  assert segments[0]["text"] == "Canción" and (stats.llm_segments, stats.llm_rejected) == (1, 0)


@pytest.mark.asyncio
async def test_the_llm_pass_works_in_batches_of_forty_and_survives_a_failing_batch(caplog):
  segments = [{"id": f"s{i}", "text_raw": f"palabra{i}"} for i in range(41)]
  provider = _Provider(fail=True)
  with caplog.at_level(logging.WARNING):
    assert await cl.apply_llm(segments, provider, cl.CleanupStats()) is segments
  assert len(provider.calls) == 2
  assert any("batch at 40" in r.getMessage() for r in caplog.records)
  empty = _Provider()
  await cl.apply_llm([{"id": "a", "text_raw": ""}], empty, cl.CleanupStats())
  assert empty.calls == []


@pytest.mark.asyncio
async def test_rejected_llm_texts_are_counted_and_keep_the_rules_text():
  provider = _Provider(json.dumps([{"id": "a", "text": "inventado"}, {"id": "zzz", "text": "ignorado"}]))
  stats = cl.CleanupStats()
  segments = [{"id": "a", "text_raw": "hola", "text": "Hola."}]
  await cl.apply_llm(segments, provider, stats)
  assert segments[0]["text"] == "Hola." and (stats.llm_segments, stats.llm_rejected) == (0, 1)


def _turn(start, end, text, speaker="S1", **extra):
  return {"start": start, "end": end, "text": text, "speaker_id": speaker, "id": text, **extra}


def test_turns_split_at_the_gap_and_not_before():
  assert len(cl.group_turns([_turn(0, 1, "a"), _turn(3, 4, "b")], gap_s=2)) == 2
  assert len(cl.group_turns([_turn(0, 1, "a"), _turn(2.99, 4, "b")], gap_s=2)) == 1


def test_turns_measure_the_gap_from_the_end_of_the_previous_segment():
  assert len(cl.group_turns([_turn(0, 10, "a"), _turn(10.5, 11, "b")], gap_s=1)) == 1
  assert len(cl.group_turns([_turn(0, 10, "a"), _turn(5, 11, "b")], gap_s=1)) == 1


def test_a_turn_never_exceeds_the_character_limit():
  segments = [_turn(0, 1, "aaaaa"), _turn(1, 2, "bbbbb")]
  assert [t["text"] for t in cl.group_turns(segments, 5, max_chars=11)] == ["aaaaa bbbbb"]
  assert [t["text"] for t in cl.group_turns(segments, 5, max_chars=10)] == ["aaaaa", "bbbbb"]


def test_turns_continue_the_latest_turn_only():
  segments = [_turn(0, 1, "a", "S1"), _turn(1, 2, "b", "S2"), _turn(2, 3, "c", "S2")]
  turns = cl.group_turns(segments, 5)
  assert [(t["speaker_id"], t["text"], t["segment_ids"], t["end"]) for t in turns] == [("S1", "a", ["a"], 1), ("S2", "b c", ["b", "c"], 3)]


def test_turns_use_the_clean_text_unless_raw_is_requested_and_name_their_speaker():
  segment = {"id": "x", "start": 0, "end": 1, "text": "limpio", "text_raw": "CRUDO", "speaker_id": "S1", "speaker": "Ana"}
  assert cl.group_turns([segment], 5)[0]["text"] == "limpio"
  assert cl.group_turns([segment], 5, use_raw=True)[0]["text"] == "CRUDO"
  assert cl.group_turns([segment], 5)[0]["speaker"] == "Ana"
  assert cl.group_turns([{**segment, "speaker": None}], 5)[0]["speaker"] == "S1"
  assert cl.group_turns([{"text": "x"}], 5)[0]["speaker_id"] == "S1"
  assert cl.group_turns([{"text": "  "}, {"text": "", "text_raw": "y"}], 5) == []


# --- summary condensing ---------------------------------------------------------------


def test_head_lines_fill_the_budget_exactly():
  lines = ["aaaa", "bbbb", "cccc"]
  assert sm._head_lines(lines, 10) == ["aaaa", "bbbb"]
  assert sm._head_lines(lines, 9) == ["aaaa"]
  assert sm._head_lines(lines, 100) == lines
  assert sm._head_lines(["abcdefghij", "x"], 4) == ["abcd"]


def test_tail_lines_fill_the_budget_exactly_from_the_end():
  lines = ["aaaa", "bbbb", "cccc"]
  assert sm._tail_lines(lines, 10) == ["bbbb", "cccc"]
  assert sm._tail_lines(lines, 9) == ["cccc"]
  assert sm._tail_lines(lines, 100) == lines
  assert sm._tail_lines(["abcdefghij", "x" * 20], 4) == ["xxxx"]
  assert sm._tail_lines(["x", "abcdefghij"], 4) == ["ghij"]


def test_the_middle_sample_takes_every_nth_line_until_the_budget_is_used():
  pool = [f"{i:02d}" for i in range(25)]
  assert sm._middle_sample(pool, 9) == ["00", "02", "04"]
  assert sm._middle_sample(pool, 8) == ["00", "02"]
  assert sm._middle_sample(pool[:5], 100) == pool[:5]
  assert sm._middle_sample([], 100) == []


def _lines(count):
  return [f"line-{i:02d}" for i in range(count)]


def test_a_transcript_that_fits_is_returned_whole():
  lines = _lines(3)
  joined = "\n".join(lines)
  assert sm.condense_transcript_lines(lines, len(joined)) == joined
  assert sm.condense_transcript_lines([], 10) == ""
  assert sm.condense_transcript_lines(lines, len(joined) - 1) != joined


def test_a_long_transcript_keeps_its_start_and_end_and_samples_the_middle():
  lines = _lines(30)
  result = sm.condense_transcript_lines(lines, 230)
  head, middle, tail = result.split("\n\n")
  assert head.split("\n") == lines[:8]
  assert middle.split("\n") == ["..."] + [lines[i] for i in range(8, 19)]
  assert tail.split("\n") == ["..."] + lines[-8:]


def test_a_single_huge_line_is_cut_instead_of_dropped():
  result = sm.condense_transcript_lines(["x" * 100], 20)
  assert result.startswith("x" * 6) and len(result) <= 20 + 5


def test_transcripts_are_fitted_to_the_budget_before_asking_for_a_summary(monkeypatch):
  calls = []

  def resolve(user_id, tier):
    calls.append(tier)
    raise RuntimeError("no provider")

  monkeypatch.setattr(sm, "resolve_provider", resolve)
  import asyncio

  lines = _lines(4)
  joined = "\n".join(lines)
  assert asyncio.run(sm._fit_transcript(lines, len(joined), "T", None)) == joined and calls == []
  assert asyncio.run(sm._fit_transcript(lines, len(joined) - 1, "T", None)) != joined and calls == ["fast"]


@pytest.mark.parametrize("size, kept", [(30, True), (31, False)])
def test_a_map_reduce_result_is_used_only_when_it_fits(monkeypatch, caplog, size, kept):
  import asyncio

  async def fake(text, max_chars, provider, feature_goal):
    return "m" * size

  monkeypatch.setattr(sm, "resolve_provider", lambda user_id, tier: object())
  monkeypatch.setattr(sm, "map_reduce_condense_context", fake)
  lines = _lines(10)
  result = asyncio.run(sm._fit_transcript(lines, 30, "Mi reunión", "u1"))
  assert (result == "m" * 30) is kept


def test_a_failed_map_reduce_falls_back_to_head_and_tail_and_logs_the_traceback(monkeypatch, caplog):
  import asyncio

  async def boom(*args, **kwargs):
    raise RuntimeError("map failed")

  monkeypatch.setattr(sm, "resolve_provider", lambda user_id, tier: object())
  monkeypatch.setattr(sm, "map_reduce_condense_context", boom)
  with caplog.at_level(logging.WARNING):
    result = asyncio.run(sm._fit_transcript(_lines(30), 100, "T", None))
  assert result == sm.condense_transcript_lines(_lines(30), 100)
  record = next(r for r in caplog.records if "Map-reduce condensation" in r.getMessage())
  assert record.exc_info and "map failed" in record.getMessage()


def test_map_reduce_is_asked_for_the_meeting_goal(monkeypatch):
  import asyncio

  seen = {}

  async def fake(text, max_chars, provider, feature_goal):
    seen.update(max_chars=max_chars, goal=feature_goal)
    return "ok"

  monkeypatch.setattr(sm, "resolve_provider", lambda user_id, tier: object())
  monkeypatch.setattr(sm, "map_reduce_condense_context", fake)
  asyncio.run(sm._fit_transcript(_lines(10), 20, "Mi reunión", None))
  assert seen["max_chars"] == 20 and "resumen de la reunión 'Mi reunión'" in seen["goal"]


# --- summary parsing ------------------------------------------------------------------


def test_summaries_are_read_by_section_with_bullets_in_any_style():
  text = "\n".join([
    "## Resumen", "Se habló del proyecto.", "## Participantes", "- Ana", "* Luis", "1. Marta", "2) Pedro", "-   ",
    "## Temas tratados", "• Alcance", "## Decisiones", "- Usar Postgres", "## Requerimientos", "- Login",
    "## Compromisos", "- Enviar acta", "## Puntos clave", "- Va bien",
  ])
  summary = sm.parse_summary_markdown_or_json(text)
  assert summary.participants == ["Ana", "Luis", "Marta", "Pedro"] and summary.topics == ["Alcance"]
  assert summary.decisions == ["Usar Postgres"] and summary.requirements == ["Login"]
  assert summary.action_items == ["Enviar acta"] and summary.key_insights == ["Va bien"]
  assert summary.summary_text == text.strip()


def test_bullets_before_any_section_are_key_insights():
  assert sm.parse_summary_markdown_or_json("- Primero\n- Segundo").key_insights == ["Primero", "Segundo"]


def test_empty_sections_show_their_defaults_and_the_topics_stand_in_for_insights():
  summary = sm.parse_summary_markdown_or_json("Sólo una frase.")
  assert summary.participants == ["Participante 1", "Participante 2"]
  assert summary.key_insights == ["Reunión de levantamiento y acuerdos iniciales del proyecto."]
  assert summary.topics == ["Requerimientos funcionales"] and summary.decisions == ["Acuerdos de arquitectura y flujo funcional"]
  assert summary.requirements == ["Requerimientos funcionales capturados en la transcripción"]
  assert summary.action_items == ["Generar documento de Inventario (.xlsx) y Levantamiento (.docx)"]
  with_topics = sm.parse_summary_markdown_or_json("## Temas\n- A\n- B\n## Decisiones\n- C")
  assert with_topics.key_insights == ["A", "B", "C"]
  with_insights = sm.parse_summary_markdown_or_json("## Puntos clave\n- a\n- b\n- c\n- d")
  assert with_insights.topics == ["a", "b", "c"]


def test_a_blank_reply_has_no_summary_text_and_a_json_block_wins():
  assert sm.parse_summary_markdown_or_json("   ").summary_text is None
  block = 'Aquí:\n```json\n{"summary": "Resumen", "participants": ["Ana"], "topics": ["T"]}\n```'
  summary = sm.parse_summary_markdown_or_json(block)
  assert (summary.summary_text, summary.participants, summary.topics, summary.decisions) == ("Resumen", ["Ana"], ["T"], [])
  assert sm.parse_summary_markdown_or_json('```json\n{"summary_text": "Otro"}\n```').summary_text == "Otro"
  broken = sm.parse_summary_markdown_or_json("```json\n{not json}\n```\n- punto")
  assert broken.key_insights == ["punto"]


def test_the_header_decides_the_section_in_priority_order():
  assert sm._header_section("puntos clave de la reunión") == "key_insights"
  assert sm._header_section("## resumen") == "summary"
  assert sm._header_section("asistentes") == "participants"
  assert sm._header_section("acuerdos") == "decisions"
  assert sm._header_section("próximos pasos") is None


# --- segments -------------------------------------------------------------------------


def test_speaker_numbers_and_new_ids():
  assert sg._speaker_number("S7") == 7 and sg._speaker_number("x") == 0 and sg._speaker_number("") == 0
  assert sg.new_speaker_id({}) == "S1" and sg.new_speaker_id({"S3": {}, "S1": {}}) == "S4" and sg.new_speaker_id({"x": {}}) == "S1"
  assert sg._next_color({}) == 0 and sg._next_color({"S1": {}}) == 1 and sg._next_color({"S1": {"color_index": 4}}) == 5


def test_generated_segment_ids_start_at_one_and_never_clash():
  segments = [{"id": "seg_0001"}, {}, {"id": "seg_0001"}, {"id": ""}, {"id": 5}]
  sg.ensure_segment_ids(segments)
  assert [s["id"] for s in segments] == ["seg_0001", "seg_0002", "seg_0003", "seg_0004", "seg_0005"]
  fresh = [{}, {}]
  sg.ensure_segment_ids(fresh)
  assert [s["id"] for s in fresh] == ["seg_0001", "seg_0002"]


def test_a_segment_with_an_unknown_speaker_id_is_assigned_by_name():
  record = {"segments": [{"speaker_id": "S9", "speaker": "Ana"}, {"speaker": "Ana"}, {"speaker_id": None}], "speakers": {}}
  sg.normalize_record(record)
  assert [s["speaker_id"] for s in record["segments"]] == ["S1", "S1", "S2"]
  assert record["speakers"] == {"S1": {"name": "Ana", "color_index": 0}, "S2": {"name": "Participante 1", "color_index": 1}}


def test_segment_timings_default_to_zero_and_the_end_to_the_start():
  record = {"segments": [{"start": None, "end": None}, {"start": 3, "end": None}, {"start": "2.5", "end": 7}, {}]}
  sg.normalize_record(record)
  assert [(s["start"], s["end"]) for s in record["segments"]] == [(0.0, 0.0), (3.0, 3.0), (2.5, 7.0), (0.0, 0.0)]


def test_speakers_that_are_not_dicts_are_dropped_and_missing_ones_tolerated():
  record = {"segments": [], "speakers": {"S1": {"name": "Ana"}, "S2": "bad"}}
  assert sg.normalize_record(record)["speakers"] == {"S1": {"name": "Ana"}}
  assert sg.normalize_record({"segments": [], "speakers": None})["speakers"] == {}


@pytest.mark.parametrize("record, source", [
  ({"metadata": {"engine": "Transformers.js (Client-side)"}}, "browser"),
  ({"model_info": "Whisper Web (Client)"}, "browser"),
  ({"metadata": {"engine": ""}, "model_info": "Transformers.js Navegador"}, "browser"),
  ({"metadata": {"engine": "Groq"}, "model_info": "Client"}, "cloud"),
  ({"model_info": "Groq Whisper"}, "cloud"),
  ({}, "cloud"),
])
def test_the_source_of_an_old_record_is_judged_by_its_engine(record, source):
  assert sg.normalize_record({"segments": [], **record})["source"] == source


def test_a_record_that_already_has_a_source_keeps_it():
  assert sg.normalize_record({"segments": [], "source": "browser", "model_info": "Groq"})["source"] == "browser"


def _record(*texts, speakers=None):
  segments = [{"id": f"seg_{i}", "speaker_id": "S1", "start": i, "end": i + 1, "text": t, "text_raw": t} for i, t in enumerate(texts, 1)]
  return {"segments": segments, "speakers": speakers or {"S1": {"name": "Ana", "color_index": 0}}, "diarization": "none"}


def test_a_new_speaker_name_creates_the_speaker_and_marks_manual_diarization():
  record = _record("hola")
  sg.edit_segment(record, "seg_1", new_speaker_name="Luis")
  assert record["diarization"] == "manual" and record["segments"][0]["speaker"] == "Luis"


def test_one_speaker_keeps_the_diarization_as_it_was():
  record = _record("hola", "adiós")
  sg.edit_segment(record, "seg_1", text="Hola!")
  assert record["diarization"] == "none"
  sg.edit_segment(record, "seg_1", new_speaker_name="Ana")
  assert record["diarization"] == "none" and len(record["speakers"]) == 1


def test_legacy_rename_merges_into_an_existing_speaker_of_that_name():
  record = _record("a", "b", speakers={"S1": {"name": "Ana", "color_index": 0}, "S2": {"name": "Luis", "color_index": 1}})
  record["segments"][1]["speaker_id"] = "S2"
  sg.rename_by_name(record, {"Luis": "Ana"})
  assert set(record["speakers"]) == {"S1"}
  assert {s["speaker"] for s in record["segments"]} == {"Ana"}


def test_legacy_rename_to_its_own_name_changes_nothing_and_unknown_names_are_skipped():
  record = _record("a", speakers={"S1": {"name": "Ana", "color_index": 0}, "S2": {"name": "Luis", "color_index": 1}})
  sg.rename_by_name(record, {"Ana": "Ana", "Nadie": "X"})
  assert record["speakers"]["S1"]["name"] == "Ana" and set(record["speakers"]) == {"S1", "S2"}


def test_legacy_rename_updates_the_name_and_the_summary_participants():
  record = _record("a")
  record["summary"] = {"participants": ["Ana", "Luis"]}
  sg.rename_by_name(record, {"Ana": "Marta"})
  assert record["speakers"]["S1"]["name"] == "Marta" and record["segments"][0]["speaker"] == "Marta"
  assert record["summary"]["participants"] == ["Marta", "Luis"]


@pytest.mark.parametrize("at", [0, 10, 11, -1])
def test_a_split_must_fall_inside_the_text(at):
  with pytest.raises(sg.EditError, match="dentro del texto"):
    sg.split_segment(_record("0123456789"), "seg_1", at)


def test_a_split_at_the_first_and_last_inner_positions_is_allowed():
  assert len(sg.split_segment(_record("abc def"), "seg_1", 1)["segments"]) == 2
  assert len(sg.split_segment(_record("abc def"), "seg_1", 6)["segments"]) == 2


def test_a_split_right_after_a_space_cuts_before_it():
  record = sg.split_segment(_record("hola mundo"), "seg_1", 5)
  assert [s["text"] for s in record["segments"]] == ["hola", "mundo"]


def test_a_split_inside_a_word_moves_to_the_nearest_space():
  record = sg.split_segment(_record("uno dos tres cuatro"), "seg_1", 9)
  assert [s["text"] for s in record["segments"]] == ["uno dos", "tres cuatro"]
  record = sg.split_segment(_record("aaaaaaaaaa bb"), "seg_1", 3)
  assert [s["text"] for s in record["segments"]] == ["aaaaaaaaaa", "bb"]


def test_a_split_that_would_leave_an_empty_half_is_refused():
  with pytest.raises(sg.EditError, match="segmento vacío"):
    sg.split_segment(_record("  abc"), "seg_1", 2)
  with pytest.raises(sg.EditError, match="segmento vacío"):
    sg.split_segment(_record("abc  "), "seg_1", 3)


def test_a_split_divides_the_time_in_proportion_to_the_text():
  record = _record("aaaa bbbbbbbb")
  record["segments"][0].update(start=10.0, end=22.0, text_raw="aaaa bbbbbbbb")
  first, second = sg.split_segment(record, "seg_1", 5)["segments"]
  assert (first["end"], second["start"]) == (14.0, 14.0) and first["start"] == 10.0 and second["end"] == 22.0
  assert second["id"] == "seg_1_b" and second["marked"] is False
  assert first["text_raw"] == "aaaa" and second["text_raw"] == "bbbbbbbb"


def test_split_ids_never_clash_and_a_missing_raw_text_is_tolerated():
  record = _record("uno dos")
  record["segments"].append({"id": "seg_1_b", "speaker_id": "S1", "start": 5, "end": 6, "text": "x", "text_raw": "x"})
  del record["segments"][0]["text_raw"]
  first, second = sg.split_segment(record, "seg_1", 3)["segments"][:2]
  assert second["id"] == "seg_1_b2" and first["text_raw"] == "" and second["text_raw"] == ""


def test_split_points_pick_the_closest_space():
  assert sg._split_point("", 0.5) == 0
  assert sg._split_point("abcdef", 0.5) == 3
  assert sg._split_point("ab cdefghij", 0.9) == 2
  assert sg._split_point("abcdefghij kl", 0.1) == 10
  assert sg._split_point("aa bbbbbbbb cc", 0.5) == 11


def test_legacy_rename_never_merges_into_a_speaker_that_was_already_merged_away():
  record = _record("a", "b", "c", speakers={"S1": {"name": "Ana", "color_index": 0}, "S2": {"name": "Luis", "color_index": 1}, "S3": {"name": "Marta", "color_index": 2}})
  record["segments"][1]["speaker_id"] = "S2"
  record["segments"][2]["speaker_id"] = "S3"
  sg.rename_by_name(record, {"Luis": "Ana", "Marta": "Luis"})
  assert set(record["speakers"]) == {"S1", "S3"} and record["speakers"]["S3"]["name"] == "Luis"
  assert [s["speaker"] for s in record["segments"]] == ["Ana", "Ana", "Luis"]
