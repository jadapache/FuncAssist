"""Autonomous Agent execution loop using tool calling and typed events."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from app.ai.events import AgentEvent
from app.ai.providers.base import AIMessage, AIProvider, ToolCall
from app.ai.tools.registry import ToolContext, get_tool, get_tools_openai_schema
from app.ai.untrusted import wrap_untrusted

logger = logging.getLogger(__name__)

TOOL_TIMEOUT_S = 30.0
TOOL_RESULT_MAX_CHARS = 8000


def _wrap_tool_output(name: str, output: str) -> str:
    """Delimit tool output as untrusted data (mitigates prompt injection from documents)."""
    return wrap_untrusted("tool", name, output, max_chars=TOOL_RESULT_MAX_CHARS)


async def _exec_tool(tc: ToolCall, ctx: ToolContext) -> tuple[ToolCall, str, bool]:
    tool = get_tool(tc.name)
    if not tool:
        logger.warning("Model requested unknown tool %s", tc.name)
        return tc, f"[Error]: Herramienta '{tc.name}' no encontrada.", True
    try:
        res = await asyncio.wait_for(tool.handler(tc.arguments, ctx), timeout=TOOL_TIMEOUT_S)
        text = str(res)
        return tc, text, text.startswith("[Error")
    except Exception as exc:  # tool errors go back to the model, not up the stack
        logger.warning("Tool %s failed: %s", tc.name, exc, exc_info=True)
        return tc, f"[Error al ejecutar {tc.name}]: {exc}", True


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

    yield AgentEvent(type="status", data={"message": "Analizando la solicitud...", "stage": "agent"})

    totals: dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cached_tokens": 0,
        "cost_usd": 0.0,
    }
    iterations = 0
    delivered_artifacts = 0
    last_finish_reason: str | None = None
    fallback_used = False
    ttft_ms: float | None = None

    for iteration in range(max(1, max_iters)):
        iterations = iteration + 1
        is_last = iteration == max_iters - 1

        # Tools stay declared on the last turn: providers such as Anthropic reject
        # conversations containing tool messages when no tools are declared.
        sink: dict[str, Any] = {}
        text_parts: list[str] = []
        async for delta in provider.complete_stream(
            convo,
            max_tokens=max_tokens,
            tools=tools_schema,
            tool_choice="none" if is_last else "auto",
            usage_sink=sink,
        ):
            text_parts.append(delta)
            yield AgentEvent(type="delta", data={"text": delta})

        for key in ("prompt_tokens", "completion_tokens", "cached_tokens"):
            totals[key] += sink.get(key) or 0
        totals["cost_usd"] += sink.get("cost_usd") or 0.0
        last_finish_reason = sink.get("finish_reason") or last_finish_reason
        fallback_used = fallback_used or bool(sink.get("fallback_used"))
        if ttft_ms is None and sink.get("ttft_ms") is not None:
            ttft_ms = sink["ttft_ms"]

        text = "".join(text_parts)
        tool_calls: list[ToolCall] = list(sink.get("tool_calls") or [])
        if not tool_calls:
            break

        for tc in tool_calls:
            yield AgentEvent(type="tool_call", data={"id": tc.id, "name": tc.name, "arguments": tc.arguments})

        convo.append(AIMessage(role="assistant", content=text, tool_calls=tool_calls))

        results = await asyncio.gather(*[_exec_tool(tc, ctx) for tc in tool_calls])

        for tc, output, is_err in results:
            yield AgentEvent(
                type="tool_result",
                data={"id": tc.id, "name": tc.name, "result": output[:500], "is_error": is_err},
            )
            convo.append(AIMessage(role="tool", tool_call_id=tc.id, content=_wrap_tool_output(tc.name, output)))

        # Deliver artifacts created by tools in this iteration.
        for art in ctx.artifacts[delivered_artifacts:]:
            yield AgentEvent(type="artifact_start", data={"title": art["title"], "extension": art["extension"]})
            yield AgentEvent(type="artifact_delta", data={"text": art["content"]})
            yield AgentEvent(type="artifact_end", data={"title": art["title"], "extension": art["extension"]})
        delivered_artifacts = len(ctx.artifacts)

    yield AgentEvent(
        type="usage",
        data={
            **totals,
            "iterations": iterations,
            "finish_reason": last_finish_reason,
            "fallback_used": fallback_used,
            "ttft_ms": ttft_ms,
        },
    )
    yield AgentEvent(type="done", data={"ok": True})
