"""Unit tests for transcript text handling: segment edits (segments.py) and cleanup.py."""

from __future__ import annotations

import copy

import pytest

from app.features.transcription import cleanup, segments
from app.features.transcription.segments import EditError


def _record():
  return segments.normalize_record({
    "segments": [
      {"id": "a", "start": 0, "end": 4, "text": "hola a todos", "speaker": "Ana"},
      {"id": "b", "start": 4, "end": 8, "text": "buenos días", "speaker": "Luis"},
      {"id": "c", "start": 8, "end": 10, "text": "seguimos", "speaker": "Ana"},
    ],
    "summary": {"participants": ["Ana", "Luis"]},
  })


class TestNormalize:
  def test_legacy_record_gets_speakers_and_defaults(self):
    rec = _record()
    assert rec["speakers"] == {"S1": {"name": "Ana", "color_index": 0}, "S2": {"name": "Luis", "color_index": 1}}
    assert [s["speaker_id"] for s in rec["segments"]] == ["S1", "S2", "S1"]
    seg = rec["segments"][0]
    assert seg["text_raw"] == "hola a todos" and seg["tags"] == [] and seg["marked"] is False
    assert rec["diarization"] == "legacy"
    assert rec["summary_status"] == "done"
    assert rec["source"] == "cloud"
    assert rec["cleanup"] is None and rec["silence_trimmed_s"] == 0.0


  def test_speaker_without_name_uses_default(self):
    rec = segments.normalize_record({"segments": [{"speaker_id": "S3", "text": "x"}], "speakers": {"S3": {"name": ""}}})
    assert rec["segments"][0]["speaker"] == "Participante 3"

  def test_ensure_segment_ids_deduplicates(self):
    segs = [{"id": "seg_0001"}, {"id": "seg_0001"}, {"id": ""}]
    segments.ensure_segment_ids(segs)
    assert [s["id"] for s in segs] == ["seg_0001", "seg_0002", "seg_0003"]

  def test_helpers(self):
    assert segments.new_speaker_id({}) == "S1"
    assert segments.new_speaker_id({"S2": {}, "X": {}}) == "S3"
    assert segments.full_text([{"text": " a "}, {"text": ""}, {}, {"text": "b"}]) == "a b"


class TestSpeakerEdits:
  def test_rename_and_merge(self):
    rec = _record()
    segments.apply_speaker_edits(rec, rename={"S1": "  Ana María  "}, merge=[{"from": "S2", "into": "S1"}])
    assert list(rec["speakers"]) == ["S1"]
    assert {s["speaker"] for s in rec["segments"]} == {"Ana María"}
    assert rec["summary"]["participants"] == ["Ana María"]
    assert rec["text"] == "hola a todos buenos días seguimos"

  def test_merge_same_is_noop_and_unknown_raises(self):
    rec = _record()
    assert segments.merge_speakers(rec, "S1", "S1") == {}
    with pytest.raises(EditError):
      segments.merge_speakers(rec, "S9", "S1")


  def test_rename_by_name_renames_and_merges(self):
    rec = _record()
    segments.rename_by_name(rec, {"Ana": "Ana B", "Nadie": "X"})
    assert rec["speakers"]["S1"]["name"] == "Ana B"
    assert rec["summary"]["participants"] == ["Ana B", "Luis"]
    segments.rename_by_name(rec, {"Luis": "Ana B"})
    assert list(rec["speakers"]) == ["S1"]
    assert all(s["speaker_id"] == "S1" for s in rec["segments"])


