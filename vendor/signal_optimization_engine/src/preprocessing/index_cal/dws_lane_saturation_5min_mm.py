#!/usr/bin/env python3
"""生成车道饱和度聚合表 dws_lane_saturation_5min_mm。

数据来源：
  - PostgreSQL xianchang.dwd_tfc_lane_roadcross_flow_5mi：车道 5 分钟流量
  - MySQL dws_lane_capacity_5min_mm：车道实际通行能力

计算口径：
  lane_flow = vehicle_count × 12（5 分钟过车数换算 pcu/h）
  lane_saturation = lane_flow / lane_capacity

更新策略：
  对过去 N 周相同 (lane_id, day_of_week, step_index) 的历史流量取均值，
  与通行能力表按主键关联后覆盖写入。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import Any

from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_CAPACITY = "dws_lane_capacity_5min_mm"
TABLE_TARGET = "dws_lane_saturation_5min_mm"

FIVE_MIN_FLOW_SCALE = 12.0

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
    "lane_flow",
    "lane_saturation",
    "is_deleted",
]


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
    `lane_capacity`     DECIMAL(10,1) NOT NULL COMMENT '车道实际通行能力（pcu/h/车道），关联 dws_lane_capacity_5min_mm 获取',
    `lane_flow`         DECIMAL(10,1) NOT NULL COMMENT '车道实际流量（pcu/h），5分钟窗口标准化小时流量',
    `lane_saturation`   DECIMAL(10,4) NOT NULL COMMENT '车道饱和度，saturation = lane_flow / lane_capacity，无量纲',
    `create_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `update_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    `is_deleted`        TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除标记：0-有效，1-已删除',
    PRIMARY KEY (`lane_id`, `day_of_week`, `step_index`),
    INDEX `idx_inter_id` (`inter_id`) COMMENT '按路口维度查询加速，获取路口下所有车道的饱和度',
    INDEX `idx_inter_id_day_step` (`inter_id`, `day_of_week`, `step_index`) COMMENT '按路口+星期+时间片联合查询加速',
    INDEX `idx_link_id` (`link_id`) COMMENT '按进口道路段查询加速',
    INDEX `idx_day_of_week` (`day_of_week`) COMMENT '按星期几筛选加速，如过滤工作日（1-5）或周末（6,7）',
    INDEX `idx_saturation_high` (`lane_saturation`) COMMENT '按饱和度值查询加速，便于筛选过饱和车道'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='车道饱和度聚合表 - 按车道+星期几+5分钟时间片存储车道实际通行能力、流量和饱和度'
""".strip()


def ensure_target_table(conn: Any, table_name: str = TABLE_TARGET) -> None:
    with conn.cursor() as cursor:
        cursor.execute(_create_table_ddl(table_name))
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
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


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _qualified_flow_table() -> str:
    import os

    from data.pg_reader import _qident

    schema = os.getenv("PG_FLOW_SCHEMA", "xianchang")
    table = os.getenv("PG_FLOW_TABLE", "dwd_tfc_lane_roadcross_flow_5mi")
    return _qident(schema) + "." + _qident(table)


def _parse_dt(value: str) -> datetime:
    return datetime.strptime(str(value).strip(), "%Y%m%d")


