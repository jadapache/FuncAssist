from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.ai.providers.base import AIMessage
from app.ai.providers.factory import resolve_provider
from app.ai.templates import get_prompt, get_rubric, rubric_to_text
from app.schemas.transcription import TranscriptionSummary

logger = logging.getLogger(__name__)


def format_timestamp(seconds: float) -> str:
  mins = int(seconds // 60)
  secs = int(seconds % 60)
  return f"{mins:02d}:{secs:02d}"


def format_transcript_lines(segments: List[Dict[str, Any]]) -> List[str]:
  if not segments:
    return []

  lines: list[str] = []
  current_speaker: str | None = None
  current_start: float = 0.0
  current_last_end: float = 0.0
  current_texts: list[str] = []
  current_chars: int = 0

  def flush() -> None:
    nonlocal current_chars
    if current_texts and current_speaker is not None:
      start_str = format_timestamp(current_start)
      merged = " ".join(current_texts).strip()
      if merged:
        lines.append(f"[{start_str}] {current_speaker}: {merged}")
    current_texts.clear()
    current_chars = 0

  for seg in segments:
    spk = seg.get("speaker") or "Participante"
    txt = (seg.get("text") or "").strip()
    if not txt:
      continue
    start = float(seg.get("start", 0.0))
    end = float(seg.get("end", start + 2.0))

    silence_gap = (start - current_last_end) if current_texts else 0.0
    speaker_changed = (spk != current_speaker)
    turn_too_long = (current_chars + len(txt) > 600)
    gap_detected = (silence_gap > 5.0)

    if speaker_changed or turn_too_long or gap_detected:
      flush()
      current_speaker = spk
      current_start = start

    current_texts.append(txt)
    current_chars += len(txt) + 1
    current_last_end = end

  flush()
  return lines


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
    if re.match(r"^[-*•\d+.]\s+", stripped):
      item_text = re.sub(r"^[-*•\d+.]\s*", "", stripped).strip()
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
  formatted_transcript = condense_transcript_lines(transcript_lines, max_chars)

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
    res = await provider.complete(messages, max_tokens=2000)
    summary = parse_summary_markdown_or_json(res.text)
    summary.template_id = target_feature
    summary.template_name = template_title
    return summary
  except Exception as exc:
    logger.error("LLM Summarization failed: %s", exc)
    raise HTTPException(
      status_code=400 if isinstance(exc, ValueError) else 500,
      detail=f"Error al generar resumen con IA: {exc}",
    ) from exc