class TestSegmentEdits:
  def test_edit_text_mark_and_existing_speaker(self):
    rec = _record()
    segments.edit_segment(rec, "a", speaker_id="S2", text="  nuevo  ", marked=True)
    seg = rec["segments"][0]
    assert (seg["speaker_id"], seg["text"], seg["marked"], seg["speaker"]) == ("S2", "nuevo", True, "Luis")


  def test_new_speaker_name_creates_or_reuses(self):
    rec = segments.normalize_record({"segments": [{"id": "a", "text": "uno"}, {"id": "b", "text": "dos"}]})
    assert rec["diarization"] == "none"
    segments.edit_segment(rec, "b", new_speaker_name="Carla")
    assert rec["segments"][1]["speaker_id"] == "S2"
    assert rec["speakers"]["S2"] == {"name": "Carla", "color_index": 1}
    assert rec["diarization"] == "manual"
    # Reusing an existing name; S2 becomes unused and is dropped.
    segments.edit_segment(rec, "b", new_speaker_name="Participante 1")
    assert rec["segments"][1]["speaker_id"] == "S1"
    assert list(rec["speakers"]) == ["S1"]

  def test_last_speaker_is_never_dropped(self):
    rec = {"segments": [{"id": "a", "speaker_id": "S1"}], "speakers": {"S1": {"name": "A"}, "S2": {"name": "B"}}}
    segments._drop_unused_speakers(rec)
    assert list(rec["speakers"]) == ["S1"]
    rec = {"segments": [], "speakers": {"S1": {"name": "A"}}}
    segments._drop_unused_speakers(rec)
    assert list(rec["speakers"]) == ["S1"]

  def test_split_at_space_keeps_timeline_proportional(self):
    rec = segments.normalize_record({"segments": [{"id": "a", "start": 0, "end": 10, "text": "uno dos tres cuatro", "text_raw": "eh uno dos tres cuatro"}]})
    segments.split_segment(rec, "a", 8)  # just after "uno dos "
    first, second = rec["segments"]
    assert first["text"] == "uno dos" and second["text"] == "tres cuatro"
    assert second["id"] == "a_b" and second["marked"] is False
    ratio = len("uno dos") / len("uno dostres cuatro")
    assert first["end"] == second["start"] == round(10 * ratio, 3)
    assert first["text_raw"] + " " + second["text_raw"] == "eh uno dos tres cuatro"

  def test_split_mid_word_snaps_to_nearest_space_and_unique_id(self):
    rec = segments.normalize_record({"segments": [
      {"id": "a", "start": 0, "end": 4, "text": "abcdef ghij"}, {"id": "a_b", "start": 4, "end": 5, "text": "x"},
    ]})
    segments.split_segment(rec, "a", 3)
    assert [s["text"] for s in rec["segments"][:2]] == ["abcdef", "ghij"]
    assert rec["segments"][1]["id"] == "a_b2"

  def test_split_errors(self):
    rec = segments.normalize_record({"segments": [{"id": "a", "start": 0, "end": 1, "text": "palabra"}]})
    with pytest.raises(EditError):
      segments.split_segment(rec, "a", 0)
    with pytest.raises(EditError):
      segments.split_segment(rec, "a", 7)
    # No spaces: the split point is the requested position, both halves non-empty.
    segments.split_segment(rec, "a", 3)
    assert [s["text"] for s in rec["segments"]] == ["pal", "abra"]




# --- cleanup -----------------------------------------------------------------------------------


class TestCleanupRules:
  def test_strip_pause_markers(self):
    text, tags = cleanup.strip_pause_markers("hola... [risas] (música) [Ana] … bien")
    assert text == "Hola [Ana] bien"
    assert tags == ["risas"]
    _, tags = cleanup.strip_pause_markers("(inaudible) algo")
    assert tags == ["inaudible"]
    assert cleanup.strip_pause_markers(None) == ("", [])

  def test_rule_cleaner_spanish(self):
    cleaner = cleanup.RuleCleaner("es-MX")
    text, removed = cleaner.clean("Bueno, o sea, eh revisemos el el inventario, ¿no? Mmm vale.")
    assert text == "Revisemos el inventario. Vale."
    assert removed >= 5

  def test_rule_cleaner_english_extra_and_false_start(self):
    cleaner = cleanup.RuleCleaner("en", extra_fillers=["basically"])
    text, removed = cleaner.clean("well, we basically go- going there, right?")
    assert text == "We going there."
    assert removed == 4

  def test_unknown_language_defaults_to_spanish(self):
    text, _ = cleanup.RuleCleaner("fr").clean("Pues, vamos")
    assert text == "Vamos"
    assert cleanup.RuleCleaner(None).clean(None) == ("", 0)


  def test_apply_rules_modes(self):
    segs = [{"id": "1", "text": "eh hola [risas]", "tags": ["x"]}, {"id": "2", "text_raw": "eh bien"}]
    out, stats = cleanup.apply_rules(segs, mode="rules")
    assert out[0]["text_raw"] == "eh hola [risas]" and out[0]["text"] == "Hola"
    assert out[0]["tags"] == ["risas", "x"] and out[1]["tags"] == []
    assert stats.fillers_removed == 2
    out, stats = cleanup.apply_rules(segs, mode="off")
    assert out[1]["text"] == "Eh bien" and stats.fillers_removed == 0
    assert stats.to_dict("off") == {"mode": "off", "fillers_removed": 0, "hallucinations_removed": 0, "llm_segments": 0, "llm_rejected": 0}


