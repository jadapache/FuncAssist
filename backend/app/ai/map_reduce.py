"""Map-reduce chunking and context budget utilities for LLM input protection."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import List

from app.ai.policies import resolve_intent_max_tokens
from app.ai.providers.base import AIMessage, AIProvider

logger = logging.getLogger(__name__)


def resolve_input_character_budget(provider_id: str) -> int:
    """Safe character budget for full prompt input to prevent ITPM errors."""
    prov = (provider_id or "").strip().lower()
    if prov in ("gemini", "google"):
        return 800_000
    if prov in ("openai", "claude"):
        return 200_000
    if prov == "groq":
        # ~14,000 chars ≈ 3,500 tokens. Far below Groq 6k-8k ITPM ceiling.
        return 14_000
    return 15_000


class _Chunker:
    """Accumulates pieces into chunks no longer than `max_chars`."""

    def __init__(self, max_chars: int) -> None:
        self.max_chars = max_chars
        self.chunks: list[str] = []
        self._parts: list[str] = []
        self._length = 0

    def fits(self, size: int) -> bool:
        return self._length + size <= self.max_chars

    def add(self, piece: str, size: int) -> None:
        self._parts.append(piece)
        self._length += size

    def flush(self, separator: str) -> None:
        if self._parts:
            self.chunks.append(separator.join(self._parts))
            self._parts.clear()
            self._length = 0


def _add_sentences(chunker: _Chunker, paragraph: str) -> None:
    for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
        size = len(sentence) + 1
        if not chunker.fits(size):
            chunker.flush(" ")
        chunker.add(sentence, size)


def _add_paragraph(chunker: _Chunker, paragraph: str) -> None:
    size = len(paragraph) + 2
    if not chunker.fits(size):
        chunker.flush("\n\n")
        if size > chunker.max_chars:
            _add_sentences(chunker, paragraph)
            return
    chunker.add(paragraph, size)


def split_text_into_chunks(text: str, max_chars: int = 12_000, overlap: int = 400) -> List[str]:
    """Splits long text on paragraph/sentence boundaries within character limit."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    chunker = _Chunker(max_chars)
    for paragraph in cleaned.split("\n\n"):
        _add_paragraph(chunker, paragraph)
    chunker.flush("\n\n")
    return chunker.chunks


_MAP_PROMPT_TEMPLATE = (
    "Eres un analista técnico. Extrae de forma concisa y estructurada todos los acuerdos, "
    "requerimientos, decisiones, roles y datos clave de este fragmento para: {goal}. "
    "Mantén nombres técnicos, parámetros y definiciones sin omitir nada crítico."
)
_REDUCE_PROMPT_TEMPLATE = (
    "Sintetiza estos hallazgos consolidados en un documento técnico unificado "
    "que no exceda {budget} caracteres, preservando todo el detalle relevante."
)


def _map_concurrency(provider: AIProvider) -> int:
    default = 2 if getattr(provider, "id", "") == "groq" else 4
    return int(os.getenv("AI_MAP_CONCURRENCY", str(default)))


async def _map_chunk(
    provider: AIProvider, semaphore: asyncio.Semaphore, map_prompt: str, idx: int, total: int, chunk: str
) -> str:
    """Summarize one chunk; fall back to an excerpt when the model fails or returns nothing."""
    async with semaphore:
        messages = [
            AIMessage(role="system", content=map_prompt),
            AIMessage(role="user", content=f"[PARTE {idx + 1} DE {total}]:\n{chunk}"),
        ]
        try:
            res = await provider.complete(messages, max_tokens=resolve_intent_max_tokens("map_chunk"))
            summary = res.text.strip()
            if summary:
                return f"--- Hallazgos Parte {idx + 1} ---\n{summary}"
            logger.warning("Map-reduce chunk %d/%d returned an empty summary; using an excerpt", idx + 1, total)
        except Exception as exc:
            model = getattr(provider, "default_model", "?")
            logger.warning(
                "Map-reduce chunk %d/%d failed with model %s; using an excerpt: %s",
                idx + 1, total, model, exc, exc_info=True,
            )
        return f"--- Extracto Parte {idx + 1} ---\n{chunk[:1200]}"


async def _reduce(provider: AIProvider, combined_map: str, target_budget: int) -> str:
    """Final synthesis of the mapped summaries; truncates them when the model fails or is empty."""
    messages = [
        AIMessage(role="system", content=_REDUCE_PROMPT_TEMPLATE.format(budget=target_budget)),
        AIMessage(role="user", content=combined_map),
    ]
    try:
        reduce_res = await provider.complete(messages, max_tokens=resolve_intent_max_tokens("reduce"))
        return reduce_res.text.strip() or combined_map[:target_budget]
    except Exception as exc:
        logger.warning(
            "Map-reduce final synthesis failed with model %s; truncating the combined summaries: %s",
            getattr(provider, "default_model", "?"), exc, exc_info=True,
        )
        return combined_map[:target_budget]


async def map_reduce_condense_context(
    text: str,
    target_budget: int,
    provider: AIProvider,
    feature_goal: str = "Resumen de requisitos técnicos y funcionales",
) -> str:
    """Condenses oversized text via map-reduce summarization under target budget."""
    if not text:
        return text

    raw_chunks = split_text_into_chunks(text, max_chars=min(target_budget, 10_000))
    if len(raw_chunks) <= 1:
        return text[:target_budget]

    map_prompt = _MAP_PROMPT_TEMPLATE.format(goal=feature_goal)
    semaphore = asyncio.Semaphore(_map_concurrency(provider))
    total = len(raw_chunks)
    mapped = await asyncio.gather(
        *(_map_chunk(provider, semaphore, map_prompt, idx, total, chunk) for idx, chunk in enumerate(raw_chunks))
    )

    combined_map = "\n\n".join(mapped)
    if len(combined_map) <= target_budget:
        return combined_map
    return await _reduce(provider, combined_map, target_budget)
