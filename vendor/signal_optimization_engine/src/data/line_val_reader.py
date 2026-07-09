"""PostgreSQL line 综合评价图层读取。"""

from __future__ import annotations

import json
import re
from typing import Any

from data.metric_reader import (
    _day_label,
    _dim_inter_qualified,
    _link_dim_qualified,
    _qident,
    _road_schema,
    _timing_schema,
    _to_float,
    _to_int,
    _value_stats,
    parse_geom_center,
    step_index_to_hhmm,
)

TABLE_LINE_VAL = "dws_line_val_index_5min_mm"
TABLE_LINE_INFO = "dim_line_info"
TABLE_LINE_LINK = "dim_line_link_rltn"
TABLE_LINE_INTER = "dim_line_inter_rltn"

TRAVEL_DIR_FORWARD = 1
TRAVEL_DIR_REVERSE = 2
TRAVEL_DIR_LABELS = {TRAVEL_DIR_FORWARD: "正向", TRAVEL_DIR_REVERSE: "反向"}

LINE_METRIC_CATALOG: dict[str, dict[str, Any]] = {
    "line_travel_time_sec": {
        "label": "行程时间",
        "level": "line",
        "table": TABLE_LINE_VAL,
        "value_field": "travel_time_sec",
        "value_type": "numeric",
        "unit": "秒",
        "description": "line 内各 link 行程时间之和",
        "thresholds": [0, 60, 120, 180, 240],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444"],
        "legend_labels": ["< 60s", "60-119s", "120-179s", "180-239s", "≥ 240s"],
    },
    "line_stop_time_sec": {
        "label": "总延误",
        "level": "line",
        "table": TABLE_LINE_VAL,
        "value_field": "stop_time_sec",
        "value_type": "numeric",
        "unit": "秒",
        "description": "line 内各 link 延误时间之和",
        "thresholds": [0, 30, 60, 90, 120],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444"],
        "legend_labels": ["< 30s", "30-59s", "60-89s", "90-119s", "≥ 120s"],
    },
    "line_travel_speed_kmh": {
        "label": "行程速度",
        "level": "line",
        "table": TABLE_LINE_VAL,
        "value_field": "travel_speed_kmh",
        "value_type": "numeric",
        "unit": "km/h",
        "description": "line 总长度 / 总行程时间",
        "severity_direction": "inverse",
        "thresholds": [0, 15, 25, 35, 45],
        "colors": ["#ef4444", "#f97316", "#eab308", "#84cc16", "#22c55e"],
        "legend_labels": ["< 15", "15-24", "25-34", "35-44", "≥ 45"],
    },
    "line_delay_index": {
        "label": "拥堵延时指数",
        "level": "line",
        "table": TABLE_LINE_VAL,
        "value_field": "delay_index",
        "value_type": "numeric",
        "unit": "",
        "description": "各 link 拥堵延时指数按长度加权平均",
        "thresholds": [0, 1.2, 1.5, 2.0, 2.5],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444"],
        "legend_labels": ["< 1.2", "1.2-1.4", "1.5-1.9", "2.0-2.4", "≥ 2.5"],
    },
    "line_total_stop_times": {
        "label": "总停车次数",
        "level": "line",
        "table": TABLE_LINE_VAL,
        "value_field": "total_stop_times",
        "value_type": "numeric",
        "unit": "次",
        "description": "line 内各 link 平均停车次数加和",
        "thresholds": [0, 0.5, 1.0, 1.5, 2.0],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444"],
        "legend_labels": ["< 0.5", "0.5-0.9", "1.0-1.4", "1.5-1.9", "≥ 2.0"],
    },
}

LINE_SERIES_METRIC_IDS = tuple(LINE_METRIC_CATALOG.keys())

_WKT_LINESTRING = re.compile(
    r"LINESTRING\s*\((.+)\)",
    re.IGNORECASE,
)


def line_metric_catalog_for_api() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for metric_id, cfg in LINE_METRIC_CATALOG.items():
        item = {
            "id": metric_id,
            "label": cfg["label"],
            "level": cfg["level"],
            "dimension": "line",
            "dimensionLabel": "line 道路",
            "valueType": cfg["value_type"],
            "unit": cfg.get("unit", ""),
            "description": cfg.get("description", ""),
            "thresholds": cfg.get("thresholds", []),
            "colors": cfg.get("colors", []),
        }
        if cfg.get("severity_direction"):
            item["severityDirection"] = cfg["severity_direction"]
        if cfg.get("legend_labels"):
            item["legendLabels"] = cfg["legend_labels"]
        items.append(item)
    return items