def resolve_flow_date_range(
    pg_conn: Any,
    *,
    weeks: int,
    start_dt: str | None,
    end_dt: str | None,
) -> tuple[str, str]:
    qualified_flow = _qualified_flow_table()
    with pg_conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT min(dt) AS min_dt, max(dt) AS max_dt
            FROM {qualified_flow}
            WHERE is_deleted = 0
              AND lane_id IS NOT NULL
              AND btrim(lane_id::text) <> ''
            """
        )
        bounds = cursor.fetchone() or {}
    min_dt = str(bounds.get("min_dt") or "").strip()
    max_dt = str(bounds.get("max_dt") or "").strip()
    if not max_dt:
        raise ValueError("流量表无可用 lane_id 记录，无法确定日期范围")

    resolved_end = end_dt or max_dt
    if start_dt:
        resolved_start = start_dt
    else:
        end_date = _parse_dt(resolved_end)
        lookback_start = end_date - timedelta(weeks=max(weeks, 1))
        resolved_start = lookback_start.strftime("%Y%m%d")
        if min_dt and resolved_start < min_dt:
            resolved_start = min_dt
    if resolved_start > resolved_end:
        raise ValueError(f"流量日期范围无效: {resolved_start} > {resolved_end}")
    return resolved_start, resolved_end


def load_capacity_index(
    conn: Any,
    *,
    capacity_table: str = TABLE_CAPACITY,
    inter_ids: set[str] | None = None,
) -> dict[tuple[str, int, int], dict[str, Any]]:
    table_ident = _quote_identifier(capacity_table)
    sql = f"""
        SELECT lane_id, day_of_week, step_index, inter_id, inter_name,
               link_id, lane_no, turn_dir_no, lane_capacity
        FROM {table_ident}
        WHERE COALESCE(is_deleted, 0) = 0
          AND lane_capacity > 0
    """
    params: list[Any] = []
    if inter_ids:
        placeholders = ", ".join(["%s"] * len(inter_ids))
        sql += f" AND inter_id IN ({placeholders})"
        params.extend(sorted(inter_ids))

    index: dict[tuple[str, int, int], dict[str, Any]] = {}
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            lane_id = str(row.get("lane_id") or "").strip()
            day_of_week = _to_int(row.get("day_of_week"))
            step_index = _to_int(row.get("step_index"))
            lane_capacity = _to_float(row.get("lane_capacity"))
            if (
                not lane_id
                or day_of_week not in range(1, 8)
                or step_index not in range(0, 288)
                or lane_capacity <= 0
            ):
                continue
            key = (lane_id, day_of_week, step_index)
            index[key] = {
                "lane_id": lane_id,
                "day_of_week": day_of_week,
                "step_index": step_index,
                "inter_id": str(row.get("inter_id") or ""),
                "inter_name": str(row.get("inter_name") or "").strip() or None,
                "link_id": str(row.get("link_id") or "").strip() or None,
                "lane_no": _to_int(row.get("lane_no")),
                "turn_dir_no": _to_int(row.get("turn_dir_no")),
                "lane_capacity": round(lane_capacity, 1),
            }
    return index


def _lane_saturation(lane_flow: float, lane_capacity: float) -> float:
    if lane_capacity <= 0:
        return 0.0
    return round(lane_flow / lane_capacity, 4)


def _build_target_row(capacity_row: dict[str, Any], lane_flow: float) -> dict[str, Any]:
    lane_capacity = float(capacity_row["lane_capacity"])
    lane_flow_value = round(lane_flow, 1)
    return {
        "lane_id": capacity_row["lane_id"],
        "day_of_week": capacity_row["day_of_week"],
        "step_index": capacity_row["step_index"],
        "inter_id": capacity_row["inter_id"],
        "inter_name": capacity_row["inter_name"],
        "link_id": capacity_row["link_id"],
        "lane_no": capacity_row["lane_no"],
        "turn_dir_no": capacity_row["turn_dir_no"],
        "lane_capacity": lane_capacity,
        "lane_flow": lane_flow_value,
        "lane_saturation": _lane_saturation(lane_flow_value, lane_capacity),
        "is_deleted": 0,
    }


def iter_target_rows(
    mysql_conn: Any,
    pg_conn: Any,
    *,
    capacity_table: str = TABLE_CAPACITY,
    weeks: int = 12,
    start_dt: str | None = None,
    end_dt: str | None = None,
    inter_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    resolved_start, resolved_end = resolve_flow_date_range(
        pg_conn,
        weeks=weeks,
        start_dt=start_dt,
        end_dt=end_dt,
    )
    capacity_index = load_capacity_index(
        mysql_conn,
        capacity_table=capacity_table,
        inter_ids=inter_ids,
    )
    if not capacity_index:
        return [], {
            "flow_start_dt": resolved_start,
            "flow_end_dt": resolved_end,
            "capacity_rows": 0,
            "flow_agg_rows": 0,
            "matched_rows": 0,
            "target_rows": 0,
        }

    qualified_flow = _qualified_flow_table()
    inter_filter = ""
    params: list[Any] = [resolved_start, resolved_end]
    if inter_ids:
        placeholders = ", ".join(["%s"] * len(inter_ids))
        inter_filter = f" AND f.inter_id::text IN ({placeholders})"
        params.extend(sorted(inter_ids))

    sql = f"""
        SELECT f.lane_id::text AS lane_id,
               EXTRACT(ISODOW FROM to_date(f.dt, 'YYYYMMDD'))::int AS day_of_week,
               f.step_index::int AS step_index,
               AVG(f.vehicle_count::float * {FIVE_MIN_FLOW_SCALE}) AS lane_flow,
               COUNT(*)::int AS sample_count
        FROM {qualified_flow} f
        WHERE f.is_deleted = 0
          AND f.lane_id IS NOT NULL
          AND btrim(f.lane_id::text) <> ''
          AND f.dt >= %s
          AND f.dt <= %s
          AND f.step_index BETWEEN 0 AND 287
          {inter_filter}
        GROUP BY f.lane_id, day_of_week, f.step_index
    """.strip()

    target_rows: list[dict[str, Any]] = []
    flow_agg_rows = 0
    matched_rows = 0
    with pg_conn.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            flow_agg_rows += 1
            lane_id = str(row.get("lane_id") or "").strip()
            day_of_week = _to_int(row.get("day_of_week"))
            step_index = _to_int(row.get("step_index"))
            if (
                not lane_id
                or day_of_week not in range(1, 8)
                or step_index not in range(0, 288)
            ):
                continue
            capacity_row = capacity_index.get((lane_id, day_of_week, step_index))
            if capacity_row is None:
                continue
            lane_flow = _to_float(row.get("lane_flow"))
            if lane_flow < 0:
                continue
            matched_rows += 1
            target_rows.append(_build_target_row(capacity_row, lane_flow))

    target_rows.sort(
        key=lambda item: (
            item["lane_id"],
            item["day_of_week"],
            item["step_index"],
        )
    )
    counts = {
        "flow_start_dt": resolved_start,
        "flow_end_dt": resolved_end,
        "capacity_rows": len(capacity_index),
        "flow_agg_rows": flow_agg_rows,
        "matched_rows": matched_rows,
        "target_rows": len(target_rows),
    }
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


def upsert_rows(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    target_table: str = TABLE_TARGET,
    batch_size: int = 2000,
) -> int:
    if not rows:
        return 0
    ensure_target_table(conn, target_table)
    sql = _build_upsert_sql(target_table)
    values = [tuple(row.get(col) for col in TARGET_COLUMNS) for row in rows]
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

    parser = argparse.ArgumentParser(description="生成车道饱和度聚合表")
    parser.add_argument("--capacity-table", default=TABLE_CAPACITY)
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument("--weeks", type=int, default=12, help="默认聚合最近 N 周流量")
    parser.add_argument("--start-dt", help="流量起始日期 YYYYMMDD")
    parser.add_argument("--end-dt", help="流量结束日期 YYYYMMDD")
    parser.add_argument(
        "--inter-ids",
        help="仅处理指定路口（逗号分隔 inter_id）",
    )
    parser.add_argument("--skip-db", action="store_true", help="仅统计，不写入 MySQL")
    args = parser.parse_args()

    inter_ids: set[str] | None = None
    if args.inter_ids:
        inter_ids = {item.strip() for item in args.inter_ids.split(",") if item.strip()}

    from data.pg_reader import connect_pg

    mysql_conn = _get_mysql_connection(streaming=False)
    pg_conn = connect_pg()
    try:
        if not args.skip_db:
            ensure_target_table(mysql_conn, args.target_table)
        target_rows, counts = iter_target_rows(
            mysql_conn,
            pg_conn,
            capacity_table=args.capacity_table,
            weeks=args.weeks,
            start_dt=args.start_dt,
            end_dt=args.end_dt,
            inter_ids=inter_ids,
        )
        if not args.skip_db:
            counts["upsert_rows"] = upsert_rows(
                mysql_conn,
                target_rows,
                target_table=args.target_table,
            )
        for key in sorted(counts):
            print(f"{key}: {counts[key]}")
    finally:
        pg_conn.close()
        mysql_conn.close()


if __name__ == "__main__":
    main()
