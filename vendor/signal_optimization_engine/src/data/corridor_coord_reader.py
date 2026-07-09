"""PostgreSQL 干线协调 DWS 图层读取。"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from data.metric_reader import (
    _dim_inter_qualified,
    _link_dim_qualified,
    _qident,
    _timing_schema,
    _to_int,
    _value_stats,
    parse_geom_center,
    step_index_to_hhmm,
)
from preprocessing.index_cal.corridor_coord_mine import WEEKDAY_NAMES, format_time

TABLE_CFG = "dws_corridor_coord_cfg"
TABLE_GROUP = "dws_corridor_coord_group"
TABLE_STOP_MM = "dws_corridor_coord_stop_mm"
TABLE_LINK_STATUS = "dws_inter_link_status_5min_mm"
# 协调口径：原始 stop_times 大于该阈值记为 1 次停车，否则为 0
COORD_STOP_TIMES_THRESHOLD = 0.6

_WKT_LINESTRING = re.compile(
    r"LINESTRING\s*\((.+)\)",
    re.IGNORECASE,
)

CORRIDOR_COLORS = [
    "#2563eb",
    "#7c3aed",
    "#db2777",
    "#ea580c",
    "#059669",
    "#0891b2",
    "#ca8a04",
    "#dc2626",
    "#4f46e5",
    "#0d9488",
]


def _parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _parse_wkt_linestring(value: Any) -> list[list[float]]:
    text = str(value or "").strip()
    if not text:
        return []
    match = _WKT_LINESTRING.search(text)
    if not match:
        return []
    coords: list[list[float]] = []
    for part in match.group(1).split(","):
        nums = part.strip().split()
        if len(nums) >= 2:
            try:
                coords.append([float(nums[0]), float(nums[1])])
            except ValueError:
                continue
    return coords


def _cfg_qualified() -> str:
    return f"{_qident(_timing_schema())}.{_qident(TABLE_CFG)}"


def _group_qualified() -> str:
    return f"{_qident(_timing_schema())}.{_qident(TABLE_GROUP)}"


def _stop_metrics_qualified() -> str:
    return f"{_qident(_timing_schema())}.{_qident(TABLE_STOP_MM)}"


def _period_matches(query_sec: int, start_sec: int, end_sec: int) -> bool:
    query_sec = max(0, min(query_sec, 86399))
    if end_sec <= 86400:
        return start_sec <= query_sec < end_sec
    # 跨午夜时段
    return query_sec >= start_sec or query_sec < (end_sec - 86400)


def _link_status_qualified() -> str:
    return f"{_qident(_timing_schema())}.{_qident(TABLE_LINK_STATUS)}"


def _period_step_indices(start_sec: int, end_sec: int) -> list[int]:
    """协调时段内全部 5 分钟 step_index（0–287）。"""
    start_sec = max(0, int(start_sec))
    end_sec = max(start_sec + 1, int(end_sec))
    steps: list[int] = []
    if end_sec <= 86400:
        lo = max(0, min(287, start_sec // 300))
        hi = max(0, min(287, (end_sec - 1) // 300))
        steps.extend(range(lo, hi + 1))
        return steps
    # 跨午夜： [start_sec, 86400) ∪ [0, end_sec)
    lo = max(0, min(287, start_sec // 300))
    steps.extend(range(lo, 288))
    hi = max(0, min(287, (end_sec - 86400 - 1) // 300))
    steps.extend(range(0, hi + 1))
    return sorted(set(steps))


def _fetch_edge_approach_links(
    conn,
    edges: list[tuple[str, str]],
) -> dict[tuple[str, str], str]:
    """(from_inter, to_inter) -> 进口 link_id（dim_link_info）。"""
    if not edges:
        return {}
    from_ids = sorted({a for a, _ in edges})
    to_ids = sorted({b for _, b in edges})
    dim = _link_dim_qualified()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT f_inter_id::text AS f_inter_id,
                   t_inter_id::text AS t_inter_id,
                   link_id::text AS link_id
            FROM {dim}
            WHERE f_inter_id::text = ANY(%s)
              AND t_inter_id::text = ANY(%s)
            """,
            (from_ids, to_ids),
        )
        rows = cur.fetchall()

    wanted = set(edges)
    out: dict[tuple[str, str], str] = {}
    for row in rows:
        key = (str(row["f_inter_id"]), str(row["t_inter_id"]))
        if key not in wanted:
            continue
        link_id = str(row.get("link_id") or "").strip()
        if link_id and key not in out:
            out[key] = link_id
    return out


