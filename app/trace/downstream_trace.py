"""Downstream one-hop trace adapted from references/流量溯源."""

from __future__ import annotations

from typing import Any

from app.metrics.traffic import THRESHOLDS
from app.trace.downstream_decision import decide_downstream_state
from app.trace.intersection_profile import build_intersection_profile
from app.trace.topology import TURN_LABEL, exit_dir8_for_turn, movement_label


def assess_downstream_capacity(
    *,
    saturation: float | None,
    queue_ratio: float | None,
    spillback_threshold: float | None = None,
    sat_threshold: float | None = None,
    remaining_storage_m: float | None = None,
    direct_downstream_inter_id: str | None = None,
    direct_downstream_inter_name: str | None = None,
    missing_metrics: list[str] | None = None,
) -> dict[str, Any]:
    """兼容旧字段，同时嵌入下游单一真源 decision。"""
    state = decide_downstream_state(
        saturation=saturation,
        queue_ratio=queue_ratio,
        spillback_threshold=spillback_threshold,
        sat_threshold=sat_threshold or THRESHOLDS["downstream_saturation_high"],
        remaining_storage_m=remaining_storage_m,
        direct_downstream_inter_id=direct_downstream_inter_id,
        direct_downstream_inter_name=direct_downstream_inter_name,
        missing_metrics=missing_metrics,
    )
    return {
        "can_release": state["can_release"],
        "blocked": state["blocked"],
        "unknown": state["unknown"],
        "reasons": state["reasons"],
        "release_guard": state["release_guard"],
        "decision": state["decision"],
        "downstream_state": state,
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
        missing_metrics: list[str] = []
        if metrics.get("saturation_rate") is None:
            missing_metrics.append("saturation")
        if metrics.get("green_utilization") is None:
            missing_metrics.append("green_utilization")
        remaining = None
        storage = metrics.get("storage_length_m")
        queue_len = metrics.get("queue_length_m")
        if storage is not None and queue_len is not None:
            try:
                remaining = max(0.0, float(storage) - float(queue_len))
            except (TypeError, ValueError):
                remaining = None
        capacity = assess_downstream_capacity(
            saturation=metrics.get("saturation_rate"),
            queue_ratio=metrics.get("queue_storage_ratio_max"),
            remaining_storage_m=remaining,
            direct_downstream_inter_id=str(node.get("inter_id") or "") or None,
            direct_downstream_inter_name=node.get("inter_name"),
            missing_metrics=missing_metrics,
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
    any_unknown = any(trace["capacity"].get("unknown") for trace in selected_traces)
    any_turn_blocked = any(trace["capacity"]["blocked"] for trace in turn_traces)
    if selected_traces:
        primary_state = selected_traces[0]["capacity"].get("downstream_state") or decide_downstream_state(
            saturation=None,
            queue_ratio=None,
        )
    elif any_unknown:
        primary_state = decide_downstream_state(saturation=None, queue_ratio=None)
    else:
        primary_state = decide_downstream_state(
            saturation=0.0 if not any_blocked else 0.9,
            queue_ratio=0.0 if not any_blocked else 0.9,
        )
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
        "downstream_state": primary_state,
        "governance": {
            "landing": "upstream_metering" if any_blocked else "local_reallocation",
            "downstream_blocked": any_blocked,
            "downstream_decision": primary_state.get("decision"),
            "all_turns_downstream_blocked": any_turn_blocked,
            "basis": "selected_movement",
            "recommendation": (
                "禁止向下游释放更多流量，优先上游控流或干线协调"
                if primary_state.get("decision") == "blocked"
                else (
                    "下游指标不足，先补证再决策"
                    if primary_state.get("decision") == "unknown"
                    else "下游初步有承接余量，可评估局部增绿或先验核验"
                )
            ),
        },
        "target_comparison": {
            "target": target_profile,
            "downstream_nodes": list(adjacent.values()),
            "same_metric_dimensions": True,
        },
    }
