#!/usr/bin/env python3
"""生成路口进口转向绿灯利用率表 dws_turn_green_utilization_5min_mm。

数据来源：
  - MySQL dws_turn_saturation_5min_mm：转向车流饱和度
  - MySQL dws_turn_min_green_5min_mm：评价用转向最小绿与计划绿灯时长

计算口径：
  green_utilization = MAX(turn_saturation, (min_green_time - 2) / green_time_plan)
  这里的 min_green_time 仅用于评价，不作为优化器阶段绿界约束。

更新策略：
  按 (inter_id, link_id, turn_dir_no, day_of_week, step_index) 关联两表有效记录，
  计算后覆盖写入。
"""

from __future__ import annotations

import argparse
from typing import Any

from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_SATURATION = "dws_turn_saturation_5min_mm"
TABLE_MIN_GREEN = "dws_turn_min_green_5min_mm"
TABLE_TARGET = "dws_turn_green_utilization_5min_mm"

TARGET_COLUMNS = [
    "inter_id",
    "link_id",
    "turn_dir_no",
    "day_of_week",
    "step_index",
    "inter_name",
    "dir8_code",
    "dir4_code",
    "green_utilization",
    "is_deleted",
]


def _create_table_ddl(table_name: str) -> str:
    table_ident = _quote_identifier(table_name)
    return f"""
CREATE TABLE IF NOT EXISTS {table_ident} (
    `inter_id`          VARCHAR(16)  NOT NULL COMMENT '路口ID，16位标准编码',
    `link_id`           VARCHAR(32)  NOT NULL COMMENT '进口道路段ID，唯一标识一个进口道',
    `turn_dir_no`       TINYINT      NOT NULL COMMENT '转向类型：1-左转（含调头），2-直行，3-右转',
    `day_of_week`       TINYINT      NOT NULL COMMENT '星期几：1-周一，2-周二，3-周三，4-周四，5-周五，6-周六，7-周日',
    `step_index`        SMALLINT     NOT NULL COMMENT '5分钟时间片序号，取值0~287，对应全天288个5分钟窗口',
    `inter_name`        VARCHAR(128) DEFAULT NULL COMMENT '路口名称，便于直观识别',
    `dir8_code`         INT          DEFAULT NULL COMMENT '八方向编码：0-北，1-东北，2-东，3-东南，4-南，5-西南，6-西，7-西北',
    `dir4_code`         INT          DEFAULT NULL COMMENT '四方向编码：0-北，1-东，2-南，3-西',
    `green_utilization` DECIMAL(10,4) NOT NULL COMMENT '转向绿灯利用率，无量纲。取值 = MAX(转向车流饱和度, (相位最小绿 - 2) / 相位绿灯时长)。从需求负荷和配时约束双维度评估绿灯时间利用效率',
    `create_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `update_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    `is_deleted`        TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除标记：0-有效，1-已删除',
    PRIMARY KEY (`inter_id`, `link_id`, `turn_dir_no`, `day_of_week`, `step_index`),
    INDEX `idx_inter_id` (`inter_id`) COMMENT '按路口维度查询加速',
    INDEX `idx_inter_id_day_step` (`inter_id`, `day_of_week`, `step_index`) COMMENT '按路口+星期+时间片联合查询加速',
    INDEX `idx_turn_dir_no` (`turn_dir_no`) COMMENT '按转向类型筛选加速',
    INDEX `idx_utilization_low` (`green_utilization`) COMMENT '按绿灯利用率查询加速，便于筛选空放/过饱和转向'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='路口进口转向绿灯利用率表 - 按进口道+转向+星期几+5分钟时间片，取值=MAX(转向饱和度, (评价用转向最小绿-2)/相位绿灯时长)'
""".strip()


def ensure_target_table(conn: Any, table_name: str = TABLE_TARGET) -> None:
    with conn.cursor() as cursor:
        cursor.execute(_create_table_ddl(table_name))
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


def compute_green_utilization(
    turn_saturation: float,
    min_green_time: float,
    green_time_plan: float,
) -> float | None:
    if green_time_plan <= 0:
        return None
    timing_utilization = (min_green_time - 2.0) / green_time_plan
    return round(max(turn_saturation, timing_utilization), 4)


