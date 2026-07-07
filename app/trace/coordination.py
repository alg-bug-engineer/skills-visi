"""干线协调（时距关系）聚合。

只做「真实字段 → 结构化协调数据」的确定性计算与降级判定，可脱库单测。
真实来源（缺失即降级，禁止合成，见 docs/rule.md 约束14/16/19）：
- 节点间距 spacing_m：dim_link_info.length_m（经 scope.adjacent_inter_spacing_detail）
- 绝对相位 offset_abs_s：目标取 signal.offset_s；相邻取相邻路口现状配时 offset_sec
- 行程速度 travel_speed_kmh：真实 link_speed / line_index
- 旅行时间 travel_time_s：间距 / 速度（calc_travel_time_sec）
"""

from __future__ import annotations

from typing import Any

from app.data.traffic_metrics_logic import calc_travel_time_sec


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _spacing_index(spacing_detail: list[dict[str, Any]] | None) -> dict[str, float]:
    """按相邻路口 id 建间距索引（取真实 spacing_m，正值优先）。"""
    index: dict[str, float] = {}
    for row in spacing_detail or []:
        cor_id = str(row.get("adjacent_inter_id") or row.get("upstream_inter_id") or "")
        spacing = _as_float(row.get("spacing_m"))
        if not cor_id or spacing is None or spacing <= 0:
            continue
        prev = index.get(cor_id)
        if prev is None or spacing < prev:
            index[cor_id] = round(spacing, 2)
    return index


def _offset_index(adjacent_offsets: dict[str, Any] | None) -> dict[str, float]:
    """相邻路口绝对相位（offset_sec）索引，仅保留真实数值。"""
    index: dict[str, float] = {}
    for key, value in (adjacent_offsets or {}).items():
        if isinstance(value, dict):
            offset = _as_float(value.get("offset_s") or value.get("offset_sec"))
        else:
            offset = _as_float(value)
        if offset is not None:
            index[str(key)] = offset
    return index


def _speed_lookup(
    speed_by_key: dict[str, Any] | None, *keys: Any
) -> tuple[float | None, str | None]:
    """按 link_id / inter_id 命中真实路段速度；返回 (speed_kmh, source)。"""
    if not speed_by_key:
        return None, None
    for key in keys:
        if key is None:
            continue
        value = speed_by_key.get(str(key))
        if value is None:
            continue
        if isinstance(value, dict):
            speed = _as_float(value.get("speed_kmh") or value.get("avg_speed_kmh"))
            source = value.get("source") or "link_speed"
        else:
            speed = _as_float(value)
            source = "link_speed"
        if speed is not None and speed > 0:
            return round(speed, 2), str(source)
    return None, None


def _phase_diff(target_offset: float | None, node_offset: float | None, cycle: float | None) -> float | None:
    if target_offset is None or node_offset is None or not cycle or cycle <= 0:
        return None
    diff = (node_offset - target_offset) % cycle
    if diff > cycle / 2:
        diff -= cycle
    return round(diff, 1)


def _coordination_direction(upstream_nodes: list, downstream_nodes: list) -> str:
    has_up = bool(upstream_nodes)
    has_down = bool(downstream_nodes)
    if has_up and has_down:
        return "bidirectional"
    if has_up:
        return "inbound"
    if has_down:
        return "outbound"
    return "unknown"


