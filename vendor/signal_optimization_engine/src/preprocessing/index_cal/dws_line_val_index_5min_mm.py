#!/usr/bin/env python3
"""生成 line 综合评价表 dws_line_val_index_5min_mm。

依据 skillpackages/linevalindex.md：
  - 评价对象：line + 行驶方向（正向/反向）
  - 时间维度：day_of_week + step_index（5 分钟）
  - 指标：行程时间、总延误、行程速度、拥堵延时指数、总停车次数、连续停车路口序列

依赖（PG）：
  - xianchang.dws_inter_link_status_5min_mm
  - road6.dim_line_info / dim_line_link_rltn / dim_line_inter_rltn

用法:
    python -m preprocessing.index_cal.dws_line_val_index_5min_mm
    python -m preprocessing.index_cal.dws_line_val_index_5min_mm --truncate
    python -m preprocessing.index_cal.dws_line_val_index_5min_mm --build-deps --truncate
    python -m preprocessing.index_cal.dws_line_val_index_5min_mm --line-id <16位line_id>
"""

from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from data.pg_reader import connect_pg
from env import load_project_env
from preprocessing.index_cal.line_val_index_logic import (
    TRAVEL_DIR_FORWARD,
    TRAVEL_DIR_REVERSE,
    compute_line_slice_row,
)

TABLE_TARGET = "dws_line_val_index_5min_mm"
TABLE_LINK_STATUS = "dws_inter_link_status_5min_mm"
TABLE_LINK_INDEX = "dws_link_index_5min_mm"
TABLE_LINE = "dim_line_info"
TABLE_LINE_LINK = "dim_line_link_rltn"
TABLE_LINE_INTER = "dim_line_inter_rltn"
CALC_VERSION = "line_val_index_v2"

TARGET_COLUMNS = [
    "line_id",
    "travel_dir",
    "day_of_week",
    "step_index",
    "line_name",
    "road_name",
    "travel_dir_label",
    "line_length_m",
    "link_count",
    "inter_count",
    "travel_time_sec",
    "stop_time_sec",
    "travel_speed_kmh",
    "delay_index",
    "total_stop_times",
    "continuous_stop_sets_json",
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
    line_id                     varchar(16)  NOT NULL,
    travel_dir                  smallint     NOT NULL,
    day_of_week                 smallint     NOT NULL,
    step_index                  smallint     NOT NULL,
    line_name                   varchar(256),
    road_name                   varchar(128),
    travel_dir_label            varchar(8),
    line_length_m               numeric(12,2),
    link_count                  integer      NOT NULL DEFAULT 0,
    inter_count                 integer      NOT NULL DEFAULT 0,
    travel_time_sec             double precision,
    stop_time_sec               double precision,
    travel_speed_kmh            double precision,
    delay_index                 double precision,
    total_stop_times            double precision,
    continuous_stop_sets_json   jsonb        NOT NULL DEFAULT '[]'::jsonb,
    calc_version                varchar(64)  NOT NULL DEFAULT '{CALC_VERSION}',
    create_time                 timestamptz  NOT NULL DEFAULT NOW(),
    update_time                 timestamptz  NOT NULL DEFAULT NOW(),
    is_deleted                  smallint     NOT NULL DEFAULT 0,
    PRIMARY KEY (line_id, travel_dir, day_of_week, step_index),
    CONSTRAINT ck_dws_line_val_index_dir CHECK (travel_dir IN (1, 2)),
    CONSTRAINT ck_dws_line_val_index_dow CHECK (day_of_week BETWEEN 1 AND 7),
    CONSTRAINT ck_dws_line_val_index_step CHECK (step_index BETWEEN 0 AND 287)
)
""".strip()


def _create_index_ddl(*, target_q: str) -> list[str]:
    return [
        f"CREATE INDEX IF NOT EXISTS idx_line_val_line_day_step ON {target_q} (line_id, day_of_week, step_index)",
        f"CREATE INDEX IF NOT EXISTS idx_line_val_road ON {target_q} (road_name)",
        f"CREATE INDEX IF NOT EXISTS idx_line_val_delay ON {target_q} (delay_index DESC NULLS LAST)",
    ]


def ensure_target_table(conn: Any, *, target_q: str, with_indexes: bool = False) -> None:
    with conn.cursor() as cur:
        cur.execute(_create_table_ddl(target_q=target_q))
        if with_indexes:
            for ddl in _create_index_ddl(target_q=target_q):
                cur.execute(ddl)
    conn.commit()


def _upsert_assignments() -> str:
    skip = {"line_id", "travel_dir", "day_of_week", "step_index", "create_time", "update_time"}
    parts = [f"{_qident(c)} = EXCLUDED.{_qident(c)}" for c in TARGET_COLUMNS if c not in skip]
    parts.append(f"{_qident('update_time')} = NOW()")
    return ", ".join(parts)


def load_line_topology(
    conn: Any,
    *,
    road_schema: str,
    line_ids: list[str] | None,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    line_q = _qualified(road_schema, TABLE_LINE)
    link_q = _qualified(road_schema, TABLE_LINE_LINK)
    inter_q = _qualified(road_schema, TABLE_LINE_INTER)

    line_clause = ""
    params: list[Any] = []
    if line_ids:
        line_clause = " AND line_id = ANY(%s)"
        params.append(line_ids)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT line_id, line_name, road_name, line_length_m, link_count, inter_count
            FROM {line_q}
            WHERE COALESCE(is_deleted, 0) = 0
              {line_clause}
            ORDER BY road_name, line_name, line_id
            """,
            params,
        )
        lines = [dict(row) for row in cur.fetchall()]

        if not lines:
            return [], {}, {}

        active_ids = [str(row["line_id"]) for row in lines]
        cur.execute(
            f"""
            SELECT line_id, seq_no, link_id, length_m, f_inter_id, t_inter_id
            FROM {link_q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND line_id = ANY(%s)
            ORDER BY line_id, seq_no
            """,
            (active_ids,),
        )
        links_by_line: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in cur.fetchall():
            links_by_line[str(row["line_id"])].append(dict(row))

        cur.execute(
            f"""
            SELECT line_id, seq_no, inter_id, inter_name
            FROM {inter_q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND line_id = ANY(%s)
            ORDER BY line_id, seq_no
            """,
            (active_ids,),
        )
        inters_by_line: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in cur.fetchall():
            inters_by_line[str(row["line_id"])].append(dict(row))

    return lines, dict(links_by_line), dict(inters_by_line)


