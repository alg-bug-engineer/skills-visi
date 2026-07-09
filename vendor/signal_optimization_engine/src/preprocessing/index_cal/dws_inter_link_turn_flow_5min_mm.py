#!/usr/bin/env python3
"""生成路口进口 link 转向 5 分钟流量中间表 dws_inter_link_turn_flow_5min_mm。

数据来源：xianchang.dwd_tfc_lane_roadcross_flow_5mi
  - turn_move(国标码) 严格按 GB 标准映射为 turn_dir_no：1=左转/掉头，2=直行
  - 同一进口方向（dir8_code）有多条 link 时，取 lane_num 最大的主路 link 代表该方向

按 dt 分批聚合（源表无索引，全表扫描较慢）。

用法:
    python -m preprocessing.index_cal.dws_inter_link_turn_flow_5min_mm
    python -m preprocessing.index_cal.dws_inter_link_turn_flow_5min_mm --truncate
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta
from typing import Any

from data.pg_reader import connect_pg
from env import load_project_env
from preprocessing.index_cal.inter_link_status_logic import (
    TURN_MOVE_LEFT,
    TURN_MOVE_STRAIGHT,
    entrance_links_cte_sql,
    turn_move_in_sql,
)

TABLE_TARGET = "dws_inter_link_turn_flow_5min_mm"
FIVE_MIN_FLOW_SCALE = 12.0

TARGET_COLUMNS = [
    "inter_id",
    "link_id",
    "turn_dir_no",
    "day_of_week",
    "step_index",
    "inter_name",
    "dir8_code",
    "turn_flow_total",
    "avg_lane_flow_5min",
    "lane_count",
    "sample_count",
    "flow_date_start",
    "flow_date_end",
    "create_time",
    "update_time",
    "is_deleted",
]


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _qualified(schema: str, table: str) -> str:
    return f"{_qident(schema)}.{_qident(table)}"


def _create_table_ddl(*, target_q: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {target_q} (
    inter_id            varchar(32)  NOT NULL,
    link_id             varchar(32)  NOT NULL,
    turn_dir_no         smallint     NOT NULL,
    day_of_week         smallint     NOT NULL,
    step_index          smallint     NOT NULL,
    inter_name          varchar(128),
    dir8_code           smallint,
    turn_flow_total     double precision NOT NULL DEFAULT 0,
    avg_lane_flow_5min  double precision NOT NULL DEFAULT 0,
    lane_count          smallint     NOT NULL DEFAULT 0,
    sample_count        integer      NOT NULL DEFAULT 0,
    flow_date_start     varchar(8),
    flow_date_end       varchar(8),
    create_time         timestamp    NOT NULL DEFAULT NOW(),
    update_time         timestamp    NOT NULL DEFAULT NOW(),
    is_deleted          smallint     NOT NULL DEFAULT 0,
    PRIMARY KEY (inter_id, link_id, turn_dir_no, day_of_week, step_index)
)
""".strip()


def _create_index_ddl(*, target_q: str) -> list[str]:
    return [
        f"CREATE INDEX IF NOT EXISTS idx_iltf_inter_day_step ON {target_q} (inter_id, day_of_week, step_index)",
        f"CREATE INDEX IF NOT EXISTS idx_iltf_link_turn ON {target_q} (link_id, turn_dir_no)",
    ]


def ensure_target_table(conn: Any, *, target_q: str, with_indexes: bool = False) -> None:
    with conn.cursor() as cur:
        cur.execute(_create_table_ddl(target_q=target_q))
        if with_indexes:
            for ddl in _create_index_ddl(target_q=target_q):
                cur.execute(ddl)
    conn.commit()


def _parse_dt(value: str) -> datetime:
    return datetime.strptime(str(value).strip(), "%Y%m%d")


