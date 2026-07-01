"""text_format helpers tests."""

from intersection_agent.models.experience import CognitionEntry, DiagnosisEntry
from intersection_agent.utils.text_format import (
    build_case_summary,
    build_cognition_tags,
    build_solution_summary,
    strip_markdown,
)


def test_strip_markdown_removes_bold():
    assert strip_markdown("主要方向绿灯时长**+0 秒**（综合研判）") == "主要方向绿灯时长+0 秒（综合研判）"


def test_build_solution_summary_prefers_measure():
    line = build_solution_summary(
        "主要方向绿灯时长+8 秒（须结合绿信比与空放情况综合研判）",
        "建议压缩空放",
        "min(x, 20)",
    )
    assert "8 秒" in line
    assert "**" not in line


def test_build_case_summary_composes_paragraph():
    summary = build_case_summary(
        intersection="奥体西路与经十路路口",
        time_period_label="晚高峰",
        cognition=[CognitionEntry(text="西左转排队过长")],
        diagnosis=[DiagnosisEntry(cause="上游来车集中", dimension="demand")],
        solution_summary="为西左转增加有效绿灯约 8 秒",
    )
    assert "奥体西路与经十路路口" in summary
    assert "西左转排队过长" in summary
    assert "上游来车集中" in summary
    assert "8 秒" in summary


def test_build_cognition_tags_dedupes():
    tags = build_cognition_tags(
        {
            "time_period": "晚高峰",
            "directions": ["东进口", "东进口"],
            "movement": "左转",
            "phenomenon": "排队",
        }
    )
    assert tags == ["晚高峰", "东进口", "左转", "排队"]
