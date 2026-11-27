"""Transcript text normalisation: pause markers, fillers/discourse markers, hallucinations and turns.

`text_raw` (the provider's literal output) is never modified; cleaning produces `text`.
See docs/TRANSCRIPTION_PROCESS.md §5.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from app.ai.providers.base import AIMessage

logger = logging.getLogger(__name__)

_W = r"[\wáéíóúüñÁÉÍÓÚÜÑ]"  # word character incl. Spanish letters (\w already covers them; explicit for clarity)

# --- pause markers and non-verbal tags ---------------------------------------------------------

_ELLIPSIS = re.compile(r"\s*(?:\.{3,}|…)+\s*")
_BRACKETED = re.compile(r"[\[\(]\s*([^\]\)]{1,40}?)\s*[\]\)]")
TAGS_KEPT = {"risas", "inaudible", "laughter", "laughs", "laughing", "risa"}
TAGS_DROPPED = {
  "música", "musica", "music", "silencio", "silence", "pausa", "pause", "aplausos", "applause",
  "ruido", "noise", "tos", "cough", "suspiro", "sigh", "sonido", "sound", "blank_audio", "blank audio",
  "ininteligible", "música de fondo", "background music", "no speech", "sin audio",
}

# --- fillers and discourse markers -------------------------------------------------------------

# Pure hesitations: never carry meaning. "e" alone is a Spanish conjunction, so it is never matched.
HESITATION = r"(?:e+h+|e{2,}|e+h*m+|m{2,}h*|a+h+|u+h+|u+m+|h+m+)"
_HESITATION_RE = re.compile(rf"(?<!{_W})(?:{HESITATION})(?!{_W})[,…]*\s*", re.IGNORECASE)

# Discourse markers removed only when they open a sentence followed by a comma ("Bueno, …").
START_MARKERS = {
  "es": ["bueno", "o sea", "este", "pues", "digamos", "a ver", "mira", "tipo", "vale", "okey", "ok"],
  "en": ["well", "so", "like", "you know", "i mean", "okay", "ok"],
}
# Tag questions removed when they close a clause after a comma (", ¿no?").
TAG_QUESTIONS = {
  "es": ["no", "vale", "sí", "si", "verdad", "cierto", "ok", "okey", "me explico", "me entiendes"],
  "en": ["right", "you know", "okay", "yeah"],
}

_REPEAT_TWO = re.compile(rf"(?<!{_W})({_W}+\s+{_W}+)(?:[\s,]+\1)+(?!{_W})", re.IGNORECASE)
_REPEAT_ONE = re.compile(rf"(?<!{_W})({_W}+)(?:[\s,]+\1)+(?!{_W})", re.IGNORECASE)
_FALSE_START = re.compile(rf"(?<!{_W})({_W}{{1,15}})-\s+(?={_W})")


def _alternation(phrases: Iterable[str]) -> str:
  ordered = sorted({p.strip() for p in phrases if p and p.strip()}, key=len, reverse=True)
  return "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in ordered)


@dataclass
class CleanupStats:
  fillers_removed: int = 0
  hallucinations_removed: int = 0
  llm_segments: int = 0
  llm_rejected: int = 0

  def to_dict(self, mode: str) -> dict[str, Any]:
    return {
      "mode": mode,
      "fillers_removed": self.fillers_removed,
      "hallucinations_removed": self.hallucinations_removed,
      "llm_segments": self.llm_segments,
      "llm_rejected": self.llm_rejected,
    }


def strip_pause_markers(text: str) -> tuple[str, list[str]]:
  """Remove ellipses and non-verbal tags; return (text, tags kept as metadata)."""
  tags: list[str] = []

  def _tag(match: re.Match[str]) -> str:
    content = match.group(1).strip().lower()
    if content in TAGS_KEPT:
      tags.append("inaudible" if content == "inaudible" else "risas")
      return " "
    if content in TAGS_DROPPED:
      return " "
    return match.group(0)

  text = _BRACKETED.sub(_tag, text or "")
  text = _ELLIPSIS.sub(" ", text)
  return _tidy(text), sorted(set(tags))


def _tidy(text: str) -> str:
  text = re.sub(r"\s+", " ", text)
  text = re.sub(r"\s+([,.;:?!])", r"\1", text)
  text = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", text)
  text = re.sub(r",\s*([.?!])", r"\1", text)
  text = re.sub(r"([.?!])\s*,", r"\1", text)
  text = re.sub(r"¿\s*\?", "", text)
  text = text.strip()
  text = re.sub(r"^[,;:.\s]+", "", text)
  return _capitalize_sentences(text)


def _capitalize_sentences(text: str) -> str:
  def _up(match: re.Match[str]) -> str:
    return match.group(1) + match.group(2).upper()

  text = re.sub(r"^([¿¡\"']*)(\w)", _up, text)
  return re.sub(r"([.?!]\s+[¿¡\"']*)(\w)", _up, text)


class RuleCleaner:
  """Rule-based filler / discourse-marker removal for one language."""

  def __init__(self, language: str = "es", extra_fillers: Optional[Sequence[str]] = None) -> None:
    lang = (language or "es").split("-")[0].lower()
    lang = lang if lang in START_MARKERS else "es"
    markers = _alternation(START_MARKERS[lang])
    tags = _alternation(TAG_QUESTIONS[lang])
    self._start_markers = re.compile(rf"(^|[.?!¡¿]\s+)(?:{markers})\s*,\s*", re.IGNORECASE)
    self._tag_questions = re.compile(rf",\s*¿?(?:{tags})\?", re.IGNORECASE)
    extra = _alternation(extra_fillers or [])
    self._extra = re.compile(rf"(?<!{_W})(?:{extra})(?!{_W})[,…]*\s*", re.IGNORECASE) if extra else None

  def clean(self, text: str) -> tuple[str, int]:
    removed = 0
    text = text or ""
    text, n = _HESITATION_RE.subn(" ", text)
    removed += n
    if self._extra:
      text, n = self._extra.subn(" ", text)
      removed += n
    text, n = _FALSE_START.subn("", text)
    removed += n
    for pattern in (_REPEAT_TWO, _REPEAT_ONE):
      text, n = pattern.subn(r"\1", text)
      removed += n
    text, n = self._tag_questions.subn(".", text)
    removed += n
    text = _tidy(text)
    while True:  # "Bueno, o sea, …" -> strip markers one at a time
      text, n = self._start_markers.subn(r"\1", text)
      if not n:
        break
      removed += n
      text = _tidy(text)
    return text, removed


# --- hallucination filter ----------------------------------------------------------------------

KNOWN_HALLUCINATIONS = [
  "subtitulos realizados por la comunidad de amara org",
  "subtitulos por la comunidad de amara org",
  "subtitulado por la comunidad de amara org",
  "gracias por ver el video",
  "gracias por ver",
  "gracias por su atencion",
  "suscribete al canal",
  "no olvides suscribirte",
  "thanks for watching",
  "thank you for watching",
  "subtitulos en espanol",
  "subtitles by the amara org community",
]


def normalize_for_match(text: str) -> str:
  decomposed = unicodedata.normalize("NFKD", (text or "").lower())
  ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
  return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _is_known_hallucination(text: str) -> bool:
  norm = normalize_for_match(text)
  if "amara org" in norm:
    return True
  return any(norm.startswith(p) and len(norm) <= len(p) + 15 for p in KNOWN_HALLUCINATIONS)


def _segment_text(seg: dict[str, Any]) -> str:
  return seg.get("text_raw") or seg.get("text") or ""


def _is_unreliable(metrics: dict[str, Any]) -> bool:
  """Whisper's own signals: confident silence (high no-speech, low log-probability) or a looping output."""
  no_speech, logprob, compression = metrics.get("no_speech_prob"), metrics.get("avg_logprob"), metrics.get("compression_ratio")
  silent = no_speech is not None and logprob is not None and no_speech > 0.6 and logprob < -1.0
  looping = compression is not None and compression > 2.4
  return silent or looping