def resolve_flow_dates(
    conn: Any,
    *,
    flow_q: str,
    weeks: int,
) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT min(dt)::text AS min_dt, max(dt)::text AS max_dt
            FROM {flow_q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND dt IS NOT NULL
              AND btrim(dt::text) <> ''
            """
        )
        bounds = cur.fetchone() or {}
    max_dt = str(bounds.get("max_dt") or "").strip()
    min_dt = str(bounds.get("min_dt") or "").strip()
    if not max_dt:
        return []

    end_date = _parse_dt(max_dt)
    start_date = max(_parse_dt(min_dt), end_date - timedelta(weeks=max(weeks, 1)))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT dt::text AS dt
            FROM {flow_q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND dt >= %s
              AND dt <= %s
            ORDER BY dt
            """,
            (start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")),
        )
        return [str(row.get("dt") or "").strip() for row in cur.fetchall() if row.get("dt")]


def _build_daily_sql(
    *,
    flow_q: str,
    channel_q: str,
    inter_filter: list[str] | None,
) -> tuple[str, list[Any]]:
    left_codes = turn_move_in_sql(TURN_MOVE_LEFT)
    straight_codes = turn_move_in_sql(TURN_MOVE_STRAIGHT)
    timing_q = _qualified(os.getenv("PG_FLOW_SCHEMA", "xianchang"), "dws_ctl_inter_turn_5min_his_mm")
    inter_clause_entrance = ""
    inter_clause_flow = ""
    params: list[Any] = []
    if inter_filter:
        inter_clause_entrance = " AND ch.inter_id::text = ANY(%s)"
        inter_clause_flow = " AND f.inter_id::text = ANY(%s)"
        params.extend([inter_filter, inter_filter])

    timing_filter = f"""
      AND EXISTS (
          SELECT 1
          FROM {timing_q} t
          WHERE t.inter_id::text = f.inter_id::text
            AND t.link_id::text = f.link_id::text
            AND COALESCE(t.is_deleted, 0) = 0
      )
    """

    sql = f"""
WITH {entrance_links_cte_sql(channel_q=channel_q, inter_clause=inter_clause_entrance)},
flow_left AS (
    SELECT
        f.inter_id::text AS inter_id,
        NULLIF(btrim(f.inter_name::text), '') AS inter_name,
        f.link_id::text AS link_id,
        1::smallint AS turn_dir_no,
        EXTRACT(ISODOW FROM to_date(f.dt, 'YYYYMMDD'))::smallint AS day_of_week,
        f.step_index::smallint AS step_index,
        SUM(f.vehicle_count::float) AS turn_flow_5min,
        AVG(f.vehicle_count::float) AS avg_lane_flow_5min,
        COUNT(DISTINCT f.lane_id::text) AS lane_count
    FROM {flow_q} f
    JOIN entrance_links el
      ON el.inter_id = f.inter_id::text
     AND el.link_id = f.link_id::text
    WHERE COALESCE(f.is_deleted, 0) = 0
      AND f.dt = %s
      AND f.step_index BETWEEN 0 AND 287
      AND f.vehicle_count IS NOT NULL
      AND f.turn_move::int IN ({left_codes})
      {timing_filter}
      {inter_clause_flow}
    GROUP BY f.inter_id, f.inter_name, f.link_id, day_of_week, f.step_index
),
flow_straight AS (
    SELECT
        f.inter_id::text AS inter_id,
        NULLIF(btrim(f.inter_name::text), '') AS inter_name,
        f.link_id::text AS link_id,
        2::smallint AS turn_dir_no,
        EXTRACT(ISODOW FROM to_date(f.dt, 'YYYYMMDD'))::smallint AS day_of_week,
        f.step_index::smallint AS step_index,
        SUM(f.vehicle_count::float) AS turn_flow_5min,
        AVG(f.vehicle_count::float) AS avg_lane_flow_5min,
        COUNT(DISTINCT f.lane_id::text) AS lane_count
    FROM {flow_q} f
    JOIN entrance_links el
      ON el.inter_id = f.inter_id::text
     AND el.link_id = f.link_id::text
    WHERE COALESCE(f.is_deleted, 0) = 0
      AND f.dt = %s
      AND f.step_index BETWEEN 0 AND 287
      AND f.vehicle_count IS NOT NULL
      AND f.turn_move::int IN ({straight_codes})
      {timing_filter}
      {inter_clause_flow}
    GROUP BY f.inter_id, f.inter_name, f.link_id, day_of_week, f.step_index
)
SELECT
    x.inter_id,
    x.link_id,
    x.turn_dir_no,
    x.day_of_week,
    x.step_index,
    x.inter_name,
    el.dir8_code,
    x.turn_flow_5min,
    x.avg_lane_flow_5min,
    x.lane_count::int AS lane_count
FROM (
    SELECT * FROM flow_left
    UNION ALL
    SELECT * FROM flow_straight
) x
JOIN entrance_links el
  ON el.inter_id = x.inter_id
 AND el.link_id = x.link_id
"""
    return sql, params


def _merge_daily_rows(
    acc: dict[tuple[str, str, int, int, int], dict[str, Any]],
    daily_rows: list[dict[str, Any]],
) -> None:
    for row in daily_rows:
        key = (
            row["inter_id"],
            row["link_id"],
            int(row["turn_dir_no"]),
            int(row["day_of_week"]),
            int(row["step_index"]),
        )
        bucket = acc.get(key)
        if bucket is None:
            acc[key] = {
                "inter_id": key[0],
                "link_id": key[1],
                "turn_dir_no": key[2],
                "day_of_week": key[3],
                "step_index": key[4],
                "inter_name": row.get("inter_name"),
                "dir8_code": row.get("dir8_code"),
                "turn_flow_sum": float(row["turn_flow_5min"]) * FIVE_MIN_FLOW_SCALE,
                "lane_flow_sum": float(row["avg_lane_flow_5min"]),
                "lane_count_max": int(row.get("lane_count") or 0),
                "sample_count": 1,
                "flow_date_start": str(row["dt"]),
                "flow_date_end": str(row["dt"]),
            }
            continue
        bucket["turn_flow_sum"] += float(row["turn_flow_5min"]) * FIVE_MIN_FLOW_SCALE
        bucket["lane_flow_sum"] += float(row["avg_lane_flow_5min"])
        bucket["lane_count_max"] = max(bucket["lane_count_max"], int(row.get("lane_count") or 0))
        bucket["sample_count"] += 1
        dt = str(row["dt"])
        if dt < bucket["flow_date_start"]:
            bucket["flow_date_start"] = dt
        if dt > bucket["flow_date_end"]:
            bucket["flow_date_end"] = dt
        if not bucket.get("inter_name") and row.get("inter_name"):
            bucket["inter_name"] = row.get("inter_name")
        if bucket.get("dir8_code") is None and row.get("dir8_code") is not None:
            bucket["dir8_code"] = row.get("dir8_code")


def _finalize_aggregate(acc: dict[tuple[str, str, int, int, int], dict[str, Any]]) -> list[dict[str, Any]]:
    target_rows: list[dict[str, Any]] = []
    for bucket in acc.values():
        count = max(int(bucket.get("sample_count") or 0), 1)
        target_rows.append(
            {
                "inter_id": bucket["inter_id"],
                "link_id": bucket["link_id"],
                "turn_dir_no": bucket["turn_dir_no"],
                "day_of_week": bucket["day_of_week"],
                "step_index": bucket["step_index"],
                "inter_name": bucket.get("inter_name"),
                "dir8_code": bucket.get("dir8_code"),
                "turn_flow_total": round(float(bucket["turn_flow_sum"]) / count, 1),
                "avg_lane_flow_5min": round(float(bucket["lane_flow_sum"]) / count, 4),
                "lane_count": bucket.get("lane_count_max") or 0,
                "sample_count": count,
                "flow_date_start": bucket.get("flow_date_start"),
                "flow_date_end": bucket.get("flow_date_end"),
                "is_deleted": 0,
            }
        )
    return target_rows


def _upsert_assignments() -> str:
    skip = {"inter_id", "link_id", "turn_dir_no", "day_of_week", "step_index", "create_time", "update_time"}
    parts = [
        f"{_qident(col)} = EXCLUDED.{_qident(col)}"
        for col in TARGET_COLUMNS
        if col not in skip
    ]
    parts.append(f"{_qident('update_time')} = NOW()")
    return ", ".join(parts)


def upsert_target_rows(
    conn: Any,
    *,
    target_schema: str,
    rows: list[dict[str, Any]],
    truncate: bool,
) -> int:
    if not rows:
        return 0
    target_q = _qualified(target_schema, TABLE_TARGET)
    cols = ", ".join(_qident(c) for c in TARGET_COLUMNS)
    placeholders = ", ".join(["%s"] * len(TARGET_COLUMNS))
    insert_sql = f"""
INSERT INTO {target_q} ({cols})
VALUES ({placeholders})
ON CONFLICT (inter_id, link_id, turn_dir_no, day_of_week, step_index)
DO UPDATE SET {_upsert_assignments()}
"""
    now = datetime.now()
    values = [
        tuple(row.get(col) if col not in {"create_time", "update_time"} else now for col in TARGET_COLUMNS)
        for row in rows
    ]
    with conn.cursor() as cur:
        if truncate:
            cur.execute(f"TRUNCATE TABLE {target_q}")
            truncate = False
        for offset in range(0, len(values), 2000):
            cur.executemany(insert_sql, values[offset : offset + 2000])
    conn.commit()
    return len(rows)


def load_daily_rows(
    conn: Any,
    *,
    flow_schema: str,
    road_schema: str,
    dt: str,
    inter_filter: list[str] | None,
) -> list[dict[str, Any]]:
    flow_q = _qualified(flow_schema, os.getenv("PG_FLOW_TABLE", "dwd_tfc_lane_roadcross_flow_5mi"))
    channel_q = _qualified(road_schema, os.getenv("PG_CHANNEL_TABLE", "dwd_tfc_rltn_wide_inter_ft_link"))
    daily_sql, _ = _build_daily_sql(
        flow_q=flow_q,
        channel_q=channel_q,
        inter_filter=inter_filter,
    )
    if inter_filter:
        params: list[Any] = [inter_filter, inter_filter, dt, inter_filter, dt]
    else:
        params = [dt, dt]

    with conn.cursor() as cur:
        cur.execute(daily_sql, params)
        rows = []
        for row in cur.fetchall():
            rows.append({**dict(row), "dt": dt})
        return rows


def run_build(
    *,
    truncate: bool = False,
    inter_ids: list[str] | None = None,
    weeks: int = 12,
    skip_db: bool = False,
) -> dict[str, Any]:
    flow_schema = os.getenv("PG_FLOW_SCHEMA", "xianchang")
    road_schema = os.getenv("PGSCHEMA", "road6")
    flow_q = _qualified(flow_schema, os.getenv("PG_FLOW_TABLE", "dwd_tfc_lane_roadcross_flow_5mi"))

    conn = connect_pg()
    try:
        target_q = _qualified(flow_schema, TABLE_TARGET)
        if not skip_db:
            ensure_target_table(conn, target_q=target_q, with_indexes=False)

        dates = resolve_flow_dates(conn, flow_q=flow_q, weeks=weeks)
        if skip_db:
            return {
                "target_table": f"{flow_schema}.{TABLE_TARGET}",
                "flow_dates": dates,
            }

        started = time.perf_counter()
        acc: dict[tuple[str, str, int, int, int], dict[str, Any]] = {}
        daily_total = 0
        for dt in dates:
            day_started = time.perf_counter()
            daily_rows = load_daily_rows(
                conn,
                flow_schema=flow_schema,
                road_schema=road_schema,
                dt=dt,
                inter_filter=inter_ids,
            )
            daily_total += len(daily_rows)
            _merge_daily_rows(acc, daily_rows)
            print(f"dt={dt} daily_rows={len(daily_rows)} acc_keys={len(acc)} elapsed={round(time.perf_counter()-day_started,1)}s")
        target_rows = _finalize_aggregate(acc)
        affected = upsert_target_rows(
            conn,
            target_schema=flow_schema,
            rows=target_rows,
            truncate=truncate,
        )
        if not skip_db:
            ensure_target_table(conn, target_q=target_q, with_indexes=True)
        elapsed = time.perf_counter() - started
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM {target_q} WHERE COALESCE(is_deleted, 0) = 0")
            total = int((cur.fetchone() or {}).get("cnt") or 0)
        return {
            "target_table": f"{flow_schema}.{TABLE_TARGET}",
            "rows_affected": affected,
            "rows_total": total,
            "daily_rows": daily_total,
            "flow_dates": dates,
            "elapsed_sec": round(elapsed, 2),
            "weeks": weeks,
            "truncate": truncate,
        }
    finally:
        conn.close()


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(description="生成 dws_inter_link_turn_flow_5min_mm")
    parser.add_argument("--inter-id", action="append", dest="inter_ids")
    parser.add_argument("--weeks", type=int, default=12)
    parser.add_argument("--truncate", action="store_true")
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()

    stats = run_build(
        truncate=args.truncate,
        inter_ids=args.inter_ids,
        weeks=args.weeks,
        skip_db=args.skip_db,
    )
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
