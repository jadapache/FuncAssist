"""Policies for token budgeting, intent max_tokens and model tiers."""

from __future__ import annotations

# Requested output ceilings per intent. The effective value is further capped per model by
# `registry.resolve_model_max_tokens`, so these only need to be generous enough for the task.
INTENT_MAX_TOKENS = {
    # Conversational turns may still contain long Markdown (a user can ask for a document in a
    # chat turn); 1500 cut those answers mid-table.
    "chat": 4096,
    "qna": 4096,
    "ask_product": 4096,
    "classification": 800,
    "plan_json": 800,
    "section": 2500,
    "summary": 500,
    "map_chunk": 1000,
    "reduce": 1500,
    "transcript_summary": 4096,
    "generic_plan": 8192,
    "generic_report": 8192,
    "template_mutation": 8192,
    "legacy_artifact": 8192,
    # Grounded feature flows (templates/rubrics) produce full documents.
    "grounded": 8192,
}

# How many times a truncated answer is continued automatically.
INTENT_MAX_CONTINUATIONS = {
    "chat": 1,
    "qna": 1,
    "ask_product": 1,
}
DEFAULT_MAX_CONTINUATIONS = 2


def resolve_intent_max_tokens(intent: str | None, default_tokens: int = 4096) -> int:
    """Resolve recommended max_tokens based on intent."""
    if not intent:
        return default_tokens
    return INTENT_MAX_TOKENS.get(intent.strip().lower(), default_tokens)


def resolve_feature_max_tokens(feature: str | None) -> int:
    """Output ceiling for a grounded feature: its own entry if any, else the grounded default."""
    key = (feature or "").strip().lower()
    return INTENT_MAX_TOKENS.get(key, INTENT_MAX_TOKENS["grounded"])


def resolve_max_continuations(intent: str | None) -> int:
    return INTENT_MAX_CONTINUATIONS.get((intent or "").strip().lower(), DEFAULT_MAX_CONTINUATIONS)
