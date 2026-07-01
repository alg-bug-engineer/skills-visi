from intersection_agent.services.dimension_pack_service import DimensionPackService
from intersection_agent.services.runtime_metric_builder import RuntimeMetricBuilder


def _base_data() -> dict:
    return {
        "cognition": {
            "metrics_by_arm": [
                {"dir4_label": "东", "saturation": 0.92},
                {"dir4_label": "西", "saturation": 0.55},
            ],
            "arms": [
                {"dir4_label": "东", "lanes": [{"turn_type": "直"}, {"turn_type": "左"}]},
                {"dir4_label": "西", "lanes": [{"turn_type": "直"}]},
            ],
        },
        "evaluation": {
            "delay_index": 1.88,
            "imbalance_index": 0.35,
            "green_utilization": 0.42,
            "empty_green_rate": 0.22,
        },
        "problem_evidence": {
            "chronic": {"is_chronic": True, "congested_days": 5, "window_days": 7},
            "metrics": {
                "delay_index": 1.88,
                "imbalance_index": 0.35,
                "avg_queue_m": 96.0,
                "max_queue_m": 138.0,
                "queue_storage_ratio_max": 0.82,
                "spillback_risk_max": 0.85,
            },
            "by_turn": [
                {"label": "东左转", "turn_saturation": 1.1, "green_utilization": 0.95},
                {"label": "北左转", "turn_saturation": 0.6, "green_utilization": 0.26},
            ],
            "timing_profile": {
                "cycle_length": 156,
                "ring_diagram": {"available": True},
                "flow_green_fit": {"verdict": "mismatch", "narrative": "流量与绿信比不匹配"},
            },
        },
        "flow_timing_governance": {
            "primary_diagnosis": {
                "turn_balance": {
                    "over": {"label": "东左转", "turn_saturation": 1.1, "green_utilization": 0.95},
                    "spare": {"label": "北左转", "turn_saturation": 0.6, "green_utilization": 0.26},
                }
            }
        },
    }


def test_runtime_profile_hides_empty_green_for_congestion():
    svc = DimensionPackService()
    profile = svc.runtime_profile(["congestion"])
    assert "empty_green_rate" in profile["hidden"]
    assert "delay_index" in profile["primary"]


def test_runtime_profile_empty_green_hides_delay():
    svc = DimensionPackService()
    profile = svc.runtime_profile(["empty_green"])
    assert "delay_index" in profile["hidden"]
    assert "green_utilization" in profile["primary"]


def test_runtime_profile_spillback_primary_queue_metrics():
    svc = DimensionPackService()
    profile = svc.runtime_profile(["spillback"])
    assert "max_queue_m" in profile["primary"]
    assert "imbalance_index" in profile["hidden"]


def test_builder_congestion_primary_metrics():
    builder = RuntimeMetricBuilder()
    items, _profile = builder.build(_base_data(), ["congestion"])
    labels = [i["label"] for i in items]
    assert "延误指数" in labels
    assert "最大排队" in labels
    assert "常发拥堵" in labels
    assert "空放率" not in labels
    assert items[0]["emphasis"] == "primary"


def test_builder_empty_green_prioritizes_green_util():
    builder = RuntimeMetricBuilder()
    items, _ = builder.build(_base_data(), ["empty_green"])
    labels = [i["label"] for i in items]
    assert labels[0] in {"绿灯利用率", "空放率", "北左转绿灯利用", "绿信比匹配"}
    assert "延误指数" not in labels
    assert "最大排队" not in labels
    assert "绿灯利用率" in labels


def test_builder_spillback_prioritizes_queue_and_spillback():
    builder = RuntimeMetricBuilder()
    items, _ = builder.build(_base_data(), ["spillback"])
    labels = [i["label"] for i in items]
    assert labels.index("最大排队") < labels.index("东进口饱和度")
    assert "溢流风险" in labels
    assert "方向失衡" not in labels


def test_builder_conflict_synthesizes_from_user_context():
    builder = RuntimeMetricBuilder()
    data = _base_data()
    user = "东进口左转和直行混行明显，机非冲突突出，相位放行也不顺"
    items, _ = builder.build(data, ["conflict"], user_context=user)
    labels = [i["label"] for i in items]
    assert "渠化匹配" in labels
    assert "机非冲突" in labels
    assert "相位相序" in labels
    assert "东进口饱和度" not in labels
    primary_items = [i for i in items if i["emphasis"] == "primary"]
    assert primary_items
    assert primary_items[0]["label"] in {"渠化匹配", "机非冲突", "相位相序", "冲突类型"}


def test_builder_empty_green_synthesizes_contrast():
    builder = RuntimeMetricBuilder()
    data = _base_data()
    from intersection_agent.models.domain import NluResult, TimePeriod

    nlu = NluResult(
        intersection="会展路与奥体中路路口",
        time_period=TimePeriod(start="17:00", end="19:00", label="晚高峰"),
        directions=["西进口", "东进口"],
        problem_types=["empty_green", "congestion"],
    )
    user = "西进口绿灯经常没车也放行，东进口却排队很长"
    items, _ = builder.build(data, ["empty_green", "congestion"], user_context=user, nlu=nlu)
    labels = [i["label"] for i in items]
    assert "绿灯利用率" in labels
    assert "绿信比" in labels or "绿信比匹配" in labels
    if "东进口饱和度" in labels:
        assert labels.index("绿灯利用率") < labels.index("东进口饱和度")


def test_builder_conflict_uses_matched_rules():
    builder = RuntimeMetricBuilder()
    data = _base_data()
    diagnosis = {
        "matched_rules": [
            {
                "id": "rule_channelization_conflict",
                "name": "渠化与配时冲突",
                "focus_category": "channelization",
                "conclusion": "渠化与配时存在冲突",
            }
        ]
    }
    items, _ = builder.build(data, ["conflict"], diagnosis=diagnosis)
    labels = [i["label"] for i in items]
    assert "渠化匹配" in labels
    if "延误指数" in labels:
        assert labels.index("渠化匹配") < labels.index("延误指数")
