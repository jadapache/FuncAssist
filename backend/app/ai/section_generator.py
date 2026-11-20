"""Helpers and pipeline for deciding and generating documents section by section."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator

from app.ai.events import AgentEvent
from app.ai.policies import resolve_intent_max_tokens
from app.ai.providers.base import AIMessage, AIProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlanSection:
    title: str
    instructions: str = ""


@dataclass(frozen=True)
class DocumentPlan:
    title: str
    extension: str
    chat_intro: str
    sections: list[PlanSection]


def is_section_generation_candidate(intent: str, query: str) -> bool:
    """Return whether a request is suitable for a multi-section document plan."""
    if (intent or "").strip().lower() in {"generic_plan", "generic_report", "template_mutation"}:
        return True
    text = (query or "").strip().lower()
    if text.startswith("/plan"):
        return True
    return bool(re.search(r"\b(elabora|genera|crear|crea|redacta)\b.*\b(plan|informe|reporte)\b", text))


def _clean_json_response(response: str) -> str:
    """Remove markdown fences and surrounding text from a JSON response."""
    text = (response or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


def _parse_plan_json(response: str) -> DocumentPlan | None:
    try:
        data: Any = json.loads(_clean_json_response(response))
        if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
            return None
        sections = [
            PlanSection(str(item["title"]), str(item.get("instructions", "")))
            for item in data["sections"]
            if isinstance(item, dict) and item.get("title")
        ]
        if not sections or not data.get("title") or not data.get("extension"):
            return None
        return DocumentPlan(
            title=str(data["title"]),
            extension=str(data["extension"]),
            chat_intro=str(data.get("chat_intro", "")),
            sections=sections,
        )
    except (TypeError, ValueError, KeyError):
        return None


async def plan_document(
    query: str,
    context_summary: str,
    template_extension: str = "docx",
    provider: AIProvider | None = None,
) -> DocumentPlan | None:
    """Create a structured section plan using the fast model tier."""
    if not provider:
        return None

    planning_prompt = (
        "Eres un arquitecto documental experto. Divide la siguiente solicitud en un plan estructurado de secciones.\n"
        "Debes responder ÚNICAMENTE con un objeto JSON válido con este esquema exacto:\n"
        "{\n"
        '  "title": "Título Formal del Documento",\n'
        f'  "extension": "{template_extension}",\n'
        '  "chat_intro": "Mensaje sintético introductorio para el chat",\n'
        '  "sections": [\n'
        '    {"title": "1. Objetivo y Alcance", "instructions": "Detallar metas y límites del proyecto"},\n'
        '    {"title": "2. Requisitos Técnicos", "instructions": "Describir arquitectura y dependencias"}\n'
        "  ]\n"
        "}\n"
    )

    user_msg = f"SOLICITUD: {query}\nCONTEXTO:\n{context_summary[:3000]}"
    messages = [
        AIMessage(role="system", content=planning_prompt),
        AIMessage(role="user", content=user_msg),
    ]

    try:
        resp = await provider.complete(
            messages,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        plan = _parse_plan_json(resp.text)
        if plan:
            return plan
    except Exception:
        pass

    # 1 retry with explicit error guidance
    try:
        retry_messages = messages + [
            AIMessage(role="assistant", content="{}"),
            AIMessage(role="user", content="El JSON anterior fue inválido. Genera solo el JSON estricto."),
        ]
        resp = await provider.complete(retry_messages, max_tokens=800)
        return _parse_plan_json(resp.text)
    except Exception:
        return None


async def generate_sections_stream(
    plan: DocumentPlan,
    system_prompt: str,
    context_block: str,
    main_provider: AIProvider,
    concurrency: int = 3,
) -> AsyncIterator[str]:
    """Generate all document sections in parallel and stream results in order without truncation."""
    chat_intro = plan.chat_intro or "He elaborado el documento estructurado por secciones."
    ext = plan.extension.lstrip(".")
    yield f"<chat>{chat_intro}</chat>\n<artifact title=\"{plan.title}\" extension=\"{ext}\">\n"

    shared_system = (
        f"{system_prompt}\n\n"
        f"DOCUMENTO: {plan.title}\n"
        f"SECCIONES DEL DOCUMENTO: {'; '.join(sec.title for sec in plan.sections)}\n\n"
        f"CONTEXTO BASE:\n{context_block}"
    )
    semaphore = asyncio.Semaphore(concurrency)
    section_results: dict[int, str] = {}
    ready_events: list[asyncio.Event] = [asyncio.Event() for _ in plan.sections]

    async def _write_section(idx: int, sec: PlanSection) -> None:
        async with semaphore:
            # System prefix is identical for every section (cacheable); only the user turn varies.
            msgs = [
                AIMessage(role="system", content=shared_system),
                AIMessage(
                    role="user",
                    content=(
                        f"Redacta ÚNICAMENTE la sección '{sec.title}'. "
                        f"Instrucciones específicas: {sec.instructions}. "
                        "No agregues etiquetas <artifact> ni <chat>, ni repitas el título general. "
                        "Entrega directamente el contenido Markdown enriquecido de esta sección."
                    ),
                ),
            ]
            try:
                res = await main_provider.complete(msgs, max_tokens=2500)
                section_results[idx] = f"\n\n## {sec.title}\n{res.text.strip()}\n"
            except Exception as exc:
                section_results[idx] = f"\n\n## {sec.title}\n(Error al generar sección: {exc})\n"
            finally:
                ready_events[idx].set()

    # Launch parallel drafting
    tasks = [asyncio.create_task(_write_section(i, sec)) for i, sec in enumerate(plan.sections)]

    # Stream out strictly in index order as each becomes ready
    for i in range(len(plan.sections)):
        await ready_events[i].wait()
        content = section_results.get(i, "")
        yield content

    yield "\n</artifact>"
    await asyncio.gather(*tasks, return_exceptions=True)