def _line_val_qualified() -> str:
    return f"{_qident(_timing_schema())}.{_qident(TABLE_LINE_VAL)}"


def _line_info_qualified() -> str:
    return f"{_qident(_road_schema())}.{_qident(TABLE_LINE_INFO)}"


def _line_link_qualified() -> str:
    return f"{_qident(_road_schema())}.{_qident(TABLE_LINE_LINK)}"


def _line_inter_qualified() -> str:
    return f"{_qident(_road_schema())}.{_qident(TABLE_LINE_INTER)}"


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


def _concat_line_coords(segments: list[list[list[float]]]) -> list[list[float]]:
    out: list[list[float]] = []
    for seg in segments:
        if not seg:
            continue
        if not out:
            out.extend(seg)
            continue
        last = out[-1]
        first = seg[0]
        if abs(last[0] - first[0]) < 1e-6 and abs(last[1] - first[1]) < 1e-6:
            out.extend(seg[1:])
        else:
            out.extend(seg)
    return out


def _fetch_link_geometries(conn, link_ids: list[str]) -> dict[str, list[list[float]]]:
    if not link_ids:
        return {}
    dim = _link_dim_qualified()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT link_id::text AS link_id, ST_AsText(geom) AS geom_wkt
            FROM {dim}
            WHERE link_id = ANY(%s)
              AND geom IS NOT NULL
            """,
            (link_ids,),
        )
        rows = cur.fetchall()
    return {
        str(row["link_id"]): _parse_wkt_linestring(row.get("geom_wkt"))
        for row in rows
        if _parse_wkt_linestring(row.get("geom_wkt"))
    }


def _fetch_line_link_order(conn, line_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not line_ids:
        return {}
    q = _line_link_qualified()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT line_id, seq_no, link_id::text AS link_id, length_m, f_inter_id, t_inter_id
            FROM {q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND line_id = ANY(%s)
            ORDER BY line_id, seq_no
            """,
            (line_ids,),
        )
        rows = cur.fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        line_id = str(row["line_id"])
        out.setdefault(line_id, []).append(dict(row))
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
        if not coords:
            continue
        out[inter_id] = {
            "interId": inter_id,
            "interName": str(row.get("inter_name") or inter_id),
            "coordinates": list(coords),
        }
    return out


def _build_line_coordinates(
    link_rows: list[dict[str, Any]],
    link_geos: dict[str, list[list[float]]],
    *,
    travel_dir: int,
) -> list[list[float]]:
    ordered = sorted(link_rows, key=lambda r: int(r["seq_no"]))
    if travel_dir == TRAVEL_DIR_REVERSE:
        ordered = list(reversed(ordered))
    segments: list[list[list[float]]] = []
    for link in ordered:
        link_id = str(link["link_id"])
        coords = link_geos.get(link_id)
        if not coords:
            continue
        if travel_dir == TRAVEL_DIR_REVERSE:
            coords = list(reversed(coords))
        segments.append(coords)
    return _concat_line_coords(segments)


def _format_value_label(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}{unit}" if unit else text


def fetch_line_catalog(conn) -> list[dict[str, Any]]:
    line_q = _line_info_qualified()
    val_q = _line_val_qualified()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT l.line_id, l.line_name, l.road_name, l.line_length_m,
                   l.inter_count, l.link_count,
                   COUNT(DISTINCT v.day_of_week) AS day_count
            FROM {line_q} l
            JOIN {val_q} v ON v.line_id = l.line_id AND COALESCE(v.is_deleted, 0) = 0
            WHERE COALESCE(l.is_deleted, 0) = 0
            GROUP BY l.line_id, l.line_name, l.road_name, l.line_length_m, l.inter_count, l.link_count
            ORDER BY l.road_name, l.line_name, l.line_id
            """
        )
        rows = cur.fetchall()
    return [
        {
            "lineId": str(row["line_id"]),
            "lineName": str(row["line_name"]),
            "roadName": str(row.get("road_name") or ""),
            "lineLengthM": float(row["line_length_m"]) if row.get("line_length_m") is not None else None,
            "interCount": int(row.get("inter_count") or 0),
            "linkCount": int(row.get("link_count") or 0),
            "dayCount": int(row.get("day_count") or 0),
        }
        for row in rows
    ]


def fetch_line_time_slices(conn, metric_id: str) -> dict[str, Any]:
    cfg = LINE_METRIC_CATALOG.get(metric_id)
    if not cfg:
        raise ValueError(f"未知 line 指标: {metric_id}")
    val_q = _line_val_qualified()
    value_field = cfg["value_field"]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT day_of_week,
                   MIN(step_index) AS min_step,
                   MAX(step_index) AS max_step,
                   COUNT(DISTINCT line_id) AS line_count
            FROM {val_q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND {_qident(value_field)} IS NOT NULL
            GROUP BY day_of_week
            ORDER BY day_of_week
            """,
        )
        rows = cur.fetchall()
    days = [
        {
            "dayOfWeek": int(row["day_of_week"]),
            "dayLabel": _day_label(int(row["day_of_week"])),
            "minStepIndex": int(row["min_step"]),
            "maxStepIndex": int(row["max_step"]),
            "lineCount": int(row["line_count"]),
        }
        for row in rows
    ]
    return {"metricId": metric_id, "days": days}


