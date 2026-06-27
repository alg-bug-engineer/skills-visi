"""Tests for paced absorption line emission."""

from __future__ import annotations

import pytest

from intersection_agent.skills.absorption_stage_emitter import emit_lines_paced


class _CaptureEmitter:
    def __init__(self) -> None:
        self.deltas: list[str] = []

    async def emit_skill_absorption(self, event_type: str, stage: str, **payload) -> None:
        if event_type == "thought_delta":
            self.deltas.append(str(payload.get("delta") or ""))


@pytest.mark.asyncio
async def test_emit_lines_paced_continues_with_leading_newline() -> None:
    emitter = _CaptureEmitter()
    await emit_lines_paced(
        emitter,
        stage="blueprint",
        lines=["> 第一行", "> 第二行"],
        budget_sec=0.01,
    )
    await emit_lines_paced(
        emitter,
        stage="blueprint",
        lines=["> 第三行"],
        budget_sec=0.01,
        continue_previous=True,
    )
    merged = "".join(emitter.deltas)
    assert merged == "> 第一行\n> 第二行\n> 第三行"
