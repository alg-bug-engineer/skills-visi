"""从 MySQL 车道历史流量聚合表读取并汇总为转向流量 API 响应。"""

from __future__ import annotations

import os
from typing import Any

from data.pg_reader import (
    WEEKDAY_LABELS,
    _normalize_weekdays,
    _windows_to_steps,
    build_turn_flow_series_from_lane_rows,
    build_turn_flow_stats_from_lane_rows,
)

TABLE_LANE_FLOW = os.getenv("MYSQL_LANE_FLOW_TABLE", "dws_lane_flow_5min_mm")


def lane_flow_table_name() -> str:
    return TABLE_LANE_FLOW


def lane_flow_table_exists(db) -> bool:
    from data.mysql_reader import _table_exists

    return _table_exists(db, TABLE_LANE_FLOW)


def _lane_flow_profile_meta(
    weekdays: list[int] | None,
    *,
    flow_date_start: str | None = None,
    flow_date_end: str | None = None,
) -> dict[str, Any]:
    normalized = _normalize_weekdays(weekdays)
    return {
        "date": None,
        "weekdays": normalized,
        "weekdayLabels": [WEEKDAY_LABELS[day] for day in normalized] if normalized else [],
        "dateComplete": True,
        "profileMode": True,
        "source": TABLE_LANE_FLOW,
        "aggregation": "historical_mean_5min",
        "flowDateStart": flow_date_start,
        "flowDateEnd": flow_date_end,
    }


def _load_lane_flow_aggregate_rows(
    db,
    inter_id: str,
    *,
    weekdays: list[int] | None,
    step_indices: set[int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalized_weekdays = _normalize_weekdays(weekdays)
    if not normalized_weekdays:
        return [], _lane_flow_profile_meta(weekdays, flow_date_start=None, flow_date_end=None)

    step_filter = ""
    params: list[Any] = [inter_id, *normalized_weekdays]
    if step_indices:
        step_filter = " AND step_index IN (" + ", ".join(["%s"] * len(step_indices)) + ")"
        params.extend(sorted(step_indices))

    with db.cursor() as cur:
        cur.execute(
            f"""
            SELECT lane_id, link_id, lane_no, turn_move, dir8_code, step_index,
                   AVG(avg_vehicle_count_5min) AS avg_vehicle_count_5min,
                   MIN(inter_name) AS inter_name,
                   MIN(flow_date_start) AS flow_date_start,
                   MAX(flow_date_end) AS flow_date_end,
                   SUM(sample_count) AS sample_count
            FROM `{TABLE_LANE_FLOW}`
            WHERE is_deleted = 0
              AND inter_id = %s
              AND day_of_week IN ({", ".join(["%s"] * len(normalized_weekdays))})
              {step_filter}
            GROUP BY lane_id, link_id, lane_no, turn_move, dir8_code, step_index
            """,
            params,
        )
        raw_rows = cur.fetchall()

    if not raw_rows:
        return [], _lane_flow_profile_meta(weekdays, flow_date_start=None, flow_date_end=None)

    inter_name = ""
    flow_date_start: str | None = None
    flow_date_end: str | None = None
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if not inter_name and row.get("inter_name"):
            inter_name = str(row["inter_name"])
        if row.get("flow_date_start"):
            flow_date_start = str(row["flow_date_start"])
        if row.get("flow_date_end"):
            flow_date_end = str(row["flow_date_end"])
        avg_count = float(row.get("avg_vehicle_count_5min") or 0)
        if avg_count <= 0:
            continue
        rows.append(
            {
                "dir8_code": row.get("dir8_code"),
                "turn_move": row.get("turn_move"),
                "link_id": row.get("link_id"),
                "lane_no": row.get("lane_no"),
                "step_index": row.get("step_index"),
                "veh": avg_count,
            }
        )

    meta = _lane_flow_profile_meta(
        weekdays,
        flow_date_start=flow_date_start,
        flow_date_end=flow_date_end,
    )
    return rows, meta | {"interName": inter_name}


def fetch_turn_flow_stats_from_lane_mm(
    db,
    pg_conn,
    inter_id: str,
    *,
    weekdays: list[int] | None,
    windows: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    windows = windows or [("00:00", "24:00")]
    steps = _windows_to_steps(windows)
    rows, flow_date_meta = _load_lane_flow_aggregate_rows(
        db,
        inter_id,
        weekdays=weekdays,
        step_indices=steps,
    )
    if not rows:
        return {
            "interId": inter_id,
            "interName": flow_date_meta.get("interName") or "",
            "date": None,
            "flowDateMeta": flow_date_meta,
            "windows": [list(w) for w in windows],
            "requestedMinutes": len(steps) * 5,
            "observedMinutes": 0,
            "flows": [],
            "laneGroups": [],
            "uncountedVehicles": {},
            "unmappedVehicles": 0,
        }

    observed_minutes = len(steps) * 5
    return build_turn_flow_stats_from_lane_rows(
        pg_conn,
        inter_id,
        rows,
        windows=windows,
        flow_date_meta=flow_date_meta,
        inter_name=str(flow_date_meta.get("interName") or ""),
        observed_minutes=observed_minutes,
    )


def fetch_turn_flow_series_from_lane_mm(
    db,
    pg_conn,
    inter_id: str,
    *,
    weekdays: list[int] | None,
    interval_min: int = 15,
) -> dict[str, Any]:
    rows, flow_date_meta = _load_lane_flow_aggregate_rows(
        db,
        inter_id,
        weekdays=weekdays,
        step_indices=None,
    )
    if not rows:
        return {
            "interId": inter_id,
            "interName": flow_date_meta.get("interName") or "",
            "date": None,
            "flowDateMeta": flow_date_meta,
            "intervalMinutes": interval_min,
            "times": [],
        "series": [],
        "laneGroupSeries": [],
        "approachSeries": [],
    }

    return build_turn_flow_series_from_lane_rows(
        pg_conn,
        inter_id,
        rows,
        interval_min=interval_min,
        flow_date_meta=flow_date_meta,
        inter_name=str(flow_date_meta.get("interName") or ""),
    )
