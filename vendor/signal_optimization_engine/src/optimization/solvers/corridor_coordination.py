"""干线协调方案生成：路由到 MVP 或完整求解器.

当请求包含 `intersections`（每路口配时数据）时使用完整求解器；
否则退化到 MVP（仅需路口 ID + links/间距 + 约束）。
"""

from __future__ import annotations

from typing import Any

from optimization.solvers.coordination import (
    solve_arterial_two_way_max_bandwidth,
    solve_corridor_full,
)
from optimization.solvers.coordination.arterial_bandwidth import ArterialLink
from optimization.solvers.plan_metadata import empty_plan_meta


def generate_corridor_coordination_plan(request: dict[str, Any]) -> dict[str, Any]:
    """单条干线协调方案生成入口."""
    corridor_id = str(request.get("corridor_id") or "").strip()
    raw_ids = request.get("intersection_ids")
    if isinstance(raw_ids, list):
        intersection_ids = [str(x) for x in raw_ids if x is not None]
    else:
        intersection_ids = []

    constraints = request.get("constraints") if isinstance(request.get("constraints"), dict) else {}
    design_speed = float(constraints.get("design_speed_kmh", 40.0))
    min_cycle_s = float(constraints.get("min_cycle_s", 60.0))
    max_cycle_s = float(constraints.get("max_cycle_s", 120.0))
    min_green_s = float(constraints.get("min_green_s", 12.0))
    max_green_s = float(constraints.get("max_green_s", 45.0))
    lost_time_s = float(constraints.get("lost_time_s", 0.0))
    default_spacing = float(constraints.get("default_link_spacing_m", 400.0))
    progression_weight = float(constraints.get("progression_weight", 0.08))
    strategy = str(constraints.get("strategy", "bidirectional"))
    target_non_coord_intensity = float(constraints.get("target_non_coord_intensity", 0.8))
    double_stop_weight = float(constraints.get("double_stop_weight", 0.5))
    sat_raw = constraints.get("saturation_x")
    saturation_x: list[float] | None = None
    if isinstance(sat_raw, list) and sat_raw:
        saturation_x = [float(v) for v in sat_raw]

    links: list[ArterialLink] | None = _parse_links(
        request.get("links"),
        n_intersections=len(intersection_ids),
        design_speed_kmh=design_speed,
        default_spacing_m=default_spacing,
    )

    if links is None:
        return _error_response(corridor_id, intersection_ids, design_speed,
                               "无法构建路段：请提供 links 或 default_link_spacing_m（≥2 路口）。")

    intersections_data = request.get("intersections")
    has_rich_data = (
        isinstance(intersections_data, list)
        and len(intersections_data) > 0
        and any(
            "phasePlanOfTimeList" in ix or "phaseStageInfoList" in ix
            for ix in intersections_data
            if isinstance(ix, dict)
        )
    )

    if has_rich_data:
        return _solve_full(
            corridor_id, intersection_ids, intersections_data,
            links, min_cycle_s, max_cycle_s, design_speed, strategy,
            target_non_coord_intensity, progression_weight, double_stop_weight,
        )

    return _solve_mvp(
        corridor_id, intersection_ids, links,
        min_cycle_s, max_cycle_s, min_green_s, max_green_s,
        lost_time_s, saturation_x, progression_weight, design_speed,
    )


# ---------------------------------------------------------------------------
# 完整求解器路径
# ---------------------------------------------------------------------------

def _solve_full(
    corridor_id: str,
    intersection_ids: list[str],
    intersections: list[dict[str, Any]],
    links: list[ArterialLink],
    min_cycle_s: float,
    max_cycle_s: float,
    design_speed: float,
    strategy: str,
    target_non_coord_intensity: float,
    progression_weight: float,
    double_stop_weight: float,
) -> dict[str, Any]:
    coord_phase_ids = [
        (item.get("coord_phase_id") if isinstance(item, dict) else None)
        for item in intersections
    ]
    solved = solve_corridor_full(
        intersection_ids,
        intersections,
        links,
        min_cycle_s=min_cycle_s,
        max_cycle_s=max_cycle_s,
        strategy=strategy,
        target_non_coord_intensity=target_non_coord_intensity,
        coord_phase_ids=coord_phase_ids,
        progression_weight=progression_weight,
        double_stop_weight=double_stop_weight,
    )
    if not solved.get("ok"):
        return _error_response(corridor_id, intersection_ids, design_speed,
                               str(solved.get("error", "full solver failed")))

    nodes_out = []
    for node in solved["nodes"]:
        nodes_out.append({
            "intersection_id": node["intersection_id"],
            "offset_s": node["offset_s"],
            "main_coordination_offset_s": node.get("main_coordination_offset_s", node["offset_s"]),
            "main_coordination_phase_id": node.get("main_coordination_phase_id", ""),
            "cycle_s": node["cycle_s"],
            "coordinated_green_s": node["coordinated_green_s"],
            "green_ratio": node["green_ratio"],
            "webster_delay_s": node.get("webster_delay_s", 0.0),
            "phase_stage_timing_list": node.get("phase_stage_timing_list", []),
            "first_optimization": node.get("first_optimization"),
            "second_optimization": node.get("second_optimization"),
        })

    meta = empty_plan_meta("corridor_coordination_optimizer", "1.0.0") | {
        "strategy": solved.get("strategy"),
        "solver": solved.get("meta", {}),
        "kpis": solved.get("kpis", {}),
    }

    return {
        "plan_type": "corridor_coordination",
        "corridor_id": corridor_id or "UNKNOWN",
        "coordination": {
            "bandwidth_s": solved["bandwidth_s"],
            "bandwidth_forward_s": solved.get("bandwidth_forward_s", 0.0),
            "bandwidth_reverse_s": solved.get("bandwidth_reverse_s", 0.0),
            "design_speed_kmh": design_speed,
            "cycle_s": solved["cycle_s"],
            "total_delay_s": solved["total_delay_s"],
            "strategy": solved.get("strategy", "bidirectional"),
            "nodes": nodes_out,
        },
        "meta": meta,
    }


