"""Tests for evidence-backed governance action plans."""

from intersection_agent.services.flow_timing_governance_service import FlowTimingGovernanceService
from intersection_agent.services.governance_action_plan_service import build_action_plan


def _reallocate_data() -> dict:
    return {
        "signal_plan": {"cycle_length": 120},
        "traffic_flow": {
            "turn_saturation_max": 2.74,
            "turn_saturation_spread": 0.55,
            "saturation_rate": 0.92,
        },
        "timing_profile": {
            "cycle_length": 120,
            "flow_green_fit": {
                "verdict": "mismatch",
                "flow_shares": [0.62, 0.18, 0.12, 0.08],
                "green_shares": [0.35, 0.28, 0.22, 0.15],
                "items": [
                    {
                        "label": "北直行",
                        "effective_green_s": 28,
                        "flow_vph": 620,
                    },
                    {
                        "label": "西左转",
                        "effective_green_s": 22,
                        "flow_vph": 180,
                    },
                ],
            },
        },
        "granularity": {
            "by_turn": [
                {"label": "北直行", "turn_saturation": 2.74, "green_utilization": 0.91},
                {"label": "西左转", "turn_saturation": 0.42, "green_utilization": 0.38},
            ],
        },
        "flow_timing_governance": {
            "primary_diagnosis": {
                "type": "timing_optimizable",
                "headline": "绿灯错配",
                "lever": "从低利用转向挪绿",
                "evidence": ["北直行过饱和"],
            },
            "problems": [
                {"category": "saturation", "detected": True},
                {"category": "imbalance", "detected": True},
            ],
        },
    }


def test_reallocate_plan_picks_donor_and_recipient():
    plan = build_action_plan(_reallocate_data())

    assert plan["action_type"] == "reallocate_green"
    assert plan["recipient_turn"]["label"] == "北直行"
    assert plan["donor_turn"]["label"] == "西左转"
    assert 5 <= plan["transfer_seconds"] <= 25
    assert "北直行" in plan["narrative_template"]
    assert "西左转" in plan["narrative_template"]
    assert str(plan["transfer_seconds"]) in plan["narrative_template"]


def test_spillback_overrides_reallocate():
    data = _reallocate_data()
    data["problem_evidence"] = {"metrics": {"spillback_risk_max": 0.88}}
    data["flow_timing_governance"]["problems"].append(
        {"category": "spillback", "detected": True},
    )
    plan = build_action_plan(data)

    assert plan["action_type"] == "spillback_control"
    assert plan["transfer_seconds"] == 0
    assert "溢流" in plan["narrative_template"]


def test_capacity_bottleneck_no_green_delta():
    data = _reallocate_data()
    data["flow_timing_governance"]["primary_diagnosis"]["type"] = "capacity_bottleneck"
    data["granularity"]["by_turn"] = [
        {"label": "北直行", "turn_saturation": 0.95, "green_utilization": 0.93},
        {"label": "西左转", "turn_saturation": 0.91, "green_utilization": 0.90},
    ]
    plan = build_action_plan(data)

    assert plan["action_type"] == "capacity_non_timing"
    assert plan["transfer_seconds"] == 0
    assert "周期" in plan["narrative_template"]


def test_flow_timing_governance_includes_action_plan():
    svc = FlowTimingGovernanceService()
    data = _reallocate_data()
    data.pop("flow_timing_governance")
    data["traffic_flow"]["turn_saturation_max"] = 2.74
    data["traffic_flow"]["turn_saturation_spread"] = 0.42
    report = svc.build(data)

    assert report.get("action_plan")
    assert report["action_plan"]["action_type"] in (
        "reallocate_green",
        "increase_green",
        "guidance_only",
    )
