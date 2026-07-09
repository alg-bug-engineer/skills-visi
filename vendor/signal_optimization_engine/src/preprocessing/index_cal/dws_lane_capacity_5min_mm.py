#!/usr/bin/env python3
"""生成车道实际通行能力聚合表 dws_lane_capacity_5min_mm。

数据来源：
  - PG road6.dim_lane_info：lane_id / inter_id / link_id / lane_no / turn_move
  - MySQL dim_lane_saturation_headway：车道饱和流率（缺省 1400 pcu/h/车道）
  - MySQL dws_ctl_inter_turn_5min_his_mm：历史平均绿灯与周期

计算口径（与信号配时优化一致）：
  lane_capacity = saturation_flow × max(green_exec_sec − 2, 0) / cycle_len_sec
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from typing import Any

from data.pg_reader import GB_TURNS, TURN_TO_TURN_DIR_NO
from preprocessing.index_cal.dim_lane_saturation_headway import (
    DEFAULT_PERIOD,
    _periods_for_inter,
    load_schedule_periods,
)
from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_SATURATION = "dim_lane_saturation_headway"
TABLE_TURN_5MIN = "dws_ctl_inter_turn_5min_his_mm"
TABLE_TARGET = "dws_lane_capacity_5min_mm"

DEFAULT_SATURATION_FLOW = 1400.0
LOSS_TIME_SEC = 2

TARGET_COLUMNS = [
    "lane_id",
    "day_of_week",
    "step_index",
    "inter_id",
    "inter_name",
    "link_id",
    "lane_no",
    "turn_dir_no",
    "lane_capacity",
    "is_deleted",
]

_HHMM_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")


def _create_table_ddl(table_name: str) -> str:
    table_ident = _quote_identifier(table_name)
    return f"""
