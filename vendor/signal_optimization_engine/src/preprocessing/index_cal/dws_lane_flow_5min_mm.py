#!/usr/bin/env python3
"""生成车道历史流量聚合表 dws_lane_flow_5min_mm。

数据来源：
  - PostgreSQL xianchang.dwd_tfc_lane_roadcross_flow_5mi：车道 5 分钟流量
  - PostgreSQL road6.dwd_tfc_rltn_wide_inter_ft_link：进口 dir8_code

聚合粒度：
  (lane_id, day_of_week, step_index)

口径：
  avg_vehicle_count_5min = 过去 N 周相同星期几、相同 5 分钟槽位的过车数均值
  lane_flow = avg_vehicle_count_5min × 12（换算 pcu/h）
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import Any

from data.pg_reader import connect_pg
from preprocessing.timing.dir8_encoding import normalize_dir8_no
from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_TARGET = "dws_lane_flow_5min_mm"
FIVE_MIN_FLOW_SCALE = 12.0

TARGET_COLUMNS = [
    "lane_id",
    "day_of_week",
    "step_index",
    "inter_id",
    "inter_name",
    "link_id",
    "lane_no",
    "dir8_code",
    "turn_move",
    "avg_vehicle_count_5min",
    "lane_flow",
    "sample_count",
    "flow_date_start",
    "flow_date_end",
    "aggregation_method",
    "is_deleted",
]


def _create_table_ddl(table_name: str) -> str:
    table_ident = _quote_identifier(table_name)
    return f"""
CREATE TABLE IF NOT EXISTS {table_ident} (
    `lane_id`                   VARCHAR(20)  NOT NULL COMMENT '车道ID，路网标准编码（当前口径20位）',
    `day_of_week`               TINYINT      NOT NULL COMMENT '星期几：1-周一 … 7-周日',
    `step_index`                SMALLINT     NOT NULL COMMENT '5分钟时间片序号 0~287',
    `inter_id`                  VARCHAR(16)  NOT NULL COMMENT '路口ID',
    `inter_name`                VARCHAR(128) DEFAULT NULL COMMENT '路口名称',
    `link_id`                   VARCHAR(32)  DEFAULT NULL COMMENT '进口 link_id',
    `lane_no`                   INT          DEFAULT NULL COMMENT '车道号',
    `dir8_code`                 TINYINT      DEFAULT NULL COMMENT '进口 8 方向编码（0 基，北=0）',
    `turn_move`                 TINYINT      DEFAULT NULL COMMENT '国标转向码 turn_move',
    `avg_vehicle_count_5min`    DECIMAL(10,4) NOT NULL COMMENT '历史 5 分钟过车数均值',
    `lane_flow`                 DECIMAL(10,1) NOT NULL COMMENT '历史小时流量 pcu/h（均值×12）',
    `sample_count`              INT          NOT NULL DEFAULT 0 COMMENT '参与均值计算的样本天数',
    `flow_date_start`           VARCHAR(8)   DEFAULT NULL COMMENT '聚合样本起始日期 YYYYMMDD',
    `flow_date_end`             VARCHAR(8)   DEFAULT NULL COMMENT '聚合样本结束日期 YYYYMMDD',
    `aggregation_method`        VARCHAR(64)  NOT NULL DEFAULT 'historical_mean_5min' COMMENT '聚合方法',
    `create_time`               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `is_deleted`                TINYINT      NOT NULL DEFAULT 0,
    PRIMARY KEY (`lane_id`, `day_of_week`, `step_index`),
    INDEX `idx_inter_id` (`inter_id`),
    INDEX `idx_inter_id_day_step` (`inter_id`, `day_of_week`, `step_index`),
    INDEX `idx_day_of_week` (`day_of_week`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='车道历史流量聚合表：按车道+星期几+5分钟时间片存储历史均值流量'
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


def _qualified_channel_table() -> str:
    import os

    from data.pg_reader import _qident

    schema = os.getenv("PGSCHEMA", "road6")
    table = os.getenv("PG_CHANNEL_TABLE", "dwd_tfc_rltn_wide_inter_ft_link")
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


def iter_target_rows(
    pg_conn: Any,
    *,
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

    qualified_flow = _qualified_flow_table()
    qualified_channel = _qualified_channel_table()
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
               MIN(f.inter_id::text) AS inter_id,
               MIN(f.inter_name) AS inter_name,
               MIN(f.link_id::text) AS link_id,
               MIN(f.lane_no::int) AS lane_no,
               MIN(f.turn_move::int) AS turn_move,
               MAX(w.dir8_code::int) AS dir8_code,
               AVG(f.vehicle_count::float) AS avg_vehicle_count_5min,
               COUNT(*)::int AS sample_count
        FROM {qualified_flow} f
        LEFT JOIN {qualified_channel} w
          ON w.inter_id::text = f.inter_id::text
         AND w.link_id::text = f.link_id::text
         AND lower(btrim(w.link_role::text)) = 'entrance'
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
    with pg_conn.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            flow_agg_rows += 1
            lane_id = str(row.get("lane_id") or "").strip()
            day_of_week = _to_int(row.get("day_of_week"))
            step_index = _to_int(row.get("step_index"))
            avg_count = _to_float(row.get("avg_vehicle_count_5min"))
            if (
                not lane_id
                or day_of_week not in range(1, 8)
                or step_index not in range(0, 288)
                or avg_count < 0
            ):
                continue
            dir8_code = normalize_dir8_no(row.get("dir8_code"))
            target_rows.append(
                {
                    "lane_id": lane_id,
                    "day_of_week": day_of_week,
                    "step_index": step_index,
                    "inter_id": str(row.get("inter_id") or "").strip(),
                    "inter_name": str(row.get("inter_name") or "").strip() or None,
                    "link_id": str(row.get("link_id") or "").strip() or None,
                    "lane_no": _to_int(row.get("lane_no")),
                    "dir8_code": dir8_code,
                    "turn_move": _to_int(row.get("turn_move")),
                    "avg_vehicle_count_5min": round(avg_count, 4),
                    "lane_flow": round(avg_count * FIVE_MIN_FLOW_SCALE, 1),
                    "sample_count": _to_int(row.get("sample_count")) or 0,
                    "flow_date_start": resolved_start,
                    "flow_date_end": resolved_end,
                    "aggregation_method": "historical_mean_5min",
                    "is_deleted": 0,
                }
            )

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
        "flow_agg_rows": flow_agg_rows,
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

    parser = argparse.ArgumentParser(description="生成车道历史流量聚合表 dws_lane_flow_5min_mm")
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument("--weeks", type=int, default=12, help="默认聚合最近 N 周流量")
    parser.add_argument("--start-dt", help="流量起始日期 YYYYMMDD")
    parser.add_argument("--end-dt", help="流量结束日期 YYYYMMDD")
    parser.add_argument("--inter-ids", help="仅处理指定路口（逗号分隔 inter_id）")
    parser.add_argument("--skip-db", action="store_true", help="仅统计，不写入 MySQL")
    args = parser.parse_args()

    inter_ids: set[str] | None = None
    if args.inter_ids:
        inter_ids = {item.strip() for item in args.inter_ids.split(",") if item.strip()}

    mysql_conn = _get_mysql_connection(streaming=False)
    pg_conn = connect_pg()
    try:
        if not args.skip_db:
            ensure_target_table(mysql_conn, args.target_table)
        target_rows, counts = iter_target_rows(
            pg_conn,
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