class TestCleanupLLM:
  def test_accept_llm_text(self):
    assert cleanup.accept_llm_text("eh pues vamos a la reunión", "Vamos a la reunión.")
    assert not cleanup.accept_llm_text("vamos", "  ")
    assert not cleanup.accept_llm_text("vamos a la reunión", "vamos al cine")
    assert not cleanup.accept_llm_text("uno dos tres cuatro cinco seis", "uno")
    assert cleanup.accept_llm_text("...", "...")  # raw empty after normalization -> accepted only if words subset

  def test_parse_llm_items(self):
    assert cleanup._parse_llm_items("no json") == {}
    assert cleanup._parse_llm_items("[broken") == {}
    assert cleanup._parse_llm_items("x [bad json] y") == {}
    assert cleanup._parse_llm_items('{"a": [1]}') == {}
    text = 'Aquí: [{"id": "1", "text": " Hola "}, {"id": 2, "text": "x"}, "s"] fin'
    assert cleanup._parse_llm_items(text) == {"1": "Hola"}

  @pytest.mark.asyncio
  async def test_apply_llm_accepts_rejects_and_survives_errors(self, monkeypatch):
    monkeypatch.setattr(cleanup, "_LLM_BATCH", 2)

    class Res:
      def __init__(self, text):
        self.text = text

    calls = []

    class Provider:
      async def complete(self, messages, max_tokens):
        calls.append(messages)
        if len(calls) == 2:
          raise RuntimeError("llm down")
        return Res('[{"id": "1", "text": "Vamos a revisar."}, {"id": "2", "text": "inventado totalmente"}]')

    segs = [
      {"id": "1", "text_raw": "eh vamos a revisar", "text": "Vamos a revisar"},
      {"id": "2", "text_raw": "el inventario", "text": "El inventario"},
      {"id": "3", "text_raw": "otra cosa", "text": "Otra cosa"},
      {"id": "4", "text_raw": "  ", "text": ""},
      {"id": "5", "text_raw": "", "text": ""},
    ]
    stats = cleanup.CleanupStats()
    original = copy.deepcopy(segs)
    out = await cleanup.apply_llm(segs, Provider(), stats)
    assert out[0]["text"] == "Vamos a revisar."
    assert out[1]["text"] == original[1]["text"]
    assert out[2]["text"] == original[2]["text"]  # failed batch keeps rules text
    assert (stats.llm_segments, stats.llm_rejected) == (1, 1)
    assert len(calls) == 2  # third batch had no text and was skipped
    assert calls[0][0].role == "system"


class TestApplyLlmDlp:
  @pytest.mark.asyncio
  async def test_dlp_block_keeps_rule_cleanup(self):
    from app.ai.errors import AIError

    class Blocked:
      async def complete(self, messages, max_tokens):
        raise AIError("confidential_data_blocked", "bloqueado")

    segs = [{"id": "1", "text_raw": "documento confidencial", "text": "Documento confidencial"}]
    stats = cleanup.CleanupStats()
    out = await cleanup.apply_llm(segs, Blocked(), stats)
    assert out[0]["text"] == "Documento confidencial"
    assert stats.llm_segments == 0


class TestGroupTurns:
  def test_group_turns(self):
    segs = [
      {"id": "1", "speaker_id": "S1", "start": 0, "end": 2, "text": "Hola", "text_raw": "eh hola"},
      {"id": "2", "speaker_id": "S1", "start": 3, "end": 5, "text": "qué tal"},
      {"id": "3", "speaker_id": "S1", "start": 20, "end": 22, "text": "tarde"},
      {"id": "4", "speaker": "Ana", "start": 22, "end": 23, "text": "yo"},
      {"id": "5", "speaker_id": "S2", "start": 23, "text": "  "},
    ]
    turns = cleanup.group_turns(segs, gap_s=8)
    assert [(t["speaker_id"], t["text"], t["segment_ids"]) for t in turns] == [
      ("S1", "Hola qué tal", ["1", "2"]),
      ("S1", "tarde", ["3"]),
      ("Ana", "yo", ["4"]),
    ]
    assert turns[0]["end"] == 5.0 and turns[2]["speaker"] == "Ana"
    raw = cleanup.group_turns(segs[:1], gap_s=8, use_raw=True)
    assert raw[0]["text"] == "eh hola"
    split = cleanup.group_turns(segs[:2], gap_s=8, max_chars=5)
    assert len(split) == 2
