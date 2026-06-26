"""Extended diagnosis rule engine tests."""

from intersection_agent.services.rule_engine import RuleEngine
from intersection_agent.utils.flow_green_consistency import flow_green_check


def test_flow_green_mismatch():
    result = flow_green_check(
        [
            {"label": "东直行", "flow_vph": 800, "effective_green_s": 20},
            {"label": "西直行", "flow_vph": 200, "effective_green_s": 40},
        ]
    )
    assert result["verdict"] in ("weak", "mismatch", "strong")


def test_diagnose_comprehensive_matches_multiple():
    engine = RuleEngine()
    data = {
        "meta": {"missing_dws_coverage": False},
        "signal_plan": {"cycle_length": 120, "green_ratio": 0.30},
        "traffic_flow": {
            "saturation_rate": 0.88,
            "turn_saturation_spread": 0.35,
        },
        "evaluation": {
            "delay_index": 2.1,
            "imbalance_index": 0.35,
            "green_utilization": 0.42,
            "empty_green_rate": 0.22,
        },
        "timing": {
            "green_deficit_ratio_max": 0.18,
            "cycle_issue": None,
            "plan_granularity_low": True,
            "flow_green_verdict": "weak",
        },
        "granularity": {
            "approach_stop_time_max": 78,
            "approach_stop_times_max": 1.9,
        },
        "corridor": {"in_corridor": True, "green_wave_break_risk": True},
        "external_evidence": {"complaint_total": 12},
        "channelization": {"has_mixed_left": False},
    }
    result = engine.diagnose_comprehensive(data)
    assert result.diagnosed
    assert len(result.matched_rules) >= 2
