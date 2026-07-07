"""Downstream one-hop trace adapted from references/流量溯源."""

from __future__ import annotations

from typing import Any

from app.metrics.traffic import THRESHOLDS
from app.trace.intersection_profile import build_intersection_profile
from app.trace.topology import exit_dir8_for_turn, movement_label


def assess_downstream_capacity(
    *,
    saturation: float | None,
    queue_ratio: float | None,
    spillback_threshold: float | None = None,
    sat_threshold: float | None = None,
) -> dict[str, Any]:
    spillback_threshold = spillback_threshold or THRESHOLDS["queue_ratio_warning"]
    sat_threshold = sat_threshold or 0.85
    blocked = False
    reasons: list[str] = []
    if queue_ratio is not None and queue_ratio >= spillback_threshold:
        blocked = True
        reasons.append(f"queue_ratio={queue_ratio:.2f}>={spillback_threshold}")
    if saturation is not None and saturation >= sat_threshold:
        blocked = True
        reasons.append(f"saturation={saturation:.2f}>={sat_threshold}")
    return {
        "can_release": not blocked,
        "blocked": blocked,
        "reasons": reasons,
        "release_guard": "downstream_blocked" if blocked else "downstream_has_slack",
    }


def build_downstream_trace(
    *,
    target_profile: dict[str, Any],
    topology: dict[str, Any],
    dir8_code: int,
    turn_dir_no: int,
) -> dict[str, Any]:
    downstream_nodes = topology.get("downstream_nodes") or []
    if not downstream_nodes:
        return {"available": False, "reason": "no_topology"}

    movement = movement_label(dir8_code, turn_dir_no)
    exit_dir8 = exit_dir8_for_turn(dir8_code, turn_dir_no)
    turn_traces: list[dict[str, Any]] = []
    adjacent: dict[str, dict[str, Any]] = {}

    for node in downstream_nodes:
        profile = build_intersection_profile({**node, "role": "downstream"})
        metrics = profile["metrics"]
        capacity = assess_downstream_capacity(
            saturation=metrics.get("saturation_rate"),
            queue_ratio=metrics.get("queue_storage_ratio_max"),
        )
        down_id = str(node.get("inter_id") or "")
        down_name = node.get("inter_name") or "下游信控节点"
        share = node.get("share_pct")

        narrative_parts = [f"{movement}去向{down_name}"]
        if share is not None:
            narrative_parts.append(f"占比{share:.1f}%")
        if capacity["blocked"]:
            narrative_parts.append("下游已饱和，不宜继续放流")
        else:
            narrative_parts.append("下游仍有余量，可局部增绿清空")

        trace_item = {
            "movement": movement,
            "dir8_code": dir8_code,
            "turn_dir_no": turn_dir_no,
            "exit_dir8": exit_dir8,
            "downstream_inter_id": down_id,
            "downstream_inter_name": down_name,
            "share_pct": share,
            "path": node.get("path") or [],
            "path_source": node.get("path_source", "demo"),
            "receiving_dir8": node.get("receiving_dir8"),
            "receiving_label": node.get("receiving_label"),
            "lng": node.get("lng"),
            "lat": node.get("lat"),
            "downstream_metrics": profile,
            "capacity": capacity,
            "trace_kind": "downstream",
            "narrative": "，".join(narrative_parts),
        }
        turn_traces.append(trace_item)

        if down_id not in adjacent:
            adjacent[down_id] = {
                **profile,
                "capacity": capacity,
                "linked_movements": [movement],
                "share_pct": share,
            }
        else:
            adjacent[down_id]["linked_movements"].append(movement)

    any_blocked = any(t["capacity"]["blocked"] for t in turn_traces)
    return {
        "available": True,
        "trace_direction": "downstream",
        "turn_traces": turn_traces,
        "adjacent_intersections": list(adjacent.values()),
        "governance": {
            "landing": "upstream_metering" if any_blocked else "local_reallocation",
            "downstream_blocked": any_blocked,
            "recommendation": (
                "禁止向下游释放更多流量，优先上游控流或干线协调"
                if any_blocked
                else "下游可承接，可评估局部增绿清空"
            ),
        },
        "target_comparison": {
            "target": target_profile,
            "downstream_nodes": list(adjacent.values()),
            "same_metric_dimensions": True,
        },
    }
