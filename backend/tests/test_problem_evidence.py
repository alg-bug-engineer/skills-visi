"""Tests for ProblemEvidenceService."""

from __future__ import annotations

import pytest

from intersection_agent.models.domain import NluResult, TimePeriod
from intersection_agent.services.problem_evidence_service import ProblemEvidenceService


@pytest.mark.asyncio
async def test_mock_evidence_chronic_and_dow():
    svc = ProblemEvidenceService()
    nlu = NluResult(
        intersection="奥体西路与经十路交叉口",
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        problem_type="congestion",
        directions=["南北向"],
    )
    evidence = await svc.build(
        "011wwe28ctu00001",
        "奥体西路与经十路路口",
        nlu,
        data_payload={
            "evaluation": {"delay_index": 2.1, "imbalance_index": 0.35},
            "traffic_flow": {"saturation_rate": 0.88},
        },
        user_context="每周三下午四点南北向拥堵",
    )
    assert evidence["chronic"]["is_chronic"] is True
    assert evidence["chronic"]["congested_days"] >= 4
    assert evidence["dow_pattern"]["dow_label"] == "周三"
    assert evidence["metrics"]["avg_queue_m"] is not None
    assert any(item["group"] == "南北向" for item in evidence["by_direction"])


@pytest.mark.asyncio
async def test_mock_evidence_summary_contains_quantitative_hints():
    svc = ProblemEvidenceService()
    nlu = NluResult(
        intersection="测试路口",
        time_period=TimePeriod(start="07:00", end="09:00", label="早高峰"),
        problem_type="congestion",
        directions=["东西向"],
    )
    evidence = await svc.build("id1", "测试路口", nlu, user_context="早高峰拥堵")
    assert "常发" in evidence["summary"] or "超标" in evidence["summary"]
    assert evidence["metrics"]["saturation_rate"] is not None
