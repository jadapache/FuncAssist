"""Fast-model intent classification for chat messages the keyword rules cannot decide.

Only called for undecided messages that plausibly concern a document (see
`document_agent._needs_model_classification`), so ordinary chat pays no extra latency.
Results are cached per message (prompt + context), so retries and repeated messages are free.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from collections import OrderedDict
from dataclasses import dataclass

from app.ai.policies import resolve_intent_max_tokens
from app.ai.providers.base import AIMessage, AIProvider

logger = logging.getLogger(__name__)

_CACHE_MAX = 512
_cache: "OrderedDict[str, str]" = OrderedDict()

# Label returned by the model → intent. SEGUIMIENTO means "act on the current document".
_LABELS = {
    "CHAT": "chat",
    "PLAN": "generic_plan",
    "INFORME": "generic_report",
    "PLANTILLA": "template_mutation",
    "SEGUIMIENTO": "follow_up",
}
_LABEL_RE = re.compile(r"\b(" + "|".join(_LABELS) + r")\b", re.IGNORECASE)


@dataclass(frozen=True)
class IntentDecision:
    intent: str
    cached: bool


def classifier_enabled() -> bool:
    return os.getenv("AI_LLM_INTENT_CLASSIFIER", "on").strip().lower() not in ("0", "off", "false", "no")


def _timeout_s() -> float:
    try:
        return max(0.5, float(os.getenv("AI_INTENT_CLASSIFIER_TIMEOUT_S", "4")))
    except ValueError:
        return 4.0


def _cache_key(prompt: str, active_intent: str | None, has_template: bool) -> str:
    raw = f"{(prompt or '').strip().lower()}\x00{active_intent or ''}\x00{int(has_template)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clear_cache() -> None:
    _cache.clear()


def _system_prompt(active_intent: str | None, has_template: bool) -> str:
    options = [
        "CHAT: pregunta, conversación o explicación que se responde en el chat",
        "PLAN: pide elaborar un plan (de pruebas, de trabajo, de implementación) como documento",
        "INFORME: pide elaborar un informe, reporte o documento formal que no es un plan",
    ]
    if has_template:
        options.append("PLANTILLA: pide llenar o generar el documento de la plantilla corporativa activa")
    if active_intent:
        options.append(
            "SEGUIMIENTO: pide modificar, ampliar, corregir, completar o regenerar el documento ya generado en la conversación"
        )
    return (
        "Clasifica la intención del último mensaje de un usuario de un asistente de QA y documentación.\n"
        "Etiquetas posibles:\n- " + "\n- ".join(options) + "\n"
        "Responde ÚNICAMENTE con la etiqueta, sin explicación."
    )


def parse_label(text: str, *, active_intent: str | None, has_template: bool) -> str | None:
    """Map the model reply to an intent; None when it is not a valid label for this context."""
    match = _LABEL_RE.search(text or "")
    if not match:
        return None
    intent = _LABELS[match.group(1).upper()]
    if intent == "follow_up":
        return active_intent or None
    if intent == "template_mutation" and not has_template:
        return None
    return intent


async def classify_intent_with_model(
    prompt: str,
    *,
    provider: AIProvider,
    active_intent: str | None = None,
    has_template: bool = False,
) -> IntentDecision | None:
    """Ask the fast model for the intent. Returns None on timeout, error or an unusable reply."""
    key = _cache_key(prompt, active_intent, has_template)
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return IntentDecision(intent=hit, cached=True)

    messages = [
        AIMessage(role="system", content=_system_prompt(active_intent, has_template)),
        AIMessage(role="user", content=(prompt or "")[:2000]),
    ]
    try:
        completion = await asyncio.wait_for(
            provider.complete(messages, max_tokens=resolve_intent_max_tokens("classification")),
            timeout=_timeout_s(),
        )
    except Exception as exc:
        logger.warning(
            "Intent classification with %s failed; keeping the rule-based intent: %s",
            getattr(provider, "default_model", "?"), exc, exc_info=True,
        )
        return None

    intent = parse_label(completion.text, active_intent=active_intent, has_template=has_template)
    if intent is None:
        logger.warning("Intent classifier returned an unusable label: %r", (completion.text or "")[:80])
        return None
    _cache[key] = intent
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return IntentDecision(intent=intent, cached=False)
