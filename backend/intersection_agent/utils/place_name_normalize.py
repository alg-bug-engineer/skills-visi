"""Normalize Jinan place/road names corrupted by ASR or LLM."""

from __future__ import annotations

import re

# Common homoglyph / OCR confusions in local road names
_CHAR_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("泩", "泺"),  # 新泺大街 — LLM often outputs 泩
    ("泦", "泺"),
    ("络", "泺"),  # rare typo in 新泺
)

_INTERSECTION_PATTERN = re.compile(
    r"([\u4e00-\u9fff]+?(?:路|街|大道|巷))"
    r"与"
    r"([\u4e00-\u9fff]+?(?:路|街|大道|巷))"
    r"(?:交叉口|路口)?"
)


def normalize_place_names(text: str) -> str:
    """Fix known character confusions in road / intersection names."""
    if not text:
        return text
    out = text
    for wrong, right in _CHAR_REPLACEMENTS:
        out = out.replace(wrong, right)
    return out


def extract_intersection_phrases(text: str) -> list[str]:
    """Pull intersection-like phrases from raw user text (preserves correct chars)."""
    if not text:
        return []
    normalized = normalize_place_names(text)
    seen: set[str] = set()
    results: list[str] = []
    for match in _INTERSECTION_PATTERN.finditer(normalized):
        a, b = match.group(1), match.group(2)
        for phrase in (
            f"{a}与{b}路口",
            f"{b}与{a}路口",
            f"{a}与{b}交叉口",
            f"{b}与{a}交叉口",
        ):
            if phrase not in seen:
                seen.add(phrase)
                results.append(phrase)
    return results