def load_link_status(
    conn: Any,
    *,
    flow_schema: str,
    link_ids: list[str],
) -> dict[tuple[str, str, int, int], dict[str, Any]]:
    if not link_ids:
        return {}
    status_q = _qualified(flow_schema, TABLE_LINK_STATUS)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT inter_id, link_id, day_of_week, step_index,
                   travel_time_sec, stop_time_sec, delay_index, stop_times, link_length_m
            FROM {status_q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND link_id = ANY(%s)
            """,
            (link_ids,),
        )
        rows = cur.fetchall()

    out: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row["inter_id"]),
            str(row["link_id"]),
            int(row["day_of_week"]),
            int(row["step_index"]),
        )
        out[key] = dict(row)
    return out


def load_link_index(
    conn: Any,
    *,
    flow_schema: str,
    link_ids: list[str],
) -> dict[tuple[str, int, int], dict[str, Any]]:
    if not link_ids:
        return {}
    index_q = _qualified(flow_schema, TABLE_LINK_INDEX)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT link_id, day_of_week, step_index,
                   delay_index, stop_time_sec, avg_speed_kmh
            FROM {index_q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND link_id = ANY(%s)
              AND avg_speed_kmh IS NOT NULL
              AND avg_speed_kmh > 0
            """,
            (link_ids,),
        )
        rows = cur.fetchall()

    out: dict[tuple[str, int, int], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["link_id"]), int(row["day_of_week"]), int(row["step_index"]))
        out[key] = dict(row)
    return out


