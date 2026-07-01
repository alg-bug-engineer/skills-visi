"""SSE streaming API tests."""

import json

import pytest


async def _collect_sse_events(response) -> list[dict]:
    """Parse SSE body from httpx streaming response."""
    events: list[dict] = []
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            for line in block.splitlines():
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    if payload.get("event") != "done":
                        events.append(payload)
    return events


@pytest.mark.asyncio
async def test_message_stream_emits_steps(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]

    async with client.stream(
        "POST",
        f"/api/v1/sessions/{sid}/messages/stream",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯应更长"},
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        events = await _collect_sse_events(response)

    steps = [e["step"] for e in events if e.get("event") == "step"]
    assert "orchestrator.start" in steps
    assert "nlu" in steps
    assert "data_fetch" in steps
    assert "rule_engine" in steps

    result_events = [e for e in events if e.get("event") == "result"]
    assert len(result_events) == 1
    assert result_events[0]["data"]["reply"]["type"] in ("diagnosis", "skill_created", "text")


@pytest.mark.asyncio
async def test_message_stream_nlu_follow_up(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]

    async with client.stream(
        "POST",
        f"/api/v1/sessions/{sid}/messages/stream",
        json={"content": "缺少时段：奥体西路与经十路交叉口经常拥堵"},
    ) as response:
        events = await _collect_sse_events(response)

    nlu_events = [e for e in events if e.get("step") == "nlu"]
    assert nlu_events
    assert nlu_events[-1]["data"].get("status") == "incomplete"

    result = next(e for e in events if e.get("event") == "result")
    assert result["data"]["reply"]["type"] == "follow_up"


@pytest.mark.asyncio
async def test_message_stream_skill_absorption_before_build(client, skill_dir_path):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]

    await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向拥堵，优先保障南北向直行，绿灯可以延长"},
    )

    async with client.stream(
        "POST",
        f"/api/v1/sessions/{sid}/messages/stream",
        json={"content": "确认固化"},
    ) as response:
        events = await _collect_sse_events(response)

    absorption = [e for e in events if e.get("event") == "skill_absorption"]
    builds = [e for e in events if e.get("event") == "skill_build"]
    assert absorption
    assert builds
    assert absorption[0]["type"] == "skill_absorption_start"
    absorption_types = [e["type"] for e in absorption]
    assert "thought_delta" in absorption_types
    assert "write_phase_start" in absorption_types
    build_types = [e["type"] for e in builds]
    assert "drawer_open" in build_types
    assert "skill_build_start" in build_types
    assert absorption[-1]["type"] == "skill_absorption_done"
    assert any(e["type"] == "skill_build_done" for e in builds)
    write_idx = next(i for i, e in enumerate(events) if e.get("type") == "write_phase_start")
    done_idx = next(
        i for i, e in enumerate(events) if e.get("type") == "skill_absorption_done"
    )
    first_file_idx = next(
        i for i, e in enumerate(events)
        if e.get("event") == "skill_build" and e.get("type") == "file_delta"
    )
    assert write_idx < first_file_idx < done_idx
