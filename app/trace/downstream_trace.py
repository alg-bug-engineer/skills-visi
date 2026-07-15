"""Downstream one-hop trace adapted from references/流量溯源."""

from __future__ import annotations

from typing import Any

from app.metrics.traffic import THRESHOLDS
from app.trace.intersection_profile import build_intersection_profile
from app.trace.topology import TURN_LABEL, exit_dir8_for_turn, movement_label


def assess_downstream_capacity(
    *,
    saturation: float | None,
    queue_ratio: float | None,
    spillback_threshold: float | None = None,
    sat_threshold: float | None = None,
) -> dict[str, Any]:
    spillback_threshold = spillback_threshold or THRESHOLDS["queue_ratio_warning"]
    sat_threshold = sat_threshold or 0.85
    # 排队与饱和度双缺：指标不足，禁止伪装「有余量」或「承接受限」
    if queue_ratio is None and saturation is None:
        return {
            "can_release": None,
            "blocked": False,
            "unknown": True,
            "reasons": ["downstream_queue_and_saturation_unavailable"],
            "release_guard": "downstream_metrics_unknown",
        }
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
        "unknown": False,
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
    downstream_nodes = topology.get("downstream_turn_nodes") or topology.get("downstream_nodes") or []
    if not downstream_nodes:
        return {"available": False, "reason": "no_topology"}

    turn_traces: list[dict[str, Any]] = []
    adjacent: dict[str, dict[str, Any]] = {}

    ordered_nodes = sorted(
        downstream_nodes,
        key=lambda node: (
            int(node.get("origin_turn_dir_no") or turn_dir_no) != int(turn_dir_no),
            int(node.get("origin_turn_dir_no") or turn_dir_no),
            -(float(node.get("share_pct")) if node.get("share_pct") is not None else -1.0),
        ),
    )
    for node in ordered_nodes:
        trace_turn = int(node.get("origin_turn_dir_no") or turn_dir_no)
        movement = movement_label(dir8_code, trace_turn)
        exit_dir8 = node.get("exit_dir8")
        if exit_dir8 is None:
            exit_dir8 = exit_dir8_for_turn(dir8_code, trace_turn)
        selected = trace_turn == int(turn_dir_no)
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
            "turn_label": TURN_LABEL.get(trace_turn),
            "dir8_code": dir8_code,
            "turn_dir_no": trace_turn,
            "selected": selected,
            "exit_dir8": exit_dir8,
            "downstream_inter_id": down_id,
            "downstream_inter_name": down_name,
            "share_pct": share,
            "path": node.get("path") or [],
            "path_source": node.get("path_source", "demo"),
            "receiving_dir8": node.get("receiving_dir8"),
            "receiving_label": node.get("receiving_label"),
            "metrics_available": profile.get("metrics_available"),
            "metrics_reason": profile.get("metrics_reason"),
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
                "selected": selected,
                "movement_metrics": [
                    {
                        "movement": movement,
                        "turn_dir_no": trace_turn,
                        "selected": selected,
                        "share_pct": share,
                        "receiving_dir8": node.get("receiving_dir8"),
                        "receiving_label": node.get("receiving_label"),
                        "metrics_available": profile.get("metrics_available"),
                        "metrics_reason": profile.get("metrics_reason"),
                        "metrics": metrics,
                        "capacity": capacity,
                    }
                ],
            }
        else:
            adjacent[down_id]["linked_movements"].append(movement)
            adjacent[down_id]["movement_metrics"].append(
                {
                    "movement": movement,
                    "turn_dir_no": trace_turn,
                    "selected": selected,
                    "share_pct": share,
                    "receiving_dir8": node.get("receiving_dir8"),
                    "receiving_label": node.get("receiving_label"),
                    "metrics_available": profile.get("metrics_available"),
                    "metrics_reason": profile.get("metrics_reason"),
                    "metrics": metrics,
                    "capacity": capacity,
                }
            )

    selected_traces = [trace for trace in turn_traces if trace["selected"]]
    any_blocked = any(trace["capacity"]["blocked"] for trace in selected_traces)
    any_turn_blocked = any(trace["capacity"]["blocked"] for trace in turn_traces)
    movement_summary = []
    for trace_turn in (1, 2, 3):
        traces = [trace for trace in turn_traces if trace["turn_dir_no"] == trace_turn]
        movement_summary.append(
            {
                "movement": movement_label(dir8_code, trace_turn),
                "turn_label": TURN_LABEL[trace_turn],
                "turn_dir_no": trace_turn,
                "selected": trace_turn == int(turn_dir_no),
                "available": bool(traces),
                "downstream_count": len(traces),
                "blocked_count": sum(1 for trace in traces if trace["capacity"]["blocked"]),
            }
        )
    return {
        "available": True,
        "trace_direction": "downstream",
        "scope": "target_approach_all_turns",
        "target_approach": movement_label(dir8_code, None) or str(dir8_code),
        "selected_turn_dir_no": turn_dir_no,
        "turn_traces": turn_traces,
        "movement_summary": movement_summary,
        "adjacent_intersections": list(adjacent.values()),
        "governance": {
            "landing": "upstream_metering" if any_blocked else "local_reallocation",
            "downstream_blocked": any_blocked,
            "all_turns_downstream_blocked": any_turn_blocked,
            "basis": "selected_movement",
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
