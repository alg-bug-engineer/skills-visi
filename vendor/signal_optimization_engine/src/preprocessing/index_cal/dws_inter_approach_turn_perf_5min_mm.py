#!/usr/bin/env python3
"""生成路口进口 rid 转向运行指标 DWS 表 dws_inter_approach_turn_perf_5min_mm。

数据来源：
  - xianchang.dwd_tfc_inter_dir_perf_5min：高德路口进口转向 5 分钟感知明细
  - road6.dim_rid_info：rid 长度 / 道路名
  - road6.dim_inter_info：路口名称

主键：inter_id + frid + turn_dir_no + day_of_week + step_index
冗余：f_dir_8 = eight_direction - 1

用法:
    python -m preprocessing.index_cal.dws_inter_approach_turn_perf_5min_mm
    python -m preprocessing.index_cal.dws_inter_approach_turn_perf_5min_mm --mode mean --truncate
    python -m preprocessing.index_cal.dws_inter_approach_turn_perf_5min_mm --inter-id 011wwe28kp600001
"""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

from data.pg_reader import DIR8_LABELS, connect_pg
from env import load_project_env

TABLE_SOURCE = "dwd_tfc_inter_dir_perf_5min"
TABLE_TARGET = "dws_inter_approach_turn_perf_5min_mm"

TURN_DIR_LABELS = {0: "掉头", 1: "左转", 2: "直行", 3: "右转"}

TARGET_COLUMNS = [
    "inter_id",
    "frid",
    "turn_dir_no",
    "day_of_week",
    "step_index",
    "f_dir_8",
    "eight_direction",
    "inter_name",
    "f_dir_8_label",
    "turn_dir_label",
    "rid_length_m",
    "road_name",
    "queue_len_max",
    "queue_len_avg",
    "pass_flow",
    "stop_time",
    "stop_times",
    "no_stop_pass_speed",
    "delay_index",
    "los",
    "confidence",
    "idx_state",
    "create_time",
    "update_time",
    "is_deleted",
]


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _qualified(schema: str, table: str) -> str:
    return f"{_qident(schema)}.{_qident(table)}"


def _f_dir_8_label_sql(expr: str) -> str:
    cases = " ".join(
        f"WHEN {expr} = {code} THEN '{label}'" for code, label in sorted(DIR8_LABELS.items())
    )
    return f"CASE {cases} ELSE NULL END"


def _turn_dir_label_sql(expr: str = "p.turn_dir_no") -> str:
    cases = " ".join(f"WHEN {expr} = {code} THEN '{label}'" for code, label in sorted(TURN_DIR_LABELS.items()))
    return f"CASE {cases} ELSE NULL END"


