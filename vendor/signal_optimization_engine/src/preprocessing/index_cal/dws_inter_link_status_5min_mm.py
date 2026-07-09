#!/usr/bin/env python3
"""生成路口进口 link 状态指标 DWS 表 dws_inter_link_status_5min_mm。

依赖中间表（须先运行）：
  - dws_link_index_5min_mm          link 2min→5min 运行指标
  - dws_inter_link_turn_flow_5min_mm link 转向流量

数据来源（PG，字段已校验）：
  - road6.dim_link_info.length_m / road_name
  - road6.dwd_tfc_rltn_wide_inter_ft_link
  - xianchang.dws_ctl_inter_turn_5min_his_mm

用法:
    python -m preprocessing.index_cal.dws_inter_link_status_5min_mm
    python -m preprocessing.index_cal.dws_inter_link_status_5min_mm --truncate
    python -m preprocessing.index_cal.dws_inter_link_status_5min_mm --build-deps --truncate
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from typing import Any

from data.pg_reader import DIR8_LABELS, connect_pg
from env import load_project_env
from preprocessing.index_cal.inter_link_status_logic import (
    MIN_RED_SEC,
    VEHICLE_HEADWAY_M,
    avg_lane_flow_for_main_turns,
    avg_red_sec_for_main_turns,
    calc_queue_len_est_m,
    calc_stop_times,
    calc_travel_time_sec,
    entrance_links_cte_sql,
    format_main_turn_dirs,
    select_main_entrance_links,
    select_main_turn_dirs,
    should_skip_timing,
)

TABLE_TARGET = "dws_inter_link_status_5min_mm"
TABLE_LINK_INDEX_5MIN = "dws_link_index_5min_mm"
TABLE_TURN_FLOW = os.getenv("PG_TURN_FLOW_TABLE", "dws_inter_link_turn_flow_5min_mm")
TABLE_TIMING = "dws_ctl_inter_turn_5min_his_mm"

TARGET_COLUMNS = [
    "inter_id",
    "link_id",
    "day_of_week",
    "step_index",
    "inter_name",
    "link_name",
    "dir8_code",
    "dir8_label",
    "link_length_m",
    "travel_time_sec",
    "delay_index",
    "stop_time_sec",
    "avg_nostop_speed",
    "stop_times",
    "avg_lane_flow",
    "queue_len_est_m",
    "main_turn_dirs",
    "avg_red_sec",
    "calc_version",
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


def _create_table_ddl(*, target_q: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {target_q} (
    inter_id            varchar(32)  NOT NULL,
    link_id             varchar(32)  NOT NULL,
    day_of_week         smallint     NOT NULL,
    step_index          smallint     NOT NULL,
    inter_name          varchar(128),
    link_name           varchar(256),
    dir8_code           smallint,
    dir8_label          varchar(8),
    link_length_m       numeric(10,2),
    travel_time_sec     double precision,
    delay_index         double precision,
    stop_time_sec       double precision,
    avg_nostop_speed    double precision,
    stop_times          double precision,
    avg_lane_flow       double precision,
    queue_len_est_m     double precision,
    main_turn_dirs      varchar(16),
    avg_red_sec         double precision,
    calc_version        varchar(64)  NOT NULL DEFAULT 'inter_link_status_v1',
    create_time         timestamp    NOT NULL DEFAULT NOW(),
    update_time         timestamp    NOT NULL DEFAULT NOW(),
    is_deleted          smallint     NOT NULL DEFAULT 0,
    PRIMARY KEY (inter_id, link_id, day_of_week, step_index)
)
""".strip()


