from __future__ import annotations

import pytest

from app.features.transcription.chunking import (
  ChunkPlan,
  map_segments_to_original,
  merge_chunk_results,
  plan_chunks,
  speech_regions,
  trimmed_seconds,
)


def _flat(regions):
  return [value for region in regions for value in region]


class TestSpeechRegions:
  def test_complement_with_padding(self):
    regions = speech_regions([(10.0, 20.0), (30.0, 33.0)], 40.0, padding_s=0.3)
    assert _flat(regions) == pytest.approx([0.0, 10.3, 19.7, 30.3, 32.7, 40.0])

  def test_short_silence_after_padding_is_kept_as_speech(self):
    assert speech_regions([(5.0, 5.5)], 10.0, padding_s=0.3) == [(0.0, 10.0)]

  def test_leading_and_trailing_silence_are_cut_entirely(self):
    regions = speech_regions([(0.0, 4.0), (8.0, 12.0)], 12.0, padding_s=0.3)
    assert _flat(regions) == pytest.approx([3.7, 8.3])

  def test_all_silence(self):
    assert speech_regions([(0.0, 60.0)], 60.0, padding_s=0.3) == []

  def test_trimmed_seconds(self):
    assert trimmed_seconds([(0.0, 10.0), (20.0, 30.0)], 40.0) == pytest.approx(20.0)


class TestChunkPlan:
  def test_to_original_maps_across_regions(self):
    plan = ChunkPlan(index=0, regions=[(10.0, 20.0), (50.0, 55.0)])
    assert plan.to_original(0.0) == 10.0
    assert plan.to_original(9.5) == 19.5
    assert plan.to_original(10.0) == 50.0
    assert plan.to_original(12.0) == 52.0
    assert plan.to_original(99.0) == 55.0  # clamped to the last region end
    assert plan.speech_s == 15.0

  def test_packs_regions_without_cutting_speech(self):
    regions = [(0.0, 200.0), (210.0, 400.0), (410.0, 700.0)]
    chunks = plan_chunks(regions, chunk_s=450.0)
    assert [c.regions for c in chunks] == [[(0.0, 200.0), (210.0, 400.0)], [(410.0, 700.0)]]
    assert chunks[0].own_end == chunks[1].own_start == pytest.approx(405.0)

  def test_long_region_is_split_with_overlap(self):
    chunks = plan_chunks([(0.0, 1000.0)], chunk_s=400.0, overlap_s=2.0)
    assert [c.regions[0] for c in chunks] == [(0.0, 400.0), (398.0, 798.0), (796.0, 1000.0)]
    assert chunks[0].own_end == pytest.approx(399.0)
    assert chunks[1].own_start == pytest.approx(399.0)


class TestMerge:
  def test_shifts_segments_and_resolves_overlap(self):
    chunks = plan_chunks([(0.0, 1000.0)], chunk_s=400.0, overlap_s=2.0)
    first = [{"start": 396.0, "end": 399.5, "text_raw": "dup"}]  # midpoint 397.75 -> owned by chunk 0
    second = [
      {"start": 0.0, "end": 1.5, "text_raw": "dup"},  # original 398-399.5, midpoint 398.75 -> chunk 0 owns it
      {"start": 2.0, "end": 4.0, "text_raw": "next"},  # original 400-402 -> chunk 1
    ]
    merged = merge_chunk_results(chunks, {0: first, 1: second, 2: []})
    assert [s["text_raw"] for s in merged] == ["dup", "next"]
    assert merged[1]["start"] == pytest.approx(400.0)

  def test_maps_trimmed_chunk_back_to_original(self):
    chunk = ChunkPlan(index=0, regions=[(5.0, 10.0), (60.0, 70.0)])
    mapped = map_segments_to_original(chunk, [{"start": 4.0, "end": 7.0, "text_raw": "a"}])
    assert mapped[0]["start"] == pytest.approx(9.0)
    assert mapped[0]["end"] == pytest.approx(62.0)
