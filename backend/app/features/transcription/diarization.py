from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SpeakerDiarization:
  def __init__(self, hf_token: Optional[str] = None):
    self.hf_token = hf_token
    self._pipeline = None

  def _get_pipeline(self):
    if self._pipeline is None and self.hf_token:
      try:
        from pyannote.audio import Pipeline
        self._pipeline = Pipeline.from_pretrained(
          "pyannote/speaker-diarization-3.1",
          use_auth_token=self.hf_token,
        )
      except Exception as e:
        logger.warning(f"Could not load pyannote pipeline: {e}. Falling back to heuristic diarization.")
    return self._pipeline

  def diarize_segments(
    self,
    segments: List[Dict[str, Any]],
    audio_path: Optional[Path] = None,
  ) -> List[Dict[str, Any]]:
    if not segments:
      return []

    pipeline = self._get_pipeline()
    if pipeline and audio_path and audio_path.exists():
      try:
        diarization = pipeline(str(audio_path))
        # Merge pyannote output with transcript segments
        return self._merge_pyannote_diarization(diarization, segments)
      except Exception as exc:
        logger.warning(f"Pyannote diarization failed: {exc}. Using heuristic diarization.")

    # Fallback to smart heuristic diarization
    return self._heuristic_diarization(segments)

  def _merge_pyannote_diarization(self, diarization: Any, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    labeled_segments: List[Dict[str, Any]] = []
    speaker_mapping: Dict[str, str] = {}
    speaker_counter = 1

    for seg in segments:
      start = seg.get("start", 0.0)
      end = seg.get("end", 0.0)
      mid = (start + end) / 2.0

      matched_speaker = None
      for turn, _, speaker in diarization.itertracks(yield_label=True):
        if turn.start <= mid <= turn.end or (turn.start <= end and turn.end >= start):
          matched_speaker = speaker
          break

      if matched_speaker:
        if matched_speaker not in speaker_mapping:
          speaker_mapping[matched_speaker] = f"Participante {speaker_counter}"
          speaker_counter += 1
        friendly_speaker = speaker_mapping[matched_speaker]
      else:
        friendly_speaker = seg.get("speaker") or "Participante 1"

      seg_copy = dict(seg)
      seg_copy["speaker"] = friendly_speaker
      labeled_segments.append(seg_copy)

    return labeled_segments

  def _heuristic_diarization(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Smart turn-based speaker attribution based on time gaps, segment lengths, and conversational patterns."""
    labeled_segments: List[Dict[str, Any]] = []
    current_speaker_idx = 1
    total_speakers = 2

    for i, seg in enumerate(segments):
      seg_copy = dict(seg)
      if i > 0:
        prev_end = segments[i - 1].get("end", 0.0)
        curr_start = seg.get("start", 0.0)
        gap = curr_start - prev_end

        # Pause longer than 1.5s or natural turn transition triggers speaker alternation
        if gap > 1.2:
          current_speaker_idx = (current_speaker_idx % total_speakers) + 1
        elif (seg.get("end", 0.0) - seg.get("start", 0.0)) > 15.0 and i % 3 == 0:
          current_speaker_idx = (current_speaker_idx % total_speakers) + 1

      seg_copy["speaker"] = f"Participante {current_speaker_idx}"
      labeled_segments.append(seg_copy)

    return labeled_segments

  @staticmethod
  def rename_speakers(
    segments: List[Dict[str, Any]],
    speaker_map: Dict[str, str],
  ) -> List[Dict[str, Any]]:
    updated = []
    for seg in segments:
      seg_copy = dict(seg)
      current_spk = seg_copy.get("speaker", "")
      if current_spk in speaker_map:
        seg_copy["speaker"] = speaker_map[current_spk]
      updated.append(seg_copy)
    return updated
