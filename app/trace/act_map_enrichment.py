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
    return {
        "queue_ratio": metrics.get("queue_ratio") or metrics.get("queue_storage_ratio_max"),
        "saturation": metrics.get("saturation") or metrics.get("saturation_rate"),
        "green_utilization": metrics.get("green_utilization"),
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
    available = t_lng is not None and (d_lng is not None or bool(pd.get("inter_name")))
    return {
        "action": "map_scene",
        "phase": "diagnosis_compare",
        "available": available,
        "reason": None if available else "缺少目标或下游坐标",
        "comparison_label": "本路口 vs 主要下游",
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
                "color": "#ff5050",
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
                "color": "#38bdf8",
            }
        )

    return {
        "action": "map_scene",
        "phase": "cause_spatial",
        "available": bool(annotations),
        "reason": None if annotations else "缺少空间标注数据",
        "primary_cause": _clean((cause.get("cause_analysis") or {}).get("primary_cause")),
        "annotations": annotations,
    }


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

    compare = build_diagnosis_compare_map(ticket, diagnosis)
    if compare.get("available"):
        map_scenes["diagnosis_compare"] = compare

    cause_spatial = build_cause_spatial_map(ticket, cause, diagnosis)
    if cause_spatial.get("available"):
        map_scenes["cause_spatial"] = cause_spatial

    preview = build_plan_preview_map(ticket, plan_block)
    if preview.get("available"):
        map_scenes["plan_preview"] = preview

    phases["diagnosis"] = diagnosis