def build_coordination_diagram(
    *,
    topology: dict[str, Any],
    signal: dict[str, Any] | None = None,
    spacing_detail: list[dict[str, Any]] | None = None,
    adjacent_offsets: dict[str, Any] | None = None,
    speed_by_key: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组装干线协调时距关系；字段全部来自真实数据源，缺失即 available=false。"""
    signal = signal or {}
    upstream_nodes = topology.get("upstream_nodes") or []
    downstream_nodes = topology.get("downstream_nodes") or []

    spacing_idx = _spacing_index(spacing_detail)
    offset_idx = _offset_index(adjacent_offsets)
    target_offset = _as_float(signal.get("offset_s"))
    cycle = _as_float(signal.get("current_cycle_s") or signal.get("cycle_s"))

    def _adjacent_node(raw: dict[str, Any], role: str) -> dict[str, Any]:
        if role == "upstream":
            cor_id = str(raw.get("upstream_inter_id") or "")
            name = raw.get("upstream_inter_name")
            lng, lat = raw.get("upstream_lng"), raw.get("upstream_lat")
        else:
            cor_id = str(raw.get("inter_id") or "")
            name = raw.get("inter_name")
            lng, lat = raw.get("lng"), raw.get("lat")
        spacing = spacing_idx.get(cor_id)
        offset = offset_idx.get(cor_id)
        phase_diff = _phase_diff(target_offset, offset, cycle)
        speed, speed_source = _speed_lookup(speed_by_key, raw.get("link_id"), cor_id)
        travel_time = calc_travel_time_sec(spacing, speed) if spacing and speed else None
        return {
            "inter_id": cor_id or None,
            "inter_name": name,
            "lng": lng,
            "lat": lat,
            "role": role,
            "spacing_m": spacing,
            "spacing_source": "dim_link_info.length_m" if spacing is not None else None,
            "offset_abs_s": offset,
            "offset_source": "plan_cfg.offset_sec" if offset is not None else None,
            "phase_diff_s": phase_diff,
            "travel_speed_kmh": speed,
            "travel_time_s": round(travel_time, 1) if travel_time is not None else None,
            "travel_source": speed_source,
        }

    target_node = {
        "inter_id": topology.get("target_inter_id") or None,
        "inter_name": topology.get("target_inter_name"),
        "lng": topology.get("target_lng"),
        "lat": topology.get("target_lat"),
        "role": "target",
        "spacing_m": 0.0,
        "spacing_source": "self" if target_offset is not None or spacing_idx else None,
        "offset_abs_s": target_offset,
        "offset_source": "plan_cfg.offset_sec" if target_offset is not None else None,
        "phase_diff_s": 0.0 if target_offset is not None else None,
        "travel_speed_kmh": None,
        "travel_time_s": None,
        "travel_source": None,
    }

    nodes: list[dict[str, Any]] = []
    nodes.extend(_adjacent_node(n, "upstream") for n in upstream_nodes)
    nodes.append(target_node)
    nodes.extend(_adjacent_node(n, "downstream") for n in downstream_nodes)

    adjacent_nodes = [n for n in nodes if n["role"] != "target"]
    has_spacing = any(n["spacing_m"] for n in adjacent_nodes)
    has_phase = any(n["phase_diff_s"] is not None for n in adjacent_nodes)
    has_travel = any(n["travel_time_s"] is not None for n in adjacent_nodes)

    available = len(nodes) >= 2 and (has_phase or has_travel)

    reasons: list[str] = []
    if len(nodes) < 2:
        reasons.append("缺少相邻路口拓扑")
    else:
        if not has_spacing:
            reasons.append("缺少节点间距")
        if not has_phase:
            reasons.append("缺少相邻路口绝对相位")
        if not has_travel:
            reasons.append("缺少路段速度")

    sources: list[str] = []
    if has_spacing:
        sources.append("link_geom")
    if has_phase:
        sources.append("pg_signal")
    if has_travel:
        speed_sources = {n["travel_source"] for n in adjacent_nodes if n["travel_source"]}
        sources.extend(sorted(speed_sources))

    result: dict[str, Any] = {
        "available": available,
        "direction": _coordination_direction(upstream_nodes, downstream_nodes),
        "cycle_s": cycle,
        "target": {
            "inter_id": target_node["inter_id"],
            "inter_name": target_node["inter_name"],
            "lng": target_node["lng"],
            "lat": target_node["lat"],
        },
        "nodes": nodes,
        "source": "+".join(sources) if sources else None,
    }
    if not available:
        result["reason"] = "；".join(reasons) if reasons else "协调所需字段不足"
    return result