CREATE TABLE IF NOT EXISTS {table_ident} (
    `lane_id`           VARCHAR(20)  NOT NULL COMMENT '车道ID，路网标准编码（当前口径20位）',
    `day_of_week`       TINYINT      NOT NULL COMMENT '星期几：1-周一，2-周二，3-周三，4-周四，5-周五，6-周六，7-周日',
    `step_index`        SMALLINT     NOT NULL COMMENT '5分钟时间片序号，取值0~287，对应全天288个5分钟窗口',
    `inter_id`          VARCHAR(16)  NOT NULL COMMENT '路口ID，16位标准编码，用于按路口维度查询',
    `inter_name`        VARCHAR(128) DEFAULT NULL COMMENT '路口名称，便于直观识别',
    `link_id`           VARCHAR(32)  DEFAULT NULL COMMENT '进口道路段ID，可关联路段维表获取更多信息',
    `lane_no`           INT          DEFAULT NULL COMMENT '车道号，从路中心线向外侧递增，如 1, 2, 3',
    `turn_dir_no`       TINYINT      DEFAULT NULL COMMENT '转向类型：1-左转（含调头），2-直行，3-右转',
    `lane_capacity`     DECIMAL(10,1) NOT NULL COMMENT '车道实际通行能力（pcu/h/车道），基于饱和流率与历史配时计算',
    `create_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `update_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    `is_deleted`        TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除标记：0-有效，1-已删除',
    PRIMARY KEY (`lane_id`, `day_of_week`, `step_index`),
    INDEX `idx_inter_id` (`inter_id`) COMMENT '按路口维度查询加速，获取路口下所有车道的通行能力',
    INDEX `idx_inter_id_day_step` (`inter_id`, `day_of_week`, `step_index`) COMMENT '按路口+星期+时间片联合查询加速，与 dws_ctl_inter_turn_5min_his_mm 对齐',
    INDEX `idx_link_id` (`link_id`) COMMENT '按进口道路段查询加速',
    INDEX `idx_day_of_week` (`day_of_week`) COMMENT '按星期几筛选加速，如过滤工作日（1-5）或周末（6,7）'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='车道实际通行能力聚合表 - 按车道+星期几+5分钟时间片存储实际通行能力'
""".strip()


def ensure_target_table(conn: Any, table_name: str = TABLE_TARGET) -> None:
    with conn.cursor() as cursor:
        cursor.execute(_create_table_ddl(table_name))
        cursor.execute(f"SHOW TABLES LIKE %s", (table_name,))
        if cursor.fetchone():
            cursor.execute(f"SHOW COLUMNS FROM {_quote_identifier(table_name)} LIKE 'lane_id'")
            row = cursor.fetchone()
            if row and "varchar(16)" in str(row.get("Type") or row[1]).lower():
                cursor.execute(
                    f"ALTER TABLE {_quote_identifier(table_name)} "
                    "MODIFY COLUMN `lane_id` VARCHAR(20) NOT NULL "
                    "COMMENT '车道ID，路网标准编码（当前口径20位）'"
                )
    conn.commit()


def _pg_qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _to_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def _hhmm_to_minutes(value: str) -> int | None:
    match = _HHMM_PATTERN.match(str(value or "").strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 24 or minute > 59 or (hour == 24 and minute > 0):
        return None
    return hour * 60 + minute


def _step_in_period(step_index: int, period: str) -> bool:
    if period == DEFAULT_PERIOD:
        return True
    if "-" not in period:
        return False
    start_text, end_text = period.split("-", 1)
    start_min = _hhmm_to_minutes(start_text)
    end_min = _hhmm_to_minutes(end_text)
    if start_min is None or end_min is None:
        return False
    step_start = step_index * 5
    step_end = step_start + 5
    if end_min <= start_min:
        return step_start >= start_min or step_end <= end_min
    return step_start >= start_min and step_end <= end_min


def _period_for_step(step_index: int, periods: list[str]) -> str:
    for period in periods:
        if _step_in_period(step_index, period):
            return period
    return DEFAULT_PERIOD


def supported_turn_dir_nos(turn_move: Any) -> list[int]:
    code = str(_to_int(turn_move, default=None) if turn_move is not None else "")
    if not code or code == "None":
        code = str(turn_move or "").strip()
    turns = GB_TURNS.get(code, ())
    values = sorted({TURN_TO_TURN_DIR_NO[turn] for turn in turns if turn in TURN_TO_TURN_DIR_NO})
    return values


def primary_turn_dir_no(turn_move: Any) -> int | None:
    values = supported_turn_dir_nos(turn_move)
    return values[0] if values else None


def _lane_capacity(saturation_flow: float, green_exec_sec: int, cycle_len_sec: int) -> float:
    if cycle_len_sec <= 0:
        return 0.0
    effective_green = max(int(green_exec_sec) - LOSS_TIME_SEC, 0)
    return round(saturation_flow * effective_green / cycle_len_sec, 1)


def load_pg_lane_rows(inter_ids: set[str]) -> list[dict[str, Any]]:
    import os

    from data.pg_reader import connect_pg

    if not inter_ids:
        return []

    schema = os.getenv("PGSCHEMA", "road6")
    qualified = f"{_pg_qident(schema)}.{_pg_qident('dim_lane_info')}"
    conn = connect_pg()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT lane_id::text AS lane_id,
                       inter_id::text AS inter_id,
                       link_id::text AS link_id,
                       lane_no,
                       turn_move::text AS turn_move
                FROM {qualified}
                WHERE inter_id::text = ANY(%s)
                  AND lane_id IS NOT NULL
                  AND link_id IS NOT NULL
                """,
                (sorted(inter_ids),),
            )
            rows = list(cursor.fetchall())
    finally:
        conn.close()

    lanes: list[dict[str, Any]] = []
    for row in rows:
        lane_id = str(row.get("lane_id") or "").strip()
        inter_id = str(row.get("inter_id") or "").strip()
        link_id = str(row.get("link_id") or "").strip()
        if not lane_id or not inter_id or not link_id:
            continue
        turn_dir_nos = supported_turn_dir_nos(row.get("turn_move"))
        if not turn_dir_nos:
            continue
        lanes.append(
            {
                "lane_id": lane_id,
                "inter_id": inter_id,
                "link_id": link_id,
                "lane_no": _to_int(row.get("lane_no")),
                "turn_move": str(row.get("turn_move") or ""),
                "turn_dir_nos": turn_dir_nos,
                "turn_dir_no": primary_turn_dir_no(row.get("turn_move")),
            }
        )
    return lanes


