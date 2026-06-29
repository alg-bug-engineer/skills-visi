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


def _primary(report: dict) -> dict:
    primary = report.get("primary_diagnosis")
    assert primary is not None
    return primary


def test_primary_timing_optimizable():
    """spread 大 + 高饱和 → 绿灯错配，配时可优化（挪绿灯）。"""
    svc = FlowTimingGovernanceService()
    data = _sample_data()
    data["traffic_flow"]["turn_saturation_max"] = 0.95
    data["traffic_flow"]["turn_saturation_spread"] = 0.42
    data["granularity"]["by_turn"] = [
        {"label": "东直行", "turn_saturation": 0.95, "green_utilization": 0.92},
        {"label": "北左转", "turn_saturation": 0.45, "green_utilization": 0.35},
    ]
    primary = _primary(svc.build(data))

    assert primary["type"] == "timing_optimizable"
    assert primary["severity"] == "high"
    assert "分配不均" in primary["headline"]
    assert "北左转" in primary["headline"]
    assert "35%" in primary["headline"] or "35" in primary["headline"]
    tb = primary.get("turn_balance") or {}
    assert tb.get("spare", {}).get("label") == "北左转"
    assert tb.get("over", {}).get("label") == "东直行"
    assert "绿信比" in primary["lever"]
    assert "让给" in primary["lever"]
    assert primary["structure_limited"] is False
    assert any("饱和度" in line for line in primary["evidence"])


def test_primary_capacity_bottleneck_full_saturation():
    """全饱和（spread 小 + 普遍高）→ 能力瓶颈，出路是非配时手段。"""
    svc = FlowTimingGovernanceService()
    data = _sample_data()
    data["traffic_flow"]["turn_saturation_max"] = 0.95
    data["traffic_flow"]["turn_saturation_spread"] = 0.10
    data["granularity"]["by_turn"] = [
        {"label": "东直行", "turn_saturation": 0.95, "green_utilization": 0.93},
        {"label": "西直行", "turn_saturation": 0.91, "green_utilization": 0.90},
    ]
    primary = _primary(svc.build(data))

    assert primary["type"] == "capacity_bottleneck"
    assert primary["severity"] == "high"
    assert "通行能力" in primary["headline"]
    lever = primary["lever"]
    assert "周期" in lever
    assert "绿波" in lever
    assert "需求" in lever
    # 全饱和场景明确禁止"调配时能解决"的暗示
    assert "调配时能解决" not in lever
    assert "配时可解决" not in lever


def test_primary_structure_limited_overlay():
    """配时可优化但关键转向已触最小绿 → 头牌叠加'触最小绿'。"""
    svc = FlowTimingGovernanceService()
    data = _sample_data()
    data["traffic_flow"]["turn_saturation_max"] = 0.95
    data["traffic_flow"]["turn_saturation_spread"] = 0.42
    data["granularity"]["by_turn"] = [
        {"label": "东直行", "turn_saturation": 0.95, "green_utilization": 0.92},
        {"label": "北左转", "turn_saturation": 0.45, "green_utilization": 0.35},
    ]
    data["timing_profile"]["green_deficit_ratio_max"] = 0.18
    data["timing_profile"]["deficit_turns"] = [
        {"label": "南直行", "green_time_plan": 12.0, "min_green_time": 15.0, "deficit_ratio": 0.18}
    ]
    primary = _primary(svc.build(data))

    assert primary["type"] == "timing_optimizable"
    assert primary["structure_limited"] is True
    assert "触最小绿" in primary["headline"]
    assert "南直行" in primary["headline"]


def test_primary_basically_matched():
    """整体不高 → 基本匹配，维持监测。"""
    svc = FlowTimingGovernanceService()
    data = _sample_data()
    data["traffic_flow"]["turn_saturation_max"] = 0.62
    data["traffic_flow"]["turn_saturation_spread"] = 0.20
    primary = _primary(svc.build(data))

    assert primary["type"] == "basically_matched"
    assert primary["severity"] == "none"
    assert "基本匹配" in primary["headline"]
    assert "维持" in primary["lever"]


def test_primary_falls_back_to_saturation_rate():
    """turn_saturation_max 缺失时回退 saturation_rate，不报错、不输出空证据行。"""
    svc = FlowTimingGovernanceService()
    data = _sample_data(
        traffic_flow={"saturation_rate": 0.95},
    )
    primary = _primary(svc.build(data))

    assert primary["type"] == "capacity_bottleneck"
    assert all(line.strip() for line in primary["evidence"])
    assert any("0.95" in line for line in primary["evidence"])
    # spread 缺失 → 不输出极差证据行
    assert not any("极差" in line for line in primary["evidence"])


def test_summary_leads_with_headline():
    svc = FlowTimingGovernanceService()
    report = svc.build(_sample_data())
    assert report["summary"].startswith(report["primary_diagnosis"]["headline"])


def test_governance_saturation_rebalance_not_blind_add_green():
    """过饱和+空放并存时，饱和度治理不宜一律加绿。"""
    svc = FlowTimingGovernanceService()
    data = _sample_data()
    data["traffic_flow"]["turn_saturation_max"] = 0.92
    report = svc.build(data)
    sat = next(p for p in report["problems"] if p["category"] == "saturation")
    assert sat["detected"] is True
    gov = sat["governance"]
    assert "一律加绿" in gov or "绿信比" in gov or "转给" in gov


def test_governance_capacity_bottleneck_saturation_guidance():
    svc = FlowTimingGovernanceService()
    data = _sample_data()
    data["traffic_flow"]["turn_saturation_max"] = 0.95
    data["traffic_flow"]["turn_saturation_spread"] = 0.08
    data["evaluation"]["green_utilization"] = 0.91
    data["evaluation"]["empty_green_rate"] = 0.05
    data["granularity"]["by_turn"] = [
        {"label": "东直行", "turn_saturation": 0.95, "green_utilization": 0.93},
        {"label": "西直行", "turn_saturation": 0.91, "green_utilization": 0.90},
    ]
    report = svc.build(data)
    sat = next(p for p in report["problems"] if p["category"] == "saturation")
    assert "加绿空间有限" in sat["governance"] or "周期" in sat["governance"]


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
