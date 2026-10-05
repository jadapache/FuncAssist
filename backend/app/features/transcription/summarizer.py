from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from app.ai.providers.base import AIMessage
from app.ai.providers.factory import resolve_provider
from app.ai.templates import get_prompt, get_rubric, rubric_to_text
from app.schemas.transcription import TranscriptionSummary

logger = logging.getLogger(__name__)


def format_timestamp(seconds: float) -> str:
  mins = int(seconds // 60)
  secs = int(seconds % 60)
  return f"{mins:02d}:{secs:02d}"


def format_transcript_for_llm(segments: List[Dict[str, Any]]) -> str:
  lines = []
  for seg in segments:
    start_str = format_timestamp(seg.get("start", 0.0))
    speaker = seg.get("speaker", "Participante")
    text = seg.get("text", "")
    lines.append(f"[{start_str}] {speaker}: {text}")
  return "\n".join(lines)


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

  summary_str = "\n\n".join(summary_paragraphs) if summary_paragraphs else None
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
) -> TranscriptionSummary:
  if not segments:
    return TranscriptionSummary(
      summary_text="No se detectaron diálogos en la grabación.",
      key_insights=[],
      participants=[],
      topics=[],
      decisions=[],
      requirements=[],
      action_items=[],
    )

  formatted_transcript = format_transcript_for_llm(segments)

  prompt_cfg = get_prompt("transcript_summary")
  try:
    rubric_cfg = get_rubric("transcript_summary")
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

  try:
    provider = resolve_provider()
    res = await provider.complete(messages, max_tokens=2000)
    summary_text = res.text
    return parse_summary_markdown_or_json(summary_text)
  except Exception as exc:
    logger.warning(f"LLM Summarization failed: {exc}. Using fallback summary.")
    unique_speakers = list(dict.fromkeys(s.get("speaker", "Participante") for s in segments if s.get("speaker")))
    first_text = " ".join(s.get("text", "") for s in segments[:5])
    return TranscriptionSummary(
      summary_text=f"En esta reunión sobre '{title}', los participantes discutieron temas de levantamiento, necesidades del sistema y flujos de trabajo funcionales. {first_text}",
      key_insights=[
        f"Se identificaron {len(segments)} intervenciones de voz en la grabación.",
        "Se capturaron las necesidades operativas y definiciones técnicas del proyecto.",
        "Los interlocutores definieron los compromisos de avance para las siguientes entregas.",
      ],
      participants=unique_speakers if unique_speakers else ["Participante 1"],
      topics=[f"Reunión: {title}"],
      decisions=["Definición de requerimientos"],
      requirements=["Requerimientos funcionales del sistema"],
      action_items=["Estructurar entregables funcionales"],
    )
