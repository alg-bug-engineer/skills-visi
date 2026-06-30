"""API integration tests."""

import pytest

from intersection_agent.models.domain import DiagnosisResult, NluResult, Session, TimePeriod
from intersection_agent.services.orchestrator import Orchestrator


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mock_llm"] is True


@pytest.mark.asyncio
async def test_full_flow(client):
    create = await client.post("/api/v1/sessions")
    assert create.status_code == 200
    sid = create.json()["session_id"]

    msg1 = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯应更长"},
    )
    assert msg1.status_code == 200
    body1 = msg1.json()
    assert body1["state"] == "awaiting_confirm"
    assert body1["reply"]["type"] == "diagnosis"
    assert body1["suggestion"] is not None
    assert "绿灯" in body1["nlu"]["user_suggestion"]
    assert body1["meta"].get("skill_action") == "awaiting_create"
    assert body1["meta"].get("data_window", {}).get("type") == "rolling_7d"

    msg2 = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "确认"},
    )
    body2 = msg2.json()
    assert body2["state"] == "done"
    assert body2["reply"]["type"] == "skill_created"


@pytest.mark.asyncio
async def test_nlu_follow_up(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]

    r1 = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "缺少时段：奥体西路与经十路交叉口经常拥堵"},
    )
    assert r1.json()["reply"]["type"] == "follow_up"
    assert r1.json()["state"] == "nlu_incomplete"

    r2 = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "下午四点南北向"},
    )
    assert r2.json()["state"] in ("awaiting_confirm", "nlu_incomplete", "processing")


@pytest.mark.asyncio
async def test_deny_suggestion_confirmation(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    first = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向拥堵"},
    )
    first_body = first.json()
    assert first_body["state"] == "awaiting_confirm"
    assert first_body["reply"]["type"] == "follow_up"
    assert first_body["suggestion"] is None
    assert first_body["meta"].get("suggestion_action") == "awaiting_generate"
    # 过饱和进口道触发上游溯源后，确认文案改为跨路口协调建议
    assert "上游治理落点" in first_body["reply"]["content"]
    assert "跨路口协调建议" in first_body["reply"]["content"]
    assert first_body["meta"].get("problem_evidence")
    assert "问题验证" in first_body["reply"]["content"] or "常发" in first_body["reply"]["content"]
    assert "建议增加绿灯时长" not in first_body["reply"]["content"]
    deny = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "否"},
    )
    assert deny.json()["state"] == "done"
    assert "未生成治理建议" in deny.json()["reply"]["content"]


def test_problem_confirm_message_strips_rule_suggestion_wording():
    session = Session()
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
                "id": "rule_oversaturation",
                "name": "过饱和需增加绿灯",
                "conclusion": "关键方向过饱和，建议增加绿灯时长",
            }
        ],
        metrics_snapshot={"saturation_rate": 0.92, "delay_index": 2.1},
    )

    content = Orchestrator._format_problem_confirm_message(session)

    assert "关键方向过饱和" in content
    assert "建议增加绿灯时长" not in content
    assert "是否需要生成治理建议" not in content


@pytest.mark.asyncio
async def test_green_light_complaint_without_explicit_advice_still_requires_confirmation(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]

    resp = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向拥堵，绿灯感觉不够"},
    )

    body = resp.json()
    assert body["state"] == "awaiting_confirm"
    assert body["reply"]["type"] == "follow_up"
    assert body["suggestion"] is None
    assert body["nlu"]["user_suggestion"] is None
    assert body["meta"].get("suggestion_action") == "awaiting_generate"


@pytest.mark.asyncio
async def test_plain_confirmation_generates_suggestion_without_skill(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向拥堵"},
    )

    confirm = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "是"},
    )
    body = confirm.json()
    assert body["state"] == "done"
    assert body["reply"]["type"] == "diagnosis"
    assert body["suggestion"] is not None
    assert body["meta"].get("suggestion_action") == "generated"
    assert body["meta"].get("skill_action") == "skipped_no_user_suggestion"


@pytest.mark.asyncio
async def test_confirmation_with_constraint_generates_suggestion_then_awaits_skill_confirm(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向拥堵"},
    )

    confirm = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "是，优先保障南北向直行，绿灯可以延长"},
    )
    body = confirm.json()
    assert body["state"] == "awaiting_confirm"
    assert body["reply"]["type"] == "diagnosis"
    assert body["suggestion"] is not None
    assert "南北向" in body["nlu"]["user_suggestion"]
    assert body["meta"].get("suggestion_action") == "generated_with_user_suggestion"
    assert body["meta"].get("skill_action") == "awaiting_create"

    persist = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "确认固化"},
    )
    persisted = persist.json()
    assert persisted["state"] == "done"
    assert persisted["reply"]["type"] == "skill_created"


@pytest.mark.asyncio
async def test_declined_skill_create(client):
    """RT-CONF-D2-02: 拒绝 Skill 固化。"""
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    first = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯应更长"},
    )
    assert first.json()["meta"].get("skill_action") == "awaiting_create"

    deny = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "否"},
    )
    body = deny.json()
    assert body["state"] == "done"
    assert body["meta"].get("skill_action") == "declined_create"
    assert "未固化" in body["reply"]["content"]


@pytest.mark.asyncio
async def test_constraint_is_reflected_in_suggestion_and_persisted_skill(client, skill_dir_path):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "奥体西路与经十路交叉口，下午四点南北向拥堵"},
    )

    confirm = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "要考虑垂直方向不能溢出"},
    )
    body = confirm.json()

    assert body["reply"]["type"] == "diagnosis"
    assert body["state"] == "awaiting_confirm"
    assert body["nlu"]["user_suggestion"] == "要考虑垂直方向不能溢出"
    assert body["meta"].get("quantitative_constraints")
    assert "东西向" in body["meta"]["quantitative_constraints"]["narrative"]
    assert "垂直方向不能溢出" in body["suggestion"]["narrative"]

    persist = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "确认固化"},
    )
    persisted = persist.json()
    assert persisted["reply"]["type"] == "skill_created"

    skill_id = persisted["meta"]["skill_id"]
    meta_files = list(skill_dir_path.glob("*/skill.meta.json"))
    assert meta_files
    meta_text = "\n".join(path.read_text(encoding="utf-8") for path in meta_files)
    reference_text = "\n".join(
        path.read_text(encoding="utf-8") for path in skill_dir_path.glob("*/reference.md")
    )
    assert skill_id in meta_text
    assert "垂直方向不能溢出" in meta_text
    assert "垂直方向不能溢出" in reference_text


@pytest.mark.asyncio
async def test_intersection_not_found(client):
    create = await client.post("/api/v1/sessions")
    sid = create.json()["session_id"]
    resp = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"content": "未知路口ABC与DEF路交叉口，下午四点南北向拥堵"},
    )
    body = resp.json()
    assert body["reply"]["type"] in ("error", "follow_up")


@pytest.mark.asyncio
async def test_list_skills(client):
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
    skills = await client.get("/api/v1/skills")
    assert skills.status_code == 200
    assert len(skills.json()) >= 1


@pytest.mark.asyncio
async def test_session_not_found(client):
    resp = await client.post(
        "/api/v1/sessions/nonexistent/messages",
        json={"content": "test"},
    )
    assert resp.status_code == 404
