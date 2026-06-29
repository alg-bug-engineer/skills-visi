"""Tests for context-aware governance guidance."""

from intersection_agent.services.governance_guidance import (
    build_governance_context,
    guidance_for_category,
)


def _data(**overrides) -> dict:
    base = {
        "traffic_flow": {
            "saturation_rate": 0.88,
            "turn_saturation_max": 0.92,
            "turn_saturation_spread": 0.42,
        },
        "evaluation": {
            "green_utilization": 0.42,
            "empty_green_rate": 0.22,
            "imbalance_index": 0.35,
        },
        "problem_evidence": {"metrics": {"spillback_risk_max": 0.85}},
        "flow_timing_governance": {
            "primary_diagnosis": {
                "type": "timing_optimizable",
                "structure_limited": False,
            }
        },
        "granularity": {
            "by_turn": [
                {"label": "东直行", "turn_saturation": 0.92, "green_utilization": 0.92},
                {"label": "北左转", "turn_saturation": 0.45, "green_utilization": 0.35},
            ]
        },
    }
    base.update(overrides)
    return base


def test_saturation_rebalance_when_empty_green_and_oversaturated():
    text = guidance_for_category("saturation", _data())
    assert "不宜一律加绿" in text or "转给" in text or "绿信比" in text


def test_saturation_capacity_bottleneck_not_add_green():
    data = _data(
        traffic_flow={
            "saturation_rate": 0.95,
            "turn_saturation_max": 0.95,
            "turn_saturation_spread": 0.08,
        },
        flow_timing_governance={
            "primary_diagnosis": {"type": "capacity_bottleneck", "structure_limited": False}
        },
    )
    text = guidance_for_category("saturation", data)
    assert "加绿空间有限" in text or "周期" in text


def test_saturation_add_green_when_utilization_low():
    data = _data(
        evaluation={
            "green_utilization": 0.68,
            "empty_green_rate": 0.05,
            "imbalance_index": 0.10,
        },
        traffic_flow={
            "saturation_rate": 0.92,
            "turn_saturation_max": 0.92,
            "turn_saturation_spread": 0.12,
        },
        flow_timing_governance={
            "primary_diagnosis": {"type": "basically_matched", "structure_limited": False}
        },
        granularity={
            "by_turn": [
                {"label": "东直行", "turn_saturation": 0.92, "green_utilization": 0.68},
            ]
        },
    )
    text = guidance_for_category("saturation", data)
    assert "增加" in text and "绿灯" in text


def test_spillback_upstream_control():
    text = guidance_for_category("spillback", _data())
    assert "上游" in text or "外溢" in text or "锁死" in text


def test_build_context_flags():
    ctx = build_governance_context(_data())
    assert ctx["oversaturated"] is True
    assert ctx["empty_green_detected"] is True
