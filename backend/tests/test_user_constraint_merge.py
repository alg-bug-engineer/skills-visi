"""Tests for user constraint merge helper."""

from intersection_agent.services.user_constraint_merge import merge_user_constraints


def test_merge_appends_new_clause():
    merged = merge_user_constraints("绿灯应更长", "垂直方向不能溢出")
    assert merged == "绿灯应更长，垂直方向不能溢出"


def test_merge_dedupes_identical_clauses():
    merged = merge_user_constraints("绿灯应更长", "绿灯应更长，周期不变")
    assert merged == "绿灯应更长，周期不变"


def test_merge_skill_service_build_preserves_both(skill_dir_path):
    from intersection_agent.models.domain import DiagnosisResult, NluResult, Session, TimePeriod
    from intersection_agent.services.skill_service import SkillService

    service = SkillService()
    session = Session()
    session.inter_id = "inter_001"
    session.resolved_intersection = "测试路口"
    session.nlu = NluResult(
        intersection="测试路口",
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        problem_type="congestion",
        directions=["南北向"],
        user_suggestion="绿灯应更长",
    )
    session.diagnosis = DiagnosisResult(
        diagnosed=True,
        matched_rules=[{"id": "rule_green_insufficient", "action": {"formula": "delta = saturation * 20"}}],
    )
    session.raw_user_context = "测试路口晚高峰拥堵"

    first = service.upsert_from_session(session)
    assert first.action == "created"

    session.nlu.user_suggestion = "垂直方向不能溢出"
    updated = service.build_from_session(session)
    assert "绿灯应更长" in (updated.user_constraints or "")
    assert "溢出" in (updated.user_constraints or "")


def test_merge_empty_returns_none():
    assert merge_user_constraints(None, None) is None
    assert merge_user_constraints("", "  ") is None
