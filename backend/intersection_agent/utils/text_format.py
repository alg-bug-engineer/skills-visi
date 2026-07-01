"""Plain-text formatting helpers for user-facing experience and case content."""

from __future__ import annotations

import re
from typing import Any

from intersection_agent.models.experience import CognitionEntry, DiagnosisEntry

_MARKDOWN_BOLD = re.compile(r"\*\*(.+?)\*\*")
_WHITESPACE = re.compile(r"\s+")


def strip_markdown(text: str | None) -> str:
    """Remove common markdown markers for UI display."""
    if not text:
        return ""
    plain = _MARKDOWN_BOLD.sub(r"\1", text)
    return _WHITESPACE.sub(" ", plain).strip()


def build_cognition_structured_from_nlu(
    nlu: Any,
    fallback_text: str = "",
) -> dict[str, Any]:
    """Fallback structured cognition when LLM output is missing."""
    time_period = ""
    directions: list[str] = []
    if nlu:
        if getattr(nlu, "time_period", None) and nlu.time_period:
            time_period = str(getattr(nlu.time_period, "label", "") or "")
        if getattr(nlu, "directions", None):
            directions = [str(d) for d in nlu.directions if d]

    phenomenon = fallback_text or "交通异常"
    return {
        "time_period": time_period,
        "directions": directions,
        "movement": "",
        "phenomenon": phenomenon,
        "summary": fallback_text or phenomenon,
    }


def build_cognition_tags(structured: dict[str, Any]) -> list[str]:
    """Turn structured cognition fields into display tags."""
    tags: list[str] = []
    if period := str(structured.get("time_period") or "").strip():
        tags.append(period)
    for direction in structured.get("directions") or []:
        if direction:
            tags.append(str(direction))
    if movement := str(structured.get("movement") or "").strip():
        tags.append(movement)
    if phenomenon := str(structured.get("phenomenon") or "").strip():
        tags.append(phenomenon)
    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def build_case_summary(
    *,
    intersection: str,
    time_period_label: str,
    cognition: list[CognitionEntry],
    diagnosis: list[DiagnosisEntry],
    solution_summary: str,
) -> str:
    """One-paragraph case summary for the intersection case library."""
    location = intersection or "该路口"
    period = time_period_label or "日常"
    cognition_bits = [c.text for c in cognition if c.text]
    diagnosis_bits = [d.cause for d in diagnosis if d.cause]

    parts: list[str] = [f"{location}在{period}存在以下问题："]
    if cognition_bits:
        parts.append("；".join(cognition_bits[:3]))
    else:
        parts.append("用户反馈交通运行异常")
    if diagnosis_bits:
        parts.append(f"可能原因包括{'、'.join(diagnosis_bits[:2])}")
    if solution_summary:
        parts.append(f"固化方案为{solution_summary}")
    return strip_markdown("。".join(parts) + "。")


def build_solution_summary(
    solution_measure: str | None,
    suggestion_narrative: str | None,
    suggestion_formula: str | None,
) -> str:
    """Plain-language solution line for case cards (no markdown, no raw formula)."""
    if solution_measure:
        return strip_markdown(solution_measure)
    if suggestion_narrative:
        return strip_markdown(suggestion_narrative)[:160]
    if suggestion_formula:
        return f"量化参考：{suggestion_formula}"
    return "已固化治理方案，详见技能包"