def _fetch_link_stop_times(
    conn,
    *,
    day_of_week: int,
    step_indices: list[int],
    profile: list[tuple[str, str]],
) -> dict[tuple[str, str, int], float]:
    """(inter_id, link_id, step_index) -> stop_times（dws_inter_link_status_5min_mm）。"""
    if not profile or not step_indices:
        return {}
    inter_ids = sorted({inter_id for inter_id, _ in profile})
    link_ids = sorted({link_id for _, link_id in profile})
    wanted = {(inter_id, link_id) for inter_id, link_id in profile}
    status_q = _link_status_qualified()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT inter_id::text AS inter_id,
                   link_id::text AS link_id,
                   step_index,
                   stop_times
            FROM {status_q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND day_of_week = %s
              AND step_index = ANY(%s)
              AND inter_id::text = ANY(%s)
              AND link_id::text = ANY(%s)
            """,
            (day_of_week, step_indices, inter_ids, link_ids),
        )
        rows = cur.fetchall()

    out: dict[tuple[str, str, int], float] = {}
    for row in rows:
        inter_id = str(row["inter_id"])
        link_id = str(row["link_id"])
        if (inter_id, link_id) not in wanted:
            continue
        step = _to_int(row.get("step_index"))
        if step is None:
            continue
        try:
            out[(inter_id, link_id, step)] = float(row.get("stop_times") or 0)
        except (TypeError, ValueError):
            out[(inter_id, link_id, step)] = 0.0
    return out


def _direction_profiles(
    ordered_ids: list[str],
    edge_links: dict[tuple[str, str], str],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """正向 / 反向干线进口 link：(inter_id, link_id) 按行驶顺序。"""
    forward: list[tuple[str, str]] = []
    reverse: list[tuple[str, str]] = []
    n = len(ordered_ids)
    for i in range(1, n):
        key = (ordered_ids[i - 1], ordered_ids[i])
        link_id = edge_links.get(key)
        if link_id:
            forward.append((ordered_ids[i], link_id))
    for i in range(n - 2, -1, -1):
        key = (ordered_ids[i + 1], ordered_ids[i])
        link_id = edge_links.get(key)
        if link_id:
            reverse.append((ordered_ids[i], link_id))
    return forward, reverse


def _coord_stop_count(raw_stop_times: float) -> int:
    """协调口径停车次数：原始 stop_times > 阈值记 1，否则 0。"""
    try:
        value = float(raw_stop_times)
    except (TypeError, ValueError):
        return 0
    return 1 if value > COORD_STOP_TIMES_THRESHOLD else 0


def _continuous_stop_sets(
    profile: list[tuple[str, str]],
    avg_by_inter: dict[str, float],
    *,
    min_len: int = 2,
    eps: float = 1e-9,
) -> list[list[str]]:
    """沿行驶顺序找出协调口径停车（0/1）时段均值 > 0 的连续路口集合（长度 >= min_len）。"""
    sets: list[list[str]] = []
    current: list[str] = []
    for inter_id, _ in profile:
        if avg_by_inter.get(inter_id, 0.0) > eps:
            current.append(inter_id)
        else:
            if len(current) >= min_len:
                sets.append(current)
            current = []
    if len(current) >= min_len:
        sets.append(current)
    return sets


def _compute_direction_stop_metrics(
    profile: list[tuple[str, str]],
    stop_data: dict[tuple[str, str, int], float],
    step_indices: list[int],
    inter_names: dict[str, str],
) -> dict[str, Any]:
    if not profile or not step_indices:
        return {
            "avgTotalStopTimes": None,
            "intersectionCount": 0,
            "interStopDetails": [],
            "continuousStopSets": [],
        }

    per_step_totals: list[float] = []
    avg_by_inter: dict[str, float] = {}
    details: list[dict[str, Any]] = []

    for inter_id, link_id in profile:
        raw_vals = [stop_data.get((inter_id, link_id, step), 0.0) for step in step_indices]
        coord_vals = [_coord_stop_count(v) for v in raw_vals]
        avg_coord_stop = sum(coord_vals) / len(coord_vals) if coord_vals else 0.0
        avg_by_inter[inter_id] = avg_coord_stop
        details.append(
            {
                "interId": inter_id,
                "interName": inter_names.get(inter_id, inter_id),
                "linkId": link_id,
                "avgStopTimes": round(avg_coord_stop, 3),
                "rawAvgStopTimes": round(sum(raw_vals) / len(raw_vals), 3) if raw_vals else 0.0,
            }
        )

    for step in step_indices:
        total = sum(
            _coord_stop_count(stop_data.get((inter_id, link_id, step), 0.0))
            for inter_id, link_id in profile
        )
        per_step_totals.append(total)

    avg_total = sum(per_step_totals) / len(per_step_totals) if per_step_totals else None
    cont_sets = _continuous_stop_sets(profile, avg_by_inter)
    cont_payload = [
        {
            "interIds": ids,
            "interNames": [inter_names.get(i, i) for i in ids],
            "count": len(ids),
        }
        for ids in cont_sets
    ]

    return {
        "stopTimesThreshold": COORD_STOP_TIMES_THRESHOLD,
        "avgTotalStopTimes": round(avg_total, 3) if avg_total is not None else None,
        "intersectionCount": len(profile),
        "stepCount": len(step_indices),
        "interStopDetails": details,
        "continuousStopSets": cont_payload,
    }


def _precomputed_row_to_stop_metrics(row: dict[str, Any]) -> dict[str, Any]:
    threshold = float(row.get("stop_times_threshold") or COORD_STOP_TIMES_THRESHOLD)
    period_step_count = int(row.get("period_step_count") or 0)
    fwd_details = _parse_json(row.get("fwd_inter_stop_json"), [])
    rev_details = _parse_json(row.get("rev_inter_stop_json"), [])
    fwd_sets = _parse_json(row.get("fwd_continuous_stop_sets_json"), [])
    rev_sets = _parse_json(row.get("rev_continuous_stop_sets_json"), [])

    def _fwd_rev_payload(prefix: str, details: list[Any], sets: list[Any]) -> dict[str, Any]:
        count_key = f"{prefix}_intersection_count"
        avg_key = f"{prefix}_avg_total_stop_times"
        return {
            "stopTimesThreshold": threshold,
            "avgTotalStopTimes": row.get(avg_key),
            "intersectionCount": int(row.get(count_key) or 0),
            "stepCount": period_step_count,
            "interStopDetails": details,
            "continuousStopSets": sets,
        }

    return {
        "sourceTable": str(row.get("source_table") or f"{_timing_schema()}.{TABLE_STOP_MM}"),
        "stopTimesThreshold": threshold,
        "periodStepCount": period_step_count,
        "forward": _fwd_rev_payload("fwd", fwd_details, fwd_sets),
        "reverse": _fwd_rev_payload("rev", rev_details, rev_sets),
    }


def _fetch_precomputed_stop_metrics_map(
    conn,
    *,
    day_of_week: int,
    group_ids: list[str],
) -> dict[str, dict[str, Any]]:
    if not group_ids:
        return {}
    stop_q = _stop_metrics_qualified()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT group_id, day_of_week, corridor_id,
                   period_start_sec, period_end_sec, cycle_len_sec,
                   stop_times_threshold, period_step_count, source_table,
                   fwd_avg_total_stop_times, rev_avg_total_stop_times,
                   fwd_intersection_count, rev_intersection_count,
                   fwd_inter_stop_json, rev_inter_stop_json,
                   fwd_continuous_stop_sets_json, rev_continuous_stop_sets_json
            FROM {stop_q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND day_of_week = %s
              AND group_id = ANY(%s)
            """,
            (day_of_week, group_ids),
        )
        rows = cur.fetchall()
    return {str(row["group_id"]): _precomputed_row_to_stop_metrics(row) for row in rows}


