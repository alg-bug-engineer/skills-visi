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
                "action": "meter_inflow",
                "priority": 100,
                "status": "candidate",
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
                "action": "protect_storage",
                "priority": 100,
                "status": "monitor" if (node.get("capacity") or {}).get("blocked") is not None else "metrics_missing",
            }
        )

    blocked = downstream_trace.get("governance", {}).get("downstream_blocked", False)
    center = None
    if ticket.get("lng") is not None and ticket.get("lat") is not None:
        center = [float(ticket["lng"]), float(ticket["lat"])]

    coordination_paths: list[dict[str, Any]] = []
    for trace in flow_trace.get("entry_traces") or []:
        path = trace.get("path")
        if not isinstance(path, list) or len(path) < 2:
            continue
        coordination_paths.append(
            {
                "inter_id": trace.get("upstream_inter_id"),
                "inter_name": trace.get("upstream_inter_name"),
                "path": path,
                "role": "upstream_inflow",
            }
        )
    # 直接下游连接只消费后端真实 turn trace path，不按节点坐标合成。
    for trace in downstream_trace.get("turn_traces") or []:
        path = trace.get("path") if isinstance(trace, dict) else None
        if not isinstance(path, list) or len(path) < 2:
            continue
        coordination_paths.append({
            "inter_id": trace.get("downstream_inter_id"),
            "inter_name": trace.get("downstream_inter_name"),
            "path": path,
            "role": "downstream_protection",
        })

    missing_fields = []
    if not upstream_points:
        missing_fields.append("upstream_metering_points")
    if not downstream_nodes:
        missing_fields.append("downstream_protection_nodes")
    if not coordination_paths:
        missing_fields.append("coordination_paths")
    missing_fields.append("risk_boundary.geometry.polygon")

    return {
        "action": "map_scene",
        "phase": "strategy_control_scope",
        "available": bool(center or upstream_points or downstream_nodes),
        "source": "postgresql" if (center or upstream_points or downstream_nodes) else "none",
        "missing_fields": missing_fields,
        "center": center,
        "target_intersection": {
            "inter_id": ticket.get("inter_id"),
            "inter_name": ticket.get("intersection_name"),
            "lng": ticket.get("lng"),
            "lat": ticket.get("lat"),
        },
        "upstream_metering_points": upstream_points,
        "downstream_protection_nodes": downstream_nodes,
        "coordination_paths": coordination_paths,
        "risk_boundary": {
            "type": "downstream_blocked" if blocked else "controlled_release",
            "geometry": {
                "available": False,
                "reason": "策略风险边界 polygon 尚无生产真源",
                "missing_fields": ["polygon"],
                "source": "none",
            },
        },
        "data_lineage": {
            "source": "postgresql" if (center or upstream_points or downstream_nodes) else "none",
            "tables": ["road6.dim_inter_info", "road6.dim_link_info"],
        },
    }