def _create_index_ddl(*, target_q: str) -> list[str]:
    return [
        f"CREATE INDEX IF NOT EXISTS idx_ils_inter_day_step ON {target_q} (inter_id, day_of_week, step_index)",
        f"CREATE INDEX IF NOT EXISTS idx_ils_link ON {target_q} (link_id)",
        f"CREATE INDEX IF NOT EXISTS idx_ils_delay ON {target_q} (delay_index DESC NULLS LAST)",
        f"CREATE INDEX IF NOT EXISTS idx_ils_queue ON {target_q} (queue_len_est_m DESC NULLS LAST)",
    ]


def ensure_target_table(conn: Any, *, target_q: str, with_indexes: bool = False) -> None:
    with conn.cursor() as cur:
        cur.execute(_create_table_ddl(target_q=target_q))
        if with_indexes:
            for ddl in _create_index_ddl(target_q=target_q):
                cur.execute(ddl)
    conn.commit()


def resolve_dim_link_table(conn: Any, *, road_schema: str) -> tuple[str, str]:
    """返回 (qualified_table, length_column)。优先 dim_link_info.length_m。"""
    preferred = (os.getenv("PG_DIM_LINK_TABLE") or "dim_link_info").strip()
    candidates = []
    for name in ("dim_link_info", preferred):
        if name and name not in candidates:
            candidates.append(name)

    with conn.cursor() as cur:
        for table in candidates:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                  AND column_name IN ('length_m', 'length', 'link_length_m')
                ORDER BY CASE column_name
                    WHEN 'length_m' THEN 1
                    WHEN 'link_length_m' THEN 2
                    WHEN 'length' THEN 3
                    ELSE 9
                END
                LIMIT 1
                """,
                (road_schema, table),
            )
            row = cur.fetchone()
            if row:
                length_col = str(row["column_name"])
                return _qualified(road_schema, table), length_col
    raise RuntimeError(f"未找到含长度字段的 link 维表，已尝试: {candidates}")


def _build_select_sql(
    conn: Any,
    *,
    flow_schema: str,
    road_schema: str,
    inter_filter: list[str] | None,
) -> tuple[str, list[Any]]:
    link_index_q = _qualified(flow_schema, TABLE_LINK_INDEX_5MIN)
    turn_flow_q = _qualified(flow_schema, TABLE_TURN_FLOW)
    timing_q = _qualified(flow_schema, os.getenv("PG_TIMING_TURN_TABLE", TABLE_TIMING))
    channel_q = _qualified(road_schema, os.getenv("PG_CHANNEL_TABLE", "dwd_tfc_rltn_wide_inter_ft_link"))
    link_q, length_col = resolve_dim_link_table(conn, road_schema=road_schema)
    inter_q = _qualified(road_schema, os.getenv("PG_DIM_INTER_TABLE", "dim_inter_info"))

    inter_clause_entrance = ""
    inter_clause_timing = ""
    params: list[Any] = []
    if inter_filter:
        inter_clause_entrance = " AND ch.inter_id::text = ANY(%s)"
        inter_clause_timing = " AND tf.inter_id = ANY(%s)"
        params.extend([inter_filter, inter_filter])

    sql = f"""
