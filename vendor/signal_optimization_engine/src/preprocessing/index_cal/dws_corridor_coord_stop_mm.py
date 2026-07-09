#!/usr/bin/env python3
"""生成干线协调停车指标 DWS 表 dws_corridor_coord_stop_mm。

按协调组 + 星期预聚合停车指标（协调时段内全部 5min 片聚合），供 GIS 地图快速读取。

依赖（须先运行）：
  - dws_corridor_coord_cfg / dws_corridor_coord_group（corridor-coord-dws + 同步 PG）
  - dws_inter_link_status_5min_mm

用法:
    python -m preprocessing.index_cal.dws_corridor_coord_stop_mm
    python -m preprocessing.index_cal.dws_corridor_coord_stop_mm --truncate
    signal-opt corridor-coord-stop-dws --truncate
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from typing import Any

from data.corridor_coord_reader import (
    TABLE_CFG,
    TABLE_GROUP,
    _parse_corridor_group_row,
    compute_corridor_group_stop_metrics,
)
from data.metric_reader import _qident, _timing_schema
from data.pg_reader import connect_pg

TABLE_TARGET = "dws_corridor_coord_stop_mm"
CALC_VERSION = "corridor_coord_stop_v1"

TARGET_COLUMNS = [
    "group_id",
    "day_of_week",
    "corridor_id",
    "period_start_sec",
    "period_end_sec",
    "cycle_len_sec",
    "stop_times_threshold",
    "period_step_count",
    "source_table",
    "fwd_avg_total_stop_times",
    "rev_avg_total_stop_times",
    "fwd_intersection_count",
    "rev_intersection_count",
    "fwd_inter_stop_json",
    "rev_inter_stop_json",
    "fwd_continuous_stop_sets_json",
    "rev_continuous_stop_sets_json",
    "calc_version",
    "create_time",
    "update_time",
    "is_deleted",
]


def _qualified(schema: str, table: str) -> str:
    return f"{_qident(schema)}.{_qident(table)}"


def _create_table_ddl(*, target_q: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {target_q} (
    group_id                        varchar(16)      NOT NULL,
    day_of_week                     smallint         NOT NULL,
    corridor_id                     varchar(16)      NOT NULL,
    period_start_sec                integer          NOT NULL,
    period_end_sec                  integer          NOT NULL,
    cycle_len_sec                   integer          NOT NULL,
    stop_times_threshold            double precision NOT NULL DEFAULT 0.6,
    period_step_count               smallint         NOT NULL DEFAULT 0,
    source_table                    varchar(128),
    fwd_avg_total_stop_times        double precision,
    rev_avg_total_stop_times        double precision,
    fwd_intersection_count          smallint,
    rev_intersection_count          smallint,
    fwd_inter_stop_json             jsonb,
    rev_inter_stop_json             jsonb,
    fwd_continuous_stop_sets_json   jsonb,
    rev_continuous_stop_sets_json   jsonb,
    calc_version                    varchar(64)      NOT NULL DEFAULT '{CALC_VERSION}',
    create_time                     timestamp        NOT NULL DEFAULT NOW(),
    update_time                     timestamp        NOT NULL DEFAULT NOW(),
    is_deleted                      smallint         NOT NULL DEFAULT 0,
    PRIMARY KEY (group_id, day_of_week)
)
""".strip()


def _create_index_ddl(*, target_q: str) -> list[str]:
    return [
        f"CREATE INDEX IF NOT EXISTS idx_ccs_day ON {target_q} (day_of_week)",
        f"CREATE INDEX IF NOT EXISTS idx_ccs_corridor_day ON {target_q} (corridor_id, day_of_week)",
        f"CREATE INDEX IF NOT EXISTS idx_ccs_period ON {target_q} (day_of_week, period_start_sec, period_end_sec)",
    ]


def ensure_target_table(conn: Any, *, target_schema: str, with_indexes: bool = False) -> None:
    target_q = _qualified(target_schema, TABLE_TARGET)
    with conn.cursor() as cur:
        cur.execute(_create_table_ddl(target_q=target_q))
        if with_indexes:
            for ddl in _create_index_ddl(target_q=target_q):
                cur.execute(ddl)
    conn.commit()


def _upsert_assignments() -> str:
    skip = {"group_id", "day_of_week", "create_time"}
    return ", ".join(
        f"{_qident(col)} = EXCLUDED.{_qident(col)}"
        for col in TARGET_COLUMNS
        if col not in skip
    )


