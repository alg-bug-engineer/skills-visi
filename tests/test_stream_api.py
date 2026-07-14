import json
import asyncio
import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app
from app.runtime.registry import get_registry
from app.services.agent_service import AgentService
from app.runtime.skill_types import SkillResult


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _parse_sse(chunk: str) -> list[dict]:
    """把 SSE 文本切成 [{event, data}] 列表。"""
    events: list[dict] = []
    for block in chunk.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
        if event:
            events.append({"event": event, "data": data})
    return events


@pytest.mark.asyncio
async def test_run_stream_event_order_and_monotonic_snapshot(script_user_input):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/api/v1/agent/run/stream",
            json={"user_input": script_user_input, "trace_id": "stream-001"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            body = ""
            async for chunk in response.aiter_text():
                body += chunk

    events = _parse_sse(body)
    types = [e["event"] for e in events]

    # 顺序：每个 phase 一对 start/done，末尾 pipeline_complete
    assert types[0] == "phase_start"
    assert types[-1] == "pipeline_complete"
    assert types.count("phase_start") == 5
    assert types.count("phase_done") == 5
    assert "error" not in types

    # 快照 phases 单调增长
    phase_done = [e for e in events if e["event"] == "phase_done"]
    sizes = [len(e["data"]["snapshot"]["phases"]) for e in phase_done]
    assert sizes == sorted(sizes)
    assert sizes[0] == 1 and sizes[-1] == 5

    # 末次完成快照
    final = events[-1]["data"]["snapshot"]
    assert final["pipeline_complete"] is True
    assert final["trace_id"] == "stream-001"
    assert final["plan"]["recommended"]["plan_id"]


@pytest.mark.asyncio
async def test_run_stream_partial_failure_emits_error(script_user_input, monkeypatch):
    registry = get_registry()
    failing_skill = registry.get("cause_analysis")

    async def boom(context, **deps):  # noqa: ANN001, ARG001
        raise RuntimeError("模拟成因分析失败")

    monkeypatch.setattr(failing_skill, "run", boom)

    agent = AgentService(get_settings())
    events = []
    async for ev in agent.run_stream(script_user_input, trace_id="stream-fail"):
        events.append(ev)

    types = [e["event"] for e in events]
    # 失败发生在 cause_analysis：出现 error，且不再有 pipeline_complete
    assert "error" in types
    assert "pipeline_complete" not in types

    error_ev = next(e for e in events if e["event"] == "error")
    assert "cause" in (error_ev["data"]["phase"] or "")
    assert error_ev["data"]["errors"]

    # 失败前的 phase 仍成功产出（以快照公开 phases 键判定）
    done_before = [e for e in events if e["event"] == "phase_done" and e["data"]["success"]]
    assert done_before
    last_ok_phases = done_before[-1]["data"]["snapshot"]["phases"].keys()
    assert {"intent", "diagnosis"}.issubset(last_ok_phases)


@pytest.mark.asyncio
async def test_blocking_skill_does_not_freeze_server_event_loop(script_user_input, monkeypatch):
    """Legacy synchronous work inside an async skill must run off the ASGI loop."""
    registry = get_registry()
    intent_skill = registry.get("intent_understanding")

    async def blocking_run(context, **deps):  # noqa: ANN001, ARG001
        time.sleep(0.15)
        return SkillResult(
            skill_id="intent_understanding",
            phase="intent_understanding",
            success=True,
            output={},
        )

    monkeypatch.setattr(intent_skill, "run", blocking_run)
    agent = AgentService(get_settings())
    finished = asyncio.Event()
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while not finished.is_set():
            ticks += 1
            await asyncio.sleep(0.01)

    async def consume():
        async for _ev in agent.run_stream(
            script_user_input,
            trace_id="stream-nonblocking",
            stop_after="intent_understanding",
        ):
            pass
        finished.set()

    await asyncio.gather(consume(), heartbeat())
    assert ticks >= 5


@pytest.mark.asyncio
async def test_stream_sends_keepalive_during_long_phase(script_user_input, monkeypatch):
    registry = get_registry()
    intent_skill = registry.get("intent_understanding")

    async def slow_run(context, **deps):  # noqa: ANN001, ARG001
        await asyncio.sleep(0.06)
        return SkillResult(
            skill_id="intent_understanding",
            phase="intent_understanding",
            success=True,
            output={},
        )

    monkeypatch.setattr(intent_skill, "run", slow_run)
    monkeypatch.setattr("app.api.routes.SSE_HEARTBEAT_INTERVAL_S", 0.01)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/run/stream",
            json={
                "user_input": script_user_input,
                "trace_id": "stream-heartbeat",
                "stop_after": "intent_understanding",
            },
        )

    assert ": keep-alive\n\n" in response.text
    assert "event: phase_done" in response.text