def load_joined_rows(
    conn: Any,
    *,
    saturation_table: str = TABLE_SATURATION,
    min_green_table: str = TABLE_MIN_GREEN,
    inter_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    sat_ident = _quote_identifier(saturation_table)
    mg_ident = _quote_identifier(min_green_table)
    sql = f"""
        SELECT
            s.inter_id,
            s.link_id,
            s.turn_dir_no,
            s.day_of_week,
            s.step_index,
            COALESCE(s.inter_name, m.inter_name) AS inter_name,
            COALESCE(s.dir8_code, m.dir8_code) AS dir8_code,
            COALESCE(s.dir4_code, m.dir4_code) AS dir4_code,
            s.turn_saturation,
            m.min_green_time,
            m.green_time_plan
        FROM {sat_ident} s
        INNER JOIN {mg_ident} m
            ON s.inter_id = m.inter_id
           AND s.link_id = m.link_id
           AND s.turn_dir_no = m.turn_dir_no
           AND s.day_of_week = m.day_of_week
           AND s.step_index = m.step_index
        WHERE COALESCE(s.is_deleted, 0) = 0
          AND COALESCE(m.is_deleted, 0) = 0
          AND s.link_id IS NOT NULL
          AND s.link_id <> ''
          AND s.turn_dir_no IN (1, 2, 3)
          AND s.day_of_week BETWEEN 1 AND 7
          AND s.step_index BETWEEN 0 AND 287
          AND m.green_time_plan > 0
    """
    params: list[Any] = []
    if inter_ids:
        placeholders = ", ".join(["%s"] * len(inter_ids))
        sql += f" AND s.inter_id IN ({placeholders})"
        params.extend(sorted(inter_ids))

    rows: list[dict[str, Any]] = []
    skipped_invalid = 0
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            inter_id = str(row.get("inter_id") or "").strip()
            link_id = str(row.get("link_id") or "").strip()
            turn_dir_no = _to_int(row.get("turn_dir_no"))
            day_of_week = _to_int(row.get("day_of_week"))
            step_index = _to_int(row.get("step_index"))
            turn_saturation = _to_float(row.get("turn_saturation"))
            min_green_time = _to_float(row.get("min_green_time"))
            green_time_plan = _to_float(row.get("green_time_plan"))
            if (
                not inter_id
                or not link_id
                or turn_dir_no not in {1, 2, 3}
                or day_of_week not in range(1, 8)
                or step_index not in range(0, 288)
            ):
                skipped_invalid += 1
                continue
            green_utilization = compute_green_utilization(
                turn_saturation,
                min_green_time,
                green_time_plan,
            )
            if green_utilization is None:
                skipped_invalid += 1
                continue
            rows.append(
                {
                    "inter_id": inter_id,
                    "link_id": link_id,
                    "turn_dir_no": turn_dir_no,
                    "day_of_week": day_of_week,
                    "step_index": step_index,
                    "inter_name": str(row.get("inter_name") or "").strip() or None,
                    "dir8_code": _to_int(row.get("dir8_code"), default=None),
                    "dir4_code": _to_int(row.get("dir4_code"), default=None),
                    "green_utilization": green_utilization,
                    "is_deleted": 0,
                }
            )
    rows.sort(
        key=lambda item: (
            item["inter_id"],
            item["link_id"],
            item["turn_dir_no"],
            item["day_of_week"],
            item["step_index"],
        )
    )
    return rows, skipped_invalid


def build_green_utilization_rows(
    conn: Any,
    *,
    saturation_table: str = TABLE_SATURATION,
    min_green_table: str = TABLE_MIN_GREEN,
    inter_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    target_rows, skipped_invalid = load_joined_rows(
        conn,
        saturation_table=saturation_table,
        min_green_table=min_green_table,
        inter_ids=inter_ids,
    )
    counts = {
        "target_rows": len(target_rows),
        "skipped_invalid": skipped_invalid,
    }
    return target_rows, counts


def _build_upsert_sql(table_name: str) -> str:
    quoted_columns = ", ".join(_quote_identifier(col) for col in TARGET_COLUMNS)
    placeholders = ", ".join(["%s"] * len(TARGET_COLUMNS))
    update_columns = [
        col
        for col in TARGET_COLUMNS
        if col not in {"inter_id", "link_id", "turn_dir_no", "day_of_week", "step_index"}
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

    parser = argparse.ArgumentParser(description="生成路口进口转向绿灯利用率表")
    parser.add_argument("--saturation-table", default=TABLE_SATURATION)
    parser.add_argument("--min-green-table", default=TABLE_MIN_GREEN)
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument(
        "--inter-ids",
        help="仅处理指定路口（逗号分隔 inter_id）",
    )
    parser.add_argument("--skip-db", action="store_true", help="仅统计，不写入 MySQL")
    args = parser.parse_args()

    inter_ids: set[str] | None = None
    if args.inter_ids:
        inter_ids = {item.strip() for item in args.inter_ids.split(",") if item.strip()}

    conn = _get_mysql_connection(streaming=False)
    try:
        if not args.skip_db:
            ensure_target_table(conn, args.target_table)
        target_rows, counts = build_green_utilization_rows(
            conn,
            saturation_table=args.saturation_table,
            min_green_table=args.min_green_table,
            inter_ids=inter_ids,
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
