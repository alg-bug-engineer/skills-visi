from __future__ import annotations

from typing import Any

from app.metrics.traffic import (
    assess_overflow_risk,
    calculate_queue_ratio,
    calculate_saturation,
    classify_release_bottleneck,
    level_of_service,
)
from app.trace.downstream_diagnosis import build_downstream_diagnosis
from app.trace.downstream_trace import build_downstream_trace
from app.trace.flow_trace import build_arterial_analysis, build_flow_trace
from app.trace.intersection_profile import build_intersection_profile
from app.trace.map_scene import build_downstream_map_scene, build_flow_map_scene
from app.trace.topology import resolve_dir8_turn


def analyze_overflow(
    metrics_input: dict[str, Any],
    ticket: dict[str, Any],
    *,
    topology: dict[str, Any] | None = None,
    spatial_objects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    dir8_code, turn_dir_no = resolve_dir8_turn(direction, movement)

    target_node = {
        "inter_id": (topology or {}).get("target_inter_id"),
        "inter_name": ticket.get("intersection_name"),
        "role": "target",
        "lng": (topology or {}).get("target_lng"),
        "lat": (topology or {}).get("target_lat"),
        "movement_label": f"{direction}{movement}",
        **metrics_input,
    }
    target_profile = build_intersection_profile(target_node)
    metrics = target_profile["metrics"]
    queue_ratio = metrics.get("queue_storage_ratio_max")
    saturation = metrics.get("saturation_rate")
    overflow = assess_overflow_risk(queue_ratio)

    downstream_trace = {"available": False, "reason": "no_topology"}
    flow_trace = {"available": False, "reason": "no_upstream_topology"}
    arterial_analysis: dict[str, Any] = {}
    downstream_diagnosis: dict[str, Any] = {"available": False}
    map_scenes: dict[str, Any] = {}

    if topology:
        downstream_trace = build_downstream_trace(
            target_profile=target_profile,
            topology=topology,
            dir8_code=dir8_code,
            turn_dir_no=turn_dir_no,
        )
        flow_trace = build_flow_trace(
            topology=topology,
            dir8_code=dir8_code,
            turn_dir_no=turn_dir_no,
            target_saturation=saturation,
        )
        arterial_analysis = build_arterial_analysis(
            target_profile=target_profile,
            downstream_trace=downstream_trace,
            flow_trace=flow_trace,
            topology=topology,
        )

    primary_downstream = (
        (downstream_trace.get("adjacent_intersections") or [{}])[0]
        if downstream_trace.get("available")
        else {}
    )
    downstream_metrics_raw = primary_downstream.get("metrics") or {}
    bottleneck = classify_release_bottleneck(
        target_saturation=saturation or 0,
        target_green_utilization=metrics_input.get("green_utilization", 0),
        downstream_queue_ratio=downstream_metrics_raw.get("queue_storage_ratio_max"),
        downstream_saturation=downstream_metrics_raw.get("saturation_rate", 0),
    )

    if topology and downstream_trace.get("available"):
        downstream_diagnosis = build_downstream_diagnosis(
            target_profile=target_profile,
            downstream_trace=downstream_trace,
            bottleneck=bottleneck,
        )
        center = None
        if target_profile.get("lng") is not None and target_profile.get("lat") is not None:
            center = (float(target_profile["lng"]), float(target_profile["lat"]))
        map_scenes = {
            "downstream_trace_map": build_downstream_map_scene(
                downstream_trace=downstream_trace,
                target_profile=target_profile,
                center=center,
            ),
            "arterial_analysis": build_flow_map_scene(
                flow_trace=flow_trace,
                arterial_analysis=arterial_analysis,
                center=center,
            ),
        }

    return {
        "metrics": {
            "queue_length_m": metrics_input["queue_length_m"],
            "storage_length_m": metrics_input["storage_length_m"],
            "queue_ratio": queue_ratio,
            "saturation": saturation,
            "los": level_of_service(saturation or 0),
            "green_utilization": metrics_input["green_utilization"],
            "stop_count": metrics_input.get("stop_count"),
            "avg_delay_s": metrics_input.get("avg_delay_s"),
            "time_series_trend": metrics_input.get("time_series_trend"),
        },
        "downstream_metrics": {
            "queue_ratio": downstream_metrics_raw.get("queue_storage_ratio_max"),
            "saturation": downstream_metrics_raw.get("saturation_rate"),
            "green_utilization": downstream_metrics_raw.get("green_utilization"),
        },
        "upstream_metrics": {
            "arrival_intensity": topology.get("upstream_arrival_intensity")
            if topology
            else metrics_input.get("upstream_arrival_intensity"),
            "arrival_flow_vph": topology.get("upstream_arrival_flow_vph") if topology else None,
            "release_intensity_vph": topology.get("upstream_release_intensity_vph")
            if topology
            else None,
        },
        "target_intersection": target_profile,
        "spatial_topology": spatial_objects or {},
        "downstream_trace": downstream_trace,
        "flow_trace": flow_trace,
        "arterial_analysis": arterial_analysis,
        "downstream_diagnosis": downstream_diagnosis,
        "map_scenes": map_scenes,
        "overflow_verification": overflow,
        "bottleneck_analysis": bottleneck,
        "problem_confirmed": overflow.get("verified")
        and overflow.get("risk_level") in ("warning", "high"),
        "target": {
            "intersection": ticket.get("intersection_name"),
            "direction": direction,
            "movement": movement,
            "dir8_code": dir8_code,
            "turn_dir_no": turn_dir_no,
        },
    }
