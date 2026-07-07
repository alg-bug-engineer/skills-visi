from __future__ import annotations

from typing import Any


def build_control_scope_map(diagnosis: dict[str, Any], ticket: dict[str, Any]) -> dict[str, Any]:
    downstream_trace = diagnosis.get("downstream_trace") or {}
    flow_trace = diagnosis.get("flow_trace") or {}
    ticket = ticket or {}

    upstream_points = []
    for trace in flow_trace.get("entry_traces") or []:
        upstream_points.append(
            {
                "inter_id": trace.get("upstream_inter_id"),
                "inter_name": trace.get("upstream_inter_name"),
                "lng": trace.get("upstream_lng"),
                "lat": trace.get("upstream_lat"),
            }
        )

    downstream_nodes = []
    for node in downstream_trace.get("adjacent_intersections") or []:
        downstream_nodes.append(
            {
                "inter_id": node.get("inter_id"),
                "inter_name": node.get("inter_name"),
                "lng": node.get("lng"),
                "lat": node.get("lat"),
                "blocked": (node.get("capacity") or {}).get("blocked"),
            }
        )

    blocked = downstream_trace.get("governance", {}).get("downstream_blocked", False)
    center = None
    if ticket.get("lng") is not None and ticket.get("lat") is not None:
        center = [float(ticket["lng"]), float(ticket["lat"])]

    return {
        "action": "map_scene",
        "phase": "strategy_control_scope",
        "available": bool(center or upstream_points or downstream_nodes),
        "center": center,
        "target_intersection": {
            "inter_id": ticket.get("inter_id"),
            "inter_name": ticket.get("intersection_name"),
            "lng": ticket.get("lng"),
            "lat": ticket.get("lat"),
        },
        "upstream_metering_points": upstream_points,
        "downstream_protection_nodes": downstream_nodes,
        "risk_boundary": "downstream_blocked" if blocked else "controlled_release",
    }
