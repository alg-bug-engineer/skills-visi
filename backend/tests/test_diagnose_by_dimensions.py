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


def _diagnose(problem_types, **overrides):
    data = _sample_data(**overrides)
    cats = DimensionPackService().focus_categories(problem_types)
    res = RuleEngine().diagnose_focused(cats, data)
    return res, [r["id"] for r in res.matched_rules]


def test_congestion_now_triggers_green_insufficient_rule():
    """补标后：拥堵核心规则 rule_green_insufficient 不再被维度门控漏掉。"""
    res, rule_ids = _diagnose(
        ["congestion"],
        signal_plan={"cycle_length": 120, "green_ratio": 0.30},
        evaluation={"delay_index": 2.1, "imbalance_index": 0.35, "green_utilization": 0.42},
        traffic_flow={"saturation_rate": 0.92, "turn_saturation_spread": 0.35},
    )
    assert res.diagnosed
    assert "rule_oversaturation" in rule_ids  # priority 5，仍为首条
    assert "rule_green_insufficient" in rule_ids  # 补标后纳入
    assert res.matched_rules[0]["id"] == "rule_oversaturation"


def test_empty_green_type_triggers_empty_green_rule():
    res, rule_ids = _diagnose(
        ["empty_green"],
        evaluation={"green_utilization": 0.30, "empty_green_rate": 0.40, "imbalance_index": 0.1},
        traffic_flow={"saturation_rate": 0.5},
    )
    assert res.diagnosed
    assert "rule_empty_green" in rule_ids


def test_spillback_type_triggers_spillback_rule():
    res, rule_ids = _diagnose(
        ["spillback"],
        problem_evidence={"metrics": {"spillback_risk_max": 0.85}},
        granularity={"approach_stop_time_max": 78},
    )
    assert res.diagnosed
    assert "rule_spillback_overflow" in rule_ids


def test_conflict_type_triggers_channelization_rule():
    res, rule_ids = _diagnose(
        ["conflict"],
        channelization={"has_mixed_left": True},
        signal_plan={"cycle_length": 120, "green_ratio": 0.25},
    )
    assert res.diagnosed
    assert "rule_channelization_conflict" in rule_ids
