"""人工调查问题类型与时段枚举。"""

from __future__ import annotations

SURVEY_PROBLEM_TYPES: tuple[str, ...] = (
    "空放",
    "溢出",
    "人车冲突",
    "过饱和",
    "失衡",
    "车车冲突",
    "机非冲突",
    "行人闯红灯",
    "车道利用率低",
    "变道干扰",
    "出口临停",
)

TIME_PERIODS: tuple[str, ...] = ("早高峰", "晚高峰", "平峰", "夜间")

_PROBLEM_TYPE_SET = frozenset(SURVEY_PROBLEM_TYPES)
_TIME_PERIOD_SET = frozenset(TIME_PERIODS)


def split_problem_types(full_problem_text: str) -> list[str]:
    """将 full_problem 按顿号拆分为问题类型列表。"""
    parts = [p.strip() for p in (full_problem_text or "").split("、")]
    return [p for p in parts if p]


def validate_problem_type(value: str) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if text in _PROBLEM_TYPE_SET:
        return text
    return None


def validate_time_period(value: str) -> str | None:
    text = (value or "").strip()
    if text in _TIME_PERIOD_SET:
        return text
    return None
