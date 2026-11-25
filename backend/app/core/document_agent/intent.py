"""Rule-based intent of a chat message: what the user wants done with the conversation's document."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


ARTIFACT_INTENTS = frozenset({"generic_plan", "generic_report", "template_mutation"})

# Follow-ups that ask to (re)produce the document already open in the conversation. Matched only
# when there is an active artifact, so they never turn an ordinary chat message into a document.
_ARTIFACT_FOLLOW_UP_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bregener",                                              # regenera, regenerar, regenéralo
        r"\bvuelve a (generar|hacer|crear|redactar|escribir)",
        r"\b(gen[eé]ralo|gen[eé]rala|hazlo|hazla|cr[eé]alo|red[aá]ctalo)\s+(de nuevo|otra vez)",
        r"\brehaz|\brehacer",
        r"\b(est[aá]|qued[oó]|sali[oó]|vino|lleg[oó]|aparece)\s+(vac[ií][oa]|en blanco|incomplet[oa]|cortad[oa]|truncad[oa])",
        r"\b(documento|artefacto|archivo|plan|informe)\s+(vac[ií]o|en blanco|incompleto|cortado|truncado)",
        r"\b(no tiene|sin) contenido",
        r"\bcompl[eé]t(alo|ala|alos|alas)\b",
        r"\bcompleta\s+(el|la|las|los)\s+(documento|artefacto|plan|informe|reporte|plantilla|secci[oó]n|secciones)",
        r"\btermina\s+(el|la)\s+(documento|artefacto|plan|informe|reporte|secci[oó]n)",
        r"\bcorrige\s+(el|la)\s+(documento|artefacto|plan|informe|reporte|plantilla)",
        r"\bcontin[uú]a\s+(con\s+)?(el|la)\s+(documento|artefacto|plan|informe|reporte|secci[oó]n)",
        r"\bfalta(n)?\s+(secciones|contenido|el contenido|partes)",
    )
]


def is_artifact_follow_up(prompt: str) -> bool:
    """Whether the message asks to regenerate, complete or fix the current document."""
    text = (prompt or "").strip()
    return bool(text) and any(p.search(text) for p in _ARTIFACT_FOLLOW_UP_PATTERNS)


def infer_active_artifact_intent(artifacts: List[Dict[str, Any]] | None, template_id: Optional[str] = None, has_current_document: bool = False) -> Optional[str]:
    """Intent that produced the conversation's active (latest) artifact, or None without one."""
    if artifacts:
        latest = artifacts[-1]
        stored = str(latest.get("intent") or "")
        if stored in ARTIFACT_INTENTS:
            return stored
        if template_id:
            return "template_mutation"
        title = str(latest.get("title") or "").lower()
        if "plan" in title:
            return "generic_plan"
        return "generic_report"
    if has_current_document:
        return "template_mutation" if template_id else "generic_report"
    return None


def classify_prompt_intent(
    prompt: str,
    mode: Optional[str] = None,
    template_id: Optional[str] = None,
    active_artifact_intent: Optional[str] = None,
) -> str:
    """Classifies user prompt intent into: generic_plan, generic_report, custom feature slug, template_mutation, or chat.

    `active_artifact_intent` is the intent of the conversation's current document, if any: a
    follow-up such as "regenera" or "el documento está vacío" then keeps that intent, even when
    phrased as a question, instead of falling into conversational chat.
    """
    return classify_prompt_intent_by_rules(prompt, mode, template_id, active_artifact_intent)[0]


_QUESTION_STARTS = (
    "¿", "que ", "qué ", "como ", "cómo ", "cual ", "cuál ", "por que", "por qué", "donde ", "dónde ",
    "explica", "cuéntame", "dime",
)


def looks_like_question(text_lower: str) -> bool:
    return text_lower.startswith(_QUESTION_STARTS) or "?" in text_lower


