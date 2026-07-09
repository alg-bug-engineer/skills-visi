"""Region-level deterministic optimization orchestration.

The vendored codebase does not contain a mature standalone region optimizer.
This layer keeps region execution deterministic by composing corridor and
standalone-intersection optimizers, then summarizing common KPIs.
"""

from __future__ import annotations

from typing import Any

from optimization.corridor_optimizer import optimize_corridor
from optimization.intersection_optimizer import optimize_intersection
from preprocessing import prepare_region_request, resolve_intersection_id


def optimize_region(request: dict[str, Any]) -> dict[str, Any]:
    """Optimize all corridors and standalone intersections in one region."""
    prepared = prepare_region_request(request)
    corridor_plans = []
    intersection_plans = []

    for corridor in prepared.get("corridors", []):
        if isinstance(corridor, dict):
            corridor_plans.append(optimize_corridor(corridor))

    covered_intersection_ids = _corridor_intersection_ids(prepared.get("corridors", []))
    for intersection in prepared.get("intersections", []):
        if not isinstance(intersection, dict):
            continue
        inter_id = resolve_intersection_id(intersection)
        if inter_id and inter_id in covered_intersection_ids:
            continue
        intersection_plans.append(optimize_intersection(intersection))

    return {
        "plan_type": "region_optimization",
        "region_id": prepared.get("region_id", "UNKNOWN"),
        "corridor_plans": corridor_plans,
        "intersection_plans": intersection_plans,
        "kpis": _summarize_region(corridor_plans, intersection_plans),
        "meta": {
            "algorithm": "deterministic_region_composition",
            "version": "0.1.0",
            "notes": ["区域层按干线优先、独立路口补充的方式组合确定性优化结果。"],
        },
    }


def _corridor_intersection_ids(corridors: list[Any]) -> set[str]:
    ids: set[str] = set()
    for corridor in corridors:
        if not isinstance(corridor, dict):
            continue
        for inter_id in corridor.get("intersection_ids") or []:
            ids.add(str(inter_id))
        for intersection in corridor.get("intersections") or []:
            if isinstance(intersection, dict):
                inter_id = resolve_intersection_id(intersection)
                if inter_id:
                    ids.add(inter_id)
    return ids


def _summarize_region(
    corridor_plans: list[dict[str, Any]],
    intersection_plans: list[dict[str, Any]],
) -> dict[str, Any]:
    bandwidths = []
    delays = []
    for plan in corridor_plans:
        coordination = plan.get("coordination") or {}
        if coordination.get("bandwidth_s") is not None:
            bandwidths.append(float(coordination["bandwidth_s"]))
        if coordination.get("total_delay_s") is not None:
            delays.append(float(coordination["total_delay_s"]))

    cycles = [
        float(plan["cycleTime"])
        for plan in intersection_plans
        if plan.get("cycleTime") is not None
    ]
    return {
        "corridor_count": len(corridor_plans),
        "standalone_intersection_count": len(intersection_plans),
        "avg_corridor_bandwidth_s": round(sum(bandwidths) / len(bandwidths), 2)
        if bandwidths
        else 0.0,
        "total_corridor_delay_s": round(sum(delays), 2),
        "avg_standalone_cycle_s": round(sum(cycles) / len(cycles), 2) if cycles else 0.0,
    }
