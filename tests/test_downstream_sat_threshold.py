"""BUG-007: sat=0.80 + low queue must not mean downstream blocked."""

from __future__ import annotations

from app.metrics.traffic import THRESHOLDS, classify_release_bottleneck
from app.trace.downstream_diagnosis import build_downstream_diagnosis
from app.trace.downstream_trace import assess_downstream_capacity


def test_downstream_saturation_threshold_aligned_at_085():
    assert THRESHOLDS["downstream_saturation_high"] == 0.85
    assert assess_downstream_capacity(saturation=0.80, queue_ratio=0.04)["blocked"] is False
    assert assess_downstream_capacity(saturation=0.85, queue_ratio=0.04)["blocked"] is True


def test_classify_release_allows_add_green_when_down_sat_080():
    result = classify_release_bottleneck(
        target_saturation=1.54,
        target_green_utilization=0.90,
        downstream_queue_ratio=0.04,
        downstream_saturation=0.80,
    )
    assert result["can_simple_add_green"] is True
    assert result["bottleneck_type"] == "local_release"


def test_downstream_diagnosis_trusts_capacity_blocked_false():
    target = {
        "metrics": {
            "queue_storage_ratio_max": 0.85,
            "saturation_rate": 1.54,
            "green_utilization": 0.90,
        }
    }
    downstream_trace = {
        "adjacent_intersections": [
            {
                "inter_id": "down",
                "inter_name": "坤顺路与礼耕路路口",
                "metrics": {
                    "queue_storage_ratio_max": 0.04,
                    "saturation_rate": 0.80,
                },
                "remaining_storage_m": 131.0,
                "capacity": {
                    "can_release": True,
                    "blocked": False,
                    "reasons": [],
                    "release_guard": "downstream_has_slack",
                },
            }
        ]
    }
    bottleneck = {
        "can_simple_add_green": True,
        "label": "本路口放行不足",
        "reason": "下游仍有承接空间",
    }
    result = build_downstream_diagnosis(
        target_profile=target,
        downstream_trace=downstream_trace,
        bottleneck=bottleneck,
    )
    assert result["release_answer"] == "本路口放不出去"
    assert result["scenario"] == "local_release_primary"
    assert result["judgment_criteria"]["downstream_near_saturation"] is False
    assert result["can_simple_add_green"] is True
