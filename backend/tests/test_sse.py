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
