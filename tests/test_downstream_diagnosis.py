import pytest

from app.trace.downstream_diagnosis import build_downstream_diagnosis


def test_downstream_diagnosis_high_demand_blocked():
    target = {
        "metrics": {
            "queue_storage_ratio_max": 0.92,
            "saturation_rate": 0.96,
            "green_utilization": 0.88,
        }
    }
    downstream_trace = {
        "adjacent_intersections": [
            {
                "inter_id": "d1",
                "inter_name": "舜华路与工业南路交叉口",
                "metrics": {"queue_storage_ratio_max": 0.89, "saturation_rate": 0.95},
                "capacity": {"blocked": True},
            }
        ]
    }
    bottleneck = {
        "bottleneck_type": "downstream_capacity",
        "can_simple_add_green": False,
        "reason": "目标方向需求高且下游承接空间不足",
    }
    result = build_downstream_diagnosis(
        target_profile=target,
        downstream_trace=downstream_trace,
        bottleneck=bottleneck,
    )
    assert result["scenario"] == "high_demand_downstream_blocked"
    assert result["release_answer"] == "下游接不住"
    assert result["judgment_criteria"]["add_green_spillback_risk"] is True


def test_downstream_diagnosis_low_green_util():
    target = {
        "metrics": {
            "queue_storage_ratio_max": 0.85,
            "saturation_rate": 0.75,
            "green_utilization": 0.45,
        }
    }
    downstream_trace = {"adjacent_intersections": [{"inter_name": "下游", "metrics": {}, "capacity": {}}]}
    bottleneck = {"can_simple_add_green": False}
    result = build_downstream_diagnosis(
        target_profile=target,
        downstream_trace=downstream_trace,
        bottleneck=bottleneck,
    )
    assert result["scenario"] == "queue_high_green_underused"
    assert result["release_answer"] == "绿灯给了也用不上"
