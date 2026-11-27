"""Transcript record model helpers: segment ids, speaker map and the speaker/segment edit operations.

A record holds `segments` (atomic, never grouped) and `speakers: {speaker_id: {name, color_index}}`.
Each segment keeps `speaker` (display name) in sync with the map for older consumers.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.features.transcription import config

MAX_SPEAKER_NAME = 80


class EditError(ValueError):
  """Invalid edit request (unknown speaker/segment, empty name...)."""


def default_speaker_name(index: int) -> str:
  return f"Participante {index}"


def _speaker_number(speaker_id: str) -> int:
  match = re.fullmatch(r"S(\d+)", speaker_id or "")
  return int(match.group(1)) if match else 0


def new_speaker_id(speakers: dict[str, Any]) -> str:
  return f"S{max((_speaker_number(k) for k in speakers), default=0) + 1}"


def _next_color(speakers: dict[str, Any]) -> int:
  used = [int(v.get("color_index", 0)) for v in speakers.values()]
  return max(used) + 1 if used else 0


def ensure_segment_ids(segments: list[dict[str, Any]]) -> None:
  seen: set[str] = set()
  counter = 0
  for seg in segments:
    seg_id = seg.get("id")
    if not isinstance(seg_id, str) or not seg_id or seg_id in seen:
      while True:
        counter += 1
        candidate = f"seg_{counter:04d}"
        if candidate not in seen:
          break
      seg["id"] = candidate
    seen.add(seg["id"])


def full_text(segments: list[dict[str, Any]]) -> str:
  return " ".join((s.get("text") or "").strip() for s in segments if (s.get("text") or "").strip())


def _speaker_id_for(seg: dict[str, Any], speakers: dict[str, dict[str, Any]], name_to_id: dict[Any, str]) -> str:
  """The segment's speaker id; a segment known only by name gets (or creates) the speaker of that name."""
  speaker_id = seg.get("speaker_id")
  if speaker_id and speaker_id in speakers:
    return speaker_id
  name = (seg.get("speaker") or "").strip() or default_speaker_name(1)
  speaker_id = name_to_id.get(name)
  if not speaker_id:
    speaker_id = new_speaker_id(speakers)
    speakers[speaker_id] = {"name": name, "color_index": _next_color(speakers)}
    name_to_id[name] = speaker_id
  return speaker_id


def _normalize_segment(seg: dict[str, Any], speakers: dict[str, dict[str, Any]], name_to_id: dict[Any, str]) -> None:
  seg["speaker_id"] = speaker_id = _speaker_id_for(seg, speakers, name_to_id)
  seg["speaker"] = speakers[speaker_id].get("name") or default_speaker_name(_speaker_number(speaker_id))
  if seg.get("text_raw") is None:
    seg["text_raw"] = seg.get("text") or ""
  seg.setdefault("text", seg["text_raw"])
  if not isinstance(seg.get("tags"), list):
    seg["tags"] = []
  seg["marked"] = bool(seg.get("marked", False))
  seg["start"] = float(seg.get("start", 0.0) or 0.0)
  seg["end"] = float(seg.get("end", seg["start"]) or seg["start"])


def _source_of(record: dict[str, Any]) -> str:
  """Where a record without a `source` came from, judged by the engine that produced it."""
  engine = str((record.get("metadata") or {}).get("engine") or record.get("model_info") or "").lower()
  return "browser" if "client" in engine or "navegador" in engine else "cloud"


def _fill_record_defaults(record: dict[str, Any]) -> None:
  if not record.get("diarization"):
    record["diarization"] = "none" if len(record["speakers"]) <= 1 else "legacy"
  record.setdefault("turn_gap_s", config.turn_gap_s())
  if not record.get("summary_status"):
    record["summary_status"] = "done" if record.get("summary") else "skipped"
  record.setdefault("cleanup", None)
  record.setdefault("silence_trimmed_s", 0.0)
  if not record.get("source"):
    record["source"] = _source_of(record)


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
  """Bring any stored record (including pre-v2 ones) to the current shape, in place."""
  segments: list[dict[str, Any]] = [dict(s) for s in (record.get("segments") or []) if isinstance(s, dict)]
  stored_speakers = record.get("speakers") or {}
  speakers: dict[str, dict[str, Any]] = {k: dict(v) for k, v in stored_speakers.items() if isinstance(v, dict)}
  name_to_id = {v.get("name"): k for k, v in speakers.items()}
  ensure_segment_ids(segments)
  for seg in segments:
    _normalize_segment(seg, speakers, name_to_id)

  record["segments"] = segments
  record["speakers"] = speakers
  _fill_record_defaults(record)
  return record


def _find_segment(record: dict[str, Any], segment_id: str) -> tuple[int, dict[str, Any]]:
  for idx, seg in enumerate(record.get("segments") or []):
    if seg.get("id") == segment_id:
      return idx, seg
  raise EditError("Segmento no encontrado.")


def _require_speaker(record: dict[str, Any], speaker_id: str) -> dict[str, Any]:
  speaker = (record.get("speakers") or {}).get(speaker_id)
  if speaker is None:
    raise EditError(f"Hablante no encontrado: {speaker_id}")
  return speaker


def _clean_name(name: Any) -> str:
  value = str(name or "").strip()
  if not value:
    raise EditError("El nombre del hablante no puede estar vacío.")
  return value[:MAX_SPEAKER_NAME]


