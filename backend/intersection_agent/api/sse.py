"""SSE helpers for streaming execution events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from intersection_agent.hooks.execution_emitter import ExecutionEmitter
from intersection_agent.utils.json_safe import to_json_safe

logger = logging.getLogger(__name__)


async def sse_event_stream(queue: asyncio.Queue[dict[str, Any] | None]) -> AsyncIterator[str]:
    """Yield Server-Sent Events from an asyncio queue until sentinel None."""
    while True:
        item = await queue.get()
        if item is None:
            yield "data: {\"event\": \"done\"}\n\n"
            break
        try:
            payload = json.dumps(to_json_safe(item), ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            logger.exception("sse serialization failed: %s", exc)
            payload = json.dumps(
                {
                    "event": "error",
                    "message": "SSE 序列化失败",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
        yield f"data: {payload}\n\n"


def make_sse_queue_callback(queue: asyncio.Queue[dict[str, Any] | None]):
    """Build an async callback that pushes events into the SSE queue."""

    async def callback(event: dict[str, Any]) -> None:
        await queue.put(event)

    return callback


def build_emitter(queue: asyncio.Queue[dict[str, Any] | None]) -> ExecutionEmitter:
    """Create an ExecutionEmitter wired to an SSE queue."""
    return ExecutionEmitter(callback=make_sse_queue_callback(queue))
