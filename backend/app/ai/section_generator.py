"""Generador de documentos extensos por secciones para evitar truncamiento por límite de modelo.

Divide la generación en dos fases:
1. Planificación: Genera el esquema y lista de secciones del artefacto.
2. Redacción iterativa: Redacta cada sección individualmente con presupuesto
   de tokens completo y emite los fragmentos en streaming continuo.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, AsyncGenerator

from app.ai.providers.base import AIMessage

logger = logging.getLogger(__name__)

DOCUMENT_INTENTS = {
    "generic_plan",
    "generic_report",
    "template_mutation",
    "mejoras_doc",
    "levantamiento_doc",
}

SECTION_KEYWORDS = (
    "plan detallado",
    "plan de prueba",
    "plan de pruebas",
    "informe completo",
    "informe detallado",
    "documento completo",
    "especificacion completa",
    "especificación completa",
    "matriz de pruebas",
    "elabora un plan",
    "genera un plan",
    "genera un informe",
    "auditoría",
    "auditoria",
    "validación",
    "validacion",
    "especificación",
    "especificacion",
    "historias de usuario",
    "casos de prueba",
    "casos de uso",
    "criterios de aceptación",
    "criterios de aceptacion",
)


@dataclass
class SectionItem:
    title: str
    instructions: str


@dataclass
class DocumentPlan:
    title: str
    extension: str
    chat_intro: str
    sections: list[SectionItem]


def is_section_generation_candidate(
    intent: str,
    query: str,
    has_attachments: bool = False,
) -> bool:
    """Determina si una solicitud amerita generación por secciones para evitar truncamiento."""
    if intent not in {"chat", "qa"}:
        return True

    q_lower = query.strip().lower()
    if q_lower.startswith("/") and not q_lower.startswith("/pregunta"):
        return True

    if has_attachments and not (q_lower.startswith("¿") or q_lower.endswith("?")):
        return True

    return any(kw in q_lower for kw in SECTION_KEYWORDS)


def _clean_json_response(raw_text: str) -> str:
    cleaned = raw_text.strip()
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        return match.group(0).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_plan_json(raw_text: str) -> DocumentPlan | None:
    try:
        clean = _clean_json_response(raw_text)
        data = json.loads(clean)
        sections = [
            SectionItem(
                title=s.get("title", f"Sección {i+1}"),
                instructions=s.get("instructions", "Desarrollar contenido detallado."),
            )
            for i, s in enumerate(data.get("sections", []))
            if isinstance(s, dict)
        ]
        if not sections:
            return None
        return DocumentPlan(
            title=data.get("title", "Documento Corporativo"),
            extension=data.get("extension", "docx").lower(),
            chat_intro=data.get("chat_intro", "He estructurado el documento por secciones."),
            sections=sections,
        )
    except Exception as exc:
        logger.warning("No se pudo parsear el plan de secciones: %s", exc)
        return None


async def create_document_plan(
    provider: Any,
    query: str,
    context_text: str,
) -> DocumentPlan | None:
    """Solicita al modelo la estructura de secciones del documento."""
    prompt = (
        "Planifica la estructura de un documento técnico profesional para la solicitud del usuario.\n"
        "Responde ÚNICAMENTE un objeto JSON válido con este formato exacto, sin texto adicional:\n"
        "{\n"
        '  "title": "Título descriptivo del documento",\n'
        '  "extension": "docx",\n'
        '  "chat_intro": "Breve explicación conversacional de la estructura propuesta",\n'
        '  "sections": [\n'
        '    {"title": "1. Introducción y Alcance", "instructions": "Detallar objetivos y contexto general"},\n'
        '    {"title": "2. ...", "instructions": "..."}\n'
        '  ]\n'
        "}\n"
        "Define entre 3 y 5 secciones claras, no redundantes y bien delimitadas.\n\n"
        f"CONTEXTO:\n{context_text[:25000]}\n\n"
        f"SOLICITUD:\n{query}"
    )

    try:
        resp = await provider.complete([AIMessage(role="user", content=prompt)], max_tokens=350)
        return _parse_plan_json(resp.text)
    except Exception as exc:
        logger.warning("Error al generar plan de secciones: %s", exc)
        return None


def _build_section_prompt(
    plan: DocumentPlan,
    section: SectionItem,
    context_text: str,
    recent_summary: str,
) -> str:
    return (
        f"DOCUMENTO: {plan.title}\n"
        f"SECCIÓN A REDACTAR: {section.title}\n"
        f"OBJETIVO: {section.instructions}\n\n"
        f"CONTEXTO GENERAL:\n{context_text[:25000]}\n\n"
        f"RESUMEN PREVIO:\n{recent_summary[-1500:] if recent_summary else 'Inicio del documento'}\n\n"
        f"Redacta el contenido técnico exhaustivo para '{section.title}' en formato Markdown.\n"
        "No incluyas etiquetas <artifact> ni <chat>, únicamente el contenido de esta sección."
    )


async def stream_sections(
    provider: Any,
    plan: DocumentPlan,
    context_text: str,
    system_prompt: str,
) -> AsyncGenerator[str, None]:
    """Emite en streaming cada sección del documento de forma secuencial."""
    yield f"<chat>{plan.chat_intro}</chat>\n\n"
    yield f'<artifact title="{plan.title}" extension="{plan.extension}">\n'

    accumulated: list[str] = []
    for idx, section in enumerate(plan.sections):
        summary = "\n".join(accumulated[-3:]) if accumulated else ""
        sec_prompt = _build_section_prompt(plan, section, context_text, summary)
        messages = [
            AIMessage(role="system", content=system_prompt),
            AIMessage(role="user", content=sec_prompt),
        ]

        if idx > 0:
            yield "\n\n"

        sec_chunks: list[str] = []
        async for chunk in provider.complete_stream(messages):
            clean_chunk = re.sub(r"</?(?:artifact|chat)[^>]*>", "", chunk, flags=re.IGNORECASE)
            sec_chunks.append(clean_chunk)
            yield clean_chunk

        accumulated.append("".join(sec_chunks))

    yield "\n</artifact>"
