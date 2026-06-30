"""Skill fast-path and upsert behavior tests."""

import pytest

from intersection_agent.models.domain import DiagnosisResult, NluResult, Session, TimePeriod
from intersection_agent.services.skill_service import SkillService


def _sample_session() -> Session:
    session = Session()
    session.inter_id = "inter_001"
    session.resolved_intersection = "测试路口"
    session.nlu = NluResult(
        intersection="测试路口",
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        problem_type="congestion",
        directions=["南北向"],
    )
    session.diagnosis = DiagnosisResult(
        diagnosed=True,
        matched_rules=[
            {
                "id": "rule_green_insufficient",
                "action": {"formula": "delta = saturation * 20"},
            }
        ],
    )
    session.raw_user_context = "测试路口晚高峰拥堵"
    return session


def test_upsert_creates_then_unchanged(skill_dir_path):
    service = SkillService()
    session = _sample_session()

    first = service.upsert_from_session(session)
    assert first.action == "created"

    second = service.upsert_from_session(session)
    assert second.action == "unchanged"


def test_diff_detects_rule_change(skill_dir_path):
    service = SkillService()
    session = _sample_session()
    skill = service.build_from_session(session)

    session.diagnosis = DiagnosisResult(
        diagnosed=True,
        matched_rules=[
            {
                "id": "rule_other",
                "action": {"formula": "delta = saturation * 20"},
            }
        ],
    )
    diff = service.diff_with_session(skill, session)
    assert diff.has_material_diff
    assert any("命中规则" in line for line in diff.changes)


def test_diff_no_change_when_same_snapshot(skill_dir_path):
    service = SkillService()
    session = _sample_session()
    skill = service.build_from_session(session)
    diff = service.diff_with_session(skill, session)
    assert not diff.has_material_diff


@pytest.mark.asyncio
async def test_fast_path_reuses_skill_with_suggestion_confirmation(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]

    first = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯应更长"},
    )
    assert first.json()["state"] == "awaiting_confirm"
    created = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "确认固化"},
    )
    assert created.json()["reply"]["type"] == "skill_created"

    second_session = await client.post("/api/v1/sessions")
    sid2 = second_session.json()["session_id"]
    second = await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵"},
    )
    body = second.json()
    assert body["meta"].get("resolution_source") == "skill_fast_path"
    assert body["state"] == "awaiting_confirm"
    assert body["meta"].get("suggestion_action") == "awaiting_generate"
    assert body["meta"].get("skill_reused") is True
    assert "沉淀技能" in body["reply"]["content"] or "沉淀" in body["reply"]["content"]

    confirm = await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "是"},
    )
    confirmed = confirm.json()
    assert confirmed["state"] == "done"
    assert confirmed["meta"].get("skill_action") == "reused_no_persist"
    assert confirmed["suggestion"] is not None


@pytest.mark.asyncio
async def test_constraint_mismatch_skips_fast_path(client):
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
    second = await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯不超过10秒"},
    )
    body = second.json()
    assert body["meta"].get("resolution_source") != "skill_fast_path"


@pytest.mark.asyncio
async def test_fast_path_supplement_triggers_skill_confirm(client):
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
    await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵"},
    )

    confirm = await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "是，垂直方向不能溢出"},
    )
    body = confirm.json()
    assert body["state"] == "awaiting_confirm"
    assert body["meta"].get("skill_action") == "awaiting_create"
    assert "垂直方向" in body["nlu"]["user_suggestion"]
    assert "绿灯应更长" in body["nlu"]["user_suggestion"]


