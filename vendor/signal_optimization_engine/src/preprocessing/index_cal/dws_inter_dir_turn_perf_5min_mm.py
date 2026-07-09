#!/usr/bin/env python3
"""生成路口进口方向转向运行指标 DWS 表 dws_inter_dir_turn_perf_5min_mm。

数据来源：
  - xianchang.dws_inter_approach_turn_perf_5min_mm：rid 级运行指标（上游须已写入）

主键：inter_id + f_dir_8 + turn_dir_no + day_of_week + step_index
聚合：pass_flow=SUM；其余运行指标=MAX；los=最差等级

用法:
    python -m preprocessing.index_cal.dws_inter_dir_turn_perf_5min_mm
    python -m preprocessing.index_cal.dws_inter_dir_turn_perf_5min_mm --truncate
    python -m preprocessing.index_cal.dws_inter_dir_turn_perf_5min_mm --inter-id 011wwe28kp600001
"""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

from data.pg_reader import DIR8_LABELS, connect_pg
from env import load_project_env

TABLE_SOURCE = "dws_inter_approach_turn_perf_5min_mm"
TABLE_TARGET = "dws_inter_dir_turn_perf_5min_mm"

TURN_DIR_LABELS = {0: "掉头", 1: "左转", 2: "直行", 3: "右转"}

TARGET_COLUMNS = [
    "inter_id",
    "f_dir_8",
    "turn_dir_no",
    "day_of_week",
    "step_index",
    "eight_direction",
    "inter_name",
    "f_dir_8_label",
    "turn_dir_label",
    "rid_length_m",
    "queue_len_max",
    "queue_len_avg",
    "pass_flow",
    "stop_time",
    "stop_times",
    "no_stop_pass_speed",
    "delay_index",
    "los",
    "create_time",
    "update_time",
    "is_deleted",
]

_LOS_WORST_ORDER = """
CASE los
    WHEN 'F' THEN 6 WHEN 'E' THEN 5 WHEN 'D' THEN 4
    WHEN 'C' THEN 3 WHEN 'B' THEN 2 WHEN 'A' THEN 1
    ELSE 0
END
""".strip()


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _qualified(schema: str, table: str) -> str:
    return f"{_qident(schema)}.{_qident(table)}"


def _f_dir_8_label_sql(expr: str) -> str:
    cases = " ".join(
        f"WHEN {expr} = {code} THEN '{label}'" for code, label in sorted(DIR8_LABELS.items())
    )
    return f"CASE {cases} ELSE NULL END"


def _turn_dir_label_sql(expr: str = "turn_dir_no") -> str:
    cases = " ".join(f"WHEN {expr} = {code} THEN '{label}'" for code, label in sorted(TURN_DIR_LABELS.items()))
    return f"CASE {cases} ELSE NULL END"