def _metrics_to_row(parsed: dict[str, Any], *, day_of_week: int, metrics: dict[str, Any]) -> dict[str, Any]:
    fwd = metrics.get("forward") or {}
    rev = metrics.get("reverse") or {}
    return {
        "group_id": parsed["group_id"],
        "day_of_week": day_of_week,
        "corridor_id": parsed["corridor_id"],
        "period_start_sec": parsed["period_start"],
        "period_end_sec": parsed["period_end"],
        "cycle_len_sec": parsed["cycle_len"],
        "stop_times_threshold": metrics.get("stopTimesThreshold"),
        "period_step_count": metrics.get("periodStepCount"),
        "source_table": metrics.get("sourceTable"),
        "fwd_avg_total_stop_times": fwd.get("avgTotalStopTimes"),
        "rev_avg_total_stop_times": rev.get("avgTotalStopTimes"),
        "fwd_intersection_count": fwd.get("intersectionCount"),
        "rev_intersection_count": rev.get("intersectionCount"),
        "fwd_inter_stop_json": json.dumps(fwd.get("interStopDetails") or [], ensure_ascii=False),
        "rev_inter_stop_json": json.dumps(rev.get("interStopDetails") or [], ensure_ascii=False),
        "fwd_continuous_stop_sets_json": json.dumps(fwd.get("continuousStopSets") or [], ensure_ascii=False),
        "rev_continuous_stop_sets_json": json.dumps(rev.get("continuousStopSets") or [], ensure_ascii=False),
        "calc_version": CALC_VERSION,
        "is_deleted": 0,
    }


def _load_corridor_groups(conn: Any) -> list[dict[str, Any]]:
    schema = _timing_schema()
    group_q = _qualified(schema, TABLE_GROUP)
    cfg_q = _qualified(schema, TABLE_CFG)
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
            ORDER BY g.day_of_week, g.corridor_id, g.period_start_sec, g.group_id
            """
        )
        return list(cur.fetchall())


def build_rows(conn: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _load_corridor_groups(conn):
        parsed = _parse_corridor_group_row(raw)
        day_of_week = int(raw["day_of_week"])
        metrics = compute_corridor_group_stop_metrics(
            conn,
            ordered_ids=parsed["ordered_ids"],
            inter_names=parsed["inter_names"],
            day_of_week=day_of_week,
            period_start_sec=parsed["period_start"],
            period_end_sec=parsed["period_end"],
        )
        rows.append(_metrics_to_row(parsed, day_of_week=day_of_week, metrics=metrics))
    return rows


def upsert_rows(
    conn: Any,
    *,
    target_schema: str,
    rows: list[dict[str, Any]],
    truncate: bool = False,
) -> int:
    if not rows:
        return 0
    target_q = _qualified(target_schema, TABLE_TARGET)
    cols = ", ".join(_qident(c) for c in TARGET_COLUMNS)
    placeholders = ", ".join(["%s"] * len(TARGET_COLUMNS))
    insert_sql = f"""
INSERT INTO {target_q} ({cols})
VALUES ({placeholders})
ON CONFLICT (group_id, day_of_week)
DO UPDATE SET {_upsert_assignments()}
"""
    now = datetime.now()
    values = [
        tuple(
            row.get(col) if col not in {"create_time", "update_time"} else now
            for col in TARGET_COLUMNS
        )
        for row in rows
    ]
    with conn.cursor() as cur:
        if truncate:
            cur.execute(f"TRUNCATE TABLE {target_q}")
            truncate = False
        for offset in range(0, len(values), 500):
            cur.executemany(insert_sql, values[offset : offset + 500])
    conn.commit()
    return len(rows)


def count_target_rows(conn: Any, *, target_schema: str) -> int:
    target_q = _qualified(target_schema, TABLE_TARGET)
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS cnt FROM {target_q} WHERE COALESCE(is_deleted, 0) = 0")
        row = cur.fetchone()
    return int((row or {}).get("cnt") or 0)


def run_build(*, truncate: bool = False, skip_db: bool = False) -> dict[str, Any]:
    target_schema = _timing_schema()
    conn = connect_pg()
    try:
        if not skip_db:
            ensure_target_table(conn, target_schema=target_schema, with_indexes=True)
        rows = build_rows(conn)
        written = 0 if skip_db else upsert_rows(conn, target_schema=target_schema, rows=rows, truncate=truncate)
        return {
            "target_schema": target_schema,
            "target_table": TABLE_TARGET,
            "built_rows": len(rows),
            "written_rows": written,
            "table_rows": count_target_rows(conn, target_schema=target_schema) if not skip_db else 0,
        }
    finally:
        conn.close()


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass

    parser = argparse.ArgumentParser(description="生成干线协调停车指标 DWS 表（PostgreSQL）")
    parser.add_argument("--truncate", action="store_true", help="写入前清空目标表")
    parser.add_argument("--skip-db", action="store_true", help="仅计算，不写入数据库")
    args = parser.parse_args()
    stats = run_build(truncate=args.truncate, skip_db=args.skip_db)
    for key in sorted(stats):
        print(f"{key}: {stats[key]}")


if __name__ == "__main__":
    main()
