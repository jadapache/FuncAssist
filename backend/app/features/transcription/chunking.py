"""Speech regions, chunk planning and merging of per-chunk transcripts back onto the original timeline.

Times are in seconds. "Original" time is the position in the uploaded recording; "chunk" time is the
position inside a chunk file, which concatenates only the speech regions assigned to that chunk.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

SPEECH_PADDING_S = 0.3
DEFAULT_OVERLAP_S = 2.0
MAX_REGIONS_PER_CHUNK = 400


def speech_regions(
  silences: Iterable[tuple[float, float]],
  duration_s: float,
  *,
  padding_s: float = SPEECH_PADDING_S,
  min_region_s: float = 0.2,
) -> list[tuple[float, float]]:
  """Complement of the silences, keeping `padding_s` of each silence next to the speech."""
  regions: list[tuple[float, float]] = []
  cursor = 0.0
  for start, end in sorted(silences):
    # Padding only matters next to speech: a silence at the very start or end is cut entirely.
    cut_start = start + padding_s if start > 0 else start
    cut_end = end - padding_s if end < duration_s else end
    if cut_end <= cut_start:
      continue  # silence too short once padded: keep it as part of the speech
    if cut_start > cursor:
      regions.append((cursor, min(cut_start, duration_s)))
    cursor = max(cursor, cut_end)
  if cursor < duration_s:
    regions.append((cursor, duration_s))
  return [(s, e) for s, e in regions if e - s >= min_region_s]


def trimmed_seconds(regions: Sequence[tuple[float, float]], duration_s: float) -> float:
  return max(0.0, duration_s - sum(e - s for s, e in regions))


@dataclass
class ChunkPlan:
  index: int
  regions: list[tuple[float, float]]
  own_start: float = float("-inf")
  own_end: float = float("inf")
  _offsets: list[float] = field(default_factory=list, repr=False)

  def __post_init__(self) -> None:
    offset = 0.0
    self._offsets = []
    for start, end in self.regions:
      self._offsets.append(offset)
      offset += end - start

  @property
  def speech_s(self) -> float:
    return sum(e - s for s, e in self.regions)

  @property
  def start(self) -> float:
    return self.regions[0][0]

  @property
  def end(self) -> float:
    return self.regions[-1][1]

  def to_original(self, t: float) -> float:
    """Map a time inside the chunk file to the original recording."""
    if not self.regions:
      return t
    t = max(0.0, t)
    idx = bisect.bisect_right(self._offsets, t) - 1
    idx = max(0, min(idx, len(self.regions) - 1))
    start, end = self.regions[idx]
    return min(end, start + (t - self._offsets[idx]))

  def to_dict(self) -> dict[str, Any]:
    return {"index": self.index, "regions": [list(r) for r in self.regions]}


def _split_long_regions(regions: Sequence[tuple[float, float]], chunk_s: float, overlap_s: float) -> list[tuple[float, float]]:
  pieces: list[tuple[float, float]] = []
  for start, end in regions:
    if end - start <= chunk_s:
      pieces.append((start, end))
      continue
    cursor = start
    while cursor < end:
      piece_end = min(end, cursor + chunk_s)
      pieces.append((cursor, piece_end))
      if piece_end >= end:
        break
      cursor = piece_end - overlap_s
  return pieces


def plan_chunks(
  regions: Sequence[tuple[float, float]],
  chunk_s: float,
  overlap_s: float = DEFAULT_OVERLAP_S,
) -> list[ChunkPlan]:
  """Pack speech regions into chunks of at most `chunk_s` seconds of speech.

  Chunks are cut between regions (i.e. inside a silence) whenever possible; only a region longer than
  a whole chunk is cut through speech, with `overlap_s` seconds of overlap. Each chunk owns the
  original-time window up to the midpoint with its neighbours, which resolves overlap duplicates.
  """
  pieces = _split_long_regions(regions, chunk_s, overlap_s)
  groups: list[list[tuple[float, float]]] = []
  current: list[tuple[float, float]] = []
  current_s = 0.0
  for piece in pieces:
    length = piece[1] - piece[0]
    if current and (current_s + length > chunk_s or len(current) >= MAX_REGIONS_PER_CHUNK):
      groups.append(current)
      current, current_s = [], 0.0
    current.append(piece)
    current_s += length
  if current:
    groups.append(current)

  chunks = [ChunkPlan(index=i, regions=g) for i, g in enumerate(groups)]
  for prev, nxt in zip(chunks, chunks[1:]):
    boundary = (prev.end + nxt.start) / 2
    prev.own_end = boundary
    nxt.own_start = boundary
  return chunks


def chunk_from_dict(data: dict[str, Any], own_start: float, own_end: float) -> ChunkPlan:
  plan = ChunkPlan(index=int(data["index"]), regions=[(float(s), float(e)) for s, e in data["regions"]])
  plan.own_start, plan.own_end = own_start, own_end
  return plan


def map_segments_to_original(chunk: ChunkPlan, segments: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
  """Shift a chunk's segments to original time and keep only those the chunk owns."""
  kept: list[dict[str, Any]] = []
  for seg in segments:
    start = chunk.to_original(float(seg.get("start", 0.0)))
    end = max(start, chunk.to_original(float(seg.get("end", seg.get("start", 0.0)))))
    mid = (start + end) / 2
    if not (chunk.own_start <= mid < chunk.own_end):
      continue
    mapped = dict(seg)
    mapped["start"] = round(start, 3)
    mapped["end"] = round(end, 3)
    kept.append(mapped)
  return kept


def merge_chunk_results(chunks: Sequence[ChunkPlan], results: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
  merged: list[dict[str, Any]] = []
  for chunk in chunks:
    merged.extend(map_segments_to_original(chunk, results.get(chunk.index, [])))
  merged.sort(key=lambda s: (s["start"], s["end"]))
  return merged