@pytest.mark.asyncio
async def test_fast_path_supplement_merges_constraints_on_persist(client):
    """RT-REUSE: D1 补充新约束时合并历史约束并更新 Skill。"""
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯应更长"},
    )
    await client.post(f"/api/v1/sessions/{sid}/messages", json={"content": "确认固化"})

    second_session = await client.post("/api/v1/sessions")
    sid2 = second_session.json()["session_id"]
    await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵"},
    )
    await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "是，垂直方向不能溢出"},
    )
    pending = await client.post(f"/api/v1/sessions/{sid2}/messages", json={"content": "是"})
    body = pending.json()
    assert body["reply"]["type"] in ("skill_created", "skill_updated", "diagnosis")
    assert body["meta"].get("skill_action") in ("updated", "created")

    skills = await client.get("/api/v1/skills/leaderboard")
    records = skills.json()
    matched = next(
        (s for s in records if "奥体西路" in (s.get("intersection") or "")),
        None,
    )
    assert matched is not None
    constraints = matched.get("user_constraints") or ""
    assert "绿灯应更长" in constraints
    assert "垂直方向" in constraints or "溢出" in constraints


@pytest.mark.asyncio
async def test_first_diagnosis_awaits_suggestion_generation(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    resp = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向拥堵"},
    )
    body = resp.json()
    assert body["state"] == "awaiting_confirm"
    assert body["meta"].get("suggestion_action") == "awaiting_generate"
    # 过饱和触发上游溯源后，确认文案改为跨路口协调建议
    assert "协调建议" in body["reply"]["content"]


async def _persist_sample_skill(client) -> None:
    """RT-Persist helper: one full persist with user constraint."""
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    first = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯应更长"},
    )
    assert first.json()["state"] == "awaiting_confirm"
    created = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "确认固化"},
    )
    assert created.json()["reply"]["type"] == "skill_created"


@pytest.mark.asyncio
async def test_fast_path_injects_historical_constraint_on_confirm_yes(client):
    """RT-REUSE-07: Skill 有约束、用户无；确认「是」后建议沿用历史约束。"""
    await _persist_sample_skill(client)

    second_session = await client.post("/api/v1/sessions")
    sid2 = second_session.json()["session_id"]
    second = await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵"},
    )
    body = second.json()
    assert body["meta"].get("resolution_source") == "skill_fast_path"

    confirm = await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "是"},
    )
    confirmed = confirm.json()
    assert confirmed["state"] == "done"
    assert confirmed["meta"].get("skill_action") == "reused_no_persist"
    assert confirmed["suggestion"] is not None
    assert confirmed["nlu"]["user_suggestion"] == "绿灯应更长"
    narrative = confirmed["suggestion"].get("narrative") or ""
    assert "绿灯" in narrative or "更长" in narrative


@pytest.mark.asyncio
async def test_fast_path_with_same_constraint_still_awaits_d1(client):
    """RT-REUSE-08: 快路径首轮带与 Skill 相同约束，仍走 D1（与普通路径不对称）。"""
    await _persist_sample_skill(client)

    second_session = await client.post("/api/v1/sessions")
    sid2 = second_session.json()["session_id"]
    second = await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={
            "content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯应更长",
        },
    )
    body = second.json()
    assert body["meta"].get("resolution_source") == "skill_fast_path"
    assert body["state"] == "awaiting_confirm"
    assert body["meta"].get("suggestion_action") == "awaiting_generate"
    assert body["meta"].get("skill_action") != "awaiting_create"
    assert body["suggestion"] is None
    assert body["reply"]["type"] == "follow_up"


@pytest.mark.asyncio
async def test_fast_path_deny_suggestion_declines(client):
    """RT-REUSE-06 / RT-CONF-D1-06: 快路径拒绝生成建议。"""
    await _persist_sample_skill(client)

    second_session = await client.post("/api/v1/sessions")
    sid2 = second_session.json()["session_id"]
    await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵"},
    )
    deny = await client.post(
        f"/api/v1/sessions/{sid2}/messages",
        json={"content": "否"},
    )
    body = deny.json()
    assert body["state"] == "done"
    assert body["meta"].get("suggestion_action") == "declined"
    assert body["suggestion"] is None
