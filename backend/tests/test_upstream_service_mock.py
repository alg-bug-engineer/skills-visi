"""UpstreamGovernanceTraceService 在 MOCK_DB 下的端到端集成。"""
import pytest

from intersection_agent.config import Settings
from intersection_agent.models.domain import NluResult, TimePeriod
from intersection_agent.services.upstream_governance_trace_service import (
    UpstreamGovernanceTraceService,
)


def _nlu() -> NluResult:
    return NluResult(
        intersection="奥体西路与经十路",
        time_period=TimePeriod(start="07:00", end="09:00", label="早高峰"),
    )


@pytest.mark.asyncio
async def test_build_returns_trees_storyboard_and_governance_points():
    service = UpstreamGovernanceTraceService(
        settings=Settings(mock_db=True, mock_llm=True)
    )
    result = await service.build("inter_demo", approach="北进口", nlu=_nlu())

    assert len(result["trees"]) >= 1
    assert result["storyboard"]["frames"]
    points = result["governance_points"]
    assert points
    assert all(p["decision"] == "治理落点" for p in points)
