"""下游指标缺失时不得伪装「有余量」或「承接受限」。"""

from app.trace.downstream_diagnosis import build_downstream_diagnosis
from app.trace.downstream_trace import assess_downstream_capacity


def test_assess_downstream_capacity_unknown_when_metrics_missing():
    cap = assess_downstream_capacity(saturation=None, queue_ratio=None)
    assert cap["unknown"] is True
    assert cap["can_release"] is None
    assert cap["blocked"] is False
    assert cap["release_guard"] == "downstream_metrics_unknown"


def test_assess_downstream_capacity_queue_still_blocks():
    cap = assess_downstream_capacity(saturation=None, queue_ratio=0.91)
    assert cap["unknown"] is False
    assert cap["blocked"] is True
    assert cap["can_release"] is False


def test_downstream_diagnosis_unknown_not_limited_capacity():
    out = build_downstream_diagnosis(
        target_profile={
            "metrics": {
                "queue_storage_ratio_max": 1.29,
                "saturation_rate": None,
                "green_utilization": 0.88,
            }
        },
        downstream_trace={
            "adjacent_intersections": [
                {
                    "inter_id": "down-1",
                    "inter_name": "奥体西路与经十路路口",
                    "metrics": {},
                    "capacity": assess_downstream_capacity(saturation=None, queue_ratio=None),
                    "by_turn": [],
                }
            ]
        },
        bottleneck={"can_simple_add_green": True, "label": "复合瓶颈", "reason": "x"},
    )
    assert out["scenario"] == "downstream_metrics_unknown"
    assert out["release_answer"] == "下游指标不足"
    assert out["can_simple_add_green"] is False
    assert out["judgment_criteria"]["downstream_metrics_unknown"] is True
