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


def condense_transcript_lines(lines: List[str], max_chars: int) -> str:
  if not lines:
    return ""
  joined = "\n".join(lines)
  if len(joined) <= max_chars:
    return joined

  head_budget = int(max_chars * 0.30)
  tail_budget = int(max_chars * 0.30)
  mid_budget = max_chars - head_budget - tail_budget

  head_lines: list[str] = []
  head_chars = 0
  for line in lines:
    if head_chars + len(line) + 1 > head_budget:
      if not head_lines:
        head_lines.append(line[:head_budget])
      break
    head_lines.append(line)
    head_chars += len(line) + 1

  tail_lines: list[str] = []
  tail_chars = 0
  for line in reversed(lines):
    if tail_chars + len(line) + 1 > tail_budget:
      if not tail_lines:
        tail_lines.insert(0, line[-tail_budget:])
      break
    tail_lines.insert(0, line)
    tail_chars += len(line) + 1

  mid_start = len(head_lines)
  mid_end = max(mid_start, len(lines) - len(tail_lines))
  mid_pool = lines[mid_start:mid_end]
  mid_lines: list[str] = []
  if mid_pool:
    step = max(1, len(mid_pool) // 10)
    sampled = mid_pool[::step]
    mid_chars = 0
    for line in sampled:
      if mid_chars + len(line) + 1 > mid_budget:
        break
      mid_lines.append(line)
      mid_chars += len(line) + 1

  sections: list[str] = []
  if head_lines:
    sections.append("\n".join(head_lines))
  if mid_lines:
    sections.append("...\n" + "\n".join(mid_lines))
  if tail_lines:
    sections.append("...\n" + "\n".join(tail_lines))

  result = "\n\n".join(sections).strip()
  return result if result else joined[:max_chars]


def parse_summary_markdown_or_json(text: str) -> TranscriptionSummary:
  participants: List[str] = []
  topics: List[str] = []
  decisions: List[str] = []
  requirements: List[str] = []
  action_items: List[str] = []
  key_insights: List[str] = []
  summary_paragraphs: List[str] = []

  # Try parsing JSON if model returned codeblock
  json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
  if json_match:
    try:
      parsed = json.loads(json_match.group(1))
      return TranscriptionSummary(
        summary_text=parsed.get("summary") or parsed.get("summary_text"),
        key_insights=parsed.get("key_insights", []),
        participants=parsed.get("participants", []),
        topics=parsed.get("topics", []),
        decisions=parsed.get("decisions", []),
        requirements=parsed.get("requirements", []),
        action_items=parsed.get("action_items", []),
      )
    except Exception:
      pass

  current_section: str = "summary"
  lines = text.splitlines()

  for line in lines:
    stripped = line.strip()
    if not stripped:
      continue

    lower = stripped.lower()
    # Check section headers
    if any(h in lower for h in ["key insight", "puntos clave", "conclusiones clave", "insights clave"]):
      current_section = "key_insights"
      continue
    elif any(h in lower for h in ["# summary", "## summary", "# resumen", "## resumen"]):
      current_section = "summary"
      continue
    elif any(h in lower for h in ["participante", "asistente", "participants"]):
      current_section = "participants"
      continue
    elif any(h in lower for h in ["tema", "temas tratados", "topics"]):
      current_section = "topics"
      continue
    elif any(h in lower for h in ["decisión", "decisiones", "decisions", "acuerdos"]):
      current_section = "decisions"
      continue
    elif any(h in lower for h in ["requerimiento", "requerimientos", "requirements", "requisitos"]):
      current_section = "requirements"
      continue
    elif any(h in lower for h in ["compromiso", "compromisos", "acción", "acciones", "action items"]):
      current_section = "action_items"
      continue

    # Extract bullet points
    if _BULLET.match(stripped):
      item_text = _BULLET.sub("", stripped, count=1).strip()
      if item_text:
        if current_section == "key_insights":
          key_insights.append(item_text)
        elif current_section == "participants":
          participants.append(item_text)
        elif current_section == "topics":
          topics.append(item_text)
        elif current_section == "decisions":
          decisions.append(item_text)
        elif current_section == "requirements":
          requirements.append(item_text)
        elif current_section == "action_items":
          action_items.append(item_text)
        else:
          key_insights.append(item_text)
    else:
      # Paragraph line
      if current_section == "summary" and not stripped.startswith("#"):
        summary_paragraphs.append(stripped)

  summary_str = text.strip() if text.strip() else ("\n\n".join(summary_paragraphs) if summary_paragraphs else None)
  if not key_insights and topics:
    key_insights = topics + decisions

  return TranscriptionSummary(
    summary_text=summary_str,
    key_insights=key_insights if key_insights else ["Reunión de levantamiento y acuerdos iniciales del proyecto."],
    participants=participants if participants else ["Participante 1", "Participante 2"],
    topics=topics if topics else (key_insights[:3] if key_insights else ["Requerimientos funcionales"]),
    decisions=decisions if decisions else ["Acuerdos de arquitectura y flujo funcional"],
    requirements=requirements if requirements else ["Requerimientos funcionales capturados en la transcripción"],
    action_items=action_items if action_items else ["Generar documento de Inventario (.xlsx) y Levantamiento (.docx)"],
  )


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
