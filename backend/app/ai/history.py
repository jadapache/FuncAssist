"""Conversation history: normalization into real turns, budget pruning and cached rolling summaries."""

from __future__ import annotations

import hashlib
import logging
import re
from collections import OrderedDict
from typing import Any, Protocol

from app.ai.budget import count_tokens
from app.ai.providers.base import AIMessage, AIProvider

logger = logging.getLogger(__name__)

KEEP_RECENT_MESSAGES = 6
MAX_HISTORY_MESSAGES = 60
SUMMARY_MAX_TOKENS = 500
_SUMMARY_CACHE_MAX = 256
_summary_cache: "OrderedDict[str, str]" = OrderedDict()

class SummaryStore(Protocol):
    """Durable storage for one rolling summary per conversation."""

    async def load(self) -> tuple[str, str] | None:
        """Return (summary_key, summary) or None."""

    async def save(self, summary_key: str, summary: str) -> None: ...


_ROLE_ALIASES = {
    "user": "user",
    "usuario": "user",
    "human": "user",
    "assistant": "assistant",
    "asistente": "assistant",
    "ai": "assistant",
    "bot": "assistant",
    "model": "assistant",
}
_ROLE_PREFIX = re.compile(r"^\s*(user|usuario|human|assistant|asistente|ai|bot|model)\s*:\s*", re.IGNORECASE)


def _normalize_role(role: Any) -> str | None:
    return _ROLE_ALIASES.get(str(role or "").strip().lower())


def _parse_prefixed_lines(lines: list[str]) -> list[dict[str, str]]:
    """Parse legacy `"role: content"` lines (as sent by the current frontend) into turns.

    Lines without a role prefix are continuation lines of the previous turn.
    """
    turns: list[dict[str, str]] = []
    for raw in lines:
        for line in str(raw).splitlines():
            match = _ROLE_PREFIX.match(line)
            if match:
                turns.append({"role": match.group(1), "content": line[match.end():]})
            elif turns:
                turns[-1]["content"] += "\n" + line
            elif line.strip():
                turns.append({"role": "user", "content": line})
    return turns


def format_history_as_messages(history: list[dict[str, Any]] | list[str] | str | None) -> list[AIMessage]:
    """Convert history input into alternating user/assistant AIMessages.

    Accepts structured turns (`[{role, content}]`), legacy `"role: content"` lines, or a raw string.
    Unknown roles (system/tool) are dropped, and consecutive turns of the same role are merged so
    providers that require strict alternation (Anthropic) accept the conversation.
    """
    messages: list[AIMessage] = []
    for item in _history_turns(history)[-MAX_HISTORY_MESSAGES:]:
        _append_turn(messages, _normalize_role(item.get("role")), item.get("content"))

    # History is followed by the current user turn, so it must not end on a user message.
    while messages and messages[-1].role == "user":
        messages.pop()
    return messages


def _history_turns(history: list[dict[str, Any]] | list[str] | str | None) -> list[Any]:
    """Raw `{role, content}` turns from any accepted history shape."""
    if not history:
        return []
    if isinstance(history, str):
        return _parse_prefixed_lines([history])
    if all(isinstance(item, str) for item in history):
        return _parse_prefixed_lines(list(history))  # type: ignore[arg-type]
    return [item for item in history if isinstance(item, dict)]


def _append_turn(messages: list[AIMessage], role: str | None, content: Any) -> None:
    """Add a turn, merging it into the previous one when the role repeats; skip unusable turns."""
    if not role or not isinstance(content, str) or not content.strip():
        return
    text = content.strip()
    if messages and messages[-1].role == role:
        messages[-1] = AIMessage(role=role, content=f"{messages[-1].content}\n\n{text}")
    else:
        messages.append(AIMessage(role=role, content=text))


