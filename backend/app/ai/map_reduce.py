"""Map-reduce chunking and context budget utilities for LLM input protection."""

from __future__ import annotations

import re
from typing import Any, List, Optional

from app.ai.providers.base import AIMessage, AIProvider


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


def split_text_into_chunks(text: str, max_chars: int = 12_000, overlap: int = 400) -> List[str]:
    """Splits long text on paragraph/sentence boundaries within character limit."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    paragraphs = cleaned.split("\n\n")
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        p_len = len(para) + 2
        if current_len + p_len <= max_chars:
            current_parts.append(para)
            current_len += p_len
        else:
            if current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts.clear()
                current_len = 0
            if p_len <= max_chars:
                current_parts.append(para)
                current_len = p_len
            else:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                for sent in sentences:
                    s_len = len(sent) + 1
                    if current_len + s_len <= max_chars:
                        current_parts.append(sent)
                        current_len += s_len
                    else:
                        if current_parts:
                            chunks.append(" ".join(current_parts))
                            current_parts.clear()
                            current_len = 0
                        current_parts.append(sent)
                        current_len = s_len

    if current_parts:
        chunks.append("\n\n".join(current_parts))
    return chunks


async def map_reduce_condense_context(
    text: str,
    target_budget: int,
    provider: AIProvider,
    feature_goal: str = "Resumen de requisitos técnicos y funcionales",
) -> str:
    """Condenses oversized text via map-reduce summarization under target budget."""
    if not text or len(text) <= target_budget:
        return text

    # Step 1 (MAP): Split oversized text and extract key functional points from each chunk
    chunk_limit = min(target_budget, 10_000)
    raw_chunks = split_text_into_chunks(text, max_chars=chunk_limit)
    if len(raw_chunks) <= 1:
        return text[:target_budget]

    mapped_summaries: list[str] = []
    map_prompt = (
        f"Eres un analista técnico. Extrae de forma concisa y estructurada todos los acuerdos, "
        f"requerimientos, decisiones, roles y datos clave de este fragmento para: {feature_goal}. "
        f"Mantén nombres técnicos, parámetros y definiciones sin omitir nada crítico."
    )

    for idx, c in enumerate(raw_chunks):
        messages = [
            AIMessage(role="system", content=map_prompt),
            AIMessage(role="user", content=f"[PARTE {idx + 1} DE {len(raw_chunks)}]:\n{c}"),
        ]
        try:
            res = await provider.complete(messages, max_tokens=1000)
            summary_txt = res.text.strip()
            if summary_txt:
                mapped_summaries.append(f"--- Hallazgos Parte {idx + 1} ---\n{summary_txt}")
        except Exception:
            # Fallback if map completion fails: truncate chunk cleanly
            mapped_summaries.append(f"--- Extracto Parte {idx + 1} ---\n{c[:1200]}")

    combined_map = "\n\n".join(mapped_summaries)
    if len(combined_map) <= target_budget:
        return combined_map

    # Step 2 (REDUCE): If still exceeding budget, perform final synthesis
    reduce_prompt = (
        f"Sintetiza estos hallazgos consolidados en un documento técnico unificado "
        f"que no exceda {target_budget} caracteres, preservando todo el detalle relevante."
    )
    messages = [
        AIMessage(role="system", content=reduce_prompt),
        AIMessage(role="user", content=combined_map),
    ]
    try:
        reduce_res = await provider.complete(messages, max_tokens=1500)
        final_txt = reduce_res.text.strip()
        return final_txt if final_txt else combined_map[:target_budget]
    except Exception:
        return combined_map[:target_budget]
