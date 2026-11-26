"""Autonomous Agent execution loop using tool calling and typed events."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.ai.events import AgentEvent
from app.ai.providers.base import AIMessage, AIProvider, ToolCall
from app.ai.tools.registry import ToolContext, get_tool, get_tools_openai_schema
from app.ai.injection import prepare_untrusted
from app.ai.logging import log_security_event
from app.ai.untrusted import contains_envelope

logger = logging.getLogger(__name__)

TOOL_TIMEOUT_S = 30.0
TOOL_RESULT_MAX_CHARS = 8000
MAX_TOOL_CALLS_PER_TURN = 12


def _wrap_tool_output(name: str, output: str) -> str:
    """Delimit tool output as untrusted data (mitigates prompt injection from documents)."""
    return prepare_untrusted("tool", name, output, max_chars=TOOL_RESULT_MAX_CHARS)


def _has_untrusted_content(convo: list[AIMessage]) -> bool:
    """Whether any message of the conversation carries external content inside an envelope."""
    for message in convo:
        content = message.content
        parts = [content] if isinstance(content, str) else [p.get("text", "") for p in (content or []) if isinstance(p, dict)]
        if any(contains_envelope(part) for part in parts):
            return True
    return False


async def _exec_tool(tc: ToolCall, ctx: ToolContext, *, untrusted_present: bool = False) -> tuple[ToolCall, str, bool]:
    tool = get_tool(tc.name)
    if not tool:
        logger.warning("Model requested unknown tool %s", tc.name)
        return tc, f"[Error]: Herramienta '{tc.name}' no encontrada.", True
    if untrusted_present and tool.external_effect:
        logger.warning("Tool %s refused: it acts outside the conversation and the context has external content", tc.name)
        log_security_event("tool_call", user=ctx.user_id, provider="agent", tool=tc.name, decision="denied",
                           reason="external_effect_with_untrusted_context")
        return tc, (
            f"[Error]: La herramienta '{tc.name}' actúa fuera de la conversación y no puede ejecutarse "
            "mientras el contexto incluya contenido externo."
        ), True
    try:
        res = await asyncio.wait_for(tool.handler(tc.arguments, ctx), timeout=TOOL_TIMEOUT_S)
        text = str(res)
        return tc, text, text.startswith("[Error")
    except Exception as exc:  # tool errors go back to the model, not up the stack
        logger.warning("Tool %s failed: %s", tc.name, exc, exc_info=True)
        return tc, f"[Error al ejecutar {tc.name}]: {exc}", True


@dataclass
class _RunStats:
    """Usage totals and last-seen metadata accumulated across the model turns of one run."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    iterations: int = 0
    finish_reason: str | None = None
    fallback_used: bool = False
    ttft_ms: float | None = None

    def absorb(self, sink: dict[str, Any]) -> None:
        self.prompt_tokens += sink.get("prompt_tokens") or 0
        self.completion_tokens += sink.get("completion_tokens") or 0
        self.cached_tokens += sink.get("cached_tokens") or 0
        self.cost_usd += sink.get("cost_usd") or 0.0
        self.finish_reason = sink.get("finish_reason") or self.finish_reason
        self.fallback_used = self.fallback_used or bool(sink.get("fallback_used"))
        if self.ttft_ms is None and sink.get("ttft_ms") is not None:
            self.ttft_ms = sink["ttft_ms"]

    def event(self) -> AgentEvent:
        return AgentEvent(
            type="usage",
            data={
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "cached_tokens": self.cached_tokens,
                "cost_usd": self.cost_usd,
                "iterations": self.iterations,
                "finish_reason": self.finish_reason,
                "fallback_used": self.fallback_used,
                "ttft_ms": self.ttft_ms,
            },
        )


@dataclass
class _Turn:
    """What one streamed model turn produced: its text and the provider's usage sink."""

    text_parts: list[str] = field(default_factory=list)
    sink: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "".join(self.text_parts)

    @property
    def tool_calls(self) -> list[ToolCall]:
        return list(self.sink.get("tool_calls") or [])


