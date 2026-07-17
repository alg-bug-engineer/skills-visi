from __future__ import annotations

from typing import Any

from app.trace.axis_roads import build_axis_roads


RECOGNITION_STEPS = [
    ("intersection_match", "路口匹配完成"),
    ("approach_direction", "进口方向识别完成"),
    ("turn_relation", "转向关系识别完成"),
    ("topology", "上下游拓扑识别完成"),
    ("arterial_path", "干线路径识别完成"),
]


def build_spatial_objects(ticket: dict[str, Any]) -> dict[str, Any]:
    direction = ticket.get("direction", "")
    return {
        "target_intersection": ticket.get("intersection_name"),
        "target_direction": direction,
        "target_movement": ticket.get("movement", "直行"),
        "upstream_scope": f"{direction}来车来源路段与相邻路口",
        "downstream_scope": f"{direction}出口路段与下游信控节点",
        "main_path": "上游来车 → 目标路口 → 下游承接节点",
    }


def build_spatial_scene(
    ticket: dict[str, Any],
    *,
    topology: dict[str, Any] | None = None,
) -> dict[str, Any]:
    topology = topology or {}
    direction = ticket.get("direction", "")
    movement = ticket.get("movement", "直行")
    inter_id = ticket.get("inter_id")
    lng = ticket.get("lng")
    lat = ticket.get("lat")

    upstream_nodes = []
    for node in topology.get("upstream_nodes") or []:
        upstream_nodes.append(
            {
                "inter_id": node.get("upstream_inter_id"),
                "inter_name": node.get("upstream_inter_name"),
                "lng": node.get("upstream_lng"),
                "lat": node.get("upstream_lat"),
                "link_id": node.get("link_id"),
                "path": node.get("path"),
            }
        )

    downstream_nodes = []
    for node in topology.get("downstream_nodes") or []:
        downstream_nodes.append(
            {
                "inter_id": node.get("inter_id"),
                "inter_name": node.get("inter_name"),
                "lng": node.get("lng"),
                "lat": node.get("lat"),
                "link_id": node.get("link_id"),
                "path": node.get("path"),
            }
        )

    # 只拼接后端真实 link geometry，不将路口中心点当成业务路径。
    target_approach_path = (
        upstream_nodes[0].get("path")
        if upstream_nodes and isinstance(upstream_nodes[0].get("path"), list)
        else []
    )
    downstream_path = (
        downstream_nodes[0].get("path")
        if downstream_nodes and isinstance(downstream_nodes[0].get("path"), list)
        else []
    )
    movement_path: list[list[float]] = []
    for path in (target_approach_path, downstream_path):
        if len(path) < 2:
            continue
        if movement_path and movement_path[-1] == path[0]:
            movement_path.extend(path[1:])
        else:
            movement_path.extend(path)
    highlight_path = movement_path or target_approach_path or downstream_path
    geometry_source = topology.get("geometry_source")
    scene_source = (
        "postgresql"
        if geometry_source == "dim_link_info.geom"
        else ("backend_topology" if highlight_path else "none")
    )

    steps = []
    for step_id, label in RECOGNITION_STEPS:
        status = "done" if (inter_id and step_id != "topology") else "pending"
        if step_id == "topology" and (upstream_nodes or downstream_nodes):
            status = "done"
        if step_id == "arterial_path" and highlight_path:
            status = "done"
        steps.append({"step": step_id, "status": status, "label": label})

    return {
        "available": bool(inter_id),
        "recognition_steps": steps,
        "target": {
            "inter_id": inter_id,
            "inter_name": ticket.get("intersection_name"),
            "lng": lng,
            "lat": lat,
            "direction": direction,
            "movement": movement,
        },
        "highlight_path": highlight_path or None,
        "target_approach_path": target_approach_path or None,
        "movement_path": movement_path or None,
        "upstream_nodes": upstream_nodes,
        "downstream_nodes": downstream_nodes,
        "source": scene_source,
        "missing_fields": [
            field
            for field, value in (
                ("target_approach_path", target_approach_path),
                ("movement_path", movement_path),
                ("upstream_nodes", upstream_nodes),
                ("downstream_nodes", downstream_nodes),
            )
            if not value
        ],
        "data_lineage": {
            "source": scene_source,
            "geometry_source": geometry_source,
            "tables": ["road6.dim_inter_info", "road6.dim_link_info"],
            "link_ids": [
                node.get("link_id")
                for node in [*upstream_nodes, *downstream_nodes]
                if node.get("link_id")
            ],
        },
        "main_path": f"上游来车 → {ticket.get('intersection_name')} → 下游承接节点",
        "axis_roads": build_axis_roads(intersection_name=ticket.get("intersection_name")),
    }
