"""Tests for flow-timing governance service."""

from intersection_agent.services.flow_timing_governance_service import FlowTimingGovernanceService
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
        "timing": {
            "flow_green_verdict": "mismatch",
            "flow_green_tau": -0.2,
        },
        "timing_profile": {
            "flow_green_fit": {
                "verdict": "mismatch",
                "spearman_tau": -0.2,
                "narrative": "高流量转向的有效绿灯占比偏低",
            }
        },
        "problem_evidence": {
            "metrics": {"spillback_risk_max": 0.85},
        },
        "granularity": {
            "by_lane": [
                {"label": "东车道", "lane_saturation": 0.92, "lane_flow": 420, "lane_capacity": 480}
            ],
            "approach_stop_time_max": 78,
        },
    }
    base.update(overrides)
    return base


def test_governance_detects_four_categories():
    svc = FlowTimingGovernanceService()
    report = svc.build(_sample_data())

    assert report["match_verdict"] == "mismatch"
    categories = {p["category"]: p for p in report["problems"]}
    assert categories["saturation"]["detected"] is True
    assert categories["imbalance"]["detected"] is True
    assert categories["empty_green"]["detected"] is True
    assert categories["spillback"]["detected"] is True
    assert "饱和度" in report["summary"]
    assert report.get("expert_rules")
    assert report.get("checklist_refs", {}).get("imbalance") == "service_imbalance"


def test_governance_uses_sustained_metrics():
    svc = FlowTimingGovernanceService()
    data = _sample_data()
    data["sustained_metrics"] = {
        "dimensions": {
            "imbalance_sustained": True,
            "empty_green_sustained": True,
        }
    }
    report = svc.build(data)
    categories = {p["category"]: p for p in report["problems"]}
    assert categories["imbalance"]["detected"] is True
    assert categories["empty_green"]["detected"] is True
    assert any("连续15分钟" in e for e in categories["imbalance"]["evidence"])


def test_governance_data_gaps_when_lane_capacity_missing():
    svc = FlowTimingGovernanceService()
    data = _sample_data(
        granularity={
            "by_lane": [{"label": "东车道", "lane_saturation": 0.8, "lane_flow": 300}],
        }
    )
    report = svc.build(data)
    assert "lane_capacity_missing" in report["data_gaps"]


def test_diagnose_focused_only_saturation_rules():
    engine = RuleEngine()
    data = _sample_data()
    data["traffic_flow"]["saturation_rate"] = 0.92
    result = engine.diagnose_focused(["saturation"], data)
    assert result.diagnosed
    assert all(r.get("focus_category") == "saturation" for r in result.matched_rules)


def test_diagnose_focused_spillback_rule():
    engine = RuleEngine()
    data = _sample_data()
    result = engine.diagnose_focused(["spillback"], data)
    assert result.diagnosed
    assert any(r["id"] == "rule_spillback_overflow" for r in result.matched_rules)
