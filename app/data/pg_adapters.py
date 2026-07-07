"""Adapt PG task payloads for diagnosis and topology builders."""

from __future__ import annotations

import re
from typing import Any

from app.trace.topology import resolve_dir8_turn


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

    target_sat = _pick_movement_metric(pg_metrics.get("movement_saturation") or {}, dir8, turn)
    target_flow = _pick_movement_metric(pg_metrics.get("movement_volume") or {}, dir8, turn)

    return {
        "queue_length_m": float(pg_metrics.get("queue_m") or 0),
        "storage_length_m": float(pg_metrics.get("storage_m") or 200),
        "volume_vph": float(target_flow or pg_metrics.get("volume") or 0),
        "capacity_vph": float(pg_metrics.get("capacity") or 0) or max(float(target_flow or 0) / max(target_sat or 0.8, 0.1), 1),
        "green_utilization": float(pg_metrics.get("green_utilization") or 0),
        "stop_count": float(pg_metrics.get("stop_count") or 0),
        "avg_delay_s": float(pg_metrics.get("avg_delay_s") or 0),
        "time_series_trend": "pg_loaded",
        "upstream_arrival_intensity": "high" if float(pg_metrics.get("saturation") or 0) >= 0.8 else "medium",
    }


def topology_from_pg_raw(raw: dict[str, Any], ticket: dict[str, Any], inter: dict[str, Any]) -> dict[str, Any]:
    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    dir8_code, turn_dir_no = resolve_dir8_turn(direction, movement)

    correlate_rows = raw.get("flow_correlate") or []
    upstream_nodes = []
    for row in correlate_rows[:3]:
        if str(row.get("cor_turn")) != str(turn_dir_no):
            continue
        upstream_nodes.append(
            {
                "upstream_inter_id": row.get("f_inter_id") or row.get("upstream_inter_id"),
                "upstream_inter_name": row.get("f_inter_name") or row.get("upstream_inter_name") or "上一路口",
                "upstream_lng": row.get("f_lng"),
                "upstream_lat": row.get("f_lat"),
                "vehicles_base": 100,
                "upstream_movements": [
                    {
                        "turn": movement,
                        "feed_direction": f"{direction}{movement}",
                        "share_pct": float(row.get("share_pct") or row.get("raw_coverage") or 0),
                        "vehicles_of_100": int(float(row.get("share_pct") or 50)),
                        "raw_coverage": float(row.get("raw_coverage") or 0),
                    }
                ],
            }
        )

    downstream_nodes = []
    for row in (raw.get("turn_perf") or [])[:5]:
        if int(row.get("turn_dir_no") or 0) != turn_dir_no:
            continue
        downstream_nodes.append(
            {
                "inter_id": row.get("t_inter_id") or row.get("downstream_inter_id"),
                "inter_name": row.get("t_inter_name") or "下游信控节点",
                "role": "downstream",
                "lng": row.get("t_lng"),
                "lat": row.get("t_lat"),
                "queue_length_m": float(row.get("queue_len_max") or row.get("queue_len_avg") or 0),
                "storage_length_m": float(row.get("storage_len") or 180),
                "volume_vph": float(row.get("turn_flow_total") or 0) * 12,
                "capacity_vph": float(row.get("capacity_vph") or 1600),
                "green_utilization": float(row.get("green_utilization") or 0.8),
            }
        )

    center = inter.get("geom_center")
    lng = lat = None
    if isinstance(center, str) and "," in center:
        parts = center.strip("() ").split(",")
        if len(parts) >= 2:
            lng, lat = float(parts[0]), float(parts[1])

    return {
        "target_inter_id": str(inter.get("inter_id") or ticket.get("inter_id") or ""),
        "target_inter_name": inter.get("inter_name") or ticket.get("intersection_name"),
        "target_lng": lng,
        "target_lat": lat,
        "dir8_code": dir8_code,
        "turn_dir_no": turn_dir_no,
        "period_type": "EVENING_PEAK",
        "day_basis": "工作日",
        "upstream_arrival_flow_vph": float(metrics_for_diagnosis(raw.get("metrics") or {}, ticket).get("volume_vph") or 0),
        "upstream_release_intensity_vph": float(metrics_for_diagnosis(raw.get("metrics") or {}, ticket).get("volume_vph") or 0) * 0.95,
        "upstream_arrival_intensity": "high",
        "phase_offset_match": "pg",
        "upstream_nodes": upstream_nodes,
        "downstream_nodes": downstream_nodes,
        "caveat": "PG 拓扑：来自 flow_correlate / turn_perf",
    }


def merge_pg_task_into_context(task: dict[str, Any], pg_task: dict[str, Any]) -> None:
    for key in ("scope", "signal", "context", "metrics", "constraints"):
        if key in pg_task and pg_task[key]:
            task[key] = {**(task.get(key) or {}), **pg_task[key]}


def _pick_movement_metric(mapping: dict[str, Any], dir8: int, turn: int) -> float | None:
    for key, value in mapping.items():
        text = str(key)
        if str(dir8) in text and str(turn) in text:
            return float(value)
    if mapping:
        return float(next(iter(mapping.values())))
    return None
