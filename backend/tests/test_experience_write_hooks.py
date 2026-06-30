import pytest

from intersection_agent.hooks.execution_emitter import ExecutionEmitter
from intersection_agent.models.domain import Session
from intersection_agent.services.orchestrator import Orchestrator
from intersection_agent.stores.intersection_profile_store import IntersectionProfileStore


@pytest.mark.asyncio
async def test_absorption_events_carry_action(tmp_path):
    store = IntersectionProfileStore(base_dir=tmp_path)
    orch = Orchestrator(profile_store=store)
    events: list[dict] = []

    async def capture(payload: dict) -> None:
        events.append(payload)

    emitter = ExecutionEmitter(capture)
    session = Session()
    await orch.handle_message(
        session,
        "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯应更长",
        emitter=emitter,
    )
    exp_events = [
        e
        for e in events
        if e.get("step", "").startswith("experience_") and e.get("status") == "completed"
    ]
    assert exp_events, "应有经验吸收事件"
    cog = next((e for e in exp_events if e["step"] == "experience_cognition"), None)
    assert cog is not None
    assert cog["data"].get("action") in {"inserted", "exists", "updated"}


@pytest.mark.asyncio
async def test_three_level_experience_written(tmp_path):
    store = IntersectionProfileStore(base_dir=tmp_path)
    orch = Orchestrator(profile_store=store)
    session = Session()

    # 识别问题步 + 归因步：数据可验证拥堵 → cognition 落 verified
    await orch.handle_message(
        session, "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯应更长"
    )
    assert session.inter_id
    prof = store.load(session.inter_id)
    assert any(c.status == "verified" for c in prof.cognition)

    # 出方案步：确认后固化 skill → solution_ref 回写档案
    await orch.handle_message(session, "确认")
    prof2 = store.load(session.inter_id)
    assert prof2.solution_ref