def _resolve_group_stop_metrics(
    conn,
    parsed: dict[str, Any],
    *,
    day_of_week: int,
    precomputed_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    cached = precomputed_map.get(parsed["group_id"])
    if cached is not None:
        return cached
    return compute_corridor_group_stop_metrics(
        conn,
        ordered_ids=parsed["ordered_ids"],
        inter_names=parsed["inter_names"],
        day_of_week=day_of_week,
        period_start_sec=parsed["period_start"],
        period_end_sec=parsed["period_end"],
    )


def compute_corridor_group_stop_metrics(
    conn,
    *,
    ordered_ids: list[str],
    inter_names: dict[str, str],
    day_of_week: int,
    period_start_sec: int,
    period_end_sec: int,
) -> dict[str, Any]:
    """计算协调组在时段内的正向/反向平均总停车次数与连续停车路口集合。"""
    if len(ordered_ids) < 2:
        return {
            "sourceTable": f'{_timing_schema()}.{TABLE_LINK_STATUS}',
            "stopTimesThreshold": COORD_STOP_TIMES_THRESHOLD,
            "periodStepCount": 0,
            "forward": _compute_direction_stop_metrics([], {}, [], inter_names),
            "reverse": _compute_direction_stop_metrics([], {}, [], inter_names),
        }

    edges_fwd = [(ordered_ids[i], ordered_ids[i + 1]) for i in range(len(ordered_ids) - 1)]
    edges = list({*edges_fwd, *((b, a) for a, b in edges_fwd)})
    edge_links = _fetch_edge_approach_links(conn, edges)
    forward_profile, reverse_profile = _direction_profiles(ordered_ids, edge_links)
    step_indices = _period_step_indices(period_start_sec, period_end_sec)
    profile = forward_profile + reverse_profile
    stop_data = _fetch_link_stop_times(
        conn,
        day_of_week=day_of_week,
        step_indices=step_indices,
        profile=profile,
    )

    return {
        "sourceTable": f'{_timing_schema()}.{TABLE_LINK_STATUS}',
        "stopTimesThreshold": COORD_STOP_TIMES_THRESHOLD,
        "periodStepCount": len(step_indices),
        "forward": _compute_direction_stop_metrics(
            forward_profile, stop_data, step_indices, inter_names
        ),
        "reverse": _compute_direction_stop_metrics(
            reverse_profile, stop_data, step_indices, inter_names
        ),
    }


def fetch_corridor_catalog(conn) -> list[dict[str, Any]]:
    qualified = _cfg_qualified()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT corridor_id, corridor_name, primary_road_name, intersection_count,
                   schedule_summary_json
            FROM {qualified}
            WHERE is_deleted = 0
            ORDER BY intersection_count DESC, corridor_id
            """
        )
        rows = cur.fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        summary = _parse_json(row.get("schedule_summary_json"), {})
        items.append(
            {
                "corridorId": str(row["corridor_id"]),
                "corridorName": str(row["corridor_name"]),
                "primaryRoadName": str(row.get("primary_road_name") or ""),
                "intersectionCount": int(row.get("intersection_count") or 0),
                "groupCount": int(summary.get("group_count") or 0),
            }
        )
    return items


def fetch_corridor_time_slices(conn) -> dict[str, Any]:
    group_q = _group_qualified()
    stop_q = _stop_metrics_qualified()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT g.day_of_week,
                   COUNT(DISTINCT g.corridor_id) AS corridor_count,
                   COUNT(DISTINCT g.group_id) AS group_count
            FROM {group_q} g
            JOIN {stop_q} s
              ON s.group_id = g.group_id
             AND s.day_of_week = g.day_of_week
             AND COALESCE(s.is_deleted, 0) = 0
            WHERE g.is_deleted = 0
            GROUP BY g.day_of_week
            ORDER BY g.day_of_week
            """
        )
        day_rows = cur.fetchall()
        if not day_rows:
            cur.execute(
                f"""
                SELECT day_of_week,
                       COUNT(DISTINCT corridor_id) AS corridor_count,
                       COUNT(*) AS group_count
                FROM {group_q}
                WHERE is_deleted = 0
                GROUP BY day_of_week
                ORDER BY day_of_week
                """
            )
            day_rows = cur.fetchall()
    days = [
        {
            "dayOfWeek": int(row["day_of_week"]),
            "dayLabel": WEEKDAY_NAMES.get(int(row["day_of_week"]), str(row["day_of_week"])),
            "corridorCount": int(row["corridor_count"] or 0),
            "groupCount": int(row["group_count"] or 0),
        }
        for row in day_rows
    ]
    return {"days": days}


