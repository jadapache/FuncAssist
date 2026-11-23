"""Speaker labelling for diarized cloud transcripts.

The backend runs no local diarization model. Speakers come either from OpenAI's diarization model
(`whisper_cloud.SpeechClient.diarize`) or, without it, every segment belongs to a single speaker `S1`.
A pause never changes the speaker.

With chunked audio, the first chunk is diarized alone; up to four of its speakers are then sent as
known-speaker references with the remaining chunks so they come back with the same labels.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

MAX_KNOWN_SPEAKERS = 4
REFERENCE_MIN_S = 2.0
REFERENCE_MAX_S = 8.0


class SpeakerLabelMapper:
  """Maps provider labels to stable ids (S1, S2…). Labels equal to an existing id are kept."""

  def __init__(self) -> None:
    self._by_chunk: dict[tuple[int, str], str] = {}
    self._next = 1
    self.known: set[str] = set()

  def _new_id(self) -> str:
    while f"S{self._next}" in self.known:
      self._next += 1
    speaker_id = f"S{self._next}"
    self.known.add(speaker_id)
    return speaker_id

  def map(self, chunk_index: int, label: str) -> str:
    if label in self.known:
      return label
    key = (chunk_index, label)
    if key not in self._by_chunk:
      self._by_chunk[key] = self._new_id()
    return self._by_chunk[key]

  def label_segments(self, chunk_index: int, segments: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    labelled = []
    for seg in segments:
      item = dict(seg)
      item["speaker_id"] = self.map(chunk_index, str(item.pop("speaker_label", "A")))
      labelled.append(item)
    return labelled


def reference_candidates(
  segments: Iterable[dict[str, Any]],
  max_speakers: int = MAX_KNOWN_SPEAKERS,
) -> list[tuple[str, float, float]]:
  """(speaker_id, start, end) of the longest usable segment per speaker, at most `max_speakers`."""
  best: dict[str, tuple[float, float]] = {}
  order: list[str] = []
  for seg in segments:
    speaker_id = seg.get("speaker_id")
    if not speaker_id:
      continue
    start, end = float(seg.get("start", 0.0)), float(seg.get("end", 0.0))
    if end - start < REFERENCE_MIN_S:
      continue
    if speaker_id not in best:
      order.append(speaker_id)
    current = best.get(speaker_id)
    if current is None or (end - start) > (current[1] - current[0]):
      best[speaker_id] = (start, end)
  return [
    (sid, best[sid][0], min(best[sid][1], best[sid][0] + REFERENCE_MAX_S))
    for sid in order[:max_speakers]
  ]


def build_speaker_map(segments: Iterable[dict[str, Any]], existing: Optional[dict[str, Any]] = None) -> dict[str, dict[str, Any]]:
  """Speaker map in order of first appearance: {S1: {name: "Participante 1", color_index: 0}, …}."""
  speakers: dict[str, dict[str, Any]] = {}
  for seg in segments:
    speaker_id = seg.get("speaker_id") or "S1"
    if speaker_id in speakers:
      continue
    previous = (existing or {}).get(speaker_id) or {}
    index = len(speakers)
    speakers[speaker_id] = {
      "name": previous.get("name") or f"Participante {index + 1}",
      "color_index": index,
    }
  if not speakers:
    speakers["S1"] = {"name": "Participante 1", "color_index": 0}
  return speakers
