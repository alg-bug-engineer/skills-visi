"""Tests for problem-type aware verification narrative."""

from intersection_agent.utils.problem_type_narrative import (
    build_conflict_story_beats,
    build_empty_green_story_beats,
    build_problem_diagnosis_story,
    infer_mixed_turn_approaches,
    resolve_primary_problem_type,
)


def test_resolve_primary_conflict_over_congestion():
    assert resolve_primary_problem_type(["congestion", "conflict"]) == "conflict"
    assert resolve_primary_problem_type(["empty_green", "congestion"]) == "empty_green"


def test_infer_mixed_turn_from_cognition_arms():
    cognition = {
        "arms": [
            {"dir4_label": "东", "lanes": [{"turn_type": "左"}, {"turn_type": "直"}]},
            {"dir4_label": "西", "lanes": [{"turn_type": "直"}]},
        ]
    }
    assert infer_mixed_turn_approaches(cognition) == ["东进口"]


def test_conflict_story_from_user_description():
    user = "东进口左转和直行混行明显，机非冲突突出，相位放行也不顺"
    beats = build_conflict_story_beats(
        {"timing_profile": {"flow_green_fit": {"verdict": "mismatch", "narrative": "流量与绿信比不匹配"}}},
        user_context=user,
        data_payload={"cognition": {"arms": [{"dir4_label": "东", "lanes": [{"turn_type": "左"}, {"turn_type": "直"}]}]}},
    )
    phases = {b["phase"] for b in beats}
    assert "conflict_channel" in phases
    assert "conflict_phase" in phases
    assert "conflict_nonmotor" in phases
    titles = {b["title"] for b in beats}
    assert "渠化匹配" in titles
    assert "机非冲突" in titles


def test_conflict_diagnosis_story_excludes_congestion_metrics():
    evidence = {
        "chronic": {"is_chronic": True, "verdict": "近7日中5日该时段运行指标超标，属常发性拥堵"},
        "dow_pattern": {"verdict": "周三同时段历史规律显示该时段运行压力偏高"},
        "metrics": {"saturation_rate": 0.73, "delay_index": 0.84, "level_of_service_label": "D"},
    }
    beats = build_problem_diagnosis_story(
        evidence,
        problem_types=["conflict"],
        user_context="东进口左转直行混行，机非冲突",
        data_payload={
            "cognition": {
                "arms": [{"dir4_label": "东", "lanes": [{"turn_type": "左"}, {"turn_type": "直"}]}]
            }
        },
    )
    phases = [b["phase"] for b in beats]
    assert "metrics" not in phases
    assert "chronic" not in phases
    assert any(p.startswith("conflict") for p in phases)


def test_empty_green_story_contrast_from_user_text():
    user = "西进口绿灯经常没车也放行，东进口却排队很长"
    beats = build_empty_green_story_beats(
        {
            "metrics": {"green_utilization": 0.53},
            "by_turn": [{"label": "西直行", "green_utilization": 0.42}],
            "timing_profile": {"flow_green_fit": {"verdict": "mismatch", "narrative": "流量与绿信比偏差"}},
        },
        user_context=user,
        nlu_directions=["西进口", "东进口"],
    )
    phases = {b["phase"] for b in beats}
    assert "empty_green_util" in phases
    assert "empty_green_contrast" in phases
    contrast = next(b for b in beats if b["phase"] == "empty_green_contrast")
    assert "西进口" in contrast["text"]
    assert "东进口" in contrast["text"]


def test_empty_green_diagnosis_story_no_saturation_metrics_phase():
    evidence = {
        "metrics": {"green_utilization": 0.53, "saturation_rate": 0.73, "delay_index": 0.84},
        "chronic": {"is_chronic": True, "congested_days": 5, "window_days": 7},
    }
    beats = build_problem_diagnosis_story(
        evidence,
        problem_types=["empty_green", "congestion"],
        user_context="西进口绿灯经常没车也放行",
        nlu_directions=["西进口", "东进口"],
    )
    phases = [b["phase"] for b in beats]
    assert "metrics" not in phases
    assert "empty_green_util" in phases or "empty_green_contrast" in phases