def _fetch_link_geometries(conn, link_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not link_ids:
        return {}
    dim = _link_dim_qualified()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT link_id::text AS link_id,
                   road_name,
                   f_inter_id::text AS f_inter_id,
                   t_inter_id::text AS t_inter_id,
                   length_m,
                   ST_AsText(geom) AS geom_wkt
            FROM {dim}
            WHERE link_id = ANY(%s)
              AND geom IS NOT NULL
            """,
            (link_ids,),
        )
        rows = cur.fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        link_id = str(row["link_id"])
        out[link_id] = {
            "linkId": link_id,
            "roadName": str(row.get("road_name") or ""),
            "fInterId": str(row.get("f_inter_id") or ""),
            "tInterId": str(row.get("t_inter_id") or ""),
            "lengthM": float(row["length_m"]) if row.get("length_m") is not None else None,
            "coordinates": _parse_wkt_linestring(row.get("geom_wkt")),
        }
    return out


def _fetch_inter_geometries(conn, inter_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not inter_ids:
        return {}
    dim = _dim_inter_qualified()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT inter_id::text AS inter_id, inter_name, geom_center::text AS geom_center
            FROM {dim}
            WHERE inter_id = ANY(%s)
            """,
            (inter_ids,),
        )
        rows = cur.fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        inter_id = str(row["inter_id"])
        coords = parse_geom_center(row.get("geom_center"))
        out[inter_id] = {
            "interId": inter_id,
            "interName": str(row.get("inter_name") or inter_id),
            "coordinates": list(coords) if coords else None,
        }
    return out


