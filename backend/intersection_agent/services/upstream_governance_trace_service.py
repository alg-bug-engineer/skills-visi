"""上游治理溯源：递归找可信控治理落点（≤2 跳）。"""
from __future__ import annotations

from collections.abc import Callable
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


def build_tree(
    inter_id: str,
    *,
    feeding_dir8: int,
    hop: int,
    window: Any,
    get_profiles: Callable[[str, Any], list[dict[str, Any]]],
    get_upstream: Callable[[str, int, Any], dict[str, Any] | None],
    get_other_approaches: Callable[[str, int], list[int]],
    full_sat: float,
    green_util: float,
    max_hops: int,
    inter_name: str | None = None,
) -> dict[str, Any]:
    profiles = get_profiles(inter_id, window)
    governable = is_governable(profiles, full_sat=full_sat, green_util=green_util)
    node: dict[str, Any] = {
        "inter_id": inter_id,
        "inter_name": inter_name,
        "feeding_dir8": feeding_dir8,
        "hop": hop,
        "approach_profiles": profiles,
        "governable": governable,
        "children": [],
    }
    if governable:
        node["decision"] = "治理落点"
        return node
    if hop >= max_hops:
        node["decision"] = "二跳截止"
        return node
    node["decision"] = "继续上溯"
    for ap in get_other_approaches(inter_id, feeding_dir8):
        up = get_upstream(inter_id, ap, window)
        if not up:
            continue
        child = build_tree(
            up["cor_inter_id"],
            feeding_dir8=up["feeding_dir8"],
            hop=hop + 1,
            window=window,
            get_profiles=get_profiles,
            get_upstream=get_upstream,
            get_other_approaches=get_other_approaches,
            full_sat=full_sat,
            green_util=green_util,
            max_hops=max_hops,
            inter_name=up.get("cor_inter_name"),
        )
        node["children"].append(child)
    return node
