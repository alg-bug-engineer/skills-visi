"""Resolve turn-flow series the same way as timing-optimizer / web API."""

from __future__ import annotations

from typing import Any

from data.lane_flow_reader import fetch_turn_flow_series_from_lane_mm, lane_flow_table_exists
from data.mysql_reader import connect_mysql, fetch_day_plan_weekdays
from data.pg_reader import connect_pg, fetch_turn_flow_series


def resolve_flow_weekdays(inter_id: str, day_plan_no: int | None) -> list[int] | None:
    if day_plan_no is None:
        return None
    db = connect_mysql()
    try:
        weekdays = fetch_day_plan_weekdays(db, inter_id, day_plan_no)
    finally:
        db.close()
    return weekdays or None


def _prefer_lane_flow_profile(date: str | None, weekdays: list[int] | None) -> bool:
    return date is None and bool(weekdays)


def fetch_turn_flow_series_resolved(
    inter_id: str,
    *,
    date: str | None = None,
    day_plan_no: int | None = None,
    weekdays: list[int] | None = None,
    interval_min: int = 5,
) -> dict[str, Any]:
    """Fetch whole-day turn-flow series with the same source priority as web API."""
    if weekdays is None and day_plan_no is not None:
        weekdays = resolve_flow_weekdays(inter_id, day_plan_no)
    if _prefer_lane_flow_profile(date, weekdays):
        mysql_db = connect_mysql()
        try:
            if lane_flow_table_exists(mysql_db):
                pg_conn = connect_pg()
                try:
                    series = fetch_turn_flow_series_from_lane_mm(
                        mysql_db,
                        pg_conn,
                        inter_id,
                        weekdays=weekdays,
                        interval_min=interval_min,
                    )
                finally:
                    pg_conn.close()
                if series.get("series") or series.get("laneGroupSeries"):
                    if day_plan_no is not None:
                        series.setdefault("flowDateMeta", {})["dayPlanNo"] = day_plan_no
                    return series
        finally:
            mysql_db.close()

    pg_conn = connect_pg()
    try:
        series = fetch_turn_flow_series(
            pg_conn,
            inter_id,
            date=date,
            weekdays=weekdays,
            interval_min=interval_min,
        )
    finally:
        pg_conn.close()
    if day_plan_no is not None:
        series.setdefault("flowDateMeta", {})["dayPlanNo"] = day_plan_no
    return series