def _color_for_corridor(corridor_id: str) -> str:
    digits = re.sub(r"\D", "", corridor_id)
    idx = int(digits) if digits else 0
    return CORRIDOR_COLORS[idx % len(CORRIDOR_COLORS)]


def _parse_corridor_group_row(row: dict[str, Any]) -> dict[str, Any]:
    inter_ids = [str(x) for x in _parse_json(row.get("inter_ids_json"), [])]
    inter_names = {
        str(k): str(v) for k, v in _parse_json(row.get("inter_names_json"), {}).items()
    }
    ordered_ids = [str(x) for x in _parse_json(row.get("inter_ids_ordered_json"), inter_ids)]
    return {
        "group_id": str(row["group_id"]),
        "corridor_id": str(row["corridor_id"]),
        "corridor_name": str(row.get("corridor_name") or row["corridor_id"]),
        "primary_road_name": str(row.get("primary_road_name") or ""),
        "period_start": int(row["period_start_sec"]),
        "period_end": int(row["period_end_sec"]),
        "cycle_len": int(row["cycle_len_sec"]),
        "intersection_count": int(row["intersection_count"] or len(inter_ids)),
        "inter_ids": inter_ids,
        "inter_names": inter_names,
        "ordered_ids": ordered_ids,
        "plan_by_inter": _parse_json(row.get("plan_by_inter_json"), {}),
        "link_ids": [str(x) for x in _parse_json(row.get("connecting_link_ids_json"), [])],
    }


def _build_group_stop_metric_entry(
    parsed: dict[str, Any],
    *,
    day_of_week: int,
    query_sec: int,
    stop_metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "groupId": parsed["group_id"],
        "corridorId": parsed["corridor_id"],
        "corridorName": parsed["corridor_name"],
        "periodStartTime": format_time(parsed["period_start"]),
        "periodEndTime": format_time(parsed["period_end"]),
        "periodStartSec": parsed["period_start"],
        "periodEndSec": parsed["period_end"],
        "cycleLenSec": parsed["cycle_len"],
        "activeAtQuery": _period_matches(
            query_sec,
            parsed["period_start"],
            parsed["period_end"],
        ),
        **stop_metrics,
    }