def load_inter_name_map(inter_ids: set[str]) -> dict[str, str]:
    import os

    from data.pg_reader import connect_pg

    if not inter_ids:
        return {}

    schema = os.getenv("PGSCHEMA", "road6")
    qualified = f"{_pg_qident(schema)}.{_pg_qident('dim_inter_info')}"
    conn = connect_pg()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT inter_id::text AS inter_id, inter_name
                FROM {qualified}
                WHERE inter_id::text = ANY(%s)
                """,
                (sorted(inter_ids),),
            )
            rows = cursor.fetchall()
    finally:
        conn.close()
    return {
        str(row.get("inter_id") or ""): str(row.get("inter_name") or "").strip() or None
        for row in rows
        if row.get("inter_id")
    }


def load_saturation_index(
    conn: Any,
    table_name: str = TABLE_SATURATION,
) -> tuple[dict[tuple[str, int, str], float], dict[tuple[str, int], float]]:
    table_ident = _quote_identifier(table_name)
    index: dict[tuple[str, int, str], float] = {}
    fallback: dict[tuple[str, int], float] = {}
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT lane_id, dayofweek, period, saturation_flow
            FROM {table_ident}
            WHERE COALESCE(is_deleted, 0) = 0
            """
        )
        for row in cursor.fetchall():
            lane_id = str(row.get("lane_id") or "").strip()
            dayofweek = _to_int(row.get("dayofweek"))
            period = str(row.get("period") or "").strip()
            flow = float(row.get("saturation_flow") or 0)
            if not lane_id or dayofweek is None or not period or flow <= 0:
                continue
            index[(lane_id, dayofweek, period)] = flow
            fallback[(lane_id, dayofweek)] = flow
    return index, fallback


def lookup_saturation_flow(
    saturation_index: dict[tuple[str, int, str], float],
    fallback_index: dict[tuple[str, int], float],
    *,
    lane_id: str,
    day_of_week: int,
    period: str,
) -> tuple[float, bool]:
    exact = saturation_index.get((lane_id, day_of_week, period))
    if exact is not None:
        return float(exact), False
    default_period = saturation_index.get((lane_id, day_of_week, DEFAULT_PERIOD))
    if default_period is not None:
        return float(default_period), False
    day_fallback = fallback_index.get((lane_id, day_of_week))
    if day_fallback is not None:
        return float(day_fallback), False
    return DEFAULT_SATURATION_FLOW, True


