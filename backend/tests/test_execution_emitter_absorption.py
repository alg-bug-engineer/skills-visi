"""Execution emitter skill_absorption tests."""

from __future__ import annotations

import pytest

from intersection_agent.hooks.execution_emitter import ExecutionEmitter


@pytest.mark.asyncio
async def test_emit_skill_absorption():
    events: list[dict] = []

    async def capture(payload: dict) -> None:
        events.append(payload)

    emitter = ExecutionEmitter(capture)
    await emitter.emit_skill_absorption(
        "skill_absorption_start",
        "",
        skill_id="skill_test",
        intersection="测试路口",
    )

    assert len(events) == 1
    assert events[0]["event"] == "skill_absorption"
    assert events[0]["type"] == "skill_absorption_start"
    assert events[0]["payload"]["skill_id"] == "skill_test"
