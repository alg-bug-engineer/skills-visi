"""Heuristic problem-type inference from user text (NLU supplement)."""

from __future__ import annotations

ALLOWED = ("congestion", "spillback", "empty_green", "conflict")


def infer_problem_types_from_text(text: str) -> list[str]:
    """Infer problem types from natural phrasing when LLM/mock under-classifies."""
    t = text or ""
    types: list[str] = []

    if any(k in t for k in ("溢出", "外溢", "蔓延", "顶到上游", "排到上游", "溢到")):
        types.append("spillback")
    if any(
        k in t
        for k in (
            "空放",
            "放空",
            "没车",
            "无车",
            "绿灯经常",
            "也放行",
            "绿灯空",
            "绿灯浪费",
            "绿灯放空",
        )
    ):
        types.append("empty_green")
    if any(
        k in t
        for k in (
            "冲突",
            "机非",
            "非机动车",
            "混行",
            "相序",
            "相位",
            "左转和直行",
            "左转与直行",
            "直行混",
        )
    ):
        types.append("conflict")
    if any(k in t for k in ("堵", "拥堵", "排队", "延误", "通行慢", "车多")):
        types.append("congestion")

    return [pt for pt in ALLOWED if pt in types]


def merge_problem_types(llm_types: list[str] | None, text: str) -> list[str]:
    """Union LLM output with text heuristics; keep allowed set only."""
    allowed = set(ALLOWED)
    merged: list[str] = []
    for item in llm_types or []:
        value = str(item).strip()
        if value in allowed and value not in merged:
            merged.append(value)

    for item in infer_problem_types_from_text(text):
        if item not in merged:
            merged.append(item)

    return merged or ["congestion"]
