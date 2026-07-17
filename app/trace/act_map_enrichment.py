"""Act-specific map scene payloads for frontend presentation (R2)."""

from __future__ import annotations

from typing import Any


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coords(row: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not isinstance(row, dict):
        return None, None
    lng, lat = row.get("lng"), row.get("lat")
    try:
        if lng is not None and lat is not None:
            return float(lng), float(lat)
    except (TypeError, ValueError):
        pass
    return None, None


def _valid_path(value: Any) -> list[list[float]]:
    if not isinstance(value, list):
        return []
    path: list[list[float]] = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return []
        try:
            path.append([float(point[0]), float(point[1])])
        except (TypeError, ValueError):
            return []
    return path if len(path) >= 2 else []


def _join_real_paths(*paths: Any) -> list[list[float]]:
    """Join only supplied real geometries; never synthesize an intermediate point."""
    merged: list[list[float]] = []
    for raw in paths:
        path = _valid_path(raw)
        if not path:
            continue
        if merged and merged[-1] == path[0]:
            merged.extend(path[1:])
        else:
            merged.extend(path)
    return merged


def _trace_visualization_contract(
    *,
    scene: dict[str, Any],
    geometry_source: str,
    ordering: str,
) -> dict[str, Any]:
    target = scene.get("target") if isinstance(scene.get("target"), dict) else {}
    origin = scene.get("center")
    if not _valid_path([origin, origin]):
        lng, lat = _coords(target)
        origin = [lng, lat] if lng is not None else None
    upstream = scene.get("trace_direction") != "downstream"
    return {
        "contract_version": "trace-spread/v3",
        "effect": "upstream_spread" if upstream else "downstream_flow",
        "direction": "target_to_source" if upstream else "source_to_target",
        "origin": origin,
        "geometry_source": geometry_source,
        "context_geometry_source": None,
        "render_geometry_scope": geometry_source,
        "ordering": ordering,
        "particle_anchor": "path",
        "particle_color": "#39dfff",
        "particle_texture": None,
        "particle_count": 0,
        "particle_color_mode": "uniform",
        "propagation_renderer": "path_prefix",
        "repeat": False,
        "color_metric": None,
        "color_semantics": "uniform_flow_trace",
        "camera": {"pitch": 48, "radius_m": 2000, "max_zoom": 13.8},
        "palette": {"trace": "#39dfff"},
        "road_classification_source": (
            "links[].fc|road6.dim_rid_trace_info.fc"
            if geometry_source == "links[].coords" else None
        ),
        "map_style": "amap://styles/darkblue",
        "source": scene.get("source") or "postgresql_and_trip_trace",
    }


def enrich_flow_trace_visualization_contract(diagnosis: dict[str, Any]) -> None:
    """让 fixture、普通 JSON、SSE/live 对同一溯源动画字段只认一个契约。"""
    map_scenes = diagnosis.get("map_scenes") if isinstance(diagnosis.get("map_scenes"), dict) else {}
    segment = map_scenes.get("flow_trace_segment_coverage_map")
    if isinstance(segment, dict):
        segment["visualization"] = _trace_visualization_contract(
            scene=segment,
            geometry_source="links[].coords",
            ordering="links[].spread_order|rank",
        )
    sniff = map_scenes.get("flow_trace_links_sniff_map")
    if isinstance(sniff, dict):
        sniff["visualization"] = _trace_visualization_contract(
            scene=sniff,
            geometry_source="intersections[].links[].path",
            ordering="intersections[].corridor_hop",
        )


def enrich_intent_spatial_scene(
    *,
    intent: dict[str, Any],
    ticket: dict[str, Any],
    topology: dict[str, Any] | None,
    source: str = "postgresql",
) -> None:
    """Align Act 1/2 payload with resolved PG topology before it reaches the UI."""
    if not isinstance(intent, dict):
        return
    scene = intent.get("spatial_scene") if isinstance(intent.get("spatial_scene"), dict) else {}
    topology = topology if isinstance(topology, dict) else {}

    upstream_nodes: list[dict[str, Any]] = []
    for node in topology.get("upstream_nodes") or []:
        if not isinstance(node, dict):
            continue
        upstream_nodes.append({
            "inter_id": node.get("upstream_inter_id") or node.get("inter_id"),
            "inter_name": node.get("upstream_inter_name") or node.get("inter_name"),
            "lng": node.get("upstream_lng") if node.get("upstream_lng") is not None else node.get("lng"),
            "lat": node.get("upstream_lat") if node.get("upstream_lat") is not None else node.get("lat"),
            "link_id": node.get("link_id"),
            "path": _valid_path(node.get("path")),
        })

    downstream_nodes: list[dict[str, Any]] = []
    for node in topology.get("downstream_nodes") or []:
        if not isinstance(node, dict):
            continue
        downstream_nodes.append({
            "inter_id": node.get("inter_id") or node.get("downstream_inter_id"),
            "inter_name": node.get("inter_name") or node.get("downstream_inter_name"),
            "lng": node.get("lng") if node.get("lng") is not None else node.get("lon"),
            "lat": node.get("lat"),
            "link_id": node.get("link_id"),
            "path": _valid_path(node.get("path")),
        })

    approach_path = next((node["path"] for node in upstream_nodes if node.get("path")), [])
    downstream_path = next((node["path"] for node in downstream_nodes if node.get("path")), [])
    movement_path = _join_real_paths(approach_path, downstream_path)
    highlight_path = movement_path or approach_path or downstream_path

    t_lng, t_lat = _coords(ticket)
    scene["target"] = {
        **(scene.get("target") if isinstance(scene.get("target"), dict) else {}),
        "inter_id": ticket.get("inter_id"),
        "inter_name": ticket.get("intersection_name"),
        "lng": t_lng,
        "lat": t_lat,
        "direction": ticket.get("direction"),
        "movement": ticket.get("movement"),
    }
    if approach_path:
        scene["target_approach_path"] = approach_path
    if movement_path:
        scene["movement_path"] = movement_path
    if highlight_path:
        scene["highlight_path"] = highlight_path
    if upstream_nodes:
        scene["upstream_nodes"] = upstream_nodes
    if downstream_nodes:
        scene["downstream_nodes"] = downstream_nodes

    missing_fields = []
    for field, value in (
        ("target_approach_path", approach_path),
        ("movement_path", movement_path),
        ("upstream_nodes", upstream_nodes),
        ("downstream_nodes", downstream_nodes),
    ):
        if not value:
            missing_fields.append(field)
    target_resolved = bool(ticket.get("inter_id") and t_lng is not None)
    scene["available"] = target_resolved or bool(scene.get("available"))
    scene["missing_fields"] = missing_fields
    if highlight_path:
        scene["source"] = source
    else:
        scene.setdefault("source", "none")
    scene["data_lineage"] = {
        "source": source,
        "geometry_source": topology.get("geometry_source"),
        "tables": ["road6.dim_inter_info", "road6.dim_link_info"],
        "link_ids": [
            node.get("link_id")
            for node in [*upstream_nodes, *downstream_nodes]
            if node.get("link_id")
        ],
    }

    steps = scene.get("recognition_steps") if isinstance(scene.get("recognition_steps"), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("step") == "topology" and (upstream_nodes or downstream_nodes):
            step["status"] = "done"
        if step.get("step") == "arterial_path" and highlight_path:
            step["status"] = "done"
    scene["recognition_steps"] = steps
    intent["spatial_scene"] = scene


def _lookup_inter_coords(inter_id: str | None, diagnosis: dict[str, Any]) -> tuple[float | None, float | None]:
    if not inter_id:
        return None, None
    downstream_trace = diagnosis.get("downstream_trace") or {}
    for node in downstream_trace.get("adjacent_intersections") or []:
        if isinstance(node, dict) and node.get("inter_id") == inter_id:
            lng, lat = _coords(node)
            if lng is not None:
                return lng, lat
    map_scenes = diagnosis.get("map_scenes") or {}
    turn_traces = (map_scenes.get("downstream_trace_map") or {}).get("turn_traces") or []
    for trace in turn_traces:
        if isinstance(trace, dict) and trace.get("downstream_inter_id") == inter_id:
            lng = trace.get("lon") if trace.get("lon") is not None else trace.get("lng")
            lat = trace.get("lat")
            try:
                if lng is not None and lat is not None:
                    return float(lng), float(lat)
            except (TypeError, ValueError):
                pass
    flow_trace = diagnosis.get("flow_trace") or {}
    for trace in flow_trace.get("entry_traces") or []:
        if isinstance(trace, dict) and trace.get("upstream_inter_id") == inter_id:
            lng, lat = _coords(trace)
            if lng is not None:
                return lng, lat
    return None, None


def _metric_badge(metrics: dict[str, Any] | None) -> dict[str, Any]:
    metrics = metrics if isinstance(metrics, dict) else {}
    def first(*keys: str) -> Any:
        for key in keys:
            if metrics.get(key) is not None:
                return metrics.get(key)
        return None
    return {
        "queue_ratio": first("queue_ratio", "queue_storage_ratio_max"),
        "saturation": first("saturation", "saturation_rate"),
        "green_utilization": metrics.get("green_utilization"),
    }


def _selected_downstream_path(diagnosis: dict[str, Any], downstream_id: str | None) -> list[Any]:
    scenes = diagnosis.get("map_scenes") or {}
    for key in ("downstream_trace_map",):
        for trace in (scenes.get(key) or {}).get("turn_traces") or []:
            if not isinstance(trace, dict):
                continue
            if downstream_id and trace.get("downstream_inter_id") != downstream_id:
                continue
            path = trace.get("path")
            if isinstance(path, list) and len(path) >= 2 and (trace.get("selected") or downstream_id):
                return path
    for trace in (diagnosis.get("downstream_trace") or {}).get("turn_traces") or []:
        if not isinstance(trace, dict) or (downstream_id and trace.get("downstream_inter_id") != downstream_id):
            continue
        path = trace.get("path")
        if isinstance(path, list) and len(path) >= 2:
            return path
    return []


def build_queue_evidence_map(diagnosis: dict[str, Any]) -> dict[str, Any]:
    """排队带严格复用 channelization_map 的真实进口 link 几何。"""
    metrics = diagnosis.get("metrics") if isinstance(diagnosis.get("metrics"), dict) else {}
    channel = ((diagnosis.get("map_scenes") or {}).get("channelization_map") or {})
    target_dir8 = str(metrics.get("dir8_code")) if metrics.get("dir8_code") is not None else None
    selected: dict[str, Any] = {}
    for link in channel.get("links") or []:
        if not isinstance(link, dict) or str(link.get("link_role", "")).lower() not in ("entrance", "进口"):
            continue
        if target_dir8 is None or str(link.get("dir8_code")) == target_dir8:
            selected = link
            break
    path = selected.get("path") if isinstance(selected.get("path"), list) else []
    available = len(path) >= 2
    return {
        "action": "map_scene",
        "phase": "queue_evidence",
        "available": available,
        "reason": None if available else "缺少目标进口真实 link geometry",
        "missing_fields": [] if available else ["path"],
        "source": "postgresql" if available else "none",
        "path_source": "road6.dim_link_info.geom" if available else None,
        "link_id": selected.get("link_id"),
        "path": path,
        "label_anchor": path[len(path) // 2] if available else None,
        "queue_length_m": metrics.get("queue_length_m"),
        "storage_length_m": metrics.get("storage_length_m"),
        "queue_ratio": metrics.get("queue_ratio"),
        "stop_line": {
            "available": False,
            "reason": "停止线几何未进入生产场景契约",
            "missing_fields": ["geometry"],
        },
        "data_lineage": {"geometry": {"schema": "road6", "table": "dim_link_info"}},
    }


def build_diagnosis_compare_map(ticket: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any]:
    """本路口 vs 主要下游对比节点（act3–4）。"""
    ticket = ticket or {}
    diagnosis = diagnosis or {}
    t_lng, t_lat = _coords(ticket)
    metrics = diagnosis.get("metrics") if isinstance(diagnosis.get("metrics"), dict) else {}
    pd = (diagnosis.get("downstream_diagnosis") or {}).get("primary_downstream") or {}
    pd_id = _clean(pd.get("inter_id"))
    d_lng, d_lat = _coords(pd)
    if d_lng is None and pd_id:
        d_lng, d_lat = _lookup_inter_coords(pd_id, diagnosis)

    target = {
        "inter_id": ticket.get("inter_id"),
        "inter_name": ticket.get("intersection_name"),
        "lng": t_lng,
        "lat": t_lat,
        "role": "target",
        "direction": ticket.get("direction"),
        "movement": ticket.get("movement"),
        "metrics": _metric_badge(metrics),
    }
    downstream = {
        "inter_id": pd_id,
        "inter_name": pd.get("inter_name"),
        "lng": d_lng,
        "lat": d_lat,
        "role": "primary_downstream",
        "metrics": _metric_badge(pd.get("metrics") if isinstance(pd.get("metrics"), dict) else {}),
        "remaining_storage_m": pd.get("remaining_storage_m"),
    }
    available = t_lng is not None and d_lng is not None
    missing_metrics = [
        name for name, value in (
            ("downstream_saturation", downstream["metrics"].get("saturation")),
            ("downstream_green_utilization", downstream["metrics"].get("green_utilization")),
        ) if value is None
    ]
    connector_path = _selected_downstream_path(diagnosis, pd_id)
    return {
        "action": "map_scene",
        "phase": "diagnosis_compare",
        "available": available,
        "reason": None if available else "缺少目标或下游坐标",
        "comparison_label": "本路口 vs 主要下游",
        "connector_path": connector_path,
        "decision": (diagnosis.get("downstream_state") or {}).get("decision"),
        "confidence": (diagnosis.get("downstream_state") or {}).get("confidence"),
        "missing_metrics": missing_metrics,
        "missing_fields": ([] if connector_path else ["connector_path"]),
        "target": target,
        "downstream": downstream,
    }


def build_cause_spatial_map(
    ticket: dict[str, Any],
    cause: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, Any]:
    """成因关联空间对象标注（act6）。"""
    ticket = ticket or {}
    cause = cause or {}
    diagnosis = diagnosis or {}
    t_lng, t_lat = _coords(ticket)
    annotations: list[dict[str, Any]] = []

    if t_lng is not None:
        direction = _clean(ticket.get("direction"))
        movement = _clean(ticket.get("movement"))
        label = f"{direction or ''}{movement or ''}进口".strip() or "问题进口"
        annotations.append(
            {
                "kind": "approach",
                "label": label,
                "lng": t_lng,
                "lat": t_lat,
                "color": "#ff3c1f",
                "evidence_role": "supporting",
                "evidence_ids": ["queue_ratio", "green_utilization"],
                "priority": 100,
            }
        )

    pd = (diagnosis.get("downstream_diagnosis") or {}).get("primary_downstream") or {}
    pd_id = _clean(pd.get("inter_id"))
    d_lng, d_lat = _coords(pd)
    if d_lng is None and pd_id:
        d_lng, d_lat = _lookup_inter_coords(pd_id, diagnosis)
    if d_lng is not None:
        annotations.append(
            {
                "kind": "downstream",
                "label": pd.get("inter_name") or "主要下游",
                "inter_id": pd_id,
                "lng": d_lng,
                "lat": d_lat,
                "color": "#39dfff",
                "evidence_role": "counter_evidence",
                "evidence_ids": ["downstream_queue_ratio"],
                "priority": 90,
            }
        )

    cause_analysis = cause.get("cause_analysis") or {}
    mechanism = (cause_analysis.get("overflow_mechanism") or {}).get("primary")
    if mechanism is None:
        mechanism = (diagnosis.get("overflow_mechanism") or {}).get("primary")
    return {
        "action": "map_scene",
        "phase": "cause_spatial",
        "available": bool(annotations),
        "reason": None if annotations else "缺少空间标注数据",
        "primary_cause": _clean(cause_analysis.get("primary_cause")),
        "mechanism": mechanism,
        "status": "trial_required" if mechanism == "discharge_anomaly" else "diagnosed",
        "confidence": (
            cause_analysis.get("confidence")
            if cause_analysis.get("confidence") is not None
            else (diagnosis.get("downstream_state") or {}).get("confidence")
        ),
        "annotations": annotations,
    }


def enrich_control_scope_map(
    *, ticket: dict[str, Any], diagnosis: dict[str, Any], strategy: dict[str, Any]
) -> None:
    """Normalize the production strategy map contract without inventing geometry."""
    if not isinstance(strategy, dict):
        return
    scope = strategy.get("control_scope_map") if isinstance(strategy.get("control_scope_map"), dict) else {}
    t_lng, t_lat = _coords(ticket)
    if t_lng is not None:
        scope["center"] = [t_lng, t_lat]
    scope["target_intersection"] = {
        "inter_id": ticket.get("inter_id"),
        "inter_name": ticket.get("intersection_name"),
        "lng": t_lng,
        "lat": t_lat,
    }

    upstream_points = [p for p in scope.get("upstream_metering_points") or [] if isinstance(p, dict)]
    if not upstream_points:
        for trace in (diagnosis.get("flow_trace") or {}).get("entry_traces") or []:
            if not isinstance(trace, dict):
                continue
            upstream_points.append({
                "inter_id": trace.get("upstream_inter_id"),
                "inter_name": trace.get("upstream_inter_name"),
                "lng": trace.get("upstream_lng"),
                "lat": trace.get("upstream_lat"),
            })
    for point in upstream_points:
        point.setdefault("action", "meter_inflow")
        point.setdefault("priority", 100)
        point.setdefault("status", "candidate")
    scope["upstream_metering_points"] = upstream_points

    downstream_nodes = [p for p in scope.get("downstream_protection_nodes") or [] if isinstance(p, dict)]
    if not downstream_nodes:
        for node in (diagnosis.get("downstream_trace") or {}).get("adjacent_intersections") or []:
            if not isinstance(node, dict):
                continue
            downstream_nodes.append({
                "inter_id": node.get("inter_id"),
                "inter_name": node.get("inter_name"),
                "lng": node.get("lng"),
                "lat": node.get("lat"),
                "blocked": (node.get("capacity") or {}).get("blocked"),
            })
    for node in downstream_nodes:
        node.setdefault("action", "protect_storage")
        node.setdefault("priority", 100)
        node.setdefault("status", "monitor" if node.get("blocked") is not None else "metrics_missing")
    scope["downstream_protection_nodes"] = downstream_nodes

    paths = [p for p in scope.get("coordination_paths") or [] if isinstance(p, dict) and _valid_path(p.get("path"))]
    if not paths:
        for trace in (diagnosis.get("flow_trace") or {}).get("entry_traces") or []:
            path = _valid_path(trace.get("path") if isinstance(trace, dict) else None)
            if path:
                paths.append({
                    "inter_id": trace.get("upstream_inter_id"),
                    "inter_name": trace.get("upstream_inter_name"),
                    "path": path,
                    "role": "upstream_inflow",
                })
        for trace in (diagnosis.get("downstream_trace") or {}).get("turn_traces") or []:
            path = _valid_path(trace.get("path") if isinstance(trace, dict) else None)
            if path:
                paths.append({
                    "inter_id": trace.get("downstream_inter_id"),
                    "inter_name": trace.get("downstream_inter_name"),
                    "path": path,
                    "role": "downstream_protection",
                })
    scope["coordination_paths"] = paths

    risk = scope.get("risk_boundary") if isinstance(scope.get("risk_boundary"), dict) else {}
    geometry = risk.get("geometry") if isinstance(risk.get("geometry"), dict) else {}
    polygon = _valid_path(geometry.get("polygon"))
    if not polygon:
        geometry.update({
            "available": False,
            "reason": geometry.get("reason") or "PostgreSQL 路网与指标表无策略风险边界 polygon 真源",
            "missing_fields": ["polygon"],
            "source": "none",
        })
        geometry.pop("polygon", None)
    else:
        geometry.update({"available": True, "polygon": polygon})
        geometry.setdefault("source", "backend")
    risk["geometry"] = geometry
    risk.setdefault("type", "controlled_release")
    scope["risk_boundary"] = risk

    missing_fields = []
    if not upstream_points:
        missing_fields.append("upstream_metering_points")
    if not downstream_nodes:
        missing_fields.append("downstream_protection_nodes")
    if not paths:
        missing_fields.append("coordination_paths")
    if not polygon:
        missing_fields.append("risk_boundary.geometry.polygon")
    scope["available"] = bool(t_lng is not None or upstream_points or downstream_nodes or paths)
    scope["missing_fields"] = missing_fields
    scope["source"] = "postgresql" if scope["available"] else "none"
    scope["data_lineage"] = {
        "source": scope["source"],
        "tables": ["road6.dim_inter_info", "road6.dim_link_info"],
    }
    strategy["control_scope_map"] = scope


def build_plan_preview_map(
    ticket: dict[str, Any],
    plan_block: dict[str, Any] | None,
) -> dict[str, Any]:
    """配时变化预览（act8）。"""
    ticket = ticket or {}
    plan_block = plan_block or {}
    recommended = plan_block.get("recommended") if isinstance(plan_block.get("recommended"), dict) else {}
    timing = recommended.get("timing") if isinstance(recommended.get("timing"), dict) else {}
    t_lng, t_lat = _coords(ticket)

    phase_changes: list[dict[str, Any]] = []
    for stage in timing.get("phase_stage_timing_list") or []:
        if not isinstance(stage, dict):
            continue
        delta = stage.get("green_delta_s")
        if delta is None:
            continue
        phase_changes.append(
            {
                "phase_stage_id": stage.get("phase_stage_id"),
                "phase_stage_name": stage.get("phase_stage_name"),
                "green_delta_s": delta,
                "label": stage.get("phase_stage_name"),
            }
        )

    available = t_lng is not None and bool(phase_changes)
    return {
        "action": "map_scene",
        "phase": "plan_preview",
        "available": available,
        "reason": None if available else "缺少推荐方案配时变化",
        "center": [t_lng, t_lat] if t_lng is not None else None,
        "plan_id": recommended.get("plan_id"),
        "plan_name": recommended.get("name"),
        "cycle_delta_s": timing.get("cycle_delta_s"),
        "phase_changes": phase_changes[:6],
        "missing_fields": [] if available else ["recommended.timing.phase_stage_timing_list"],
    }


def build_plan_output_map(ticket: dict[str, Any], diagnosis: dict[str, Any], plan_block: dict[str, Any] | None) -> dict[str, Any]:
    """最终方案地图只认 action_package/trial_loop；不再把优化器候选 timing 当成已采纳动作。"""
    plan_block = plan_block or {}
    recommended = plan_block.get("recommended") if isinstance(plan_block.get("recommended"), dict) else {}
    action_package = recommended.get("action_package") if isinstance(recommended.get("action_package"), dict) else {}
    layers = action_package.get("layers") if isinstance(action_package.get("layers"), dict) else {}
    actions = [a for a in layers.get("proposed_timing") or [] if isinstance(a, dict)]
    trial = plan_block.get("trial_loop") if isinstance(plan_block.get("trial_loop"), dict) else {}
    metrics = diagnosis.get("metrics") if isinstance(diagnosis.get("metrics"), dict) else {}
    channel = ((diagnosis.get("map_scenes") or {}).get("channelization_map") or {})
    target_link: dict[str, Any] = {}
    channel_links = [link for link in channel.get("links") or [] if isinstance(link, dict)]
    for link in channel.get("links") or []:
        if isinstance(link, dict) and str(link.get("link_role", "")).lower() in ("entrance", "进口") and str(link.get("dir8_code")) == str(metrics.get("dir8_code")):
            target_link = link
            break
    changes: list[dict[str, Any]] = []
    timing = recommended.get("timing") if isinstance(recommended.get("timing"), dict) else {}
    timing_stages = [stage for stage in timing.get("phase_stage_timing_list") or [] if isinstance(stage, dict)]
    for action in actions:
        if action.get("green_delta_s") is None:
            continue
        is_target = action.get("green_delta_s", 0) > 0
        matching_stages = [stage for stage in timing_stages if stage.get("green_delta_s") == action.get("green_delta_s")]
        if is_target and metrics.get("target_movement_key"):
            matching_stages = [stage for stage in matching_stages if any(
                (movement.get("movement_key") or movement.get("movementKey")) == metrics.get("target_movement_key")
                for movement in stage.get("movements") or [] if isinstance(movement, dict)
            )] or matching_stages
        stage = matching_stages[0] if matching_stages else {}
        movements = [m for m in stage.get("movements") or [] if isinstance(m, dict)]
        movement_keys = [m.get("movement_key") or m.get("movementKey") for m in movements if m.get("movement_key") or m.get("movementKey")]
        dir8_codes = {str(m.get("dir8No")) for m in movements if m.get("dir8No") is not None}
        mapped_links = [link for link in channel_links if str(link.get("link_role", "")).lower() in ("entrance", "进口") and str(link.get("dir8_code")) in dir8_codes]
        if is_target and not mapped_links and target_link:
            mapped_links = [target_link]
        paths = [link.get("path") for link in mapped_links if isinstance(link.get("path"), list) and len(link.get("path")) >= 2]
        path = paths[0] if is_target and paths else []
        resolved = bool(stage) and bool(paths)
        changes.append({
            "movement_key": metrics.get("target_movement_key") if is_target else None,
            "movement_keys": movement_keys,
            "label": trial.get("target_label") if is_target else action.get("action"),
            "green_delta_s": action.get("green_delta_s"),
            "phase_stage_id": stage.get("phase_stage_id"),
            "phase_stage_ids": [stage.get("phase_stage_id")] if stage.get("phase_stage_id") is not None else [],
            "link_id": mapped_links[0].get("link_id") if is_target and mapped_links else None,
            "link_ids": [link.get("link_id") for link in mapped_links if link.get("link_id")],
            "path": path,
            "paths": paths,
            "label_anchor": (path or (paths[0] if paths else []))[len(path or (paths[0] if paths else [])) // 2] if (path or paths) else None,
            "mapping_status": "phase_resolved" if resolved else "phase_unresolved",
            "missing_fields": [] if resolved else ["phase_stage_id", "movement_key", "link_id"],
        })
    t_lng, t_lat = _coords(ticket)
    unresolved = [change for change in changes if change.get("mapping_status") != "phase_resolved"]
    available = t_lng is not None and bool(changes) and not unresolved
    missing_fields = sorted({
        field
        for change in unresolved
        for field in change.get("missing_fields") or []
    })
    return {
        "action": "map_scene", "phase": "plan_output", "available": available,
        "reason": None if available else (
            "最终方案相位与真实 link geometry 未完全映射"
            if unresolved else "缺少最终 action_package 或目标坐标"
        ),
        "missing_fields": missing_fields if unresolved else ([] if available else ["recommended.action_package", "center"]),
        "center": [t_lng, t_lat] if t_lng is not None else None,
        "plan_id": recommended.get("plan_id"), "plan_name": recommended.get("name"),
        "cycle_delta_s": trial.get("cycle_delta_s"), "phase_changes": changes,
        "source": "final_plan_and_postgresql",
        "consistency": {"source": "plan.recommended.action_package", "trial_loop_cycle_delta_s": trial.get("cycle_delta_s")},
    }


def enrich_map_scenes(
    *,
    ticket: dict[str, Any] | None,
    phases: dict[str, Any],
    plan_block: dict[str, Any] | None = None,
) -> None:
    """写入 diagnosis.map_scenes 下的 act 专用图层（前端统一消费）。"""
    diagnosis = phases.get("diagnosis")
    if not isinstance(diagnosis, dict):
        return
    map_scenes = diagnosis.get("map_scenes")
    if not isinstance(map_scenes, dict):
        map_scenes = {}
        diagnosis["map_scenes"] = map_scenes

    ticket = ticket or {}
    cause = phases.get("cause") if isinstance(phases.get("cause"), dict) else {}
    strategy = phases.get("strategy") if isinstance(phases.get("strategy"), dict) else None

    enrich_flow_trace_visualization_contract(diagnosis)

    map_scenes["queue_evidence"] = build_queue_evidence_map(diagnosis)
    map_scenes["diagnosis_compare"] = build_diagnosis_compare_map(ticket, diagnosis)

    cause_spatial = build_cause_spatial_map(ticket, cause, diagnosis)
    map_scenes["cause_spatial"] = cause_spatial
    if strategy is not None:
        enrich_control_scope_map(ticket=ticket, diagnosis=diagnosis, strategy=strategy)
        phases["strategy"] = strategy

    preview = build_plan_preview_map(ticket, plan_block)
    map_scenes["plan_preview"] = preview
    if isinstance(plan_block, dict):
        plan_block["map_scene"] = build_plan_output_map(ticket, diagnosis, plan_block)

    phases["diagnosis"] = diagnosis
