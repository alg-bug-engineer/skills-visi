"""Upstream flow trace adapted from references/流量溯源 (FlowTrace schema)."""

from __future__ import annotations

from typing import Any

from app.trace.topology import DIR8_ENTRY, TURN_LABEL, movement_label


def build_flow_trace(
    *,
    topology: dict[str, Any],
    dir8_code: int,
    turn_dir_no: int,
    target_saturation: float | None = None,
) -> dict[str, Any]:
    upstream_nodes = topology.get("upstream_nodes") or []
    if not upstream_nodes:
        return {"available": False, "reason": "no_upstream_topology"}

    entry_label = DIR8_ENTRY.get(dir8_code, "进口")
    entry_traces: list[dict[str, Any]] = []
    problem_turns: list[dict[str, Any]] = []
    governance_hints: list[dict[str, Any]] = []
    out_of_range = False
    raw_share_pct: float | None = None

    for node in upstream_nodes:
        movements = node.get("upstream_movements") or []
        # 过滤越界占比（需求 34 G4）
        cleaned: list[dict[str, Any]] = []
        for mv in movements:
            share = mv.get("share_pct")
            vehicles = mv.get("vehicles_of_100")
            raw = mv.get("raw_coverage")
            bad = False
            for val in (share, vehicles, raw):
                try:
                    if val is not None and (float(val) < 0 or float(val) > 100):
                        bad = True
                        out_of_range = True
                        raw_share_pct = float(val)
                        break
                except (TypeError, ValueError):
                    continue
            if bad:
                continue
            cleaned.append(mv)
        movements = cleaned
        if not movements:
            continue
        node = {**node, "upstream_movements": movements}
        dom = movements[0] if movements else None
        up_name = node.get("upstream_inter_name", "上一路口")
        vehicles = dom.get("vehicles_of_100") if dom else None
        if dom and vehicles is not None:
            narrative = (
                f"{entry_label}约100辆过境车中，约{vehicles}辆来自上一路口"
                f"{up_name}，以{dom.get('turn', '直行')}为主"
            )
        elif dom:
            narrative = f"{entry_label}来向上游路口{up_name}（占比数据缺失）"
        else:
            narrative = f"{entry_label}暂无可用上一跳溯源"

        entry_traces.append(
            {
                "entry": entry_label,
                "dir8_code": dir8_code,
                "entry_max_saturation": target_saturation,
                "upstream_inter_id": node.get("upstream_inter_id"),
                "upstream_inter_name": node.get("upstream_inter_name"),
                "upstream_lng": node.get("upstream_lng"),
                "upstream_lat": node.get("upstream_lat"),
                "vehicles_base": node.get("vehicles_base", 100),
                "upstream_movements": movements,
                "dominant_movement": dom,
                "path": node.get("path") or [],
                "narrative": narrative,
            }
        )

        if dom and int(dom.get("vehicles_of_100") or 0) >= 50:
            governance_hints.append(
                {
                    "type": "upstream_coordination",
                    "problem_turn": f"{entry_label}{TURN_LABEL.get(turn_dir_no, '')}",
                    "inter_id": node.get("upstream_inter_id"),
                    "inter_name": node.get("upstream_inter_name"),
                    "feed_direction": dom.get("feed_direction"),
                    "coverage": dom.get("vehicles_of_100"),
                }
            )

    if out_of_range and not entry_traces:
        return {
            "available": False,
            "reason": "flow_share_out_of_range",
            "raw_share_pct": raw_share_pct,
        }

    sources = []
    for node in upstream_nodes:
        for mv in node.get("upstream_movements") or []:
            sources.append(
                {
                    "inter_id": node.get("upstream_inter_id"),
                    "inter_name": node.get("upstream_inter_name"),
                    "feed_direction": mv.get("feed_direction"),
                    "path_coverage": mv.get("raw_coverage"),
                    "lng": node.get("upstream_lng"),
                    "lat": node.get("upstream_lat"),
                }
            )

    pattern = "single_corridor" if len(upstream_nodes) == 1 else "multi_corridor"
    problem_turns.append(
        {
            "entry": entry_label,
            "turn": TURN_LABEL.get(turn_dir_no, ""),
            "turn_saturation": target_saturation,
            "source_pattern": pattern,
            "dominant_feed": sources[0] if sources else None,
            "sources": sources[:3],
        }
    )

    return {
        "available": True,
        "period_type": topology.get("period_type", "EVENING_PEAK"),
        "day_basis": topology.get("day_basis", "工作日"),
        "vehicles_base": 100,
        "entry_traces": entry_traces,
        "problem_turns": problem_turns,
        "governance_hints": governance_hints,
        "caveat": topology.get("caveat") or topology.get("flow_trace_period_caveat"),
    }


def build_arterial_analysis(
    *,
    target_profile: dict[str, Any],
    downstream_trace: dict[str, Any],
    flow_trace: dict[str, Any],
    topology: dict[str, Any],
) -> dict[str, Any]:
    target_metrics = target_profile.get("metrics") or {}
    target_remaining = target_profile.get("remaining_storage_m")
    downstream_nodes = downstream_trace.get("adjacent_intersections") or []
    downstream_remaining = None
    if downstream_nodes:
        remainings = [
            float(n["remaining_storage_m"])
            for n in downstream_nodes
            if n.get("remaining_storage_m") is not None
        ]
        downstream_remaining = min(remainings) if remainings else None

    upstream_release = topology.get("upstream_release_intensity_vph")
    upstream_arrival = topology.get("upstream_arrival_flow_vph")
    downstream_blocked = downstream_trace.get("governance", {}).get("downstream_blocked", False)
    upstream_high = (upstream_arrival or 0) > 1400 or bool(flow_trace.get("governance_hints"))

    return {
        "upstream_arrival_flow_vph": upstream_arrival,
        "upstream_release_intensity_vph": upstream_release,
        "target_remaining_storage_m": target_remaining,
        "downstream_remaining_storage_m": downstream_remaining,
        "phase_offset_match": topology.get("phase_offset_match"),
        "need_upstream_metering": downstream_blocked and upstream_high,
        "need_downstream_dissipation_first": downstream_blocked,
        "upstream_arrival_intensity": topology.get("upstream_arrival_intensity", "unknown"),
        "summary": (
            "下游接不住且上游持续来车，目标路口被上下两端挤压，需干线联控"
            if downstream_blocked and upstream_high
            else "下游承接不足，需先保护下游再小步释放"
            if downstream_blocked
            else "上下游压力可控，可评估局部优化"
        ),
    }
