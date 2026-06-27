"""Tests for experience absorption report and SSE ordering."""

from __future__ import annotations

from intersection_agent.models.domain import DiagnosisResult, NluResult, Session, TimePeriod
from intersection_agent.models.skill import SkillDiff, SkillRecord
from intersection_agent.services.skill_matcher import build_skill_tags
from intersection_agent.skills.absorption_renderer import render_stage_lines
from intersection_agent.skills.experience_absorption import build_absorption_report
from intersection_agent.skills.tag_helpers import formula_hash


def _session(*, with_constraint: bool = True) -> Session:
    nlu = NluResult(
        intersection="测试路口",
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        problem_type="congestion",
        directions=["南北向"],
        user_suggestion="垂直方向不能溢出" if with_constraint else None,
    )
    session = Session(
        nlu=nlu,
        inter_id="inter_001",
        resolved_intersection="测试路口",
        raw_user_context="测试路口，晚高峰南北向拥堵，垂直方向不能溢出",
    )
    session.diagnosis = DiagnosisResult(
        diagnosed=True,
        matched_rules=[
            {
                "id": "rule_a",
                "action": {"formula": "delta = queue * 0.1"},
            }
        ],
    )
    session.data_payload = {
        "quantitative_constraints": {"intent": "max_spillback"},
        "flow_timing_governance": {
            "problems": [{"category": "saturation", "detected": True}],
        },
        "meta": {"data_window": {"source_tier": "dwd_rolling_7d"}},
    }
    return session


def _candidate(session: Session) -> SkillRecord:
    tags = build_skill_tags(
        intersection="测试路口",
        inter_id="inter_001",
        problem_type="congestion",
        time_period_label="晚高峰",
        directions=["南北向"],
        match_keywords=["拥堵"],
        rule_ids=["rule_a"],
        user_constraints=session.nlu.user_suggestion if session.nlu else None,
        quantitative_constraints=session.data_payload.get("quantitative_constraints"),
        suggestion_formula="delta = queue * 0.1",
        issue_codes=["saturation"],
        data_window={"source_tier": "dwd_rolling_7d"},
    )
    return SkillRecord(
        skill_id="skill_inter_001_congestion_晚高峰",
        skill_dir="pkg",
        intersection="测试路口",
        inter_id="inter_001",
        problem_type="congestion",
        time_period_label="晚高峰",
        match_keywords=["拥堵"],
        data_query_spec={"data_window": {"source_tier": "dwd_rolling_7d"}},
        rule_ids=["rule_a"],
        suggestion_formula="delta = queue * 0.1",
        created_at="2026-01-01T00:00:00+00:00",
        user_constraints=session.nlu.user_suggestion if session.nlu else None,
        tags=tags,
    )


def test_build_skill_tags_v2_three_layers():
    tags = build_skill_tags(
        intersection="路口A",
        inter_id="id1",
        problem_type="congestion",
        time_period_label="晚高峰",
        directions=["南北向"],
        match_keywords=["拥堵"],
        rule_ids=["r1"],
        user_constraints="约束",
        quantitative_constraints={"intent": "cap"},
        suggestion_formula="f=1",
        issue_codes=["saturation"],
        data_window={"source_tier": "dwd_rolling_7d"},
        source_utterance_summary="摘要",
        library_count_before=1,
        library_count_after=2,
        version=1,
    )
    assert "match" in tags and "content" in tags and "meta" in tags
    assert tags["match"]["inter_id"] == "id1"
    assert tags["content"]["issue_codes"] == ["saturation"]
    assert tags["meta"]["library_count_after"] == 2
    assert tags["content"]["suggestion_formula_hash"] == formula_hash("f=1")


def test_absorption_report_create():
    session = _session()
    candidate = _candidate(session)
    report = build_absorption_report(
        session=session,
        candidate=candidate,
        existing=None,
        diff=SkillDiff(False, []),
        all_skills=[],
        snapshot_equal=False,
    )
    assert report.action == "CREATE"
    assert report.library_count_before == 0
    assert report.library_count_after == 1
    assert report.tags["meta"]["version"] == 1


def test_absorption_renderer_no_marketing_tone():
    session = _session()
    candidate = _candidate(session)
    report = build_absorption_report(
        session=session,
        candidate=candidate,
        existing=None,
        diff=SkillDiff(False, []),
        all_skills=[],
        snapshot_equal=False,
    )
    lines: list[str] = []
    for stage in ("recap", "retrieve", "compare", "value", "blueprint"):
        lines.extend(render_stage_lines(report, stage))
    joined = "\n".join(lines)
    assert "您" not in joined
    assert "众智成城" not in joined
    assert "收到固化指令" in joined
    assert "左侧" not in joined
    assert "decompose" not in joined.lower()


def test_absorption_sse_stage_order():
    expected = ("recap", "retrieve", "compare", "value", "blueprint")
    assert expected[0] == "recap"
    assert expected[-1] == "blueprint"
