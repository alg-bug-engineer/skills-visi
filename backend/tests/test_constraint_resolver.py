"""Tests for ConstraintResolverService."""

from __future__ import annotations

from intersection_agent.services.constraint_resolver_service import ConstraintResolverService


def test_vertical_overflow_constraint_maps_to_perpendicular_group():
    svc = ConstraintResolverService()
    evidence = {
        "by_direction": [
            {
                "group": "南北向",
                "saturation": 0.92,
                "avg_queue_m": 112.0,
                "queue_storage_ratio": 0.68,
            },
            {
                "group": "东西向",
                "saturation": 0.55,
                "avg_queue_m": 48.0,
                "queue_storage_ratio": 0.42,
            },
        ]
    }
    result = svc.resolve(
        "要考虑垂直方向不能溢出",
        nlu_directions=["南北向"],
        problem_evidence=evidence,
    )
    assert result is not None
    assert result["protected_directions"] == ["东西向"]
    assert any(c["scope"] == "东西向" for c in result["constraints"])
    assert "东西向" in result["narrative"]


def test_apply_to_delta_clips_when_spillback_near_cap():
    svc = ConstraintResolverService()
    constraints = {
        "constraints": [
            {
                "metric": "spillback_risk",
                "scope": "东西向",
                "operator": "<=",
                "value": 0.77,
                "baseline": 0.75,
            }
        ]
    }
    clipped, note = svc.apply_to_delta(20, constraints)
    assert clipped < 20
    assert note


def test_max_delta_constraint():
    svc = ConstraintResolverService()
    result = svc.resolve("绿灯延长不超过8秒", nlu_directions=["南北向"])
    assert result is not None
    assert any(c["metric"] == "delta_seconds" and c["value"] == 8 for c in result["constraints"])


def test_max_delta_constraint_cannot_exceed_wording():
    svc = ConstraintResolverService()
    result = svc.resolve("绿灯增加时间不能超过5秒", nlu_directions=["南北向"])
    assert result is not None
    assert any(c["metric"] == "delta_seconds" and c["value"] == 5 for c in result["constraints"])