def _create_table_ddl(*, target_q: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {target_q} (
    inter_id            varchar(32)  NOT NULL,
    f_dir_8             smallint     NOT NULL,
    turn_dir_no         smallint     NOT NULL,
    day_of_week         smallint     NOT NULL,
    step_index          smallint     NOT NULL,
    eight_direction     smallint     NOT NULL,
    inter_name          varchar(128),
    f_dir_8_label       varchar(8),
    turn_dir_label      varchar(8),
    rid_length_m        numeric(10,2),
    queue_len_max       double precision NOT NULL DEFAULT 0,
    queue_len_avg       double precision NOT NULL DEFAULT 0,
    pass_flow           double precision NOT NULL DEFAULT 0,
    stop_time           double precision NOT NULL DEFAULT 0,
    stop_times          double precision NOT NULL DEFAULT 0,
    no_stop_pass_speed  double precision,
    delay_index         double precision NOT NULL DEFAULT 0,
    los                 varchar(1)   NOT NULL DEFAULT 'A',
    create_time         timestamp    NOT NULL DEFAULT NOW(),
    update_time         timestamp    NOT NULL DEFAULT NOW(),
    is_deleted          smallint     NOT NULL DEFAULT 0,
    PRIMARY KEY (inter_id, f_dir_8, turn_dir_no, day_of_week, step_index)
)
""".strip()


def _create_index_ddl(*, target_q: str) -> list[str]:
    return [
        f"CREATE INDEX IF NOT EXISTS idx_idtp_inter_day_step ON {target_q} (inter_id, day_of_week, step_index)",
        f"CREATE INDEX IF NOT EXISTS idx_idtp_inter_dir_turn ON {target_q} (inter_id, f_dir_8, turn_dir_no)",
        f"CREATE INDEX IF NOT EXISTS idx_idtp_los ON {target_q} (los)",
        f"CREATE INDEX IF NOT EXISTS idx_idtp_delay ON {target_q} (delay_index DESC)",
    ]


def ensure_target_table(conn: Any, *, target_q: str) -> None:
    with conn.cursor() as cur:
        cur.execute(_create_table_ddl(target_q=target_q))
        for ddl in _create_index_ddl(target_q=target_q):
            cur.execute(ddl)
    conn.commit()


def _build_aggregate_select_sql(
    *,
    source_q: str,
    inter_filter: list[str] | None,
) -> tuple[str, list[Any]]:
    params: list[Any] = []
    inter_clause = ""
    if inter_filter:
        inter_clause = " AND inter_id = ANY(%s)"
        params.append(inter_filter)

    sql = f"""
SELECT
    inter_id,
    f_dir_8,
    turn_dir_no,
    day_of_week,
    step_index,
    f_dir_8::smallint AS eight_direction,
    MAX(inter_name) AS inter_name,
    MAX(f_dir_8_label) AS f_dir_8_label,
    MAX(turn_dir_label) AS turn_dir_label,
    MAX(rid_length_m) AS rid_length_m,
    MAX(queue_len_max) AS queue_len_max,
    MAX(queue_len_avg) AS queue_len_avg,
    SUM(pass_flow) AS pass_flow,
    MAX(stop_time) AS stop_time,
    MAX(stop_times) AS stop_times,
    MAX(no_stop_pass_speed) AS no_stop_pass_speed,
    MAX(delay_index) AS delay_index,
    (ARRAY_AGG(los ORDER BY {_LOS_WORST_ORDER} DESC NULLS LAST))[1] AS los,
    NOW() AS create_time,
    NOW() AS update_time,
    0::smallint AS is_deleted
FROM {source_q}
WHERE COALESCE(is_deleted, 0) = 0
  {inter_clause}
GROUP BY inter_id, f_dir_8, turn_dir_no, day_of_week, step_index
"""
    return sql, params


def _upsert_assignments() -> str:
    skip = {"inter_id", "f_dir_8", "turn_dir_no", "day_of_week", "step_index", "create_time", "update_time"}
    parts = [
        f"{_qident(col)} = EXCLUDED.{_qident(col)}"
        for col in TARGET_COLUMNS
        if col not in skip
    ]
    parts.append(f"{_qident('update_time')} = NOW()")
    return ", ".join(parts)


def build_rows(
    *,
    flow_schema: str,
    inter_ids: list[str] | None,
) -> tuple[str, list[Any]]:
    source_q = _qualified(flow_schema, TABLE_SOURCE)
    return _build_aggregate_select_sql(source_q=source_q, inter_filter=inter_ids)


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
ON CONFLICT (inter_id, f_dir_8, turn_dir_no, day_of_week, step_index)
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
    inter_ids: list[str] | None = None,
    skip_db: bool = False,
) -> dict[str, Any]:
    flow_schema = os.getenv("PG_FLOW_SCHEMA", "xianchang")
    target_schema = flow_schema

    conn = connect_pg()
    try:
        target_q = _qualified(target_schema, TABLE_TARGET)
        if not skip_db:
            ensure_target_table(conn, target_q=target_q)

        select_sql, params = build_rows(flow_schema=flow_schema, inter_ids=inter_ids)

        if skip_db:
            return {
                "target_table": f"{target_schema}.{TABLE_TARGET}",
                "source_table": f"{flow_schema}.{TABLE_SOURCE}",
                "inter_ids": inter_ids,
                "select_sql_preview": select_sql[:500],
            }

        started = time.perf_counter()
        affected = upsert_rows(
            conn,
            target_schema=target_schema,
            select_sql=select_sql,
            params=params,
            truncate=truncate,
        )
        elapsed = time.perf_counter() - started
        total = count_target_rows(conn, target_schema=target_schema)
        return {
            "target_table": f"{target_schema}.{TABLE_TARGET}",
            "source_table": f"{flow_schema}.{TABLE_SOURCE}",
            "rows_affected": affected,
            "rows_total": total,
            "elapsed_sec": round(elapsed, 2),
            "inter_ids": inter_ids,
            "truncate": truncate,
        }
    finally:
        conn.close()


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(description="生成 dws_inter_dir_turn_perf_5min_mm")
    parser.add_argument(
        "--inter-id",
        action="append",
        dest="inter_ids",
        help="可选，仅处理指定路口（可重复）",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="写入前清空目标表",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="仅输出 SQL 预览，不建表/写入",
    )
    args = parser.parse_args()

    stats = run_build(
        truncate=args.truncate,
        inter_ids=args.inter_ids,
        skip_db=args.skip_db,
    )
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