def _append_corridor_group_features(
    features: list[dict[str, Any]],
    *,
    parsed: dict[str, Any],
    stop_metrics: dict[str, Any],
    day_of_week: int,
    step_index: int,
    query_sec: int,
    link_geos: dict[str, dict[str, Any]],
    inter_geos: dict[str, dict[str, Any]],
) -> None:
    corridor_id_val = parsed["corridor_id"]
    color = _color_for_corridor(corridor_id_val)
    ordered_ids = parsed["ordered_ids"]
    inter_names = parsed["inter_names"]
    plan_by_inter = parsed["plan_by_inter"]
    period_start = parsed["period_start"]
    period_end = parsed["period_end"]
    cycle_len = parsed["cycle_len"]
    intersection_count = parsed["intersection_count"]

    base_props = {
        "layerKind": "corridor_coord",
        "groupId": parsed["group_id"],
        "corridorId": corridor_id_val,
        "corridorName": parsed["corridor_name"],
        "primaryRoadName": parsed["primary_road_name"],
        "dayOfWeek": day_of_week,
        "dayLabel": WEEKDAY_NAMES.get(day_of_week, str(day_of_week)),
        "timeLabel": step_index_to_hhmm(step_index),
        "querySec": query_sec,
        "periodStartTime": format_time(period_start),
        "periodEndTime": format_time(period_end),
        "cycleLenSec": cycle_len,
        "intersectionCount": intersection_count,
        "interIds": parsed["inter_ids"],
        "interNamesOrdered": [inter_names.get(i, i) for i in ordered_ids],
        "planByInter": plan_by_inter,
        "stopMetrics": stop_metrics,
        "value": intersection_count,
        "valueLabel": f"{intersection_count} 口 · {cycle_len}s",
        "color": color,
    }

    for link_id in parsed["link_ids"]:
        link = link_geos.get(link_id)
        if not link or not link.get("coordinates"):
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"{parsed['group_id']}:{link_id}",
                "geometry": {"type": "LineString", "coordinates": link["coordinates"]},
                "properties": {
                    **base_props,
                    "featureKind": "corridor_link",
                    "linkId": link_id,
                    "fInterId": link.get("fInterId") or "",
                    "tInterId": link.get("tInterId") or "",
                    "roadName": link.get("roadName") or "",
                    "lengthM": link.get("lengthM"),
                },
            }
        )

    for seq, inter_id in enumerate(ordered_ids, start=1):
        inter = inter_geos.get(inter_id)
        if not inter or not inter.get("coordinates"):
            continue
        inter_stop_fwd = next(
            (
                d
                for d in stop_metrics.get("forward", {}).get("interStopDetails", [])
                if d.get("interId") == inter_id
            ),
            None,
        )
        inter_stop_rev = next(
            (
                d
                for d in stop_metrics.get("reverse", {}).get("interStopDetails", [])
                if d.get("interId") == inter_id
            ),
            None,
        )
        features.append(
            {
                "type": "Feature",
                "id": f"{parsed['group_id']}:{inter_id}",
                "geometry": {"type": "Point", "coordinates": inter["coordinates"]},
                "properties": {
                    **base_props,
                    "featureKind": "corridor_inter",
                    "interId": inter_id,
                    "interName": inter_names.get(inter_id) or inter.get("interName") or inter_id,
                    "seqNo": seq,
                    "planNo": plan_by_inter.get(inter_id),
                    "forwardAvgStopTimes": inter_stop_fwd.get("avgStopTimes") if inter_stop_fwd else None,
                    "reverseAvgStopTimes": inter_stop_rev.get("avgStopTimes") if inter_stop_rev else None,
                },
            }
        )


