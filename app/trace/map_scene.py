"""Map scene payload aligned with references/流量溯源 frontend types/map.ts."""

from __future__ import annotations

from typing import Any


def build_downstream_map_scene(
    *,
    downstream_trace: dict[str, Any],
    target_profile: dict[str, Any],
    center: tuple[float, float] | None = None,
) -> dict[str, Any]:
    if not downstream_trace.get("available"):
        return {"action": "map_scene", "phase": "downstream_trace_map", "available": False}

    lng = target_profile.get("lng")
    lat = target_profile.get("lat")
    center_tuple: list[float] | None = None
    if center:
        center_tuple = [center[0], center[1]]
    elif lng is not None and lat is not None:
        center_tuple = [float(lng), float(lat)]

    turn_traces = []
    for item in downstream_trace.get("turn_traces") or []:
        turn_traces.append(
            {
                "movement": item.get("movement"),
                "downstream_inter_id": item.get("downstream_inter_id"),
                "name": item.get("downstream_inter_name"),
                "share_pct": item.get("share_pct"),
                "path": item.get("path"),
                "lon": item.get("lng"),
                "lat": item.get("lat"),
                "capacity": {
                    "blocked": (item.get("capacity") or {}).get("blocked"),
                    "can_release": (item.get("capacity") or {}).get("can_release"),
                },
                "trace_kind": "downstream",
            }
        )

    adjacent = []
    for node in downstream_trace.get("adjacent_intersections") or []:
        adjacent.append(
            {
                "inter_id": node.get("inter_id"),
                "inter_name": node.get("inter_name"),
                "lng": node.get("lng"),
                "lat": node.get("lat"),
                "metrics": node.get("metrics"),
                "by_turn": node.get("by_turn"),
                "remaining_storage_m": node.get("remaining_storage_m"),
                "capacity": node.get("capacity"),
            }
        )

    governance = downstream_trace.get("governance") or {}
    return {
        "action": "map_scene",
        "phase": "downstream_trace_map",
        "available": True,
        "center": center_tuple,
        "trace_direction": "downstream",
        "turn_traces": turn_traces,
        "adjacent_intersections": adjacent,
        "hud": {
            "title": "下游一跳去向",
            "metrics": [
                {
                    "label": "治理落点",
                    "value": governance.get("landing", "-"),
                    "severity": "high" if governance.get("downstream_blocked") else "low",
                },
                {
                    "label": "建议",
                    "value": governance.get("recommendation", "-"),
                },
            ],
        },
    }


def build_flow_map_scene(
    *,
    flow_trace: dict[str, Any],
    arterial_analysis: dict[str, Any],
    center: tuple[float, float] | None = None,
) -> dict[str, Any]:
    if not flow_trace.get("available"):
        return {"action": "map_scene", "phase": "upstream_correlate_map", "available": False}

    entry_traces = []
    for item in flow_trace.get("entry_traces") or []:
        dom = item.get("dominant_movement") or {}
        entry_traces.append(
            {
                "entry": item.get("entry"),
                "dir8_code": item.get("dir8_code"),
                "upstream_inter_id": item.get("upstream_inter_id"),
                "name": item.get("upstream_inter_name"),
                "narrative": item.get("narrative"),
                "lon": item.get("upstream_lng"),
                "lat": item.get("upstream_lat"),
                "dominant_turn": dom.get("turn"),
                "vehicles_of_100": dom.get("vehicles_of_100"),
                "movements": [
                    {
                        "turn": mv.get("turn"),
                        "vehicles_of_100": mv.get("vehicles_of_100"),
                        "feed_direction": mv.get("feed_direction"),
                    }
                    for mv in item.get("upstream_movements") or []
                ],
                "path": item.get("path"),
                "dominant": True,
            }
        )

    center_tuple = [center[0], center[1]] if center else None
    return {
        "action": "map_scene",
        "phase": "arterial_analysis",
        "available": True,
        "center": center_tuple,
        "trace_direction": "upstream",
        "entry_traces": entry_traces,
        "hud": {
            "title": "干线协调分析",
            "metrics": [
                {"label": "上游到达流量", "value": str(arterial_analysis.get("upstream_arrival_flow_vph") or "-")},
                {"label": "上游放行强度", "value": str(arterial_analysis.get("upstream_release_intensity_vph") or "-")},
                {
                    "label": "目标剩余空间(m)",
                    "value": str(arterial_analysis.get("target_remaining_storage_m") or "-"),
                },
                {
                    "label": "下游剩余空间(m)",
                    "value": str(arterial_analysis.get("downstream_remaining_storage_m") or "-"),
                },
                {
                    "label": "相位差匹配",
                    "value": str(arterial_analysis.get("phase_offset_match") or "-"),
                },
                {
                    "label": "上游控流",
                    "value": "需要" if arterial_analysis.get("need_upstream_metering") else "暂不需要",
                    "severity": "high" if arterial_analysis.get("need_upstream_metering") else "low",
                },
            ],
        },
        "speakable": arterial_analysis.get("summary"),
    }