def fetch_line_val_layer(
    conn,
    *,
    metric_id: str,
    day_of_week: int,
    step_index: int,
    travel_dir: int | None = None,
    line_id: str | None = None,
) -> dict[str, Any]:
    cfg = LINE_METRIC_CATALOG.get(metric_id)
    if not cfg:
        raise ValueError(f"未知 line 指标: {metric_id}")
    value_field = cfg["value_field"]
    unit = cfg.get("unit", "")
    val_q = _line_val_qualified()

    params: list[Any] = [day_of_week, step_index]
    filters = ""
    if travel_dir in (TRAVEL_DIR_FORWARD, TRAVEL_DIR_REVERSE):
        filters += " AND v.travel_dir = %s"
        params.append(travel_dir)
    if line_id and line_id.strip() and line_id.strip() != "全部":
        filters += " AND v.line_id = %s"
        params.append(line_id.strip())

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT v.line_id, v.travel_dir, v.line_name, v.road_name, v.travel_dir_label,
                   v.line_length_m, v.link_count, v.inter_count,
                   v.travel_time_sec, v.stop_time_sec, v.travel_speed_kmh,
                   v.delay_index, v.total_stop_times, v.continuous_stop_sets_json,
                   v.{_qident(value_field)} AS metric_value
            FROM {val_q} v
            WHERE COALESCE(v.is_deleted, 0) = 0
              AND v.day_of_week = %s
              AND v.step_index = %s
              AND v.{_qident(value_field)} IS NOT NULL
              {filters}
            ORDER BY v.road_name, v.line_name, v.travel_dir
            """,
            params,
        )
        rows = cur.fetchall()

    line_ids = sorted({str(row["line_id"]) for row in rows})
    links_by_line = _fetch_line_link_order(conn, line_ids)
    all_link_ids = sorted(
        {str(link["link_id"]) for links in links_by_line.values() for link in links}
    )
    link_geos = _fetch_link_geometries(conn, all_link_ids)

    inter_ids: set[str] = set()
    inter_q = _line_inter_qualified()
    if line_ids:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT line_id, inter_id::text AS inter_id, inter_name, seq_no
                FROM {inter_q}
                WHERE COALESCE(is_deleted, 0) = 0
                  AND line_id = ANY(%s)
                ORDER BY line_id, seq_no
                """,
                (line_ids,),
            )
            inter_rows = cur.fetchall()
    else:
        inter_rows = []
    inter_by_line: dict[str, list[dict[str, Any]]] = {}
    for row in inter_rows:
        line_key = str(row["line_id"])
        inter_by_line.setdefault(line_key, []).append(dict(row))
        inter_ids.add(str(row["inter_id"]))
    inter_geos = _fetch_inter_geometries(conn, sorted(inter_ids))

    features: list[dict[str, Any]] = []
    value_numbers: list[float] = []

    for row in rows:
        line_key = str(row["line_id"])
        dir_val = int(row["travel_dir"])
        metric_value = _to_float(row.get("metric_value"))
        if metric_value is None:
            continue
        value_numbers.append(metric_value)
        cont_sets = _parse_json(row.get("continuous_stop_sets_json"), [])
        base_props = {
            "layerKind": "line_val",
            "featureKind": "line_road",
            "lineId": line_key,
            "lineName": str(row.get("line_name") or line_key),
            "roadName": str(row.get("road_name") or ""),
            "travelDir": dir_val,
            "travelDirLabel": str(row.get("travel_dir_label") or TRAVEL_DIR_LABELS.get(dir_val, "")),
            "dayOfWeek": day_of_week,
            "dayLabel": _day_label(day_of_week),
            "stepIndex": step_index,
            "timeLabel": step_index_to_hhmm(step_index),
            "metricId": metric_id,
            "metricLabel": cfg["label"],
            "unit": unit,
            "value": metric_value,
            "valueLabel": _format_value_label(metric_value, unit),
            "travelTimeSec": _to_float(row.get("travel_time_sec")),
            "stopTimeSec": _to_float(row.get("stop_time_sec")),
            "travelSpeedKmh": _to_float(row.get("travel_speed_kmh")),
            "delayIndex": _to_float(row.get("delay_index")),
            "totalStopTimes": _to_float(row.get("total_stop_times")),
            "continuousStopSets": cont_sets,
            "lineLengthM": _to_float(row.get("line_length_m")),
            "linkCount": _to_int(row.get("link_count")),
            "interCount": _to_int(row.get("inter_count")),
        }

        coords = _build_line_coordinates(
            links_by_line.get(line_key, []),
            link_geos,
            travel_dir=dir_val,
        )
        if coords:
            features.append(
                {
                    "type": "Feature",
                    "id": f"{line_key}:{dir_val}",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": base_props,
                }
            )

        for inter in inter_by_line.get(line_key, []):
            inter_id = str(inter["inter_id"])
            inter_geo = inter_geos.get(inter_id)
            if not inter_geo:
                continue
            features.append(
                {
                    "type": "Feature",
                    "id": f"{line_key}:{dir_val}:{inter_id}",
                    "geometry": {"type": "Point", "coordinates": inter_geo["coordinates"]},
                    "properties": {
                        **base_props,
                        "featureKind": "line_inter",
                        "interId": inter_id,
                        "interName": str(inter.get("inter_name") or inter_geo.get("interName") or inter_id),
                        "seqNo": int(inter.get("seq_no") or 0),
                    },
                }
            )

    stats = _value_stats(value_numbers)
    return {
        "type": "FeatureCollection",
        "layerKind": "line_val",
        "metricId": metric_id,
        "metricLabel": cfg["label"],
        "unit": unit,
        "dayOfWeek": day_of_week,
        "dayLabel": _day_label(day_of_week),
        "stepIndex": step_index,
        "timeLabel": step_index_to_hhmm(step_index),
        "travelDir": travel_dir,
        "lineId": line_id or "全部",
        "featureCount": len(features),
        "lineCount": len({str(r["line_id"]) for r in rows}),
        "valueStats": stats,
        "features": features,
    }