_MODE_INTENTS = {
    "plan": "generic_plan", "generic_plan": "generic_plan",
    "report": "generic_report", "informe": "generic_report", "generic_report": "generic_report",
    "chat": "chat", "qa": "chat",
    "template": "template_mutation", "template_mutation": "template_mutation",
}
_COMMAND_INTENTS = {
    "plan": "generic_plan", "generic_plan": "generic_plan",
    "report": "generic_report", "informe": "generic_report", "generic_report": "generic_report",
    "plantilla": "template_mutation", "template": "template_mutation", "template_mutation": "template_mutation",
    "pregunta": "ask_product", "question": "ask_product", "ask": "ask_product",
}
_PLAN_PHRASES = (
    "plan de prueba", "plan de implementaci", "plan de trabajo", "genera un plan", "crea un plan", "elabora un plan",
)
_REPORT_PHRASES = ("informe", "reporte", "resumen ejecutivo")
_TEMPLATE_PHRASES = (
    "completa la plantilla",
    "llena la plantilla",
    "genera el documento de mejora",
    "genera el documento funcional",
    "genera el levantamiento",
    "genera el inventario",
    "redacta el documento corporativo",
    "actualiza la plantilla",
    "generar artefacto",
    "genera el artefacto",
    "genera artefacto",
    "crear artefacto",
    "crea el artefacto",
    "generar documento",
    "genera el documento",
    "genera documento",
    "crear documento",
    "crea el documento",
    "redacta el documento",
    "elabora el documento",
    "regenera y completa",
    "regenera el documento",
    "regenerar documento",
    "regenerar el documento",
)


def _command_intent(prompt: str) -> Optional[str]:
    """Intent named by a leading "/command", the command itself when it is not a known one."""
    first_token = prompt.split()[0][1:].lower()
    return _COMMAND_INTENTS.get(first_token, first_token) or None


def _explicit_intent(p_trimmed: str, mode: Optional[str]) -> Optional[str]:
    """The intent the client asked for with a mode or a "/command", if it did."""
    if mode and mode not in {"auto", "default"}:
        return _MODE_INTENTS.get(mode, mode)
    return _command_intent(p_trimmed) if p_trimmed.startswith("/") else None


def _keyword_intent(p_lower: str) -> Optional[str]:
    for intent, phrases in (
        ("generic_plan", _PLAN_PHRASES),
        ("generic_report", _REPORT_PHRASES),
        ("template_mutation", _TEMPLATE_PHRASES),
    ):
        if any(phrase in p_lower for phrase in phrases):
            return intent
    return None


def classify_prompt_intent_by_rules(
    prompt: str,
    mode: Optional[str] = None,
    template_id: Optional[str] = None,
    active_artifact_intent: Optional[str] = None,
) -> tuple[str, bool]:
    """Rule-based intent plus whether a rule actually decided it.

    Undecided (False): the message fell through every rule to the default "chat", or it is a
    question while a document is active (it may ask to change that document).
    """
    p_trimmed = prompt.strip()
    explicit = _explicit_intent(p_trimmed, mode)
    if explicit:
        return explicit, True

    if active_artifact_intent in ARTIFACT_INTENTS and is_artifact_follow_up(p_trimmed):
        return active_artifact_intent, True

    p_lower = p_trimmed.lower()

    # Conversational inquiries and questions should always route to conversational chat
    if looks_like_question(p_lower):
        return "chat", active_artifact_intent not in ARTIFACT_INTENTS

    # If the user has an active corporate template selected and isn't asking a general question,
    # default to mutating/populating that template artifact directly.
    if template_id and template_id.strip():
        return "template_mutation", True

    keyword_intent = _keyword_intent(p_lower)
    return (keyword_intent, True) if keyword_intent else ("chat", False)


# Undecided messages are sent to the fast model only when they plausibly concern a document, so
# small talk ("gracias", "hola") never pays the extra call.
_DOCUMENT_HINT = re.compile(
    r"\b(documento|doc|plan|informe|reporte|plantilla|matriz|acta|especificaci[oó]n|secci[oó]n|"
    r"artefacto|formato|casos de prueba|requerimientos?|entregable|word|excel|docx|xlsx)\b",
    re.IGNORECASE,
)


def needs_model_classification(prompt: str, decided: bool, active_artifact_intent: Optional[str]) -> bool:
    if decided:
        return False
    return active_artifact_intent in ARTIFACT_INTENTS or bool(_DOCUMENT_HINT.search(prompt or ""))