WITH {entrance_links_cte_sql(channel_q=channel_q, inter_clause=inter_clause_entrance)},
turn_flow AS (
    SELECT
        tf.inter_id,
        tf.link_id,
        tf.turn_dir_no,
        tf.day_of_week,
        tf.step_index,
        tf.turn_flow_total,
        tf.avg_lane_flow_5min
    FROM {turn_flow_q} tf
    WHERE COALESCE(tf.is_deleted, 0) = 0
      AND tf.turn_dir_no IN (1, 2)
),
main_direction AS (
    SELECT
        tf.inter_id,
        tf.link_id,
        tf.day_of_week,
        tf.step_index,
        MAX(CASE WHEN tf.turn_dir_no = 2 THEN tf.turn_flow_total END) AS straight_flow,
        MAX(CASE WHEN tf.turn_dir_no = 1 THEN tf.turn_flow_total END) AS left_flow,
        MAX(CASE WHEN tf.turn_dir_no = 2 THEN tf.avg_lane_flow_5min END) AS straight_lane_flow,
        MAX(CASE WHEN tf.turn_dir_no = 1 THEN tf.avg_lane_flow_5min END) AS left_lane_flow
    FROM turn_flow tf
    GROUP BY tf.inter_id, tf.link_id, tf.day_of_week, tf.step_index
),
main_turn_pick AS (
    SELECT
        md.*,
        CASE
            WHEN COALESCE(md.straight_flow, 0) > COALESCE(md.left_flow, 0) * 1.5 THEN ARRAY[2::smallint]
            WHEN COALESCE(md.left_flow, 0) > COALESCE(md.straight_flow, 0) * 1.5 THEN ARRAY[1::smallint]
            ELSE ARRAY[1::smallint, 2::smallint]
        END AS main_turns
    FROM main_direction md
),
turn_timing AS (
    SELECT
        t.inter_id::text AS inter_id,
        t.link_id::text AS link_id,
        t.turn_dir_no::smallint AS turn_dir_no,
        t.day_of_week::smallint AS day_of_week,
        t.step_index::smallint AS step_index,
        GREATEST(t.cycle_len_sec::float - t.green_exec_sec::float, 0) AS red_exec_sec
    FROM {timing_q} t
    JOIN entrance_links el
      ON el.inter_id = t.inter_id::text
     AND el.link_id = t.link_id::text
    WHERE COALESCE(t.is_deleted, 0) = 0
      AND t.turn_dir_no IN (1, 2)
      {inter_clause_timing}
),
main_metrics AS (
    SELECT
        mtp.inter_id,
        mtp.link_id,
        mtp.day_of_week,
        mtp.step_index,
        array_to_string(mtp.main_turns, ',') AS main_turn_dirs,
        CASE
            WHEN cardinality(mtp.main_turns) = 1 THEN
                CASE WHEN mtp.main_turns[1] = 2 THEN mtp.straight_lane_flow ELSE mtp.left_lane_flow END
            ELSE (
                COALESCE(mtp.straight_lane_flow, 0) + COALESCE(mtp.left_lane_flow, 0)
            ) / NULLIF(
                (CASE WHEN mtp.straight_lane_flow IS NOT NULL THEN 1 ELSE 0 END)
              + (CASE WHEN mtp.left_lane_flow IS NOT NULL THEN 1 ELSE 0 END),
                0
            )
        END AS avg_lane_flow,
        SUM(
            tt.red_exec_sec * CASE tt.turn_dir_no
                WHEN 2 THEN GREATEST(COALESCE(mtp.straight_flow, 0), 0.001)
                ELSE GREATEST(COALESCE(mtp.left_flow, 0), 0.001)
            END
        ) / NULLIF(
            SUM(CASE tt.turn_dir_no
                WHEN 2 THEN GREATEST(COALESCE(mtp.straight_flow, 0), 0.001)
                ELSE GREATEST(COALESCE(mtp.left_flow, 0), 0.001)
            END),
            0
        ) AS avg_red_sec
    FROM main_turn_pick mtp
    JOIN turn_timing tt
      ON tt.inter_id = mtp.inter_id
     AND tt.link_id = mtp.link_id
     AND tt.day_of_week = mtp.day_of_week
     AND tt.step_index = mtp.step_index
     AND tt.turn_dir_no = ANY(mtp.main_turns)
     AND tt.red_exec_sec > 0
    GROUP BY
        mtp.inter_id,
        mtp.link_id,
        mtp.day_of_week,
        mtp.step_index,
        mtp.main_turns,
        mtp.straight_flow,
        mtp.left_flow,
        mtp.straight_lane_flow,
        mtp.left_lane_flow
)
SELECT
    mm.inter_id,
    mm.link_id,
    mm.day_of_week,
    mm.step_index,
    di.inter_name,
    dl.road_name AS link_name,
    el.dir8_code,
    {_f_dir_8_label_sql("el.dir8_code")} AS dir8_label,
    dl.{_qident(length_col)} AS link_length_m,
    CASE
        WHEN li.avg_speed_kmh > 0 AND dl.{_qident(length_col)} > 0
        THEN dl.{_qident(length_col)}::float / (li.avg_speed_kmh / 3.6)
        ELSE NULL
    END AS travel_time_sec,
    li.delay_index,
    li.stop_time_sec,
    li.avg_nostop_speed,
    CASE
        WHEN mm.avg_red_sec >= {MIN_RED_SEC} AND li.stop_time_sec IS NOT NULL
        THEN li.stop_time_sec / mm.avg_red_sec
        ELSE NULL
    END AS stop_times,
    mm.avg_lane_flow,
    CASE
        WHEN mm.avg_red_sec >= {MIN_RED_SEC}
         AND li.stop_time_sec IS NOT NULL
         AND mm.avg_lane_flow IS NOT NULL
         AND dl.{_qident(length_col)} > 0
        THEN LEAST(
            (li.stop_time_sec / mm.avg_red_sec) * mm.avg_lane_flow * {VEHICLE_HEADWAY_M},
            dl.{_qident(length_col)}::float
        )
        ELSE NULL
    END AS queue_len_est_m,
    mm.main_turn_dirs,
    mm.avg_red_sec,
    'inter_link_status_v1' AS calc_version,
    NOW() AS create_time,
    NOW() AS update_time,
    0::smallint AS is_deleted