def fetch_line_val_series(
    conn,
    *,
    line_id: str,
    day_of_week: int,
    metric_id: str,
    travel_dir: int | None = None,
) -> dict[str, Any]:
    cfg = LINE_METRIC_CATALOG.get(metric_id)
    if not cfg:
        raise ValueError(f"未知 line 指标: {metric_id}")
    value_field = cfg["value_field"]
    unit = cfg.get("unit", "")
    val_q = _line_val_qualified()

    params: list[Any] = [line_id.strip(), day_of_week]
    dir_filter = ""
    if travel_dir in (TRAVEL_DIR_FORWARD, TRAVEL_DIR_REVERSE):
        dir_filter = " AND travel_dir = %s"
        params.append(travel_dir)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT line_id, line_name, travel_dir, travel_dir_label, step_index,
                   {_qident(value_field)} AS metric_value
            FROM {val_q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND line_id = %s
              AND day_of_week = %s
              AND {_qident(value_field)} IS NOT NULL
              {dir_filter}
            ORDER BY travel_dir, step_index
            """,
            params,
        )
        rows = cur.fetchall()

    by_dir: dict[int, dict[str, Any]] = {}
    line_name = ""
    for row in rows:
        line_name = str(row.get("line_name") or line_id)
        dir_val = int(row["travel_dir"])
        step = _to_int(row.get("step_index"))
        num = _to_float(row.get("metric_value"))
        if step is None or num is None:
            continue
        if dir_val not in by_dir:
            by_dir[dir_val] = {
                "seriesId": f"{line_id}:{dir_val}",
                "travelDir": dir_val,
                "label": str(row.get("travel_dir_label") or TRAVEL_DIR_LABELS.get(dir_val, str(dir_val))),
                "values": [],
            }
        by_dir[dir_val]["values"].append(
            {
                "stepIndex": step,
                "timeLabel": step_index_to_hhmm(step),
                "value": round(num, 4),
            }
        )

    series = [by_dir[k] for k in sorted(by_dir)]
    return {
        "lineId": line_id.strip(),
        "lineName": line_name,
        "dayOfWeek": day_of_week,
        "dayLabel": _day_label(day_of_week),
        "metricId": metric_id,
        "metricLabel": cfg["label"],
        "unit": unit,
        "dimension": "line",
        "travelDir": travel_dir,
        "series": series,
    }
