"""Consume an async generator in a task that can be stopped while it is waiting on the model.

Checking "should I stop?" only between chunks misses long silent stretches (the agent waiting on a
tool, sections being written in parallel, a slow first token). Here the generator runs in its own
task feeding a queue; the consumer polls the stop condition while waiting and cancels the task, so
the cancellation reaches whatever the generator is awaiting (LiteLLM call, section tasks...).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import aclosing
from typing import AsyncIterator, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_POLL_S = 0.5


class StreamStopped(Exception):
    """The stop condition fired; `reason` is what it returned (e.g. "cancelled", "disconnected")."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def iterate_until_stopped(
    source: AsyncIterator[T],
    should_stop: Callable[[], Awaitable[str | None]],
    poll_s: float = DEFAULT_POLL_S,
) -> AsyncIterator[T]:
    """Yield items of `source`; raise `StreamStopped` as soon as `should_stop()` returns a reason.

    `should_stop` is checked after every item and every `poll_s` seconds while waiting. When it
    fires, or when the consumer stops iterating, the producing task is cancelled and awaited, so the
    source's cleanup (finally blocks, closing provider streams) runs before this returns.
    Exceptions raised by the source are re-raised to the consumer.
    """
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    async def _produce() -> None:
        try:
            if hasattr(source, "aclose"):
                async with aclosing(source) as items:  # type: ignore[type-var]
                    async for item in items:
                        await queue.put(("item", item))
            else:
                async for item in source:
                    await queue.put(("item", item))
            await queue.put(("done", None))
        except Exception as exc:
            await queue.put(("error", exc))

    task = asyncio.create_task(_produce())
    try:
        while True:
            try:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=poll_s)
            except asyncio.TimeoutError:
                reason = await should_stop()
                if reason:
                    raise StreamStopped(reason)
                continue
            if kind == "done":
                return
            if kind == "error":
                raise payload  # type: ignore[misc]
            yield payload  # type: ignore[misc]
            reason = await should_stop()
            if reason:
                raise StreamStopped(reason)
    finally:
        if not task.done():
            task.cancel()
            logger.info("Stopping generation task")
        # Waits for the cancellation to be processed; propagates if we are cancelled ourselves.
        await asyncio.gather(task, return_exceptions=True)
