from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.ai.map_reduce import map_reduce_condense_context
from app.ai.policies import resolve_intent_max_tokens
from app.ai.providers.base import AIMessage
from app.ai.providers.factory import resolve_provider
from app.ai.templates import get_prompt, get_rubric, rubric_to_text
from app.features.transcription import config
from app.features.transcription.cleanup import group_turns
from app.schemas.transcription import TranscriptionSummary

logger = logging.getLogger(__name__)

_BULLET = re.compile(r"^(?:[-*•]|\d+[.)])\s+")
_GENERIC_SPEAKER = re.compile(r"(participante|speaker|hablante|interlocutor)\s*\d+", re.IGNORECASE)


def format_timestamp(seconds: float) -> str:
  mins = int(seconds // 60)
  secs = int(seconds % 60)
  return f"{mins:02d}:{secs:02d}"


def format_transcript_lines(segments: List[Dict[str, Any]], gap_s: Optional[float] = None) -> List[str]:
  """One line per speaker turn (clean text). Pauses below the turn gap never split a turn."""
  turns = group_turns(segments, config.turn_gap_s() if gap_s is None else gap_s)
  return [f"[{format_timestamp(t['start'])}] {t['speaker']}: {t['text']}" for t in turns]


def format_transcript_for_llm(segments: List[Dict[str, Any]]) -> str:
  return "\n".join(format_transcript_lines(segments))


def resolve_transcript_character_budget(provider_id: str) -> int:
  prov = (provider_id or "").strip().lower()
  if prov in ("gemini", "google"):
    return 1_000_000
  if prov in ("openai", "claude"):
    return 300_000
  if prov == "groq":
    return 20_000
  return 15_000


def _head_lines(lines: List[str], budget: int) -> list[str]:
  """Leading lines that fit the budget; a first line longer than the budget is cut."""
  taken: list[str] = []
  used = 0
  for line in lines:
    if used + len(line) + 1 > budget:
      return taken or [line[:budget]]
    taken.append(line)
    used += len(line) + 1
  return taken


def _tail_lines(lines: List[str], budget: int) -> list[str]:
  """Trailing lines that fit the budget, in their original order; a last line longer than the budget is cut."""
  taken: list[str] = []
  used = 0
  for line in reversed(lines):
    if used + len(line) + 1 > budget:
      return taken or [line[-budget:]]
    taken.insert(0, line)
    used += len(line) + 1
  return taken


def _middle_sample(pool: List[str], budget: int) -> list[str]:
  """About ten evenly spaced lines of the middle, as many as fit the budget."""
  taken: list[str] = []
  used = 0
  for line in pool[:: max(1, len(pool) // 10)]:
    if used + len(line) + 1 > budget:
      break
    taken.append(line)
    used += len(line) + 1
  return taken


def condense_transcript_lines(lines: List[str], max_chars: int) -> str:
  if not lines:
    return ""
  joined = "\n".join(lines)
  if len(joined) <= max_chars:
    return joined

  edge_budget = int(max_chars * 0.30)
  head = _head_lines(lines, edge_budget)
  tail = _tail_lines(lines, edge_budget)
  middle_start = len(head)
  middle = _middle_sample(lines[middle_start:max(middle_start, len(lines) - len(tail))], max_chars - 2 * edge_budget)

  sections = ["\n".join(head), "...\n" + "\n".join(middle) if middle else "", "...\n" + "\n".join(tail)]
  result = "\n\n".join(section for section in sections if section).strip()
  return result or joined[:max_chars]


# Section headers in the order they are tried; the first one found in a line decides the section.
_SECTION_HEADERS = (
  ("key_insights", ("key insight", "puntos clave", "conclusiones clave", "insights clave")),
  ("summary", ("# summary", "## summary", "# resumen", "## resumen")),
  ("participants", ("participante", "asistente", "participants")),
  ("topics", ("tema", "temas tratados", "topics")),
  ("decisions", ("decisión", "decisiones", "decisions", "acuerdos")),
  ("requirements", ("requerimiento", "requerimientos", "requirements", "requisitos")),
  ("action_items", ("compromiso", "compromisos", "acción", "acciones", "action items")),
)
_LIST_SECTIONS = ("key_insights", "participants", "topics", "decisions", "requirements", "action_items")


def _header_section(lower_line: str) -> Optional[str]:
  return next((section for section, headers in _SECTION_HEADERS if any(h in lower_line for h in headers)), None)


def _summary_from_json_block(text: str) -> Optional[TranscriptionSummary]:
  """The summary a model returned as a fenced JSON object, or None when there is none or it is unusable."""
  match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
  if not match:
    return None
  try:
    parsed = json.loads(match.group(1))
    return TranscriptionSummary(
      summary_text=parsed.get("summary") or parsed.get("summary_text"),
      **{name: parsed.get(name, []) for name in _LIST_SECTIONS},
    )
  except Exception:
    return None


def _read_sections(text: str) -> dict[str, List[str]]:
  """Bullet items per section; a bullet outside the known sections counts as a key insight."""
  items: dict[str, List[str]] = {name: [] for name in _LIST_SECTIONS}
  current = "summary"
  for line in text.splitlines():
    stripped = line.strip()
    if not stripped:
      continue
    header = _header_section(stripped.lower())
    if header:
      current = header
    elif _BULLET.match(stripped):
      item = _BULLET.sub("", stripped).strip()
      if item:
        items[current if current in items else "key_insights"].append(item)
  return items


# What a summary shows for a section the model left empty.
_SECTION_DEFAULTS = {
  "key_insights": ["Reunión de levantamiento y acuerdos iniciales del proyecto."],
  "participants": ["Participante 1", "Participante 2"],
  "topics": ["Requerimientos funcionales"],
  "decisions": ["Acuerdos de arquitectura y flujo funcional"],
  "requirements": ["Requerimientos funcionales capturados en la transcripción"],
  "action_items": ["Generar documento de Inventario (.xlsx) y Levantamiento (.docx)"],
}


def _sections_with_defaults(items: dict[str, List[str]]) -> dict[str, List[str]]:
  key_insights = items["key_insights"]
  if not key_insights and items["topics"]:
    key_insights = items["topics"] + items["decisions"]
  filled = {name: items[name] or _SECTION_DEFAULTS[name] for name in _LIST_SECTIONS}
  filled["key_insights"] = key_insights or _SECTION_DEFAULTS["key_insights"]
  filled["topics"] = items["topics"] or key_insights[:3] or _SECTION_DEFAULTS["topics"]
  return filled


def parse_summary_markdown_or_json(text: str) -> TranscriptionSummary:
  from_json = _summary_from_json_block(text)
  if from_json:
    return from_json
  return TranscriptionSummary(summary_text=text.strip() or None, **_sections_with_defaults(_read_sections(text)))


async def _fit_transcript(lines: List[str], max_chars: int, title: str, user_id: Optional[str]) -> str:
  """Whole transcript when it fits; otherwise map-reduce with the fast tier (no middle is dropped).

  Head/tail condensation is only the last resort when the map-reduce step fails.
  """
  joined = "\n".join(lines)
  if len(joined) <= max_chars:
    return joined
  try:
    fast = resolve_provider(user_id=user_id, tier="fast")
    condensed = await map_reduce_condense_context(
      joined,
      max_chars,
      fast,
      feature_goal=(
        f"resumen de la reunión '{title}': decisiones, acuerdos, requerimientos, compromisos, "
        "responsables, fechas y participantes con nombre"
      ),
    )
    if condensed and len(condensed) <= max_chars:
      return condensed
  except Exception as exc:
    logger.warning("Map-reduce condensation of transcript failed; using head/tail condensation: %s", exc, exc_info=True)
  return condense_transcript_lines(lines, max_chars)


async def summarize_transcript(
  segments: List[Dict[str, Any]],
  title: str = "Reunión",
  feature: str = "transcript_summary_standard_meeting",
  user_id: Optional[str] = None,
) -> TranscriptionSummary:
  target_feature = feature or "transcript_summary_standard_meeting"
  if target_feature == "transcript_summary":
    target_feature = "transcript_summary_standard_meeting"

  if not segments:
    return TranscriptionSummary(
      summary_text="No se detectaron diálogos en la grabación.",
      key_insights=[],
      participants=[],
      topics=[],
      decisions=[],
      requirements=[],
      action_items=[],
      template_id=target_feature,
    )

  try:
    provider = resolve_provider(user_id=user_id)
  except Exception as exc:
    logger.error("Failed to resolve AI provider: %s", exc)
    raise HTTPException(
      status_code=400,
      detail=f"Error al configurar proveedor de IA: {exc}",
    ) from exc

  max_chars = resolve_transcript_character_budget(provider.id)
  transcript_lines = format_transcript_lines(segments)
  formatted_transcript = await _fit_transcript(transcript_lines, max_chars, title, user_id)

  prompt_cfg = await get_prompt(target_feature)
  try:
    rubric_cfg = await get_rubric(target_feature)
    rubric_text = rubric_to_text(rubric_cfg)
  except Exception:
    rubric_text = ""

  system_msg = prompt_cfg.get("system", "")
  user_template = prompt_cfg.get("user_template", "")
  user_content = (
    user_template.replace("{title}", title)
    .replace("{transcript}", formatted_transcript)
    .replace("{rubric}", rubric_text)
  )

  messages = [
    AIMessage(role="system", content=system_msg),
    AIMessage(role="user", content=user_content),
  ]

  template_title = prompt_cfg.get("title", target_feature)
  try:
    res = await provider.complete(messages, max_tokens=resolve_intent_max_tokens("transcript_summary"))
    summary = parse_summary_markdown_or_json(res.text)
    summary.template_id = target_feature
    summary.template_name = template_title
    # Generic labels ("Participante 2") are not people: only named speakers are participants.
    summary.participants = [p for p in summary.participants if not _GENERIC_SPEAKER.fullmatch(str(p).strip())]
    return summary
  except Exception as exc:
    logger.error("LLM Summarization failed: %s", exc)
    raise HTTPException(
      status_code=400 if isinstance(exc, ValueError) else 500,
      detail=f"Error al generar resumen con IA: {exc}",
    ) from exc
