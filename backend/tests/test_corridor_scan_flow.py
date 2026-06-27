"""Corridor scan flow integration tests."""

import pytest


@pytest.mark.asyncio
async def test_corridor_scan_asks_time_period(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    r1 = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西最拥堵的路口是哪个？"},
    )
    body = r1.json()
    assert body["state"] == "corridor_nlu_incomplete"
    assert body["reply"]["type"] == "follow_up"
    assert body["meta"].get("intent") == "corridor_scan"
    missing = body["meta"].get("missing_fields") or []
    assert "time_period" in missing
    assert "intersection" not in missing


@pytest.mark.asyncio
async def test_corridor_scan_list_query_with_time(client):
    """「路口有哪些」+ 已含时段 → 直接干线扫描，不追问单点路口。"""
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    r1 = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西晚高峰经常拥堵的路口有哪些"},
    )
    body = r1.json()
    assert body["state"] == "awaiting_corridor_pick", body
    assert body["reply"]["type"] == "corridor_scan"
    assert body["meta"].get("intent") == "corridor_scan"
    missing = body["meta"].get("missing_fields") or []
    assert "intersection" not in missing


@pytest.mark.asyncio
async def test_corridor_pick_after_scan(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西最拥堵的路口是哪个？"},
    )
    await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "早高峰"},
    )
    r3 = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西与经十路"},
    )
    body = r3.json()
    assert body["state"] in ("nlu_incomplete", "processing", "done"), body
    assert "请告诉我您想深入分析哪个路口" not in body["reply"]["content"]


@pytest.mark.asyncio
async def test_corridor_scan_with_real_shape(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西最拥堵的路口是哪个？"},
    )
    r2 = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "晚高峰"},
    )
    body = r2.json()
    assert body["state"] == "awaiting_corridor_pick"
    assert body["reply"]["type"] == "corridor_scan"
    scan = body["meta"].get("corridor_scan") or {}
    assert scan.get("intersection_count", 0) > 0
