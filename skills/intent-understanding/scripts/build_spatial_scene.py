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
                "path": node.get("path"),
            }
        )

    highlight_path: list[list[float]] = []
    if lng is not None and lat is not None:
        highlight_path.append([float(lng), float(lat)])
        if upstream_nodes and upstream_nodes[0].get("path"):
            highlight_path = upstream_nodes[0]["path"] + highlight_path
        if downstream_nodes and downstream_nodes[0].get("path"):
            highlight_path = highlight_path + downstream_nodes[0]["path"][1:]

    steps = []
    for step_id, label in RECOGNITION_STEPS:
        status = "done" if inter_id and step_id != "topology" or topology else "pending"
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
        "upstream_nodes": upstream_nodes,
        "downstream_nodes": downstream_nodes,
        "main_path": f"上游来车 → {ticket.get('intersection_name')} → 下游承接节点",
        "axis_roads": build_axis_roads(intersection_name=ticket.get("intersection_name")),
    }