FROM main_metrics mm
JOIN entrance_links el
  ON el.inter_id = mm.inter_id
 AND el.link_id = mm.link_id
JOIN {link_index_q} li
  ON li.link_id = mm.link_id
 AND li.day_of_week = mm.day_of_week
 AND li.step_index = mm.step_index
 AND COALESCE(li.is_deleted, 0) = 0
LEFT JOIN {link_q} dl ON dl.link_id::text = mm.link_id
LEFT JOIN {inter_q} di ON di.inter_id::text = mm.inter_id
WHERE mm.avg_red_sec IS NOT NULL
  AND mm.avg_red_sec >= {MIN_RED_SEC}
"""
    return sql, params


def _upsert_assignments() -> str:
    skip = {"inter_id", "link_id", "day_of_week", "step_index", "create_time", "update_time"}
    parts = [
        f"{_qident(col)} = EXCLUDED.{_qident(col)}"
        for col in TARGET_COLUMNS
        if col not in skip
    ]
    parts.append(f"{_qident('update_time')} = NOW()")
    return ", ".join(parts)


def _load_entrance_links(conn: Any, *, channel_q: str, inter_filter: list[str] | None) -> dict[str, dict[str, Any]]:
    clause = ""
    params: list[Any] = []
    if inter_filter:
        clause = " AND ch.inter_id::text = ANY(%s)"
        params.append(inter_filter)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                ch.inter_id::text AS inter_id,
                ch.link_id::text AS link_id,
                NULLIF(ch.dir8_code::text, '')::smallint AS dir8_code,
                COALESCE(NULLIF(ch.lane_num::text, '')::int, 0) AS lane_num
            FROM {channel_q} ch
            WHERE lower(btrim(ch.link_role::text)) = 'entrance'
              AND ch.link_id IS NOT NULL
              AND btrim(ch.link_id::text) <> ''
              {clause}
            """,
            params,
        )
        rows = select_main_entrance_links([dict(r) for r in cur.fetchall()])
    return {str(r["link_id"]): dict(r) for r in rows}


