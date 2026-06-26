"""Skill matcher unit tests."""

from intersection_agent.models.domain import NluResult, TimePeriod
from intersection_agent.models.skill import SkillRecord
from intersection_agent.services.skill_matcher import build_skill_tags, match_skill


def _skill(
    *,
    inter_id: str = "inter_001",
    directions: list[str] | None = None,
    user_constraints: str | None = None,
) -> SkillRecord:
    directions = directions or ["南北向"]
    tags = build_skill_tags(
        intersection="测试路口",
        inter_id=inter_id,
        problem_type="congestion",
        time_period_label="晚高峰",
        directions=directions,
        match_keywords=["拥堵"],
        rule_ids=["rule_a"],
        user_constraints=user_constraints,
        quantitative_constraints=None,
    )
    return SkillRecord(
        skill_id=f"skill_{inter_id}_congestion_晚高峰",
        skill_dir="pkg",
        intersection="测试路口",
        inter_id=inter_id,
        problem_type="congestion",
        time_period_label="晚高峰",
        match_keywords=["拥堵"],
        data_query_spec={},
        rule_ids=["rule_a"],
        suggestion_formula="delta = 1",
        created_at="2026-01-01T00:00:00+00:00",
        user_constraints=user_constraints,
        tags=tags,
    )


def _nlu(
    *,
    directions: list[str] | None = None,
    user_suggestion: str | None = None,
) -> NluResult:
    return NluResult(
        intersection="测试路口",
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        problem_type="congestion",
        directions=directions or ["南北向"],
        user_suggestion=user_suggestion,
    )


def test_match_without_user_constraints():
    skill = _skill(user_constraints="绿灯应更长")
    result = match_skill([skill], _nlu(user_suggestion=None), "inter_001", "晚高峰拥堵")
    assert result.matched
    assert result.skill is skill


def test_match_with_same_constraints():
    skill = _skill(user_constraints="绿灯应更长")
    result = match_skill(
        [skill],
        _nlu(user_suggestion="绿灯应更长"),
        "inter_001",
        "晚高峰拥堵 绿灯应更长",
    )
    assert result.matched


def test_constraint_mismatch():
    skill = _skill(user_constraints="绿灯应更长")
    result = match_skill(
        [skill],
        _nlu(user_suggestion="绿灯不超过10秒"),
        "inter_001",
        "晚高峰拥堵 绿灯不超过10秒",
    )
    assert not result.matched
    assert result.reason == "constraint_mismatch"


def test_new_constraint_on_skill_without_constraints():
    skill = _skill(user_constraints=None)
    result = match_skill(
        [skill],
        _nlu(user_suggestion="垂直方向不能溢出"),
        "inter_001",
        "晚高峰拥堵",
    )
    assert not result.matched
    assert result.reason == "constraint_mismatch"


def test_direction_mismatch():
    skill = _skill(directions=["南北向"])
    result = match_skill(
        [skill],
        _nlu(directions=["东西向"]),
        "inter_001",
        "晚高峰东西向拥堵",
    )
    assert not result.matched
    assert result.reason == "direction_mismatch"
