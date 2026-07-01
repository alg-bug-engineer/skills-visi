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
async def test_oversaturated_emits_upstream_trace_and_tree(monkeypatch):
    events: list[dict] = []

    async def capture(payload: dict) -> None:
        events.append(payload)

    emitter = ExecutionEmitter(capture)
    orch = Orchestrator()
    from intersection_agent.config import Settings

    mock_settings = Settings(mock_db=True, mock_llm=True)
    orch._upstream_trace._settings = mock_settings
    orch._upstream_trace._fetcher._settings = mock_settings
    orch._upstream_trace._flow_trace._settings = mock_settings
    orch._upstream_trace._topology._settings = mock_settings
    orch._upstream_correlate_map._settings = mock_settings
    orch._upstream_correlate_map._flow_trace._settings = mock_settings
    session = _session([{"label": "北直行", "turn_saturation": 0.95, "green_utilization": 0.38}])

    count = await orch._run_upstream_trace(session, {}, emitter)

    assert count >= 1
    steps = [e for e in events if e.get("step") == "upstream_trace"]
    assert {s["status"] for s in steps} == {"running", "completed"}
    map_actions = [
        e for e in events
        if e.get("step") == "map_action" and e.get("data", {}).get("action") == "upstream_correlate_map"
    ]
    assert map_actions
    assert map_actions[0]["data"]["correlate_map"]["intersections"]


@pytest.mark.asyncio
async def test_user_direction_takes_priority(monkeypatch):
    """用户明示「西进口」时只溯西进口，不并入过饱和的北/东。"""
    captured: dict = {}

    async def fake_build(inter_id, *, approaches=None, **_kw):
        captured["approaches"] = approaches
        return {
            "trees": [{"tree_id": "W"}],
            "governance_points": [],
            "storyboard": {"trees": [], "frames": [{"idx": 0}]},
        }

    orch = Orchestrator()
    monkeypatch.setattr(orch._upstream_trace, "build", fake_build)
    session = _session(
        [
            {"label": "北直行", "dir8_code": 0, "turn_saturation": 0.95},
            {"label": "东直行", "dir8_code": 2, "turn_saturation": 0.95},
            {"label": "西直行", "dir8_code": 6, "turn_saturation": 0.40},
        ]
    )
    session.nlu.directions = ["西进口"]

    await orch._run_upstream_trace(session, {}, None)

    assert captured["approaches"] == ["西进口"]


@pytest.mark.asyncio
async def test_no_user_direction_defaults_to_top_saturated(monkeypatch):
    """用户未指定方向时只聚焦诊断命中的「首个（最饱和）问题进口」一条链路。"""
    captured: dict = {}

    async def fake_build(inter_id, *, approaches=None, **_kw):
        captured["approaches"] = approaches
        return {
            "trees": [],
            "governance_points": [],
            "storyboard": {"trees": [], "frames": [{"idx": 0}]},
        }

    orch = Orchestrator()
    monkeypatch.setattr(orch._upstream_trace, "build", fake_build)
    session = _session(
        [
            {"label": "北直行", "dir8_code": 0, "turn_saturation": 0.95},
            {"label": "东直行", "dir8_code": 2, "turn_saturation": 0.98},
        ]
    )
    session.nlu.directions = []

    await orch._run_upstream_trace(session, {}, None)

    assert captured["approaches"] == ["东进口"]


@pytest.mark.asyncio
async def test_turn_specific_direction_only_traces_one_approach(monkeypatch):
    """「西左转」只溯西进口，不把同句附带的「北进口」并入。"""
    captured: dict = {}

    async def fake_build(inter_id, *, approaches=None, **_kw):
        captured["approaches"] = approaches
        return {
            "trees": [{"tree_id": "W"}],
            "governance_points": [],
            "storyboard": {"trees": [], "frames": [{"idx": 0}]},
        }

    orch = Orchestrator()
    monkeypatch.setattr(orch._upstream_trace, "build", fake_build)
    session = _session(
        [
            {"label": "北直行", "dir8_code": 0, "turn_saturation": 0.95},
            {"label": "西左转", "dir8_code": 6, "turn_saturation": 1.10},
        ]
    )
    session.nlu.directions = ["西左转", "北进口"]

    await orch._run_upstream_trace(session, {}, None)

    assert captured["approaches"] == ["西进口"]


@pytest.mark.asyncio
async def test_direction_group_east_west_only_east(monkeypatch):
    """「东西向」只溯东进口，不并入西进口。"""
    captured: dict = {}

    async def fake_build(inter_id, *, approaches=None, **_kw):
        captured["approaches"] = approaches
        return {
            "trees": [{"tree_id": "E"}],
            "governance_points": [],
            "storyboard": {"trees": [], "frames": [{"idx": 0}]},
        }

    orch = Orchestrator()
    monkeypatch.setattr(orch._upstream_trace, "build", fake_build)
    session = _session(
        [
            {"label": "东直行", "dir8_code": 2, "turn_saturation": 0.92},
            {"label": "西直行", "dir8_code": 6, "turn_saturation": 0.99},
        ]
    )
    session.nlu.directions = ["东西向"]

    await orch._run_upstream_trace(session, {}, None)

    assert captured["approaches"] == ["东进口"]


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