def _load_link_dim(
    conn: Any,
    *,
    road_schema: str,
    link_ids: set[str],
) -> dict[str, dict[str, Any]]:
    if not link_ids:
        return {}
    link_q, length_col = resolve_dim_link_table(conn, road_schema=road_schema)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT link_id::text AS link_id,
                   road_name,
                   {_qident(length_col)}::float AS link_length_m
            FROM {link_q}
            WHERE link_id::text = ANY(%s)
            """,
            (sorted(link_ids),),
        )
        rows = cur.fetchall()
    return {str(r["link_id"]): dict(r) for r in rows}


def _load_inter_names(conn: Any, *, inter_q: str, inter_ids: set[str]) -> dict[str, str]:
    if not inter_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT inter_id::text AS inter_id, inter_name
            FROM {inter_q}
            WHERE inter_id::text = ANY(%s)
            """,
            (sorted(inter_ids),),
        )
        rows = cur.fetchall()
    return {str(r["inter_id"]): str(r.get("inter_name") or "") for r in rows}


def _load_turn_flow_index(
    conn: Any,
    *,
    turn_flow_q: str,
    inter_filter: list[str] | None,
) -> dict[tuple[str, str, int, int], dict[str, float | None]]:
    clause = ""
    params: list[Any] = []
    if inter_filter:
        clause = " AND tf.inter_id = ANY(%s)"
        params.append(inter_filter)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT tf.inter_id, tf.link_id, tf.turn_dir_no, tf.day_of_week, tf.step_index,
                   tf.turn_flow_total, tf.avg_lane_flow_5min
            FROM {turn_flow_q} tf
            WHERE COALESCE(tf.is_deleted, 0) = 0
              AND tf.turn_dir_no IN (1, 2)
              {clause}
            """,
            params,
        )
        rows = cur.fetchall()
    index: dict[tuple[str, str, int, int], dict[str, float | None]] = {}
    for row in rows:
        key = (str(row["inter_id"]), str(row["link_id"]), int(row["day_of_week"]), int(row["step_index"]))
        bucket = index.setdefault(
            key,
            {"straight_flow": None, "left_flow": None, "straight_lane_flow": None, "left_lane_flow": None},
        )
        turn = int(row["turn_dir_no"])
        if turn == 2:
            bucket["straight_flow"] = float(row["turn_flow_total"] or 0)
            bucket["straight_lane_flow"] = float(row["avg_lane_flow_5min"] or 0)
        else:
            bucket["left_flow"] = float(row["turn_flow_total"] or 0)
            bucket["left_lane_flow"] = float(row["avg_lane_flow_5min"] or 0)
    return index


def _load_timing_index(
    conn: Any,
    *,
    timing_q: str,
    inter_filter: list[str] | None,
) -> dict[tuple[str, str, int, int, int], float]:
    clause = ""
    params: list[Any] = []
    if inter_filter:
        clause = " AND t.inter_id::text = ANY(%s)"
        params.append(inter_filter)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT t.inter_id::text AS inter_id,
                   t.link_id::text AS link_id,
                   t.turn_dir_no::int AS turn_dir_no,
                   t.day_of_week::int AS day_of_week,
                   t.step_index::int AS step_index,
                   GREATEST(t.cycle_len_sec::float - t.green_exec_sec::float, 0) AS red_exec_sec
            FROM {timing_q} t
            WHERE COALESCE(t.is_deleted, 0) = 0
              AND t.turn_dir_no IN (1, 2)
              {clause}
            """,
            params,
        )
        rows = cur.fetchall()
    return {
        (
            str(row["inter_id"]),
            str(row["link_id"]),
            int(row["turn_dir_no"]),
            int(row["day_of_week"]),
            int(row["step_index"]),
        ): float(row["red_exec_sec"] or 0)
        for row in rows
        if float(row["red_exec_sec"] or 0) > 0
    }


