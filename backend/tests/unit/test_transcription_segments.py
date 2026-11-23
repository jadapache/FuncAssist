from __future__ import annotations

import pytest

from app.features.transcription import segments as ops


def _record():
  record = {
    "id": "t1",
    "segments": [
      {"start": 0.0, "end": 2.0, "speaker": "Participante 1", "text": "Hola a todos."},
      {"start": 2.0, "end": 4.0, "speaker": "Participante 2", "text": "Buenos días."},
      {"start": 4.0, "end": 8.0, "speaker": "Participante 1", "text": "Revisemos el inventario de citas."},
    ],
    "summary": {"participants": ["Participante 1", "Participante 2"]},
  }
  return ops.normalize_record(record)


class TestNormalize:
  def test_legacy_record_gets_ids_speakers_and_raw_text(self):
    record = _record()
    assert [s["id"] for s in record["segments"]] == ["seg_0001", "seg_0002", "seg_0003"]
    assert [s["speaker_id"] for s in record["segments"]] == ["S1", "S2", "S1"]
    assert record["speakers"]["S2"] == {"name": "Participante 2", "color_index": 1}
    assert record["segments"][0]["text_raw"] == "Hola a todos."
    assert record["diarization"] == "legacy"
    assert record["summary_status"] == "done"

  def test_single_speaker_is_marked_as_not_diarized(self):
    record = ops.normalize_record({"segments": [{"start": 0, "end": 1, "text": "Hola"}]})
    assert record["diarization"] == "none"
    assert record["segments"][0]["speaker"] == "Participante 1"


class TestSpeakerEdits:
  def test_rename_updates_segments_text_and_summary(self):
    record = ops.apply_speaker_edits(_record(), rename={"S1": "Ana"})
    assert {s["speaker"] for s in record["segments"] if s["speaker_id"] == "S1"} == {"Ana"}
    assert record["summary"]["participants"] == ["Ana", "Participante 2"]

  def test_merge_moves_segments_and_removes_speaker(self):
    record = ops.apply_speaker_edits(_record(), merge=[{"from": "S2", "into": "S1"}])
    assert set(record["speakers"]) == {"S1"}
    assert all(s["speaker_id"] == "S1" for s in record["segments"])
    assert record["summary"]["participants"] == ["Participante 1"]

  def test_unknown_speaker_is_an_error(self):
    with pytest.raises(ops.EditError):
      ops.apply_speaker_edits(_record(), rename={"S9": "X"})

  def test_legacy_rename_twice_and_merge_by_name(self):
    record = ops.rename_by_name(_record(), {"Participante 1": "Ana"})
    record = ops.rename_by_name(record, {"Ana": "Ana María"})
    assert record["speakers"]["S1"]["name"] == "Ana María"
    record = ops.rename_by_name(record, {"Participante 2": "Ana María"})
    assert set(record["speakers"]) == {"S1"}


class TestSegmentEdits:
  def test_assign_new_speaker_and_mark(self):
    record = ops.edit_segment(_record(), "seg_0003", new_speaker_name="Luis", marked=True)
    seg = record["segments"][2]
    assert seg["speaker"] == "Luis" and seg["speaker_id"] == "S3" and seg["marked"] is True
    assert record["speakers"]["S3"]["color_index"] == 2

  def test_reassign_existing_and_drop_unused(self):
    record = ops.edit_segment(_record(), "seg_0002", speaker_id="S1")
    assert set(record["speakers"]) == {"S1"}

  def test_edit_text_keeps_raw(self):
    record = ops.edit_segment(_record(), "seg_0001", text="Hola, equipo.")
    assert record["segments"][0]["text"] == "Hola, equipo."
    assert record["segments"][0]["text_raw"] == "Hola a todos."

  def test_split_interpolates_times(self):
    record = ops.split_segment(_record(), "seg_0003", at=len("Revisemos el"))
    first, second = record["segments"][2], record["segments"][3]
    assert first["text"] == "Revisemos el"
    assert second["text"] == "inventario de citas."
    assert first["end"] == second["start"]
    assert 4.0 < first["end"] < 8.0
    assert second["id"] == "seg_0003_b"

  def test_split_outside_text_is_an_error(self):
    with pytest.raises(ops.EditError):
      ops.split_segment(_record(), "seg_0001", at=500)
