"""Helpers and pipeline for deciding and generating documents section by section."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator

from app.ai.events import AgentEvent
from app.ai.multimodal import user_message_with_images
from app.ai.policies import resolve_intent_max_tokens
from app.ai.providers.base import AIMessage, AIProvider

logger = logging.getLogger(__name__)

PLAN_HISTORY_MESSAGES = 6
SECTION_ATTEMPTS = 2


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
    braces = re.search(r"\{.*\}", text, re.DOTALL)
    return braces.group(0) if braces else text


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


def _numeric_field(completion: Any, key: str, kind: type | tuple[type, ...]) -> Any:
    """`completion.<key>` when it is a number of `kind` (booleans excluded), else None."""
    value = getattr(completion, key, None)
    return value if isinstance(value, kind) and not isinstance(value, bool) else None


def _add_usage(sink: dict[str, Any] | None, completion: Any) -> None:
    """Accumulate token usage and cost of one completion into `sink`."""
    if sink is None or completion is None:
        return
    for key in ("prompt_tokens", "completion_tokens", "cached_tokens"):
        value = _numeric_field(completion, key, int)
        if value is not None:
            sink[key] = (sink.get(key) or 0) + value
    cost = _numeric_field(completion, "cost_usd", (int, float))
    if cost is not None:
        sink["cost_usd"] = (sink.get("cost_usd") or 0.0) + float(cost)
    sink["llm_calls"] = (sink.get("llm_calls") or 0) + 1


async def plan_document(
    query: str,
    context_summary: str,
    template_extension: str = "docx",
    provider: AIProvider | None = None,
    history: list[AIMessage] | None = None,
    usage_sink: dict[str, Any] | None = None,
) -> DocumentPlan | None:
    """Create a structured section plan using the fast model tier.

    `history` (already pruned, alternating, ending on an assistant turn) lets follow-ups such as
    "regenera el documento" be planned against what was produced before.
    Returns None when no valid plan could be produced; every failure is logged.
    """
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
    recent = list(history or [])[-PLAN_HISTORY_MESSAGES:]
    while recent and recent[0].role != "user":
        recent = recent[1:]
    messages = [
        AIMessage(role="system", content=planning_prompt),
        *recent,
        AIMessage(role="user", content=user_msg),
    ]
    model = getattr(provider, "default_model", "?")
    max_tokens = resolve_intent_max_tokens("plan_json")

    try:
        resp = await provider.complete(messages, max_tokens=max_tokens, response_format={"type": "json_object"})
        _add_usage(usage_sink, resp)
        plan = _parse_plan_json(resp.text)
        if plan:
            return plan
        logger.warning("Document plan from %s was not valid JSON; retrying once", model)
    except Exception as exc:
        logger.warning(
            "Document planning with %s failed; retrying without response_format: %s", model, exc, exc_info=True,
        )

    # 1 retry with explicit error guidance (and without response_format, which some models reject)
    try:
        retry_messages = messages + [
            AIMessage(role="assistant", content="{}"),
            AIMessage(role="user", content="El JSON anterior fue inválido. Genera solo el JSON estricto."),
        ]
        resp = await provider.complete(retry_messages, max_tokens=max_tokens)
        _add_usage(usage_sink, resp)
        plan = _parse_plan_json(resp.text)
        if not plan:
            logger.warning("Document plan retry from %s was not valid JSON; section generation skipped", model)
        return plan
    except Exception as exc:
        logger.warning(
            "Document planning retry with %s failed; section generation skipped: %s", model, exc, exc_info=True,
        )
        return None


def _section_user_message(sec: PlanSection, images: list[dict[str, Any]] | None) -> AIMessage:
    text = (
        f"Redacta ÚNICAMENTE la sección '{sec.title}'. "
        f"Instrucciones específicas: {sec.instructions}. "
        "No agregues etiquetas <artifact> ni <chat>, ni repitas el título general. "
        "Entrega directamente el contenido Markdown enriquecido de esta sección."
    )
    return user_message_with_images(text, images, skip_empty=True)


def pending_section_text(title: str) -> str:
    """Placeholder kept in the document for a section that could not be generated."""
    return (
        f"\n\n## {title}\n"
        f"_(Sección pendiente: no se pudo generar. Pide «completa la sección {title}» para reintentarla.)_\n"
    )


def _plan_event(plan: DocumentPlan) -> AgentEvent:
    return AgentEvent(
        type="plan",
        data={
            "title": plan.title,
            "extension": plan.extension.lstrip("."),
            "sections": [sec.title for sec in plan.sections],
        },
    )


def _shared_system_prompt(plan: DocumentPlan, system_prompt: str, context_block: str) -> str:
    titles = "; ".join(sec.title for sec in plan.sections)
    return f"{system_prompt}\n\nDOCUMENTO: {plan.title}\nSECCIONES DEL DOCUMENTO: {titles}\n\nCONTEXTO BASE:\n{context_block}"


def _section_status(index: int, sec: PlanSection, total: int, pending: bool) -> AgentEvent:
    return AgentEvent(
        type="status",
        data={
            "message": f"Sección {index + 1}/{total} lista",
            "stage": "section",
            "section_index": index,
            "section_title": sec.title,
            "pending": pending,
        },
    )


def _failure_note(failed: list[str]) -> str:
    """Trailing `<chat>` note naming the sections left pending."""
    names = ", ".join(f"«{t}»" for t in failed)
    noun = "la sección" if len(failed) == 1 else "las secciones"
    return (
        f"\n<chat>No pude generar {noun} {names}; quedaron marcadas como pendientes en el documento. "
        "Pídeme que las complete para reintentarlo.</chat>"
    )


class _SectionWriter:
    """Writes the sections of a plan concurrently, retrying each one and recording the failures."""

    def __init__(
        self,
        plan: DocumentPlan,
        shared_system: str,
        provider: AIProvider,
        concurrency: int,
        history: list[AIMessage],
        images: list[dict[str, Any]] | None,
        usage_sink: dict[str, Any] | None,
    ) -> None:
        self.provider = provider
        self.shared_system = shared_system
        self.history = history
        self.images = images
        self.usage_sink = usage_sink
        self.results: dict[int, str] = {}
        self.failed: list[str] = []
        self.ready = [asyncio.Event() for _ in plan.sections]
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._max_tokens = resolve_intent_max_tokens("section")
        self._model = getattr(provider, "default_model", "?")

    async def write(self, idx: int, sec: PlanSection) -> None:
        try:
            async with self._semaphore:
                # System prefix and history are identical for every section (cacheable);
                # only the final user turn varies.
                msgs = [
                    AIMessage(role="system", content=self.shared_system),
                    *self.history,
                    _section_user_message(sec, self.images),
                ]
                for attempt in range(1, SECTION_ATTEMPTS + 1):
                    body = await self._attempt(msgs, sec, attempt)
                    if body:
                        self.results[idx] = f"\n\n## {sec.title}\n{body}\n"
                        return
                self.failed.append(sec.title)
                self.results[idx] = pending_section_text(sec.title)
        finally:
            self.ready[idx].set()

    async def _attempt(self, msgs: list[AIMessage], sec: PlanSection, attempt: int) -> str:
        """Body text of one try; empty when the model fails or returns nothing."""
        try:
            res = await self.provider.complete(msgs, max_tokens=self._max_tokens)
            _add_usage(self.usage_sink, res)
            body = (res.text or "").strip()
            if not body:
                logger.warning("Section '%s' came back empty from %s (attempt %d)", sec.title, self._model, attempt)
            return body
        except Exception as exc:
            logger.warning(
                "Section '%s' failed with %s (attempt %d/%d): %s",
                sec.title, self._model, attempt, SECTION_ATTEMPTS, exc, exc_info=True,
            )
            return ""

    def text_for(self, idx: int, sec: PlanSection) -> str:
        return self.results.get(idx) or pending_section_text(sec.title)


async def _cancel_pending(tasks: list[asyncio.Task]) -> None:
    pending = [t for t in tasks if not t.done()]
    for t in pending:
        t.cancel()
    if pending:
        logger.info("Cancelled %d pending section task(s)", len(pending))
    await asyncio.gather(*tasks, return_exceptions=True)


async def generate_sections_stream(
    plan: DocumentPlan,
    system_prompt: str,
    context_block: str,
    main_provider: AIProvider,
    concurrency: int = 3,
    history: list[AIMessage] | None = None,
    images: list[dict[str, Any]] | None = None,
    usage_sink: dict[str, Any] | None = None,
) -> AsyncIterator[str | AgentEvent]:
    """Generate all sections in parallel and stream them in order.

    Yields text (chat intro, artifact markup, each section) and typed events: one `plan` event with
    the planned sections, then a `status` event per finished section. A section that fails twice is
    left marked as pending in the document and reported in a trailing `<chat>` note, never as an
    error message inside the document. Pending section tasks are cancelled if the consumer stops
    early (client disconnect or cancellation).
    """
    yield _plan_event(plan)

    chat_intro = plan.chat_intro or "He elaborado el documento estructurado por secciones."
    ext = plan.extension.lstrip(".")
    yield f"<chat>{chat_intro}</chat>\n<artifact title=\"{plan.title}\" extension=\"{ext}\">\n"

    shared_system = _shared_system_prompt(plan, system_prompt, context_block)
    writer = _SectionWriter(plan, shared_system, main_provider, concurrency, list(history or []), images, usage_sink)
    tasks = [asyncio.create_task(writer.write(i, sec)) for i, sec in enumerate(plan.sections)]
    try:
        # Stream out strictly in index order as each becomes ready
        for i, sec in enumerate(plan.sections):
            await writer.ready[i].wait()
            yield writer.text_for(i, sec)
            yield _section_status(i, sec, len(plan.sections), sec.title in writer.failed)

        yield "\n</artifact>"
        if writer.failed:
            if usage_sink is not None:
                usage_sink["failed_sections"] = list(writer.failed)
            yield _failure_note(writer.failed)
    finally:
        await _cancel_pending(tasks)
