#!/usr/bin/env python3
"""将 link 2 分钟运行指标聚合为 5 分钟表 dws_link_index_5min_mm。

数据来源：xianchang.dwd_tfc_link_index_2mi（720 片/天，2 分钟粒度）

实际字段（已校验 PG）：
  - avg_jam_delay_index → delay_index
  - delay_dur           → stop_time_sec
  - avg_speed           → avg_speed_kmh
  - avg_nostop_speed
  - week_day            → day_of_week
  - step_index          → (step_index * 2) / 5 映射到 5 分钟片

聚合口径：
  1. 同一 link + dt + week_day 内，2min → 5min 取 AVG
  2. 跨历史自然日，对相同 (link_id, day_of_week, step_index) 再取 AVG

用法:
    python -m preprocessing.index_cal.dws_link_index_5min_mm
    python -m preprocessing.index_cal.dws_link_index_5min_mm --truncate
"""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

from data.pg_reader import connect_pg
from env import load_project_env
from preprocessing.index_cal.inter_link_status_logic import LINK_INDEX_SOURCE_FIELDS

TABLE_SOURCE = "dwd_tfc_link_index_2mi"
TABLE_TARGET = "dws_link_index_5min_mm"

TARGET_COLUMNS = [
    "link_id",
    "day_of_week",
    "step_index",
    "delay_index",
    "stop_time_sec",
    "avg_speed_kmh",
    "avg_nostop_speed",
    "sample_cnt",
    "history_day_count",
    "source_dt_start",
    "source_dt_end",
    "calc_version",
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
    link_id             varchar(32)  NOT NULL,
    day_of_week         smallint     NOT NULL,
    step_index          smallint     NOT NULL,
    delay_index         double precision,
    stop_time_sec       double precision,
    avg_speed_kmh       double precision,
    avg_nostop_speed    double precision,
    sample_cnt          integer      NOT NULL DEFAULT 0,
    history_day_count   integer      NOT NULL DEFAULT 0,
    source_dt_start     varchar(8),
    source_dt_end       varchar(8),
    calc_version        varchar(64)  NOT NULL DEFAULT 'link_index_5min_v1',
    create_time         timestamp    NOT NULL DEFAULT NOW(),
    update_time         timestamp    NOT NULL DEFAULT NOW(),
    is_deleted          smallint     NOT NULL DEFAULT 0,
    PRIMARY KEY (link_id, day_of_week, step_index)
)
""".strip()


def _create_index_ddl(*, target_q: str) -> list[str]:
    return [
        f"CREATE INDEX IF NOT EXISTS idx_lidx5_link_day_step ON {target_q} (link_id, day_of_week, step_index)",
        f"CREATE INDEX IF NOT EXISTS idx_lidx5_day_step ON {target_q} (day_of_week, step_index)",
    ]


def ensure_target_table(conn: Any, *, target_q: str) -> None:
    with conn.cursor() as cur:
        cur.execute(_create_table_ddl(target_q=target_q))
        for ddl in _create_index_ddl(target_q=target_q):
            cur.execute(ddl)
    conn.commit()


def _build_select_sql(
    *,
    flow_schema: str,
    link_ids: list[str] | None,
    weeks: int,
) -> tuple[str, list[Any]]:
    source_q = _qualified(flow_schema, os.getenv("PG_LINK_INDEX_TABLE", TABLE_SOURCE))
    delay_col = LINK_INDEX_SOURCE_FIELDS["delay_index"]
    stop_col = LINK_INDEX_SOURCE_FIELDS["stop_time_sec"]
    speed_col = LINK_INDEX_SOURCE_FIELDS["avg_speed_kmh"]
    nostop_col = LINK_INDEX_SOURCE_FIELDS["avg_nostop_speed"]
    dow_col = LINK_INDEX_SOURCE_FIELDS["day_of_week"]

    link_clause = ""
    params: list[Any] = [str(weeks)]
    if link_ids:
        link_clause = " AND li.link_id::text = ANY(%s)"
        params.append(link_ids)

    sql = f"""