def _load_link_index_index(
    conn: Any,
    *,
    link_index_q: str,
    link_ids: set[str],
) -> dict[tuple[str, int, int], dict[str, Any]]:
    if not link_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT link_id, day_of_week, step_index,
                   delay_index, stop_time_sec, avg_speed_kmh, avg_nostop_speed
            FROM {link_index_q}
            WHERE COALESCE(is_deleted, 0) = 0
              AND link_id = ANY(%s)
            """,
            (sorted(link_ids),),
        )
        rows = cur.fetchall()
    return {
        (str(row["link_id"]), int(row["day_of_week"]), int(row["step_index"])): dict(row)
        for row in rows
    }


def _f_dir_8_label(code: int | None) -> str | None:
    if code is None:
        return None
    return DIR8_LABELS.get(int(code))


def build_status_rows_python(
    conn: Any,
    *,
    flow_schema: str,
    road_schema: str,
    inter_filter: list[str] | None,
) -> list[dict[str, Any]]:
    channel_q = _qualified(road_schema, os.getenv("PG_CHANNEL_TABLE", "dwd_tfc_rltn_wide_inter_ft_link"))
    inter_q = _qualified(road_schema, os.getenv("PG_DIM_INTER_TABLE", "dim_inter_info"))
    turn_flow_q = _qualified(flow_schema, TABLE_TURN_FLOW)
    timing_q = _qualified(flow_schema, os.getenv("PG_TIMING_TURN_TABLE", TABLE_TIMING))
    link_index_q = _qualified(flow_schema, TABLE_LINK_INDEX_5MIN)

    entrance = _load_entrance_links(conn, channel_q=channel_q, inter_filter=inter_filter)
    turn_flow = _load_turn_flow_index(conn, turn_flow_q=turn_flow_q, inter_filter=inter_filter)
    timing = _load_timing_index(conn, timing_q=timing_q, inter_filter=inter_filter)
    link_ids = set(entrance)
    link_dim = _load_link_dim(conn, road_schema=road_schema, link_ids=link_ids)
    link_index = _load_link_index_index(conn, link_index_q=link_index_q, link_ids=link_ids)
    inter_names = _load_inter_names(
        conn,
        inter_q=inter_q,
        inter_ids={v["inter_id"] for v in entrance.values()},
    )

    rows: list[dict[str, Any]] = []
    for (inter_id, link_id, day_of_week, step_index), flow in turn_flow.items():
        ent = entrance.get(link_id)
        if ent is None or ent["inter_id"] != inter_id:
            continue
        li = link_index.get((link_id, day_of_week, step_index))
        if li is None:
            continue

        main_turns = select_main_turn_dirs(flow.get("straight_flow"), flow.get("left_flow"))
        timing_by_turn = {
            turn: timing.get((inter_id, link_id, turn, day_of_week, step_index))
            for turn in main_turns
        }
        weights = {
            2: float(flow.get("straight_flow") or 0),
            1: float(flow.get("left_flow") or 0),
        }
        avg_red = avg_red_sec_for_main_turns(timing_by_turn, main_turns, weights=weights)
        if should_skip_timing(avg_red, has_timing=avg_red is not None):
            continue

        lane_flow_by_turn = {
            2: flow.get("straight_lane_flow"),
            1: flow.get("left_lane_flow"),
        }
        avg_lane_flow = avg_lane_flow_for_main_turns(lane_flow_by_turn, main_turns)
        dim = link_dim.get(link_id, {})
        link_length_m = float(dim.get("link_length_m") or 0)
        stop_time_sec = float(li.get("stop_time_sec") or 0)
        avg_speed_kmh = float(li.get("avg_speed_kmh") or 0)
        stop_times = calc_stop_times(stop_time_sec, float(avg_red or 0))
        queue_len = (
            calc_queue_len_est_m(float(stop_times or 0), float(avg_lane_flow or 0), link_length_m)
            if stop_times is not None and avg_lane_flow is not None
            else None
        )
        dir8_code = ent.get("dir8_code")
        rows.append(
            {
                "inter_id": inter_id,
                "link_id": link_id,
                "day_of_week": day_of_week,
                "step_index": step_index,
                "inter_name": inter_names.get(inter_id) or None,
                "link_name": dim.get("road_name"),
                "dir8_code": dir8_code,
                "dir8_label": _f_dir_8_label(dir8_code),
                "link_length_m": link_length_m or None,
                "travel_time_sec": calc_travel_time_sec(link_length_m, avg_speed_kmh),
                "delay_index": float(li["delay_index"]) if li.get("delay_index") is not None else None,
                "stop_time_sec": stop_time_sec,
                "avg_nostop_speed": float(li["avg_nostop_speed"])
                if li.get("avg_nostop_speed") is not None
                else None,
                "stop_times": stop_times,
                "avg_lane_flow": avg_lane_flow,
                "queue_len_est_m": queue_len,
                "main_turn_dirs": format_main_turn_dirs(main_turns),
                "avg_red_sec": avg_red,
                "calc_version": "inter_link_status_v1",
                "is_deleted": 0,
            }
        )
    return rows


def upsert_status_rows(
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
ON CONFLICT (inter_id, link_id, day_of_week, step_index)
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
    inter_ids: list[str] | None = None,
    weeks: int = 12,
    build_deps: bool = False,
    skip_db: bool = False,
) -> dict[str, Any]:
    from preprocessing.index_cal.dws_inter_link_turn_flow_5min_mm import run_build as run_turn_flow_build
    from preprocessing.index_cal.dws_link_index_5min_mm import run_build as run_link_index_build

    flow_schema = os.getenv("PG_FLOW_SCHEMA", "xianchang")
    road_schema = os.getenv("PGSCHEMA", "road6")

    result: dict[str, Any] = {"deps": {}}
    if build_deps and not skip_db:
        result["deps"]["link_index_5min"] = run_link_index_build(truncate=truncate, weeks=weeks)
        result["deps"]["turn_flow"] = run_turn_flow_build(
            truncate=truncate,
            inter_ids=inter_ids,
            weeks=weeks,
        )

    conn = connect_pg()
    try:
        target_q = _qualified(flow_schema, TABLE_TARGET)
        if not skip_db:
            ensure_target_table(conn, target_q=target_q, with_indexes=False)

        if skip_db:
            rows = build_status_rows_python(
                conn,
                flow_schema=flow_schema,
                road_schema=road_schema,
                inter_filter=inter_ids,
            )
            result.update(
                {
                    "target_table": f"{flow_schema}.{TABLE_TARGET}",
                    "preview_rows": len(rows),
                }
            )
            return result

        started = time.perf_counter()
        rows = build_status_rows_python(
            conn,
            flow_schema=flow_schema,
            road_schema=road_schema,
            inter_filter=inter_ids,
        )
        affected = upsert_status_rows(
            conn,
            target_schema=flow_schema,
            rows=rows,
            truncate=truncate,
        )
        if not skip_db:
            ensure_target_table(conn, target_q=target_q, with_indexes=True)
        elapsed = time.perf_counter() - started
        total = count_target_rows(conn, target_schema=flow_schema)
        result.update(
            {
                "target_table": f"{flow_schema}.{TABLE_TARGET}",
                "rows_affected": affected,
                "rows_total": total,
                "elapsed_sec": round(elapsed, 2),
                "inter_ids": inter_ids,
                "truncate": truncate,
            }
        )
        return result
    finally:
        conn.close()


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(description="生成 dws_inter_link_status_5min_mm")
    parser.add_argument("--inter-id", action="append", dest="inter_ids")
    parser.add_argument("--weeks", type=int, default=12)
    parser.add_argument("--build-deps", action="store_true", help="先构建 link_index_5min 与 turn_flow 中间表")
    parser.add_argument("--truncate", action="store_true")
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()

    stats = run_build(
        truncate=args.truncate,
        inter_ids=args.inter_ids,
        weeks=args.weeks,
        build_deps=args.build_deps,
        skip_db=args.skip_db,
    )
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
