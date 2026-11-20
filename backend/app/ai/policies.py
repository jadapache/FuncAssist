"""Policies for token budgeting, intent max_tokens and model tiers."""

from __future__ import annotations

INTENT_MAX_TOKENS = {
    "chat": 1500,
    "qna": 1500,
    "classification": 800,
    "plan_json": 800,
    "section": 2500,
    "generic_plan": 8192,
    "generic_report": 8192,
    "template_mutation": 8192,
    "legacy_artifact": 8192,
}


def resolve_intent_max_tokens(intent: str | None, default_tokens: int = 1500) -> int:
    """Resolve recommended max_tokens based on intent."""
    if not intent:
        return default_tokens
    return INTENT_MAX_TOKENS.get(intent.strip().lower(), default_tokens)