def _repeats_previous(previous: dict[str, Any], seg: dict[str, Any]) -> bool:
  text = normalize_for_match(_segment_text(seg))
  return bool(text) and text == normalize_for_match(_segment_text(previous)) and previous.get("speaker_id") == seg.get("speaker_id")


def filter_hallucinations(segments: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
  """Drop typical Whisper filler output: low-confidence silence, loops, known phrases, repeats."""
  kept: list[dict[str, Any]] = []
  removed = 0
  for seg in segments:
    if _is_unreliable(seg.get("_metrics") or {}) or _is_known_hallucination(_segment_text(seg)):
      removed += 1
    elif kept and _repeats_previous(kept[-1], seg):
      kept[-1]["end"] = max(float(kept[-1].get("end", 0.0)), float(seg.get("end", 0.0)))
      removed += 1
    else:
      kept.append(seg)
  return kept, removed


# --- applying cleanup to segments --------------------------------------------------------------


def apply_rules(
  segments: Sequence[dict[str, Any]],
  *,
  mode: str,
  language: str = "es",
  extra_fillers: Optional[Sequence[str]] = None,
) -> tuple[list[dict[str, Any]], CleanupStats]:
  """Fill `text_raw` (if missing) and compute `text` for every segment. Mode `off` only strips markup."""
  cleaner = RuleCleaner(language, extra_fillers)
  stats = CleanupStats()
  out: list[dict[str, Any]] = []
  for seg in segments:
    item = dict(seg)
    raw = item.get("text_raw")
    if raw is None:
      raw = item.get("text") or ""
      item["text_raw"] = raw
    text, tags = strip_pause_markers(raw)
    if mode != "off":
      text, removed = cleaner.clean(text)
      stats.fillers_removed += removed
    item["text"] = text
    if tags:
      item["tags"] = sorted(set((item.get("tags") or []) + tags))
    else:
      item.setdefault("tags", [])
    out.append(item)
  return out, stats


_LLM_BATCH = 40
_LLM_SYSTEM = (
  "Eres un editor de transcripciones. Recibes segmentos de una reunión transcrita literalmente. "
  "Para cada segmento elimina SOLO muletillas, vacilaciones (eh, em, mmm), marcadores del discurso "
  "sin contenido (o sea, este, bueno, digamos, ¿no?), repeticiones y arranques fallidos. "
  "No reformules, no resumas, no corrijas el contenido, no traduzcas y no añadas palabras. "
  "Conserva nombres, cifras y términos técnicos. Corrige solo puntuación y mayúsculas. "
  'Responde únicamente con un array JSON: [{"id": "...", "text": "..."}], un elemento por segmento recibido.'
)


def _words(text: str) -> list[str]:
  return normalize_for_match(text).split()


def accept_llm_text(raw: str, candidate: str, *, max_shrink: float = 0.4) -> bool:
  """The LLM version must not invent words nor cut more than `max_shrink` of the raw text."""
  if not candidate.strip():
    return False
  raw_words = set(_words(raw))
  cand_words = _words(candidate)
  if any(w not in raw_words for w in cand_words):
    return False
  return len(normalize_for_match(candidate)) >= len(normalize_for_match(raw)) * (1 - max_shrink)


def _parse_llm_items(text: str) -> dict[str, str]:
  match = re.search(r"\[.*\]", text, re.DOTALL)
  if not match:
    return {}
  try:
    items = json.loads(match.group(0))
  except json.JSONDecodeError:
    return {}
  result: dict[str, str] = {}
  for item in items if isinstance(items, list) else []:
    if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("text"), str):
      result[item["id"]] = item["text"].strip()
  return result


