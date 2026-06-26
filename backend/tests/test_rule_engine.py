"""Rule engine tests."""

from intersection_agent.services.rule_engine import RuleEngine, evaluate_formula, resolve_metric


def test_resolve_metric():
    data = {"traffic_flow": {"saturation_rate": 0.9}, "signal_plan": {"green_ratio": 0.3}}
    assert resolve_metric("traffic_flow.saturation_rate", data) == 0.9


def test_rule_green_insufficient_matches():
    engine = RuleEngine()
    data = {
        "meta": {"missing_dws_coverage": False},
        "signal_plan": {"cycle_length": 120, "green_ratio": 0.30},
        "traffic_flow": {"saturation_rate": 0.88},
        "evaluation": {"delay_index": 2.1, "imbalance_index": 0.2},
        "congestion_index": {"delay_index": 2.1},
        "channelization": {"has_mixed_left": False, "turn_types": ""},
    }
    result = engine.diagnose(data, "congestion")
    assert result.diagnosed
    rule_id = result.matched_rules[0]["id"]
    assert rule_id in ("rule_oversaturation", "rule_green_insufficient")


def test_no_match():
    engine = RuleEngine()
    data = {
        "meta": {"missing_dws_coverage": False},
        "signal_plan": {"cycle_length": 120, "green_ratio": 0.45},
        "traffic_flow": {"saturation_rate": 0.5},
        "evaluation": {"delay_index": 1.0, "imbalance_index": 0.1},
        "channelization": {"has_mixed_left": False, "turn_types": ""},
    }
    result = engine.diagnose(data, "congestion")
    assert not result.diagnosed


def test_evaluate_formula():
    data = {
        "traffic_flow": {"saturation_rate": 0.9},
        "signal_plan": {"cycle_length": 120},
    }
    formula = "min(traffic_flow.saturation_rate * signal_plan.cycle_length * 0.15, 20)"
    delta = evaluate_formula(formula, data)
    assert delta == 16
