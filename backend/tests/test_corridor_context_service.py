"""Corridor context narrative formatting."""

from intersection_agent.services.corridor_context_service import CorridorContextService


def test_narrative_in_corridor_omits_line_road_listing():
    svc = CorridorContextService()
    ctx = svc._mock_context("测试路口")
    narrative = ctx["narrative"]
    assert "干线路网上" not in narrative
    assert "协调走廊" in narrative
    assert "第 3/5 个节点" in narrative
    assert "绿波断裂" in narrative


def test_narrative_not_in_corridor_without_coord_group():
    svc = CorridorContextService()
    empty = svc._empty("missing_time_period")
    assert empty["narrative"] == "干线协调上下文不可用"
