"""Tests for user-facing problem evidence verdict filtering."""

from intersection_agent.services.problem_evidence_service import (
    ProblemEvidenceService,
    _flow_trace_beat_text,
    _is_display_verdict,
)


def test_internal_methodology_verdict_hidden():
    assert _is_display_verdict("无逐日历史明细，按周一同时段的周内规律分析") is False
    assert _is_display_verdict("") is False
    assert _is_display_verdict("数据不足，暂无法判定常发性拥堵") is False
    assert _is_display_verdict("暂无投诉或现场调研台账，诊断完全基于运行数据") is False
    assert _is_display_verdict("周三同时段历史规律显示该时段运行压力偏高") is True
    assert _is_display_verdict("近7日中5日该时段运行指标超标，属常发性拥堵") is True


def test_flow_trace_beat_single_corridor():
    """TC flow_trace_beat：有进口道溯源 → 输出 100 辆口径 beat。"""
    flow_trace = {
        "available": True,
        "entry_traces": [
            {
                "entry": "东进口",
                "entry_max_saturation": 1.73,
                "narrative": "东进口约100辆过境车中，约82辆来自上一路口岔口，以直行为主（82辆）",
            },
        ],
    }
    text = _flow_trace_beat_text(flow_trace)
    assert "岔口" in text
    assert "100辆" in text
    assert "贡献" not in text


def test_flow_trace_beat_absent_when_unavailable():
    assert _flow_trace_beat_text({"available": False}) == ""
    assert _flow_trace_beat_text({}) == ""


def test_diagnosis_story_includes_flow_trace_beat():
    evidence = {
        "chronic": {}, "dow_pattern": {}, "metrics": {},
        "flow_trace": {
            "available": True,
            "entry_traces": [
                {
                    "entry": "东进口",
                    "entry_max_saturation": 1.73,
                    "narrative": "东进口约100辆过境车中，约82辆来自上一路口岔口，以直行为主（82辆）",
                },
            ],
        },
    }
    beats = ProblemEvidenceService._build_diagnosis_story(evidence)
    phases = [b["phase"] for b in beats]
    assert "flow_trace" in phases
