#!/usr/bin/env python3
"""生成车道饱和车头时距标定表 dim_lane_saturation_headway。

数据来源：
  - Excel：近 7 日车道级车头时距（dwd_tfc_lane_roadcross_headway_7d_period）
  - PG road6.dim_lane_info：校验 lane_id / inter_id / lane_no
  - MySQL 日计划时段：按路口星期几展开 period 切片（无配时方案时回退 00:00-24:00）
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_TARGET = "dim_lane_saturation_headway"
TABLE_SCHEDULE_CFG = "dwd_ctl_inter_schedule_cfg"
TABLE_DAY_PLAN_PERIOD = "dwd_ctl_inter_day_plan_period"
DEFAULT_PERIOD = "00:00-24:00"

TARGET_COLUMNS = [
    "lane_id",
    "dayofweek",
    "period",
    "inter_id",
    "lane_no",
    "saturation_headway",
    "saturation_flow",
    "is_deleted",
]


def _create_table_ddl(table_name: str) -> str:
    table_ident = _quote_identifier(table_name)
    return f"""
CREATE TABLE IF NOT EXISTS {table_ident} (
    `lane_id`          VARCHAR(20)  NOT NULL  COMMENT '车道ID，路网标准编码（当前口径20位）',
    `dayofweek`        TINYINT      NOT NULL  COMMENT '星期几，1=周一，2=周二，...，7=周日',
    `period`           VARCHAR(13)  NOT NULL  COMMENT '时段区间，格式如 07:00-09:00、17:00-19:00',
    `inter_id`         VARCHAR(16)  NOT NULL  COMMENT '路口ID，用于关联查询和血缘追溯',
    `lane_no`          INT                   DEFAULT NULL COMMENT '车道号，从路中心线向外侧递增，如 1, 2, 3',
    `saturation_headway` DECIMAL(10,3) NOT NULL COMMENT '饱和车头时距（秒/辆），近N周期历史数据的第15百分位车头时距',
    `saturation_flow`    DECIMAL(10,1) NOT NULL COMMENT '饱和流率（pcu/h/车道），saturation_flow = 3600 / saturation_headway',
    `create_time`      DATETIME     NOT NULL  DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `update_time`      DATETIME     NOT NULL  DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    `is_deleted`       TINYINT      NOT NULL  DEFAULT 0 COMMENT '逻辑删除标记，0-有效，1-已删除',
    PRIMARY KEY (`lane_id`, `dayofweek`, `period`),
    INDEX `idx_inter_id` (`inter_id`),
    INDEX `idx_lane_no` (`lane_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='车道饱和车头时距标定表 — 提供车道级通行能力基准参数'
""".strip()


def ensure_target_table(conn: Any, table_name: str = TABLE_TARGET) -> None:
    with conn.cursor() as cursor:
        cursor.execute(_create_table_ddl(table_name))
    conn.commit()


def _timedelta_to_hhmm(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, timedelta):
        total = int(value.total_seconds())
        if total >= 86400:
            total = 0
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
    text = str(value).strip()
    if len(text) >= 5 and text[2] == ":":
        return text[:5]
    return None


def _period_label(start: Any, end: Any) -> str | None:
    start_hhmm = _timedelta_to_hhmm(start)
    end_hhmm = _timedelta_to_hhmm(end)
    if not start_hhmm or not end_hhmm or start_hhmm == end_hhmm:
        return None
    return f"{start_hhmm}-{end_hhmm}"


def _saturation_flow(headway: float) -> float:
    return round(3600.0 / max(headway, 0.001), 1)


def _pg_qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def load_pg_lane_map() -> dict[str, dict[str, Any]]:
    import os

    from data.pg_reader import connect_pg

    schema = os.getenv("PGSCHEMA", "road6")
    qualified = f"{_pg_qident(schema)}.{_pg_qident('dim_lane_info')}"
    conn = connect_pg()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT lane_id::text AS lane_id,
                       inter_id::text AS inter_id,
                       lane_no
                FROM {qualified}
                WHERE lane_id IS NOT NULL
                """
            )
            rows = cursor.fetchall()
    finally:
        conn.close()
    return {str(row["lane_id"]): row for row in rows}


def load_schedule_periods(conn: Any) -> tuple[dict[str, dict[int | str, int]], dict[tuple[str, int], list[str]]]:
    schedule_by_inter: dict[str, dict[int | str, int]] = defaultdict(dict)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT inter_id, week_day_no, day_plan_no
            FROM {_quote_identifier(TABLE_SCHEDULE_CFG)}
            WHERE is_deleted = 0
            """
        )
        for row in cursor.fetchall():
            inter_id = str(row.get("inter_id") or "")
            if not inter_id:
                continue
            week_day_no = row.get("week_day_no")
            day_plan_no = row.get("day_plan_no")
            if day_plan_no is None:
                continue
            if week_day_no is None:
                schedule_by_inter[inter_id]["default"] = int(day_plan_no)
            else:
                schedule_by_inter[inter_id][int(week_day_no)] = int(day_plan_no)

    periods_by_key: dict[tuple[str, int], list[str]] = defaultdict(list)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT inter_id, day_plan_no, start_time, end_time
            FROM {_quote_identifier(TABLE_DAY_PLAN_PERIOD)}
            WHERE is_deleted = 0
            ORDER BY inter_id, day_plan_no, period_seq_no
            """
        )
        for row in cursor.fetchall():
            inter_id = str(row.get("inter_id") or "")
            day_plan_no = row.get("day_plan_no")
            if not inter_id or day_plan_no is None:
                continue
            label = _period_label(row.get("start_time"), row.get("end_time"))
            if not label:
                continue
            key = (inter_id, int(day_plan_no))
            if label not in periods_by_key[key]:
                periods_by_key[key].append(label)

    return schedule_by_inter, periods_by_key


def _periods_for_inter(
    inter_id: str,
    dayofweek: int,
    schedule_by_inter: dict[str, dict[int | str, int]],
    periods_by_key: dict[tuple[str, int], list[str]],
) -> list[str]:
    schedule = schedule_by_inter.get(inter_id) or {}
    day_plan_no = schedule.get(dayofweek) or schedule.get("default")
    if day_plan_no is not None:
        periods = periods_by_key.get((inter_id, int(day_plan_no)))
        if periods:
            return list(periods)
    return [DEFAULT_PERIOD]


def read_headway_excel(path: Path) -> list[dict[str, Any]]:
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise RuntimeError("读取 Excel 需要 pandas 与 openpyxl") from exc

    df = pd.read_excel(path)
    required = {"lane_id", "dt", "inter_id", "lane_no", "time_headway"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Excel 缺少列: {sorted(missing)}")

    rows: list[dict[str, Any]] = []
    for record in df.itertuples(index=False):
        lane_id = str(record.lane_id).strip()
        dt_text = str(record.dt).strip()
        if not lane_id or not dt_text:
            continue
        dayofweek = datetime.strptime(dt_text, "%Y%m%d").isoweekday()
        headway = float(record.time_headway)
        if headway <= 0:
            continue
        rows.append(
            {
                "lane_id": lane_id,
                "dayofweek": dayofweek,
                "inter_id": str(record.inter_id).strip(),
                "lane_no": int(record.lane_no),
                "saturation_headway": round(headway, 3),
                "saturation_flow": _saturation_flow(headway),
                "is_deleted": int(getattr(record, "is_deleted", 0) or 0),
            }
        )
    return rows


def build_target_rows(
    source_rows: list[dict[str, Any]],
    pg_lane_map: dict[str, dict[str, Any]],
    schedule_by_inter: dict[str, dict[int | str, int]],
    periods_by_key: dict[tuple[str, int], list[str]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts: dict[str, int] = {
        "source_rows": len(source_rows),
        "skipped_missing_pg_lane": 0,
        "used_schedule_periods": 0,
        "used_default_period": 0,
    }
    target_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()

    for row in source_rows:
        lane_id = row["lane_id"]
        pg_lane = pg_lane_map.get(lane_id)
        if pg_lane is None:
            counts["skipped_missing_pg_lane"] += 1
            continue

        inter_id = str(pg_lane.get("inter_id") or row["inter_id"])
        lane_no = pg_lane.get("lane_no")
        if lane_no is None:
            lane_no = row.get("lane_no")

        periods = _periods_for_inter(
            inter_id,
            int(row["dayofweek"]),
            schedule_by_inter,
            periods_by_key,
        )
        if periods == [DEFAULT_PERIOD]:
            counts["used_default_period"] += 1
        else:
            counts["used_schedule_periods"] += 1

        for period in periods:
            key = (lane_id, int(row["dayofweek"]), period)
            if key in seen:
                continue
            seen.add(key)
            target_rows.append(
                {
                    "lane_id": lane_id,
                    "dayofweek": int(row["dayofweek"]),
                    "period": period,
                    "inter_id": inter_id,
                    "lane_no": int(lane_no) if lane_no is not None else None,
                    "saturation_headway": row["saturation_headway"],
                    "saturation_flow": row["saturation_flow"],
                    "is_deleted": row.get("is_deleted", 0),
                }
            )

    counts["target_rows"] = len(target_rows)
    return target_rows, counts


def _build_upsert_sql(table_name: str) -> str:
    quoted_columns = ", ".join(_quote_identifier(col) for col in TARGET_COLUMNS)
    placeholders = ", ".join(["%s"] * len(TARGET_COLUMNS))
    update_columns = [
        col
        for col in TARGET_COLUMNS
        if col not in {"lane_id", "dayofweek", "period"}
    ]
    update_clause = ", ".join(
        f"{_quote_identifier(col)}=VALUES({_quote_identifier(col)})" for col in update_columns
    )
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
    with conn.cursor() as cursor:
        cursor.executemany(sql, values)
    conn.commit()
    return len(rows)


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass

    parser = argparse.ArgumentParser(description="生成车道饱和车头时距标定表")
    parser.add_argument(
        "--input-xlsx",
        type=Path,
        default=Path("data/dwd_tfc_lane_roadcross_headway_7d_period_20260614.xlsx"),
        help="车道车头时距 Excel 路径",
    )
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument("--skip-db", action="store_true", help="仅统计，不写入 MySQL")
    args = parser.parse_args()

    source_rows = read_headway_excel(args.input_xlsx)
    pg_lane_map = load_pg_lane_map()

    conn = _get_mysql_connection(streaming=False)
    try:
        schedule_by_inter, periods_by_key = load_schedule_periods(conn)
        target_rows, counts = build_target_rows(
            source_rows,
            pg_lane_map,
            schedule_by_inter,
            periods_by_key,
        )
        if not args.skip_db:
            counts["upsert_rows"] = upsert_rows(conn, target_rows, target_table=args.target_table)
        for key in sorted(counts):
            print(f"{key}: {counts[key]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
