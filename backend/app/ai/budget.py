"""Token-based input budgets from the model catalog, LiteLLM metadata and provider rate limits."""

from __future__ import annotations

import logging
from typing import Any

import litellm
from litellm import token_counter

from app.ai.catalog import load_local_catalog
from app.ai.providers.registry import find_provider_spec

logger = logging.getLogger(__name__)

SAFETY_MARGIN_TOKENS = 1_000
DEFAULT_CHARS_PER_TOKEN = 4.0

# Per-request input ceilings imposed by rate limits (tokens per minute), not by the context window.
# Groq's free tier ITPM (~6k) is far below the model's context window.
_PROVIDER_ITPM_CEILING = {
    "groq": 6_000,
}

_PROVIDER_DEFAULT_WINDOW = {
    "gemini": 1_000_000,
    "google": 1_000_000,
    "claude": 200_000,
    "anthropic": 200_000,
    "openai": 128_000,
    "deepseek": 64_000,
    "openrouter": 32_000,
    "groq": 8_192,
}

_PROVIDER_DEFAULT_OUTPUT = {
    "groq": 4_096,
}


def count_tokens(model: str, messages: list[dict[str, Any]] | str) -> int:
    """Count tokens with litellm's tokenizer; fall back to ~4 chars/token."""
    try:
        if isinstance(messages, str):
            return token_counter(model=model, text=messages)
        return token_counter(model=model, messages=messages)
    except Exception:
        if isinstance(messages, str):
            return max(1, len(messages) // 4)
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        return max(1, total_chars // 4)


def chars_per_token(model: str, sample: str) -> float:
    """Measured character/token ratio for `sample` (used to translate token budgets to chars)."""
    if not sample:
        return DEFAULT_CHARS_PER_TOKEN
    probe = sample[:20_000]
    tokens = count_tokens(model, probe)
    return max(1.0, len(probe) / max(1, tokens))


def _model_info(provider: str, model: str) -> dict[str, Any] | None:
    """LiteLLM metadata, trying the bare name and the provider-prefixed name."""
    spec = find_provider_spec(provider)
    candidates = [model]
    if spec and spec.litellm_prefix and not model.startswith(f"{spec.litellm_prefix}/"):
        candidates.append(f"{spec.litellm_prefix}/{model}")
    for candidate in candidates:
        try:
            info = litellm.get_model_info(candidate)
            if info:
                return dict(info)
        except Exception:
            continue
    return None


def context_window(provider: str, model: str) -> int:
    """Model context window: catalog → LiteLLM metadata → provider default."""
    p_norm = (provider or "").strip().lower()
    m_norm = (model or "").strip().lower()

    try:
        for item in load_local_catalog():
            if item.id.lower() == m_norm or (getattr(item, "raw_id", "") or "").lower() == m_norm:
                if getattr(item, "context_length", None):
                    return int(item.context_length)
    except Exception as exc:
        logger.debug("Catalog lookup failed for %s: %s", model, exc)

    info = _model_info(p_norm, model)
    if info:
        for key in ("max_input_tokens", "max_tokens"):
            if info.get(key):
                return int(info[key])

    return _PROVIDER_DEFAULT_WINDOW.get(p_norm, 16_384)


def max_output(provider: str, model: str) -> int:
    """Max output tokens: LiteLLM metadata → registry default → provider default."""
    p_norm = (provider or "").strip().lower()
    info = _model_info(p_norm, model)
    if info and info.get("max_output_tokens"):
        return int(info["max_output_tokens"])
    spec = find_provider_spec(p_norm)
    if spec and spec.default_max_tokens:
        return int(spec.default_max_tokens)
    return _PROVIDER_DEFAULT_OUTPUT.get(p_norm, 8_192)


def calculate_input_budget(provider: str, model: str, reserved_output: int | None = None) -> int:
    """Input tokens available for one request.

    budget = min(context_window - reserved_output, itpm_ceiling) - margin

    `reserved_output` should be the request's actual max_tokens; it defaults to the model maximum.
    """
    p_norm = (provider or "").strip().lower()
    window = context_window(p_norm, model)
    output = reserved_output if reserved_output is not None else max_output(p_norm, model)
    output = min(output, max(0, window // 2))  # never let output reservation eat the whole window
    budget = window - output
    ceiling = _PROVIDER_ITPM_CEILING.get(p_norm)
    if ceiling:
        budget = min(budget, ceiling)
    return max(1_500, budget - SAFETY_MARGIN_TOKENS)
