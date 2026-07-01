"""suggestion_context：治理建议上下文拼装。"""

from intersection_agent.services.suggestion_context import (
    compose_monitoring_feedback_narrative,
    compose_suggestion_narrative,
    format_upstream_trace_for_prompt,
    is_healthy_monitoring_case,
    narrative_echoes_diagnosis,
    prepare_suggestion_data,
    synthesize_flow_trace_from_upstream,
)


def _sample_upstream_trace():
    return {
        "trees": [
            {
                "approach": "西进口",
                "target": {"inter_id": "T1", "name": "奥体西路与经十路路口"},
                "root": {
                    "inter_id": "U1",
                    "inter_name": "经十路与转山西路路口",
                    "decision": "治理落点",
                    "turn_split": [
                        {"turn": "直行", "share_pct": 67.0},
                        {"turn": "左转", "share_pct": 22.0, "data_gap": False},
                    ],
                    "approach_profiles": [{"turn_saturation_max": 0.73}],
                    "children": [],
                },
            }
        ],
        "governance_points": [
            {
                "approach": "西进口",
                "inter_name": "经十路与转山西路路口",
                "hop": 1,
            }
        ],
    }


def test_synthesize_flow_trace_from_upstream():
    hints = synthesize_flow_trace_from_upstream(_sample_upstream_trace())["governance_hints"]
    assert hints
    assert hints[0]["inter_name"] == "经十路与转山西路路口"
    assert "直行" in hints[0]["turn_split"]


def test_format_upstream_trace_mentions_governance_point():
    text = format_upstream_trace_for_prompt({"upstream_trace": _sample_upstream_trace()})
    assert "经十路与转山西路路口" in text
    assert "治理落点" in text


def test_prepare_suggestion_data_upstream_coordination():
    data = {
        "traffic_flow": {"turn_saturation_max": 1.2, "saturation_rate": 1.1},
        "granularity": {"by_turn": [{"label": "西直行", "turn_saturation": 1.2, "green_utilization": 1.1}]},
        "timing_profile": {},
        "timing": {},
        "upstream_trace": _sample_upstream_trace(),
        "flow_timing_governance": {
            "primary_diagnosis": {"type": "capacity_bottleneck"},
            "problems": [],
        },
    }
    prepared = prepare_suggestion_data(data)
    plan = prepared["flow_timing_governance"]["action_plan"]
    assert plan.get("action_type") == "upstream_coordination"
    assert plan.get("upstream_inter_name")


def test_compose_suggestion_narrative_includes_upstream_and_constraint():
    data = prepare_suggestion_data(
        {
            "meta": {"intersection": "奥体西路与经十路路口", "time_period": {"label": "晚高峰"}},
            "traffic_flow": {},
            "granularity": {
                "by_turn": [
                    {"label": "东左转", "turn_saturation": 1.83, "green_utilization": 1.84},
                    {"label": "西直行", "turn_saturation": 0.03, "green_utilization": 0.35},
                ],
            },
            "timing_profile": {"cycle_length": 120, "flow_green_fit": {"verdict": "mismatch"}},
            "timing": {"cycle_length": 120},
            "upstream_trace": _sample_upstream_trace(),
            "flow_timing_governance": {
                "primary_diagnosis": {
                    "type": "timing_optimizable",
                    "headline": "东左转已过饱和",
                    "lever": "挪绿",
                    "severity": "high",
                    "evidence": [],
                    "structure_limited": False,
                },
                "problems": [],
            },
            "quantitative_constraints": {"narrative": "垂直方向不得溢出"},
        }
    )
    text = compose_suggestion_narrative(
        data,
        user_suggestion="垂直方向不能溢出",
        quantitative_constraints=data.get("quantitative_constraints"),
    )
    assert "经十路与转山西路" in text or "上游" in text
    assert "垂直" in text
    assert "挪绿" not in text or "从" in text
    assert not narrative_echoes_diagnosis(text, data)


def test_is_healthy_monitoring_case_basically_matched():
    assert is_healthy_monitoring_case(
        {"primary_diagnosis": {"type": "basically_matched"}}
    )
    assert not is_healthy_monitoring_case(
        {"primary_diagnosis": {"type": "timing_optimizable"}}
    )


def test_compose_monitoring_feedback_narrative_lists_metrics():
    data = prepare_suggestion_data(
        {
            "meta": {
                "intersection": "会展路与奥体中路路口",
                "time_period": {"label": "晚高峰"},
            },
            "traffic_flow": {"saturation_rate": 0.73},
            "evaluation": {
                "level_of_service_label": "D-临界",
                "imbalance_index": 0.18,
                "green_utilization": 0.62,
            },
            "signal_plan": {"cycle_length": 167},
            "granularity": {
                "by_turn": [
                    {"label": "东直行", "turn_saturation": 0.73, "green_utilization": 0.65},
                ],
            },
            "flow_timing_governance": {
                "primary_diagnosis": {
                    "type": "basically_matched",
                    "headline": "供需与配时基本匹配，未见明显绿灯错配",
                    "lever": "维持现有配时方案，持续监测高峰表现",
                    "evidence": ["最高转向饱和度 0.73"],
                },
                "problems": [],
            },
        }
    )
    text = compose_monitoring_feedback_narrative(data)
    assert "已记录" in text
    assert "0.73" in text
    assert "持续关注" in text
    assert "暂无需调整信控方案" in text