async def _stream_turn(
    turn: _Turn, convo: list[AIMessage], provider: AIProvider, tools_schema: Any, max_tokens: int | None, is_last: bool
) -> AsyncIterator[AgentEvent]:
    """Stream one model turn, emitting text deltas and filling `turn`.

    Tools stay declared on the last turn: providers such as Anthropic reject conversations
    containing tool messages when no tools are declared.
    """
    async for delta in provider.complete_stream(
        convo,
        max_tokens=max_tokens,
        tools=tools_schema,
        tool_choice="none" if is_last else "auto",
        usage_sink=turn.sink,
    ):
        turn.text_parts.append(delta)
        yield AgentEvent(type="delta", data={"text": delta})


async def _run_tool_calls(
    tool_calls: list[ToolCall], ctx: ToolContext, convo: list[AIMessage], calls_made: int
) -> tuple[list[tuple[ToolCall, str, bool]], int]:
    """Run the calls that fit under the per-run cap; the rest get an error result instead.

    Returns the results of all calls and how many actually ran.
    """
    room = max(0, MAX_TOOL_CALLS_PER_TURN - calls_made)
    to_run, refused = tool_calls[:room], tool_calls[room:]
    untrusted_present = _has_untrusted_content(convo)
    results = list(await asyncio.gather(*[_exec_tool(tc, ctx, untrusted_present=untrusted_present) for tc in to_run]))
    limit_error = f"[Error]: Se alcanzó el límite de {MAX_TOOL_CALLS_PER_TURN} llamadas a herramientas en este turno."
    return results + [(tc, limit_error, True) for tc in refused], len(to_run)


def _tool_result_events(results: list[tuple[ToolCall, str, bool]], convo: list[AIMessage]) -> list[AgentEvent]:
    """Record each result in the conversation as untrusted data and return its event."""
    events = []
    for tc, output, is_err in results:
        events.append(AgentEvent(
            type="tool_result",
            data={"id": tc.id, "name": tc.name, "result": output[:500], "is_error": is_err},
        ))
        convo.append(AIMessage(role="tool", tool_call_id=tc.id, content=_wrap_tool_output(tc.name, output)))
    return events


def _artifact_events(artifacts: list[dict[str, Any]]) -> list[AgentEvent]:
    """Events delivering artifacts created by tools."""
    events = []
    for art in artifacts:
        header = {"title": art["title"], "extension": art["extension"]}
        events.append(AgentEvent(type="artifact_start", data=dict(header)))
        events.append(AgentEvent(type="artifact_delta", data={"text": art["content"]}))
        events.append(AgentEvent(type="artifact_end", data=dict(header)))
    return events


async def run_agent(
    messages: list[AIMessage],
    provider: AIProvider,
    ctx: ToolContext,
    max_iters: int = 8,
    max_tokens: int | None = None,
) -> AsyncIterator[AgentEvent]:
    """Execute the tool-calling loop over a fully assembled conversation.

    `messages` must already contain system prompt, documentary context, history and the
    current user turn (including images), so the agent sees the same context as the plain route.
    Each model turn is streamed: text deltas are emitted as they arrive and tool-call deltas are
    accumulated by the provider into complete calls when the turn ends.
    """
    tools_schema = get_tools_openai_schema()
    convo = list(messages)
    stats = _RunStats()
    tool_calls_made = 0
    delivered_artifacts = 0

    yield AgentEvent(type="status", data={"message": "Analizando la solicitud...", "stage": "agent"})

    for iteration in range(max(1, max_iters)):
        stats.iterations = iteration + 1
        turn = _Turn()
        async for event in _stream_turn(turn, convo, provider, tools_schema, max_tokens, iteration == max_iters - 1):
            yield event
        stats.absorb(turn.sink)

        tool_calls = turn.tool_calls
        if not tool_calls:
            break
        for tc in tool_calls:
            yield AgentEvent(type="tool_call", data={"id": tc.id, "name": tc.name, "arguments": tc.arguments})
        convo.append(AIMessage(role="assistant", content=turn.text, tool_calls=tool_calls))

        results, ran = await _run_tool_calls(tool_calls, ctx, convo, tool_calls_made)
        tool_calls_made += ran
        for event in _tool_result_events(results, convo):
            yield event
        for event in _artifact_events(ctx.artifacts[delivered_artifacts:]):
            yield event
        delivered_artifacts = len(ctx.artifacts)

    yield stats.event()
    yield AgentEvent(type="done", data={"ok": True})
