"""上游治理溯源：递归找可信控治理落点（≤2 跳）。"""
from __future__ import annotations

from typing import Any


def is_governable(
    profiles: list[dict[str, Any]], *, full_sat: float, green_util: float
) -> bool:
    """有信控空间 = 非四向全饱和，或任一进口道绿灯利用率有空槽。"""
    if not profiles:
        return False
    has_slack_dir = any((p.get("turn_saturation_max") or 0.0) < full_sat for p in profiles)
    has_empty_green = any(
        p.get("green_util_min") is not None and p["green_util_min"] < green_util
        for p in profiles
    )
    return has_slack_dir or has_empty_green
