"""Skill leaderboard API and hit counter tests."""

import pytest

from intersection_agent.services.skill_service import SkillService
from intersection_agent.skills.tag_helpers import read_hit_count


@pytest.mark.asyncio
async def test_leaderboard_empty(client):
    resp = await client.get("/api/v1/skills/leaderboard")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_leaderboard_after_persist(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    pending = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向拥堵，绿灯延长"},
    )
    assert pending.json()["meta"]["skill_action"] == "awaiting_create"
    await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "确认固化"},
    )

    resp = await client.get("/api/v1/skills/leaderboard")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    row = body[0]
    assert row["skill_id"]
    assert row["intersection"]
    assert row["hit_count"] == 0
    assert "tags" in row
    assert row["tags"]["match"]["intersection"]
    assert row["download_url"].endswith("/download")


def test_record_hit_increments(skill_dir_path):
    from tests.test_skill_fast_path import _sample_session

    service = SkillService()
    result = service.upsert_from_session(_sample_session())
    skill_id = result.record.skill_id

    assert service.record_hit(skill_id) == 1
    reloaded = service.get_by_id(skill_id)
    assert reloaded is not None
    assert read_hit_count(reloaded.tags) == 1

    assert service.record_hit(skill_id) == 2
    reloaded = service.get_by_id(skill_id)
    assert read_hit_count(reloaded.tags) == 2


def test_upsert_preserves_hit_count(skill_dir_path):
    from tests.test_skill_fast_path import _sample_session

    service = SkillService()
    session = _sample_session()
    created = service.upsert_from_session(session)
    service.record_hit(created.record.skill_id)

    updated = service.upsert_from_session(session)
    assert updated.action == "unchanged"
    reloaded = service.get_by_id(created.record.skill_id)
    assert read_hit_count(reloaded.tags) == 1


@pytest.mark.asyncio
async def test_fast_path_records_hit(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    first = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯应更长"},
    )
    assert first.json()["state"] == "awaiting_confirm"
    await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "确认固化"},
    )

    second_session = await client.post("/api/v1/sessions")
    sid2 = second_session.json()["session_id"]
    resp = await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("meta", {}).get("skill_reused") is True

    board = await client.get("/api/v1/skills/leaderboard?sort=hits")
    assert board.status_code == 200
    rows = board.json()
    assert rows
    assert rows[0]["hit_count"] >= 1
