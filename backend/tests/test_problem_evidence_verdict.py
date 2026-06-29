"""Tests for user-facing problem evidence verdict filtering."""

from intersection_agent.services.problem_evidence_service import _is_display_verdict


def test_internal_methodology_verdict_hidden():
    assert _is_display_verdict("无逐日历史明细，按周一同时段的周内规律分析") is False
    assert _is_display_verdict("") is False
    assert _is_display_verdict("数据不足，暂无法判定常发性拥堵") is False
    assert _is_display_verdict("暂无投诉或现场调研台账，诊断完全基于运行数据") is False
    assert _is_display_verdict("周三同时段历史规律显示该时段运行压力偏高") is True
    assert _is_display_verdict("近7日中5日该时段运行指标超标，属常发性拥堵") is True