def _create_table_ddl(*, target_q: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {target_q} (
    inter_id            varchar(32)  NOT NULL,
    frid                varchar(64)  NOT NULL,
    turn_dir_no         smallint     NOT NULL,
    day_of_week         smallint     NOT NULL,
    step_index          smallint     NOT NULL,
    f_dir_8             smallint     NOT NULL,
    eight_direction     smallint     NOT NULL,
    inter_name          varchar(128),
    f_dir_8_label       varchar(8),
    turn_dir_label      varchar(8),
    rid_length_m        numeric(10,2),
    road_name           varchar(255),
    queue_len_max       double precision NOT NULL DEFAULT 0,
    queue_len_avg       double precision NOT NULL DEFAULT 0,
    pass_flow           double precision NOT NULL DEFAULT 0,
    stop_time           double precision NOT NULL DEFAULT 0,
    stop_times          double precision NOT NULL DEFAULT 0,
    no_stop_pass_speed  double precision,
    delay_index         double precision NOT NULL DEFAULT 0,
    los                 varchar(1)   NOT NULL DEFAULT 'A',
    confidence          smallint     NOT NULL DEFAULT 0,
    idx_state           smallint     NOT NULL DEFAULT 0,
    create_time         timestamp    NOT NULL DEFAULT NOW(),
    update_time         timestamp    NOT NULL DEFAULT NOW(),
    is_deleted          smallint     NOT NULL DEFAULT 0,
    PRIMARY KEY (inter_id, frid, turn_dir_no, day_of_week, step_index)
)
""".strip()


def _create_index_ddl(*, target_q: str) -> list[str]:
    return [
        f"CREATE INDEX IF NOT EXISTS idx_iatp_inter_day_step ON {target_q} (inter_id, day_of_week, step_index)",
        f"CREATE INDEX IF NOT EXISTS idx_iatp_inter_dir_turn ON {target_q} (inter_id, f_dir_8, turn_dir_no)",
        f"CREATE INDEX IF NOT EXISTS idx_iatp_frid ON {target_q} (frid)",
        f"CREATE INDEX IF NOT EXISTS idx_iatp_los ON {target_q} (los)",
        f"CREATE INDEX IF NOT EXISTS idx_iatp_delay ON {target_q} (delay_index DESC)",
    ]


def ensure_target_table(conn: Any, *, target_q: str) -> None:
    with conn.cursor() as cur:
        cur.execute(_create_table_ddl(target_q=target_q))
        for ddl in _create_index_ddl(target_q=target_q):
            cur.execute(ddl)
    conn.commit()


def _time_bucket_sql(prefix: str = "p") -> tuple[str, str]:
    day_sql = f"EXTRACT(ISODOW FROM {prefix}.stat_time)::smallint"
    step_sql = (
        f"((EXTRACT(HOUR FROM {prefix}.stat_time) * 60"
        f" + EXTRACT(MINUTE FROM {prefix}.stat_time)) / 5)::smallint"
    )
    return day_sql, step_sql


def _base_from_sql(
    *,
    source_q: str,
    rid_q: str,
    inter_q: str,
    inter_filter: list[str] | None,
) -> tuple[str, list[Any]]:
    day_sql, step_sql = _time_bucket_sql("p")
    params: list[Any] = []
    inter_clause = ""
    if inter_filter:
        inter_clause = " AND p.inter_id = ANY(%s)"
        params.append(inter_filter)

    sql = f"""
FROM {source_q} p
LEFT JOIN {rid_q} r
  ON r.rid_id = p.frid
LEFT JOIN {inter_q} di
  ON di.inter_id = p.inter_id
WHERE COALESCE(p.is_deleted, 0) = 0
  AND p.eight_direction BETWEEN 1 AND 8
  AND p.turn_dir_no BETWEEN 0 AND 3
  {inter_clause}
"""
    return sql, params


def _build_snapshot_select_sql(
    *,
    source_q: str,
    rid_q: str,
    inter_q: str,
    inter_filter: list[str] | None,
) -> tuple[str, list[Any]]:
    day_sql, step_sql = _time_bucket_sql("p")
    from_sql, params = _base_from_sql(
        source_q=source_q,
        rid_q=rid_q,
        inter_q=inter_q,
        inter_filter=inter_filter,
    )
    f_dir_expr = "(p.eight_direction - 1)::smallint"
    sql = f"""
SELECT
    p.inter_id,
    p.frid,
    p.turn_dir_no,
    {day_sql} AS day_of_week,
    {step_sql} AS step_index,
    {f_dir_expr} AS f_dir_8,
    p.eight_direction::smallint AS eight_direction,
    di.inter_name,
    {_f_dir_8_label_sql(f_dir_expr)} AS f_dir_8_label,
    {_turn_dir_label_sql()} AS turn_dir_label,
    r.length_m AS rid_length_m,
    r.road_name,
    p.queue_len_max,
    p.queue_len_avg,
    p.pass_flow,
    p.stop_time,
    p.stop_times,
    p.no_stop_pass_speed,
    p.delay_index,
    p.los,
    p.confidence::smallint AS confidence,
    p.idx_state::smallint AS idx_state,
    p.stat_time,
    NOW() AS create_time,
    NOW() AS update_time,
    0::smallint AS is_deleted
{from_sql}
"""
    col_list = ", ".join(_qident(c) for c in TARGET_COLUMNS)
    dedup = f"""
SELECT {col_list}
FROM (
    SELECT DISTINCT ON (inter_id, frid, turn_dir_no, day_of_week, step_index)
        inter_id,
        frid,
        turn_dir_no,
        day_of_week,
        step_index,
        f_dir_8,
        eight_direction,
        inter_name,
        f_dir_8_label,
        turn_dir_label,
        rid_length_m,
        road_name,
        queue_len_max,
        queue_len_avg,
        pass_flow,
        stop_time,
        stop_times,
        no_stop_pass_speed,
        delay_index,
        los,
        confidence,
        idx_state,
        create_time,
        update_time,
        is_deleted,
        stat_time
    FROM ({sql}) src
    ORDER BY inter_id, frid, turn_dir_no, day_of_week, step_index, stat_time DESC
) picked
"""
    return dedup, params


def _build_mean_select_sql(
    *,
    source_q: str,
    rid_q: str,
    inter_q: str,
    inter_filter: list[str] | None,
) -> tuple[str, list[Any]]:
    day_sql, step_sql = _time_bucket_sql("p")
    from_sql, params = _base_from_sql(
        source_q=source_q,
        rid_q=rid_q,
        inter_q=inter_q,
        inter_filter=inter_filter,
    )
    f_dir_expr = "(MAX(p.eight_direction) - 1)::smallint"
    sql = f"""
SELECT
    p.inter_id,
    p.frid,
    p.turn_dir_no,
    {day_sql} AS day_of_week,
    {step_sql} AS step_index,
    {f_dir_expr} AS f_dir_8,
    MAX(p.eight_direction)::smallint AS eight_direction,
    MAX(di.inter_name) AS inter_name,
    {_f_dir_8_label_sql(f_dir_expr)} AS f_dir_8_label,
    {_turn_dir_label_sql("p.turn_dir_no")} AS turn_dir_label,
    MAX(r.length_m) AS rid_length_m,
    MAX(r.road_name) AS road_name,
    MAX(p.queue_len_max) AS queue_len_max,
    AVG(p.queue_len_avg) AS queue_len_avg,
    AVG(p.pass_flow) AS pass_flow,
    AVG(p.stop_time) AS stop_time,
    AVG(p.stop_times) AS stop_times,
    AVG(p.no_stop_pass_speed) AS no_stop_pass_speed,
    AVG(p.delay_index) AS delay_index,
    (ARRAY_AGG(p.los ORDER BY p.delay_index DESC NULLS LAST))[1] AS los,
    MIN(p.confidence)::smallint AS confidence,
    MAX(p.idx_state)::smallint AS idx_state,
    NOW() AS create_time,
    NOW() AS update_time,
    0::smallint AS is_deleted
{from_sql}
GROUP BY
    p.inter_id,
    p.frid,
    p.turn_dir_no,
    {day_sql},
    {step_sql}
"""
    return sql, params


def _upsert_assignments() -> str:
    skip = {"inter_id", "frid", "turn_dir_no", "day_of_week", "step_index", "create_time", "update_time"}
    parts = [
        f"{_qident(col)} = EXCLUDED.{_qident(col)}"
        for col in TARGET_COLUMNS
        if col not in skip
    ]
    parts.append(f"{_qident('update_time')} = NOW()")
    return ", ".join(parts)


def build_rows(
    conn: Any,
    *,
    flow_schema: str,
    road_schema: str,
    target_schema: str,
    mode: str,
    inter_ids: list[str] | None,
) -> tuple[str, list[Any]]:
    source_q = _qualified(flow_schema, TABLE_SOURCE)
    rid_q = _qualified(road_schema, "dim_rid_info")
    inter_q = _qualified(road_schema, os.getenv("PG_DIM_INTER_TABLE", "dim_inter_info"))
    if mode == "snapshot":
        return _build_snapshot_select_sql(
            source_q=source_q,
            rid_q=rid_q,
            inter_q=inter_q,
            inter_filter=inter_ids,
        )
    if mode == "mean":
        return _build_mean_select_sql(
            source_q=source_q,
            rid_q=rid_q,
            inter_q=inter_q,
            inter_filter=inter_ids,
        )
    raise ValueError(f"未知 mode: {mode}")


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
ON CONFLICT (inter_id, frid, turn_dir_no, day_of_week, step_index)
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
    mode: str = "mean",
    truncate: bool = False,
    inter_ids: list[str] | None = None,
    skip_db: bool = False,
) -> dict[str, Any]:
    flow_schema = os.getenv("PG_FLOW_SCHEMA", "xianchang")
    road_schema = os.getenv("PGSCHEMA", "road6")
    target_schema = flow_schema

    conn = connect_pg()
    try:
        target_q = _qualified(target_schema, TABLE_TARGET)
        if not skip_db:
            ensure_target_table(conn, target_q=target_q)

        select_sql, params = build_rows(
            conn,
            flow_schema=flow_schema,
            road_schema=road_schema,
            target_schema=target_schema,
            mode=mode,
            inter_ids=inter_ids,
        )

        if skip_db:
            return {
                "mode": mode,
                "target_table": f"{target_schema}.{TABLE_TARGET}",
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
            "mode": mode,
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
    parser = argparse.ArgumentParser(description="生成 dws_inter_approach_turn_perf_5min_mm")
    parser.add_argument(
        "--mode",
        choices=("mean", "snapshot"),
        default="mean",
        help="mean=同一 weekday+step 跨日取均值（默认）；snapshot=取最新 stat_time 快照",
    )
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
        mode=args.mode,
        truncate=args.truncate,
        inter_ids=args.inter_ids,
        skip_db=args.skip_db,
    )
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
