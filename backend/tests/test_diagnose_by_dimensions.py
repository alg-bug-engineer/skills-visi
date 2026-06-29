"""问题类型 → 维度包 → 聚焦诊断 的集成校验。"""

from intersection_agent.services.dimension_pack_service import DimensionPackService
from intersection_agent.services.rule_engine import RuleEngine


def _sample_data(**overrides) -> dict:
    base = {
        "meta": {"missing_dws_coverage": False},
        "signal_plan": {"cycle_length": 120, "green_ratio": 0.30},
        "traffic_flow": {
            "saturation_rate": 0.88,
            "turn_saturation_spread": 0.35,
            "lane_saturation_max": 0.92,
            "lane_capacity_min": 450.0,
        },
        "evaluation": {
            "delay_index": 2.1,
            "imbalance_index": 0.35,
            "green_utilization": 0.42,
            "empty_green_rate": 0.22,
        },
        "problem_evidence": {
            "metrics": {"spillback_risk_max": 0.85},
        },
        "granularity": {
            "approach_stop_time_max": 78,
        },
    }
    base.update(overrides)
    return base


def test_pipeline_uses_focused_categories():
    data = _sample_data()
    cats = DimensionPackService().focus_categories(["spillback"])
    res = RuleEngine().diagnose_focused(cats, data)
    rule_ids = [r["id"] for r in res.matched_rules]
    assert "rule_spillback_overflow" in rule_ids
    assert "rule_empty_green" not in rule_ids  # 未激活的类目不命中


def test_empty_green_pack_activates_empty_green_rule():
    data = _sample_data()
    data["evaluation"]["empty_green_rate"] = 0.40
    data["evaluation"]["green_utilization"] = 0.30
    cats = DimensionPackService().focus_categories(["empty_green"])
    res = RuleEngine().diagnose_focused(cats, data)
    rule_ids = [r["id"] for r in res.matched_rules]
    assert "rule_spillback_overflow" not in rule_ids