WITH link_index_2to5 AS (
    SELECT
        li.link_id::text AS link_id,
        li.{dow_col}::smallint AS day_of_week,
        ((li.step_index::int * 2) / 5)::smallint AS step_index,
        AVG(li.{delay_col}::float) AS delay_index,
        AVG(li.{stop_col}::float) AS stop_time_sec,
        AVG(li.{speed_col}::float) AS avg_speed_kmh,
        AVG(li.{nostop_col}::float) AS avg_nostop_speed,
        SUM(COALESCE(li.sample_cnt, 0))::int AS sample_cnt,
        COUNT(*)::int AS bucket_2min_cnt,
        li.dt::text AS dt
    FROM {source_q} li
    WHERE li.link_id IS NOT NULL
      AND btrim(li.link_id::text) <> ''
      AND li.{dow_col} BETWEEN 1 AND 7
      AND li.step_index BETWEEN 0 AND 719
      AND li.dt >= to_char(NOW() - (%s || ' weeks')::interval, 'YYYYMMDD')
      {link_clause}
    GROUP BY li.link_id, li.{dow_col}, ((li.step_index::int * 2) / 5), li.dt
)
SELECT
    link_id,
    day_of_week,
    step_index,
    AVG(delay_index) AS delay_index,
    AVG(stop_time_sec) AS stop_time_sec,
    AVG(avg_speed_kmh) AS avg_speed_kmh,
    AVG(avg_nostop_speed) AS avg_nostop_speed,
    SUM(sample_cnt)::int AS sample_cnt,
    COUNT(DISTINCT dt)::int AS history_day_count,
    MIN(dt) AS source_dt_start,
    MAX(dt) AS source_dt_end,
    'link_index_5min_v1' AS calc_version,
    NOW() AS create_time,
    NOW() AS update_time,
    0::smallint AS is_deleted
FROM link_index_2to5
WHERE step_index BETWEEN 0 AND 287
GROUP BY link_id, day_of_week, step_index
"""
    return sql, params


def _upsert_assignments() -> str:
    skip = {"link_id", "day_of_week", "step_index", "create_time", "update_time"}
    parts = [
        f"{_qident(col)} = EXCLUDED.{_qident(col)}"
        for col in TARGET_COLUMNS
        if col not in skip
    ]
    parts.append(f"{_qident('update_time')} = NOW()")
    return ", ".join(parts)


def upsert_rows(
    conn: Any,
    *,
    target_schema: str,
    select_sql: str,
    params: list[Any],
    truncate: bool,
) -> int:
    target_q = _qualified(target_schema, TABLE_TARGET)
    cols = ", ".join(_qident(c) for c in TARGET_COLUMNS)
    insert_sql = f"""
INSERT INTO {target_q} ({cols})
{select_sql}
ON CONFLICT (link_id, day_of_week, step_index)
DO UPDATE SET {_upsert_assignments()}
"""
    with conn.cursor() as cur:
        if truncate:
            cur.execute(f"TRUNCATE TABLE {target_q}")
        cur.execute(insert_sql, params)
        affected = cur.rowcount
    conn.commit()
    return affected


def count_target_rows(conn: Any, *, target_schema: str) -> int:
    target_q = _qualified(target_schema, TABLE_TARGET)
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS cnt FROM {target_q} WHERE COALESCE(is_deleted, 0) = 0")
        row = cur.fetchone()
    return int((row or {}).get("cnt") or 0)


def run_build(
    *,
    truncate: bool = False,
    link_ids: list[str] | None = None,
    weeks: int = 12,
    skip_db: bool = False,
) -> dict[str, Any]:
    flow_schema = os.getenv("PG_FLOW_SCHEMA", "xianchang")

    conn = connect_pg()
    try:
        target_q = _qualified(flow_schema, TABLE_TARGET)
        if not skip_db:
            ensure_target_table(conn, target_q=target_q)

        select_sql, params = _build_select_sql(
            flow_schema=flow_schema,
            link_ids=link_ids,
            weeks=weeks,
        )

        if skip_db:
            return {
                "target_table": f"{flow_schema}.{TABLE_TARGET}",
                "weeks": weeks,
                "select_sql_preview": select_sql[:800],
            }

        started = time.perf_counter()
        affected = upsert_rows(
            conn,
            target_schema=flow_schema,
            select_sql=select_sql,
            params=params,
            truncate=truncate,
        )
        elapsed = time.perf_counter() - started
        total = count_target_rows(conn, target_schema=flow_schema)
        return {
            "target_table": f"{flow_schema}.{TABLE_TARGET}",
            "source_table": f"{flow_schema}.{TABLE_SOURCE}",
            "rows_affected": affected,
            "rows_total": total,
            "elapsed_sec": round(elapsed, 2),
            "weeks": weeks,
            "truncate": truncate,
        }
    finally:
        conn.close()


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(description="生成 dws_link_index_5min_mm")
    parser.add_argument("--link-id", action="append", dest="link_ids")
    parser.add_argument("--weeks", type=int, default=12)
    parser.add_argument("--truncate", action="store_true")
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()

    stats = run_build(
        truncate=args.truncate,
        link_ids=args.link_ids,
        weeks=args.weeks,
        skip_db=args.skip_db,
    )
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