def fetch_corridor_coord_layer(
    conn,
    *,
    day_of_week: int,
    step_index: int,
    corridor_id: str | None = None,
) -> dict[str, Any]:
    query_sec = max(0, min(int(step_index), 287)) * 300
    group_q = _group_qualified()
    cfg_q = _cfg_qualified()

    params: list[Any] = [day_of_week]
    corridor_filter = ""
    specific_corridor = corridor_id and corridor_id.strip() and corridor_id.strip() != "全部"
    if specific_corridor:
        corridor_filter = " AND g.corridor_id = %s"
        params.append(corridor_id.strip())

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT g.group_id, g.corridor_id, g.day_of_week,
                   g.period_start_sec, g.period_end_sec, g.cycle_len_sec,
                   g.intersection_count, g.inter_ids_json, g.inter_names_json,
                   g.plan_by_inter_json, g.connecting_link_ids_json,
                   c.corridor_name, c.primary_road_name, c.inter_ids_ordered_json
            FROM {group_q} g
            JOIN {cfg_q} c ON c.corridor_id = g.corridor_id AND c.is_deleted = 0
            WHERE g.is_deleted = 0
              AND g.day_of_week = %s
              {corridor_filter}
            ORDER BY g.corridor_id, g.period_start_sec, g.cycle_len_sec
            """,
            params,
        )
        rows = list(cur.fetchall())

    parsed_rows = [_parse_corridor_group_row(row) for row in rows]
    precomputed_map = _fetch_precomputed_stop_metrics_map(
        conn,
        day_of_week=day_of_week,
        group_ids=[parsed["group_id"] for parsed in parsed_rows],
    )
    matched_parsed = [
        parsed
        for parsed in parsed_rows
        if _period_matches(query_sec, parsed["period_start"], parsed["period_end"])
    ]

    if specific_corridor:
        visible_corridor_ids = {corridor_id.strip()}  # type: ignore[union-attr]
    else:
        visible_corridor_ids = {parsed["corridor_id"] for parsed in matched_parsed}

    corridor_period_options_by_corridor: dict[str, list[dict[str, Any]]] = {}
    for corridor_id_val in sorted(visible_corridor_ids):
        corridor_parsed = sorted(
            [parsed for parsed in parsed_rows if parsed["corridor_id"] == corridor_id_val],
            key=lambda item: (item["period_start"], item["cycle_len"], item["group_id"]),
        )
        corridor_period_options_by_corridor[corridor_id_val] = [
            _build_group_stop_metric_entry(
                parsed,
                day_of_week=day_of_week,
                query_sec=query_sec,
                stop_metrics=_resolve_group_stop_metrics(
                    conn,
                    parsed,
                    day_of_week=day_of_week,
                    precomputed_map=precomputed_map,
                ),
            )
            for parsed in corridor_parsed
        ]

    corridor_period_options = (
        corridor_period_options_by_corridor.get(corridor_id.strip(), [])  # type: ignore[union-attr]
        if specific_corridor
        else []
    )

    all_link_ids: set[str] = set()
    all_inter_ids: set[str] = set()
    for parsed in matched_parsed:
        all_link_ids.update(parsed["link_ids"])
        all_inter_ids.update(parsed["inter_ids"])

    link_geos = _fetch_link_geometries(conn, sorted(all_link_ids))
    inter_geos = _fetch_inter_geometries(conn, sorted(all_inter_ids))

    features: list[dict[str, Any]] = []
    value_numbers: list[float] = []
    group_stop_metrics: list[dict[str, Any]] = []

    for parsed in matched_parsed:
        value_numbers.append(float(parsed["intersection_count"]))
        stop_metrics = _resolve_group_stop_metrics(
            conn,
            parsed,
            day_of_week=day_of_week,
            precomputed_map=precomputed_map,
        )
        entry = _build_group_stop_metric_entry(
            parsed,
            day_of_week=day_of_week,
            query_sec=query_sec,
            stop_metrics=stop_metrics,
        )
        group_stop_metrics.append(entry)
        _append_corridor_group_features(
            features,
            parsed=parsed,
            stop_metrics=stop_metrics,
            day_of_week=day_of_week,
            step_index=step_index,
            query_sec=query_sec,
            link_geos=link_geos,
            inter_geos=inter_geos,
        )

    stats = _value_stats(value_numbers)
    return {
        "type": "FeatureCollection",
        "layerKind": "corridor_coord",
        "dayOfWeek": day_of_week,
        "stepIndex": step_index,
        "timeLabel": step_index_to_hhmm(step_index),
        "corridorId": corridor_id or "全部",
        "featureCount": len(features),
        "corridorCount": len({parsed["corridor_id"] for parsed in matched_parsed}),
        "groupCount": len(matched_parsed),
        "valueStats": stats,
        "stopMetricsByGroup": group_stop_metrics,
        "corridorPeriodOptions": corridor_period_options,
        "corridorPeriodOptionsByCorridor": corridor_period_options_by_corridor,
        "stopMetricsSource": TABLE_STOP_MM if precomputed_map else TABLE_LINK_STATUS,
        "features": features,
    }