def build_line_val_rows(
    conn: Any,
    *,
    flow_schema: str,
    road_schema: str,
    line_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    lines, links_by_line, inters_by_line = load_line_topology(
        conn,
        road_schema=road_schema,
        line_ids=line_ids,
    )
    if not lines:
        return []

    all_link_ids = sorted(
        {
            str(link["link_id"])
            for link_rows in links_by_line.values()
            for link in link_rows
        }
    )
    status_data = load_link_status(conn, flow_schema=flow_schema, link_ids=all_link_ids)
    index_data = load_link_index(conn, flow_schema=flow_schema, link_ids=all_link_ids)

    time_slices = sorted({(dow, step) for (_, _, dow, step) in status_data} | {(dow, step) for (_, dow, step) in index_data})
    if not time_slices:
        return []

    status_by_slice: dict[tuple[int, int], dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
    for (inter_id, link_id, dow, step), metric in status_data.items():
        status_by_slice[(dow, step)][(inter_id, link_id)] = metric

    index_by_slice: dict[tuple[int, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for (link_id, dow, step), metric in index_data.items():
        index_by_slice[(dow, step)][link_id] = metric

    rows: list[dict[str, Any]] = []
    for line in lines:
        line_id = str(line["line_id"])
        link_rows = links_by_line.get(line_id, [])
        inter_rows = inters_by_line.get(line_id, [])
        if not link_rows:
            continue
        inter_names = {str(i["inter_id"]): str(i.get("inter_name") or i["inter_id"]) for i in inter_rows}

        for day_of_week, step_index in time_slices:
            status_lookup = status_by_slice.get((day_of_week, step_index), {})
            link_index_lookup = index_by_slice.get((day_of_week, step_index), {})
            for travel_dir in (TRAVEL_DIR_FORWARD, TRAVEL_DIR_REVERSE):
                row = compute_line_slice_row(
                    line_row=line,
                    link_rows=link_rows,
                    inter_rows=inter_rows,
                    inter_names=inter_names,
                    status_lookup=status_lookup,
                    link_index_lookup=link_index_lookup,
                    travel_dir=travel_dir,
                    day_of_week=day_of_week,
                    step_index=step_index,
                    calc_version=CALC_VERSION,
                )
                if row:
                    rows.append(row)
    return rows


def upsert_rows(
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
ON CONFLICT (line_id, travel_dir, day_of_week, step_index)
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


def count_target_rows(conn: Any, *, target_schema: str) -> int:
    target_q = _qualified(target_schema, TABLE_TARGET)
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS cnt FROM {target_q} WHERE COALESCE(is_deleted, 0) = 0")
        row = cur.fetchone()
    return int((row or {}).get("cnt") or 0)


def run_build(
    *,
    truncate: bool = False,
    line_ids: list[str] | None = None,
    build_deps: bool = False,
    skip_db: bool = False,
) -> dict[str, Any]:
    from preprocessing.line.dim_line_info import run_build as run_line_build
    from preprocessing.index_cal.dws_inter_link_status_5min_mm import run_build as run_status_build

    flow_schema = os.getenv("PG_FLOW_SCHEMA", "xianchang")
    road_schema = os.getenv("PGSCHEMA", "road6")
    result: dict[str, Any] = {"deps": {}}

    if build_deps and not skip_db:
        result["deps"]["dim_line_info"] = run_line_build(truncate=False)
        result["deps"]["inter_link_status"] = run_status_build(truncate=truncate, build_deps=True)

    conn = connect_pg()
    try:
        target_q = _qualified(flow_schema, TABLE_TARGET)
        if not skip_db:
            ensure_target_table(conn, target_q=target_q, with_indexes=False)

        started = time.perf_counter()
        rows = build_line_val_rows(
            conn,
            flow_schema=flow_schema,
            road_schema=road_schema,
            line_ids=line_ids,
        )
        if skip_db:
            return {
                "target_table": f"{flow_schema}.{TABLE_TARGET}",
                "preview_rows": len(rows),
                "line_ids": line_ids,
            }

        affected = upsert_rows(
            conn,
            target_schema=flow_schema,
            rows=rows,
            truncate=truncate,
        )
        ensure_target_table(conn, target_q=target_q, with_indexes=True)
        elapsed = time.perf_counter() - started
        total = count_target_rows(conn, target_schema=flow_schema)
        result.update(
            {
                "target_table": f"{flow_schema}.{TABLE_TARGET}",
                "rows_affected": affected,
                "rows_total": total,
                "elapsed_sec": round(elapsed, 2),
                "line_ids": line_ids,
                "truncate": truncate,
            }
        )
        return result
    finally:
        conn.close()


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(description="生成 dws_line_val_index_5min_mm")
    parser.add_argument("--line-id", action="append", dest="line_ids", help="可选，指定 line_id（可重复）")
    parser.add_argument(
        "--build-deps",
        action="store_true",
        help="先构建 dim_line_info 与 dws_inter_link_status_5min_mm（含中间表）",
    )
    parser.add_argument("--truncate", action="store_true")
    parser.add_argument("--skip-db", action="store_true", help="仅预览行数，不写库")
    args = parser.parse_args()

    stats = run_build(
        truncate=args.truncate,
        line_ids=args.line_ids,
        build_deps=args.build_deps,
        skip_db=args.skip_db,
    )
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