def _accept_llm_results(batch: list[dict[str, Any]], cleaned: dict[str, str], stats: CleanupStats) -> None:
  """Take the LLM text of each segment that passes the checks; the rest keep the rules text."""
  for seg in batch:
    candidate = cleaned.get(seg["id"])
    if candidate is None:
      continue
    if accept_llm_text(seg.get("text_raw") or "", candidate):
      seg["text"], _ = strip_pause_markers(candidate)
      stats.llm_segments += 1
    else:
      stats.llm_rejected += 1


async def _llm_clean_batch(batch: list[dict[str, Any]], provider: Any, offset: int, stats: CleanupStats) -> None:
  payload = [{"id": s["id"], "text": s["text_raw"]} for s in batch if (s.get("text_raw") or "").strip()]
  if not payload:
    return
  request = json.dumps(payload, ensure_ascii=False)
  messages = [AIMessage(role="system", content=_LLM_SYSTEM), AIMessage(role="user", content=request)]
  try:
    res = await provider.complete(messages, max_tokens=4096)
  except Exception as exc:
    logger.warning("LLM transcript cleanup failed for batch at %d; keeping rule cleanup: %s", offset, exc)
    return
  _accept_llm_results(batch, _parse_llm_items(getattr(res, "text", "") or ""), stats)


async def apply_llm(segments: list[dict[str, Any]], provider: Any, stats: CleanupStats) -> list[dict[str, Any]]:
  """Optional LLM pass over rule-cleaned segments; any rejected or failed item keeps the rules text."""
  for offset in range(0, len(segments), _LLM_BATCH):
    await _llm_clean_batch(segments[offset : offset + _LLM_BATCH], provider, offset, stats)
  return segments


# --- turns -------------------------------------------------------------------------------------


def _turn_text(seg: dict[str, Any], use_raw: bool) -> str:
  return ((seg.get("text_raw") if use_raw else seg.get("text")) or "").strip()


def _continues_turn(last: Optional[dict[str, Any]], speaker_id: str, start: float, text: str, gap_s: float, max_chars: int) -> bool:
  return (
    last is not None
    and last["speaker_id"] == speaker_id
    and start - last["end"] < gap_s
    and len(last["text"]) + len(text) + 1 <= max_chars
  )


def group_turns(segments: Sequence[dict[str, Any]], gap_s: float, max_chars: int = 600, *, use_raw: bool = False) -> list[dict[str, Any]]:
  """Consecutive segments of the same speaker separated by less than `gap_s` form one turn."""
  turns: list[dict[str, Any]] = []
  for seg in segments:
    text = _turn_text(seg, use_raw)
    if not text:
      continue
    speaker_id = seg.get("speaker_id") or seg.get("speaker") or "S1"
    start = float(seg.get("start", 0.0))
    end = float(seg.get("end", start))
    last = turns[-1] if turns else None
    if _continues_turn(last, speaker_id, start, text, gap_s, max_chars):
      last["text"] = f"{last['text']} {text}"
      last["end"] = max(last["end"], end)
      last["segment_ids"].append(seg.get("id"))
    else:
      turns.append({
        "speaker_id": speaker_id,
        "speaker": seg.get("speaker") or speaker_id,
        "start": start,
        "end": end,
        "text": text,
        "segment_ids": [seg.get("id")],
      })
  return turns
