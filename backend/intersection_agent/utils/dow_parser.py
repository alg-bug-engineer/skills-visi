"""Parse explicit day-of-week mentions from user text."""

from __future__ import annotations

import re

from intersection_agent.utils.direction_groups import DOW_LABELS

_DOW_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"每周?一"), 1),
    (re.compile(r"每周?二"), 2),
    (re.compile(r"每周?三"), 3),
    (re.compile(r"每周?四"), 4),
    (re.compile(r"每周?五"), 5),
    (re.compile(r"每周?六"), 6),
    (re.compile(r"每周?日|每周?天|每周?末"), 7),
    (re.compile(r"周[一二三四五六日天]"), 0),
]


def extract_explicit_dow(text: str) -> int | None:
    """Return ISO weekday 1-7 if user explicitly mentions a weekday."""
    cleaned = str(text or "")
    for pattern, dow in _DOW_PATTERNS:
        match = pattern.search(cleaned)
        if not match:
            continue
        if dow:
            return dow
        token = match.group(0)
        mapping = {
            "周一": 1,
            "周二": 2,
            "周三": 3,
            "周四": 4,
            "周五": 5,
            "周六": 6,
            "周日": 7,
            "周天": 7,
            "周天": 7,
        }
        for key, value in mapping.items():
            if key in token:
                return value
    return None


def dow_label(dow: int) -> str:
    """ISO weekday to Chinese label."""
    return DOW_LABELS.get(dow, f"周{dow}")
