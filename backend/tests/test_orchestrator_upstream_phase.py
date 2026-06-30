"""orchestrator upstream_trace phase：过饱和触发 emit，未过饱和跳过。"""
import pytest

from intersection_agent.hooks.execution_emitter import ExecutionEmitter
from intersection_agent.models.domain import NluResult, Session, TimePeriod
from intersection_agent.services.orchestrator import Orchestrator


def _session(by_turn: list[dict]) -> Session:
    session = Session()
    session.inter_id = "inter_demo"
    session.nlu = NluResult(
        intersection="奥体西路与经十路",
        time_period=TimePeriod(start="07:00", end="09:00", label="早高峰"),
    )
    session.data_payload = {"granularity": {"by_turn": by_turn}}
    return session


@pytest.mark.asyncio
async def test_oversaturated_emits_upstream_trace_and_tree():
    events: list[dict] = []

    async def capture(payload: dict) -> None:
        events.append(payload)

    emitter = ExecutionEmitter(capture)
    orch = Orchestrator()
    session = _session([{"label": "北直行", "turn_saturation": 0.95, "green_utilization": 0.38}])

    count = await orch._run_upstream_trace(session, {}, emitter)

    assert count >= 1
    steps = [e for e in events if e.get("step") == "upstream_trace"]
    assert {s["status"] for s in steps} == {"running", "completed"}
    map_actions = [
        e for e in events
        if e.get("step") == "map_action" and e.get("data", {}).get("action") == "upstream_tree"
    ]
    assert map_actions
    assert map_actions[0]["data"]["storyboard"]["frames"]


@pytest.mark.asyncio
async def test_not_oversaturated_skips_phase():
    events: list[dict] = []

    async def capture(payload: dict) -> None:
        events.append(payload)

    emitter = ExecutionEmitter(capture)
    orch = Orchestrator()
    session = _session([{"label": "北直行", "turn_saturation": 0.55, "green_utilization": 0.70}])

    count = await orch._run_upstream_trace(session, {}, emitter)

    assert count == 0
    assert not [e for e in events if e.get("step") == "upstream_trace"]