def _summary_key(scope: str | None, older: list[AIMessage]) -> str:
    digest = hashlib.sha256()
    digest.update((scope or "").encode("utf-8"))
    for m in older:
        digest.update(m.role.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(str(m.content).encode("utf-8"))
        digest.update(b"\x01")
    return digest.hexdigest()


def _cache_get(key: str) -> str | None:
    value = _summary_cache.get(key)
    if value is not None:
        _summary_cache.move_to_end(key)
    return value


def _cache_put(key: str, value: str) -> None:
    _summary_cache[key] = value
    _summary_cache.move_to_end(key)
    while len(_summary_cache) > _SUMMARY_CACHE_MAX:
        _summary_cache.popitem(last=False)


def _encode_store_key(covered: int, digest: str) -> str:
    return f"{covered}:{digest}"


def _decode_store_key(raw: str) -> tuple[int, str] | None:
    count, sep, digest = (raw or "").partition(":")
    if not sep or not count.isdigit() or not digest:
        return None
    return int(count), digest


async def _summarize_older(
    older: list[AIMessage],
    *,
    scope: str | None,
    fast_provider: AIProvider | None,
    store: SummaryStore | None,
) -> str | None:
    """Summary covering `older`, reusing cached/persisted work where possible.

    Lookup order: in-process cache → persisted summary of the same prefix → incremental update
    of a persisted summary that covers a shorter prefix (only the new turns are sent) → full run.
    """
    full_digest = _summary_key(scope, older)
    cached = _cache_get(full_digest)
    if cached is not None:
        return cached

    covered, previous = await _load_persisted_summary(store, scope, older)
    if previous is not None and covered == len(older):
        _cache_put(full_digest, previous)
        return previous
    if fast_provider is None:
        return previous

    summary = await _request_summary(fast_provider, previous, older[covered:])
    if not summary:
        return previous
    _cache_put(full_digest, summary)
    await _persist_summary(store, _encode_store_key(len(older), full_digest), summary)
    return summary


async def _load_persisted_summary(
    store: SummaryStore | None, scope: str | None, older: list[AIMessage]
) -> tuple[int, str | None]:
    """(turns covered, summary) of the persisted summary when it covers a prefix of `older`."""
    if store is None:
        return 0, None
    try:
        record = await store.load()
    except Exception as exc:
        logger.warning("Could not load persisted history summary: %s", exc, exc_info=True)
        return 0, None
    decoded = _decode_store_key(record[0]) if record else None
    if decoded and 0 < decoded[0] <= len(older) and _summary_key(scope, older[: decoded[0]]) == decoded[1]:
        return decoded[0], record[1]
    return 0, None


def _summary_prompt(previous: str | None, new_turns: list[AIMessage]) -> tuple[str, str]:
    """(system, user) prompt that summarizes `new_turns`, updating `previous` when there is one."""
    turns_text = "\n".join(f"{m.role}: {m.content}" for m in new_turns)
    if previous:
        system = (
            "Actualiza el resumen de una conversación incorporando los nuevos turnos. Conserva acuerdos, "
            "decisiones, datos y temas pendientes; elimina lo que quedó resuelto o superado. No inventes información."
        )
        return system, f"RESUMEN ACTUAL:\n{previous}\n\nNUEVOS TURNOS:\n{turns_text}"
    system = (
        "Resume de forma concisa los acuerdos, decisiones, datos y temas pendientes "
        "de esta conversación previa. No inventes información."
    )
    return system, turns_text


async def _request_summary(provider: AIProvider, previous: str | None, new_turns: list[AIMessage]) -> str:
    """Summary text from the model; empty when the call fails or returns nothing."""
    system, user = _summary_prompt(previous, new_turns)
    try:
        res = await provider.complete(
            [AIMessage(role="system", content=system), AIMessage(role="user", content=user)],
            max_tokens=SUMMARY_MAX_TOKENS,
        )
    except Exception as exc:
        logger.warning(
            "History summarization failed with model %s; older turns are dropped without a summary: %s",
            getattr(provider, "default_model", "?"), exc, exc_info=True,
        )
        return ""
    return (res.text or "").strip()


async def _persist_summary(store: SummaryStore | None, key: str, summary: str) -> None:
    if store is None:
        return
    try:
        await store.save(key, summary)
    except Exception as exc:
        logger.warning("Could not persist history summary: %s", exc, exc_info=True)


def _recent_window(messages: list[AIMessage], max_tokens_budget: int, model: str) -> list[AIMessage]:
    """Latest turns kept verbatim: they start on a user turn and fit the budget."""
    recent = messages[-KEEP_RECENT_MESSAGES:]
    # Start the verbatim window on a user turn so alternation survives the summary.
    while recent and recent[0].role != "user":
        recent = recent[1:]
    # Recent turns alone may still exceed the budget: drop oldest pairs until they fit.
    while len(recent) > 2 and count_tokens(model, [m.to_litellm() for m in recent]) > max_tokens_budget:
        recent = recent[2:]
    return recent


async def prune_or_summarize_history(
    messages: list[AIMessage],
    max_tokens_budget: int,
    model: str,
    fast_provider: AIProvider | None = None,
    scope: str | None = None,
    store: SummaryStore | None = None,
) -> list[AIMessage]:
    """Keep recent turns verbatim within budget; replace older turns with a rolling summary.

    `scope` (e.g. the conversation id) namespaces summaries so identical prefixes in different
    conversations never share one. `store` persists the summary across requests and processes.
    """
    if not messages:
        return []

    if count_tokens(model, [m.to_litellm() for m in messages]) <= max_tokens_budget or len(messages) <= 2:
        return messages

    recent = _recent_window(messages, max_tokens_budget, model)
    older = messages[: len(messages) - len(recent)]

    summary_text = (
        await _summarize_older(older, scope=scope, fast_provider=fast_provider, store=store) if older else None
    )
    if not summary_text:
        return recent

    # Delivered as a user/assistant pair so it fits between the context and the recent turns
    # without breaking alternation or injecting a mid-conversation system message.
    return [
        AIMessage(role="user", content=f"[Resumen de la conversación previa]\n{summary_text}"),
        AIMessage(role="assistant", content="Entendido, tengo en cuenta ese contexto."),
        *recent,
    ]
