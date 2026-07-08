"""Adapt PG task payloads for diagnosis and topology builders."""

from __future__ import annotations

import re
from typing import Any

from app.trace.geometry import orient_path, parse_linestring_wkt, parse_point_wkt
from app.trace.topology import TURN_LABEL, exit_dir8_for_turn, movement_label, resolve_dir8_turn


def parse_day_of_week(ticket: dict[str, Any]) -> int:
    period = str(ticket.get("period") or "")
    if "周六" in period or "周日" in period:
        return 6
    return 5


def parse_time_hhmm(time_range: str | None) -> str | None:
    if not time_range:
        return None
    match = re.search(r"(\d{1,2})[:：](\d{2})", str(time_range))
    if not match:
        return None
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def _hhmm_to_step(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 12 + int(minute) // 5


def parse_time_step_range(time_range: str | None) -> tuple[int | None, int | None]:
    """Parse time_range like 17:30-18:30 into 5-min step_index bounds."""
    if not time_range:
        return None, None
    matches = re.findall(r"(\d{1,2})[:：](\d{2})", str(time_range))
    if not matches:
        return None, None
    steps = [_hhmm_to_step(f"{int(h):02d}:{m}") for h, m in matches]
    if len(steps) == 1:
        return steps[0], steps[0]
    lo, hi = min(steps[0], steps[1]), max(steps[0], steps[1])
    return lo, hi


def metrics_for_diagnosis(pg_metrics: dict[str, Any], ticket: dict[str, Any]) -> dict[str, Any]:
    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    dir8, turn = resolve_dir8_turn(direction, movement)

    target_sat = _pick_row_metric(
        pg_metrics.get("turn_saturation_detail") or [],
        dir8,
        turn,
        ("turn_saturation", "saturation", "saturation_rate"),
    )
    if target_sat is None:
        target_sat = _pick_movement_metric(pg_metrics.get("movement_saturation") or {}, dir8, turn)
    saturation = float(target_sat if target_sat is not None else pg_metrics.get("saturation") or 0)

    target_flow = _pick_row_metric(
        pg_metrics.get("turn_flow_detail") or [],
        dir8,
        turn,
        ("turn_flow_total", "flow_vph", "volume_vph", "volume"),
    )
    if target_flow is None:
        target_flow = _pick_movement_metric(pg_metrics.get("movement_volume") or {}, dir8, turn)
    volume = float(target_flow if target_flow is not None else pg_metrics.get("volume") or 0)

    return {
        "queue_length_m": float(pg_metrics.get("queue_m") or 0),
        "storage_length_m": float(pg_metrics.get("storage_m") or 200),
        "volume_vph": volume,
        "capacity_vph": float(pg_metrics.get("capacity") or 0) or max(volume / max(saturation or 0.8, 0.1), 1),
        "saturation": saturation,
        "saturation_rate": saturation,
        "green_utilization": float(pg_metrics.get("green_utilization") or 0),
        "stop_count": float(pg_metrics.get("stop_count") or 0),
        "avg_delay_s": float(pg_metrics.get("avg_delay_s") or 0),
        "time_series_trend": "pg_loaded",
        "upstream_arrival_intensity": "high" if saturation >= 0.8 else "medium",
    }


def _target_center(inter: dict[str, Any]) -> tuple[float | None, float | None]:
    """从 dim_inter_info.geom_center（WKT POINT）解析目标路口中心。"""
    point = parse_point_wkt(inter.get("geom_center"))
    if point:
        return point[0], point[1]
    return None, None


def _coverage_index(
    correlate_rows: list[dict[str, Any]], dir8_code: int, turn_dir_no: int
) -> dict[tuple[str, str], float]:
    """构建 (trace_type, cor_inter_id) → 覆盖率索引（限定基准进口方向）。

    上游来向（PG trace_type=DOWNSTREAM）采用同进口物理合流口径；下游去向
    （PG trace_type=UPSTREAM）保持目标转向的一跳严格口径。
    """
    best: dict[tuple[str, str], float] = {}
    combined_upstream: dict[tuple[str, str], float] = {}
    for row in correlate_rows or []:
        try:
            row_dir8 = int(row.get("f_dir8_no"))
        except (TypeError, ValueError):
            continue
        if row_dir8 != int(dir8_code):
            continue
        cor_id = str(row.get("cor_inter_id") or "")
        if not cor_id:
            continue
        trace_type = str(row.get("trace_type") or "").upper()
        try:
            row_turn = int(row.get("turn_dir_no"))
            share = float(row.get("flow_share_ratio") or row.get("share_pct") or 0)
        except (TypeError, ValueError):
            continue
        key = (trace_type, cor_id)
        if trace_type == "DOWNSTREAM":
            combined_upstream[key] = combined_upstream.get(key, 0.0) + share
            continue
        if row_turn != int(turn_dir_no):
            continue
        prev = best.get(key)
        if prev is None or share > prev:
            best[key] = share
    for key, share in combined_upstream.items():
        best[key] = round(share, 2)
    return best


def _match_coverage(
    coverage: dict[tuple[str, str], float], preferred_trace: str, cor_id: str
) -> float | None:
    """按溯源类型匹配真实覆盖率；优先 preferred_trace，缺失回退另一类型。"""
    if not cor_id:
        return None
    other = "DOWNSTREAM" if preferred_trace == "UPSTREAM" else "UPSTREAM"
    for trace_type in (preferred_trace, other):
        val = coverage.get((trace_type, cor_id))
        if val is not None:
            return val
    return None


def topology_from_pg_raw(raw: dict[str, Any], ticket: dict[str, Any], inter: dict[str, Any]) -> dict[str, Any]:
    """基于真实路网几何（dim_link_info.geom）构建上下游一跳拓扑。

    方向为几何真源：problem 进口的 entrance link → 上游来向；对应转向的 exit link →
    下游去向。占比取自 flow_correlate（真实统计），缺失则为空。严禁合成坐标/折线。
    """
    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    dir8_code, turn_dir_no = resolve_dir8_turn(direction, movement)
    exit_dir8 = exit_dir8_for_turn(dir8_code, turn_dir_no)

    target_lng, target_lat = _target_center(inter)

    geom_rows = raw.get("trace_geometry") or []
    correlate_rows = raw.get("flow_correlate") or []
    coverage = _coverage_index(correlate_rows, dir8_code, turn_dir_no)

    upstream_nodes: list[dict[str, Any]] = []
    downstream_nodes: list[dict[str, Any]] = []
    seen_up: set[str] = set()
    seen_down: set[str] = set()

    for row in geom_rows:
        try:
            link_dir8 = int(row.get("dir8_code"))
        except (TypeError, ValueError):
            continue
        relation = str(row.get("relation_direction") or "")
        cor_id = str(row.get("adjacent_inter_id") or "")
        cor_name = row.get("adjacent_inter_name")
        adj_lng = row.get("adjacent_lng")
        adj_lat = row.get("adjacent_lat")
        path = parse_linestring_wkt(row.get("geom_wkt"))

        if relation == "upstream" and link_dir8 == dir8_code:
            if cor_id and cor_id in seen_up:
                continue
            seen_up.add(cor_id)
            share = _match_coverage(coverage, "UPSTREAM", cor_id)
            oriented = orient_path(path, adj_lng, adj_lat, target_lng, target_lat)
            upstream_nodes.append(
                {
                    "upstream_inter_id": cor_id or None,
                    "upstream_inter_name": cor_name or "上一路口",
                    "upstream_lng": adj_lng,
                    "upstream_lat": adj_lat,
                    "vehicles_base": 100,
                    "link_id": row.get("link_id"),
                    "path": oriented,
                    "path_source": "link_geom" if len(oriented) >= 2 else "none",
                    "upstream_movements": [
                        {
                            "turn": movement,
                            "feed_direction": f"{direction}{movement}",
                            "share_pct": share,
                            "vehicles_of_100": int(round(share)) if share is not None else None,
                            "raw_coverage": share,
                        }
                    ],
                }
            )
        elif relation == "downstream" and exit_dir8 is not None and link_dir8 == exit_dir8:
            if cor_id and cor_id in seen_down:
                continue
            seen_down.add(cor_id)
            share = _match_coverage(coverage, "DOWNSTREAM", cor_id)
            oriented = orient_path(path, target_lng, target_lat, adj_lng, adj_lat)
            downstream_nodes.append(
                {
                    "inter_id": cor_id or None,
                    "inter_name": cor_name or "下游信控节点",
                    "role": "downstream",
                    "lng": adj_lng,
                    "lat": adj_lat,
                    "share_pct": share,
                    "link_id": row.get("link_id"),
                    "receiving_dir8": exit_dir8,
                    "receiving_label": movement_label(exit_dir8, 2),
                    "path": oriented,
                    "path_source": "link_geom" if len(oriented) >= 2 else "none",
                }
            )

    # 主来向占比降序（真实值优先），无占比排后
    upstream_nodes.sort(
        key=lambda n: (n["upstream_movements"][0].get("share_pct") or -1), reverse=True
    )
    downstream_nodes.sort(key=lambda n: (n.get("share_pct") or -1), reverse=True)

    volume_vph = float(metrics_for_diagnosis(raw.get("metrics") or {}, ticket).get("volume_vph") or 0)
    has_geometry = bool(upstream_nodes or downstream_nodes)

    from app.trace.map_scene import resolve_correlate_period

    period_type = resolve_correlate_period(ticket.get("period"), ticket.get("time_range")) or "EVENING_PEAK"

    return {
        "target_inter_id": str(inter.get("inter_id") or ticket.get("inter_id") or ""),
        "target_inter_name": inter.get("inter_name") or ticket.get("intersection_name"),
        "target_lng": target_lng,
        "target_lat": target_lat,
        "dir8_code": dir8_code,
        "turn_dir_no": turn_dir_no,
        "exit_dir8": exit_dir8,
        "period_type": period_type,
        "day_basis": "工作日",
        "upstream_arrival_flow_vph": volume_vph,
        "upstream_release_intensity_vph": volume_vph * 0.95,
        "upstream_arrival_intensity": "high",
        "phase_offset_match": None,
        "upstream_nodes": upstream_nodes,
        "downstream_nodes": downstream_nodes,
        "geometry_source": "dim_link_info.geom" if has_geometry else "unavailable",
        "caveat": "PG 拓扑：几何取自 dim_link_info.geom，占比取自 flow_correlate",
    }


def merge_pg_task_into_context(task: dict[str, Any], pg_task: dict[str, Any]) -> None:
    for key in ("scope", "signal", "context", "metrics", "constraints"):
        if key in pg_task and pg_task[key]:
            task[key] = {**(task.get(key) or {}), **pg_task[key]}


def _as_float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_dir8(row: dict[str, Any]) -> int | None:
    for key in ("dir8No", "dir8_no", "f_dir_8", "f_dir8_no", "dir8"):
        value = _as_float_or_none(row.get(key))
        if value is not None:
            return int(value)
    return None


def _row_turn(row: dict[str, Any]) -> int | None:
    for key in ("turnDirNo", "turn_dir_no", "turn"):
        value = _as_float_or_none(row.get(key))
        if value is not None:
            return int(value)
    return None


def _pick_row_metric(
    rows: list[dict[str, Any]],
    dir8: int,
    turn: int,
    fields: tuple[str, ...],
) -> float | None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _row_dir8(row) != int(dir8) or _row_turn(row) != int(turn):
            continue
        for field in fields:
            value = _as_float_or_none(row.get(field))
            if value is not None:
                return value
    return None


def _metric_value(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("value", "saturation", "saturation_rate", "volume", "flow_vph", "turn_flow_total"):
            parsed = _as_float_or_none(value.get(key))
            if parsed is not None:
                return parsed
        return None
    return _as_float_or_none(value)


def _movement_key_matches(text: str, dir8: int, turn: int) -> bool:
    normalized = text.strip()
    candidates = {
        f"d{dir8}_t{turn}",
        f"dir{dir8}_turn{turn}",
        movement_label(dir8, turn),
    }
    turn_label = TURN_LABEL.get(int(turn))
    if turn_label:
        candidates.add(f"{dir8}_{turn_label}")
    return any(candidate and candidate in normalized for candidate in candidates)


def _pick_movement_metric(mapping: dict[str, Any], dir8: int, turn: int) -> float | None:
    for key, value in mapping.items():
        if isinstance(value, dict) and _row_dir8(value) == int(dir8) and _row_turn(value) == int(turn):
            return _metric_value(value)
        if _movement_key_matches(str(key), dir8, turn):
            return _metric_value(value)
    if len(mapping) == 1:
        return _metric_value(next(iter(mapping.values())))
    return None