# ---------------------------------------------------------------------------
# MVP 求解器路径（向后兼容）
# ---------------------------------------------------------------------------

def _solve_mvp(
    corridor_id: str,
    intersection_ids: list[str],
    links: list[ArterialLink],
    min_cycle_s: float,
    max_cycle_s: float,
    min_green_s: float,
    max_green_s: float,
    lost_time_s: float,
    saturation_x: list[float] | None,
    progression_weight: float,
    design_speed: float,
) -> dict[str, Any]:
    solved = solve_arterial_two_way_max_bandwidth(
        intersection_ids,
        links,
        min_cycle_s=min_cycle_s,
        max_cycle_s=max_cycle_s,
        min_green_s=min_green_s,
        max_green_s=max_green_s,
        lost_time_s=lost_time_s,
        saturation_x=saturation_x,
        progression_weight=progression_weight,
    )

    if not solved.get("ok"):
        return _error_response(corridor_id, intersection_ids, design_speed,
                               str(solved.get("error", "unknown")))

    nodes_out = []
    for node in solved["nodes"]:
        nodes_out.append({
            "intersection_id": node["intersection_id"],
            "offset_s": node["offset_s"],
            "main_coordination_offset_s": node["offset_s"],
            "main_coordination_phase_id": "",
            "cycle_s": node["cycle_s"],
            "coordinated_green_s": node["coordinated_green_s"],
            "green_ratio": node["green_ratio"],
            "webster_delay_s": node["webster_delay_s"],
            "phase_stage_timing_list": [],
        })

    meta = empty_plan_meta("corridor_coordination_optimizer", "0.2.0-mvp") | {
        "strategy": solved.get("strategy"),
        "solver": solved.get("meta", {}),
        "kpis": solved.get("kpis", {}),
    }

    return {
        "plan_type": "corridor_coordination",
        "corridor_id": corridor_id or "UNKNOWN",
        "coordination": {
            "bandwidth_s": solved["bandwidth_s"],
            "bandwidth_forward_s": 0.0,
            "bandwidth_reverse_s": 0.0,
            "design_speed_kmh": design_speed,
            "cycle_s": solved["cycle_s"],
            "total_delay_s": solved["total_delay_s"],
            "strategy": solved.get("strategy", "bidirectional_max_bandwidth"),
            "nodes": nodes_out,
        },
        "meta": meta,
    }


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _error_response(
    corridor_id: str,
    intersection_ids: list[str],
    design_speed: float,
    error_msg: str,
) -> dict[str, Any]:
    return {
        "plan_type": "corridor_coordination",
        "corridor_id": corridor_id or "UNKNOWN",
        "coordination": {
            "bandwidth_s": 0.0,
            "bandwidth_forward_s": 0.0,
            "bandwidth_reverse_s": 0.0,
            "design_speed_kmh": design_speed,
            "cycle_s": None,
            "total_delay_s": None,
            "strategy": "bidirectional",
            "nodes": [
                {"intersection_id": iid, "offset_s": 0.0, "notes": error_msg}
                for iid in intersection_ids
            ],
        },
        "meta": empty_plan_meta("corridor_coordination_optimizer", "1.0.0")
        | {"notes": [error_msg]},
    }


def _parse_links(
    raw: Any,
    *,
    n_intersections: int,
    design_speed_kmh: float,
    default_spacing_m: float,
) -> list[ArterialLink] | None:
    """返回 ArterialLink 列表；无法构建时返回 None."""
    if n_intersections < 2:
        return []
    if isinstance(raw, list) and len(raw) == n_intersections - 1:
        out: list[ArterialLink] = []
        for item in raw:
            if not isinstance(item, dict):
                return None
            dist = item.get("distance_m", item.get("length_m"))
            if dist is None:
                return None
            d_m = float(dist)
            v_f = float(item.get("forward_speed_kmh", design_speed_kmh))
            v_r = item.get("reverse_speed_kmh")
            out.append(
                ArterialLink(
                    distance_m=d_m,
                    forward_speed_kmh=v_f,
                    reverse_speed_kmh=float(v_r) if v_r is not None else None,
                )
            )
        return out
    if raw is None or (isinstance(raw, list) and len(raw) == 0):
        if default_spacing_m <= 0:
            return None
        return [
            ArterialLink(distance_m=default_spacing_m, forward_speed_kmh=design_speed_kmh)
            for _ in range(n_intersections - 1)
        ]
    return None
