"""Tests for LLM-guided absorption narrative."""

from __future__ import annotations

import pytest

from intersection_agent.models.domain import DiagnosisResult, NluResult, Session, TimePeriod
from intersection_agent.models.skill import SkillDiff, SkillRecord
from intersection_agent.services.skill_matcher import build_skill_tags
from intersection_agent.skills.absorption_narrative_service import (
    AbsorptionNarrativeService,
    contains_banned_narration,
)
from intersection_agent.skills.absorption_renderer import render_stage_lines
from intersection_agent.skills.experience_absorption import build_absorption_report


def _session() -> Session:
    nlu = NluResult(
        intersection="奥体西路与经十路交叉口",
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        problem_type="congestion",
        directions=["南北向"],
        user_suggestion="垂直方向不能明显溢出",
    )
    session = Session(
        nlu=nlu,
        inter_id="011wwe28ctu00001",
        resolved_intersection="奥体西路与经十路交叉口",
        raw_user_context="奥体西路与经十路交叉口，晚高峰南北向经常拥堵，垂直方向不能明显溢出",
    )
    session.diagnosis = DiagnosisResult(
        diagnosed=True,
        matched_rules=[{"id": "rule_saturation", "action": {"formula": "delta = queue * 0.1"}}],
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
        intersection="奥体西路与经十路交叉口",
        inter_id="011wwe28ctu00001",
        problem_type="congestion",
        time_period_label="晚高峰",
        directions=["南北向"],
        match_keywords=["拥堵"],
        rule_ids=["rule_saturation"],
        user_constraints=session.nlu.user_suggestion if session.nlu else None,
        quantitative_constraints=session.data_payload.get("quantitative_constraints"),
        suggestion_formula="delta = queue * 0.1",
        issue_codes=["saturation"],
        data_window={"source_tier": "dwd_rolling_7d"},
    )
    return SkillRecord(
        skill_id="skill_test",
        skill_dir="pkg",
        intersection="奥体西路与经十路交叉口",
        inter_id="011wwe28ctu00001",
        problem_type="congestion",
        time_period_label="晚高峰",
        match_keywords=["拥堵"],
        data_query_spec={"data_window": {"source_tier": "dwd_rolling_7d"}},
        rule_ids=["rule_saturation"],
        suggestion_formula="delta = queue * 0.1",
        created_at="2026-01-01T00:00:00+00:00",
        user_constraints=session.nlu.user_suggestion if session.nlu else None,
        tags=tags,
    )


def test_build_experience_points_include_user_constraint():
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
    joined = " ".join(report.experience_points)
    assert "溢出" in joined or "垂直方向" in joined


def test_renderer_has_no_ui_meta_or_decompose():
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
    assert render_stage_lines(report, "decompose") == []
    lines: list[str] = []
    for stage in ("recap", "retrieve", "compare", "value", "blueprint"):
        lines.extend(render_stage_lines(report, stage))
    joined = "\n".join(lines)
    assert not contains_banned_narration(joined)
    assert "识别本次沉淀" in joined or "溢出" in joined


@pytest.mark.asyncio
async def test_narrative_service_mock_llm():
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
    service = AbsorptionNarrativeService()
    narrative = await service.generate(report, session)
    recap = "\n".join(narrative.lines_for("recap", report))
    assert not contains_banned_narration(recap)
    assert "溢出" in recap or report.experience_points