def _sync(record: dict[str, Any], renamed: Optional[dict[str, str]] = None) -> dict[str, Any]:
  speakers = record.get("speakers") or {}
  for seg in record.get("segments") or []:
    sp = speakers.get(seg.get("speaker_id"))
    if sp:
      seg["speaker"] = sp["name"]
  record["text"] = full_text(record.get("segments") or [])
  summary = record.get("summary")
  if renamed and isinstance(summary, dict) and isinstance(summary.get("participants"), list):
    # Renamed participants, without the duplicates a merge can create; first occurrence wins.
    summary["participants"] = list(dict.fromkeys(renamed.get(p, p) for p in summary["participants"]))
  return record


def rename_speakers(record: dict[str, Any], rename: dict[str, str]) -> dict[str, str]:
  """Rename by speaker id. Returns {old name: new name} for summary participants."""
  changes: dict[str, str] = {}
  for speaker_id, name in rename.items():
    speaker = _require_speaker(record, speaker_id)
    new_name = _clean_name(name)
    if speaker["name"] != new_name:
      changes[speaker["name"]] = new_name
      speaker["name"] = new_name
  return changes


def merge_speakers(record: dict[str, Any], source_id: str, target_id: str) -> dict[str, str]:
  if source_id == target_id:
    return {}
  source = _require_speaker(record, source_id)
  target = _require_speaker(record, target_id)
  for seg in record.get("segments") or []:
    if seg.get("speaker_id") == source_id:
      seg["speaker_id"] = target_id
  del record["speakers"][source_id]
  return {source["name"]: target["name"]}


def apply_speaker_edits(
  record: dict[str, Any],
  rename: Optional[dict[str, str]] = None,
  merge: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
  changes: dict[str, str] = {}
  for item in merge or []:
    changes.update(merge_speakers(record, str(item.get("from") or ""), str(item.get("into") or "")))
  renamed = rename_speakers(record, rename or {})
  # A speaker merged into one that is then renamed must end with the final name too.
  for old, new in list(changes.items()):
    changes[old] = renamed.get(new, new)
  changes.update(renamed)
  return _sync(record, changes)


def rename_by_name(record: dict[str, Any], speaker_map: dict[str, str]) -> dict[str, Any]:
  """Legacy `{current name: new name}` rename; a name equal to another speaker's merges them."""
  speakers = record.get("speakers") or {}
  by_name = {v["name"]: k for k, v in speakers.items()}
  changes: dict[str, str] = {}
  for old_name, new_name in speaker_map.items():
    speaker_id = by_name.get(old_name)
    if not speaker_id:
      continue
    clean = _clean_name(new_name)
    existing = by_name.get(clean)
    if existing in speakers:  # merging a speaker into itself changes nothing; a merged-away one no longer exists
      changes.update(merge_speakers(record, speaker_id, existing))
    else:
      changes[old_name] = clean
      speakers[speaker_id]["name"] = clean
      by_name[clean] = speaker_id
  return _sync(record, changes)


def edit_segment(
  record: dict[str, Any],
  segment_id: str,
  *,
  speaker_id: Optional[str] = None,
  new_speaker_name: Optional[str] = None,
  text: Optional[str] = None,
  marked: Optional[bool] = None,
) -> dict[str, Any]:
  _, seg = _find_segment(record, segment_id)
  speakers = record.setdefault("speakers", {})
  if new_speaker_name is not None:
    name = _clean_name(new_speaker_name)
    existing = next((k for k, v in speakers.items() if v["name"] == name), None)
    if existing:
      seg["speaker_id"] = existing
    else:
      sid = new_speaker_id(speakers)
      speakers[sid] = {"name": name, "color_index": _next_color(speakers)}
      seg["speaker_id"] = sid
  elif speaker_id is not None:
    _require_speaker(record, speaker_id)
    seg["speaker_id"] = speaker_id
  if text is not None:
    seg["text"] = str(text).strip()
  if marked is not None:
    seg["marked"] = bool(marked)
  if record.get("diarization") == "none" and len(speakers) > 1:
    record["diarization"] = "manual"
  _drop_unused_speakers(record)
  return _sync(record)


def _drop_unused_speakers(record: dict[str, Any]) -> None:
  used = {s.get("speaker_id") for s in record.get("segments") or []}
  for sid in [k for k in record.get("speakers") or {} if k not in used]:
    if len(record["speakers"]) > 1:
      del record["speakers"][sid]


def _split_point(text: str, ratio: float) -> int:
  if not text:
    return 0
  target = int(round(len(text) * ratio))
  spaces = [m.start() for m in re.finditer(r"\s", text)]
  if not spaces:
    return target
  return min(spaces, key=lambda p: abs(p - target))


def split_segment(record: dict[str, Any], segment_id: str, at: int) -> dict[str, Any]:
  idx, seg = _find_segment(record, segment_id)
  text = seg.get("text") or ""
  if not 0 < at < len(text):
    raise EditError("La posición de división debe estar dentro del texto del segmento.")
  cut = _split_point(text, at / len(text))
  first_text, second_text = text[:cut].strip(), text[cut:].strip()
  if not first_text or not second_text:
    raise EditError("La división dejaría un segmento vacío.")
  ratio = len(first_text) / (len(first_text) + len(second_text))
  raw = seg.get("text_raw") or ""
  raw_cut = _split_point(raw, ratio)
  start, end = float(seg["start"]), float(seg["end"])
  middle = round(start + (end - start) * ratio, 3)

  second = dict(seg)
  existing_ids = {s.get("id") for s in record["segments"]}
  base = f"{seg['id']}_b"
  new_id, n = base, 1
  while new_id in existing_ids:
    n += 1
    new_id = f"{base}{n}"
  seg.update({"text": first_text, "text_raw": raw[:raw_cut].strip(), "end": middle})
  second.update({"id": new_id, "text": second_text, "text_raw": raw[raw_cut:].strip(), "start": middle, "marked": False})
  record["segments"].insert(idx + 1, second)
  return _sync(record)