def load_timing_rows(conn: Any, table_name: str = TABLE_TURN_5MIN) -> list[dict[str, Any]]:
    table_ident = _quote_identifier(table_name)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT inter_id, inter_name, link_id, turn_dir_no,
                   day_of_week, step_index, cycle_len_sec, green_exec_sec
            FROM {table_ident}
            WHERE COALESCE(is_deleted, 0) = 0
              AND cycle_len_sec > 0
            """
        )
        return list(cursor.fetchall())


def build_target_rows(
    conn: Any,
    *,
    saturation_table: str = TABLE_SATURATION,
    timing_table: str = TABLE_TURN_5MIN,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    timing_rows = load_timing_rows(conn, timing_table)
    inter_ids = {str(row.get("inter_id") or "") for row in timing_rows if row.get("inter_id")}
    inter_ids.discard("")

    lanes = load_pg_lane_rows(inter_ids)
    inter_name_map = load_inter_name_map(inter_ids)
    saturation_index, saturation_fallback = load_saturation_index(conn, saturation_table)
    schedule_by_inter, periods_by_key = load_schedule_periods(conn)

    lanes_by_movement: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for lane in lanes:
        for turn_dir_no in lane["turn_dir_nos"]:
            lanes_by_movement[(lane["inter_id"], lane["link_id"], turn_dir_no)].append(lane)

    partial: dict[tuple[str, int, int], dict[str, Any]] = {}
    counts: dict[str, int] = {
        "timing_rows": len(timing_rows),
        "pg_lanes": len(lanes),
        "timing_without_lane": 0,
        "used_default_saturation_flow": 0,
    }

    for timing in timing_rows:
        inter_id = str(timing.get("inter_id") or "")
        link_id = str(timing.get("link_id") or "")
        turn_dir_no = _to_int(timing.get("turn_dir_no"))
        day_of_week = _to_int(timing.get("day_of_week"))
        step_index = _to_int(timing.get("step_index"))
        cycle_len_sec = _to_int(timing.get("cycle_len_sec"), default=0) or 0
        green_exec_sec = _to_int(timing.get("green_exec_sec"), default=0) or 0
        if (
            not inter_id
            or not link_id
            or turn_dir_no not in {1, 2, 3}
            or day_of_week not in range(1, 8)
            or step_index not in range(0, 288)
            or cycle_len_sec <= 0
        ):
            continue

        matched_lanes = lanes_by_movement.get((inter_id, link_id, turn_dir_no), [])
        if not matched_lanes:
            counts["timing_without_lane"] += 1
            continue

        inter_name = str(timing.get("inter_name") or "").strip() or inter_name_map.get(inter_id)
        periods = _periods_for_inter(inter_id, day_of_week, schedule_by_inter, periods_by_key)
        period = _period_for_step(step_index, periods)

        for lane in matched_lanes:
            key = (lane["lane_id"], day_of_week, step_index)
            current = partial.get(key)
            if current is None or green_exec_sec > current["_green_exec_sec"]:
                saturation_flow, used_default = lookup_saturation_flow(
                    saturation_index,
                    saturation_fallback,
                    lane_id=lane["lane_id"],
                    day_of_week=day_of_week,
                    period=period,
                )
                if used_default:
                    counts["used_default_saturation_flow"] += 1
                partial[key] = {
                    "lane_id": lane["lane_id"],
                    "day_of_week": day_of_week,
                    "step_index": step_index,
                    "inter_id": inter_id,
                    "inter_name": inter_name,
                    "link_id": link_id,
                    "lane_no": lane["lane_no"],
                    "turn_dir_no": lane["turn_dir_no"],
                    "_green_exec_sec": green_exec_sec,
                    "_cycle_len_sec": cycle_len_sec,
                    "_saturation_flow": saturation_flow,
                }

    target_rows: list[dict[str, Any]] = []
    for item in partial.values():
        target_rows.append(
            {
                "lane_id": item["lane_id"],
                "day_of_week": item["day_of_week"],
                "step_index": item["step_index"],
                "inter_id": item["inter_id"],
                "inter_name": item["inter_name"],
                "link_id": item["link_id"],
                "lane_no": item["lane_no"],
                "turn_dir_no": item["turn_dir_no"],
                "lane_capacity": _lane_capacity(
                    item["_saturation_flow"],
                    item["_green_exec_sec"],
                    item["_cycle_len_sec"],
                ),
                "is_deleted": 0,
            }
        )

    target_rows.sort(
        key=lambda row: (
            row["lane_id"],
            row["day_of_week"],
            row["step_index"],
        )
    )
    counts["target_rows"] = len(target_rows)
    return target_rows, counts


def _build_upsert_sql(table_name: str) -> str:
    quoted_columns = ", ".join(_quote_identifier(col) for col in TARGET_COLUMNS)
    placeholders = ", ".join(["%s"] * len(TARGET_COLUMNS))
    update_columns = [
        col
        for col in TARGET_COLUMNS
        if col not in {"lane_id", "day_of_week", "step_index"}
    ]
    update_clause = ", ".join(
        f"{_quote_identifier(col)}=VALUES({_quote_identifier(col)})" for col in update_columns
    )
    update_clause += ", `update_time`=CURRENT_TIMESTAMP"
    table_ident = _quote_identifier(table_name)
    return (
        f"INSERT INTO {table_ident} ({quoted_columns}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )


def upsert_rows(conn: Any, rows: list[dict[str, Any]], *, target_table: str = TABLE_TARGET) -> int:
    if not rows:
        return 0
    ensure_target_table(conn, target_table)
    sql = _build_upsert_sql(target_table)
    values = [tuple(row.get(col) for col in TARGET_COLUMNS) for row in rows]
    batch_size = 2000
    with conn.cursor() as cursor:
        for offset in range(0, len(values), batch_size):
            cursor.executemany(sql, values[offset : offset + batch_size])
    conn.commit()
    return len(rows)


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass

    parser = argparse.ArgumentParser(description="生成车道实际通行能力聚合表")
    parser.add_argument("--saturation-table", default=TABLE_SATURATION)
    parser.add_argument("--timing-table", default=TABLE_TURN_5MIN)
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument("--skip-db", action="store_true", help="仅统计，不写入 MySQL")
    args = parser.parse_args()

    conn = _get_mysql_connection(streaming=False)
    try:
        target_rows, counts = build_target_rows(
            conn,
            saturation_table=args.saturation_table,
            timing_table=args.timing_table,
        )
        if not args.skip_db:
            counts["upsert_rows"] = upsert_rows(
                conn,
                target_rows,
                target_table=args.target_table,
            )
        for key in sorted(counts):
            print(f"{key}: {counts[key]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
