#!/usr/bin/env python3
"""生成路口综合评价表 dws_inter_evaluation_5min_mm。

数据来源：
  - MySQL dws_turn_saturation_5min_mm：进口转向级饱和度
  - MySQL dws_turn_green_utilization_5min_mm：进口转向绿灯利用率（修正后转向饱和度）

计算口径：
  saturation_max   = 该路口所有转向饱和度的最大值
  saturation_avg   = 该路口所有转向饱和度的算术平均值
  unbalance_index  = 该路口各转向绿灯利用率的标准差
  level_of_service = 基于 saturation_max 判定（A~F）
  turn_count       = 参与统计的转向数量

更新策略：
  读取转向饱和度与绿灯利用率表有效记录，按 (inter_id, day_of_week, step_index)
  聚合后覆盖写入。
"""

from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from typing import Any

from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_SOURCE = "dws_turn_saturation_5min_mm"
TABLE_SOURCE_UTILIZATION = "dws_turn_green_utilization_5min_mm"
TABLE_TARGET = "dws_inter_evaluation_5min_mm"

TARGET_COLUMNS = [
    "inter_id",
    "day_of_week",
    "step_index",
    "inter_name",
    "saturation_max",
    "saturation_avg",
    "unbalance_index",
    "level_of_service",
    "turn_count",
    "is_deleted",
]


def _level_of_service(saturation_max: float) -> str:
    if saturation_max <= 0.60:
        return "A"
    if saturation_max <= 0.70:
        return "B"
    if saturation_max <= 0.80:
        return "C"
    if saturation_max <= 0.90:
        return "D"
    if saturation_max <= 1.00:
        return "E"
    return "F"


def _create_table_ddl(table_name: str) -> str:
    table_ident = _quote_identifier(table_name)
    return f"""
CREATE TABLE IF NOT EXISTS {table_ident} (
    `inter_id`          VARCHAR(16)  NOT NULL COMMENT '路口ID，16位标准编码',
    `day_of_week`       TINYINT      NOT NULL COMMENT '星期几：1-周一，2-周二，3-周三，4-周四，5-周五，6-周六，7-周日',
    `step_index`        SMALLINT     NOT NULL COMMENT '5分钟时间片序号，取值0~287，对应全天288个5分钟窗口',
    `inter_name`        VARCHAR(128) DEFAULT NULL COMMENT '路口名称，便于直观识别',
    `saturation_max`    DECIMAL(10,4) NOT NULL COMMENT '最大饱和度，该路口所有转向饱和度的最大值，无量纲',
    `saturation_avg`    DECIMAL(10,4) NOT NULL COMMENT '平均饱和度，该路口所有转向饱和度的算术平均值，无量纲',
    `unbalance_index`   DECIMAL(10,4) NOT NULL COMMENT '失衡系数，该路口各转向绿灯利用率（修正后转向饱和度）的标准差，反映各方向负荷均衡程度，无量纲',
    `level_of_service`  CHAR(1)       NOT NULL COMMENT '服务水平：A-畅通，B-稳定，C-较稳，D-临界，E-拥堵，F-阻塞。基于saturation_max判定',
    `turn_count`        TINYINT      NOT NULL COMMENT '该路口参与统计的转向数量（进口道×转向），用于评估聚合粒度',
    `create_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `update_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    `is_deleted`        TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除标记：0-有效，1-已删除',
    PRIMARY KEY (`inter_id`, `day_of_week`, `step_index`),
    INDEX `idx_inter_id` (`inter_id`) COMMENT '按路口维度查询加速',
    INDEX `idx_day_of_week` (`day_of_week`) COMMENT '按星期几筛选加速',
    INDEX `idx_inter_id_day_step` (`inter_id`, `day_of_week`, `step_index`) COMMENT '按路口+星期+时间片联合查询加速',
    INDEX `idx_los` (`level_of_service`) COMMENT '按服务水平筛选加速',
    INDEX `idx_saturation_max_high` (`saturation_max`) COMMENT '按最大饱和度查询加速',
    INDEX `idx_unbalance_high` (`unbalance_index`) COMMENT '按失衡系数查询加速，便于筛选失衡路口'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='路口综合评价表 - 按路口+星期几+5分钟时间片存储最大饱和度、平均饱和度、失衡系数和服务水平'
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


def load_turn_saturation_rows(
    conn: Any,
    *,
    source_table: str = TABLE_SOURCE,
    inter_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    table_ident = _quote_identifier(source_table)
    sql = f"""
        SELECT inter_id, inter_name, link_id, turn_dir_no,
               day_of_week, step_index, turn_saturation
        FROM {table_ident}
        WHERE COALESCE(is_deleted, 0) = 0
          AND link_id IS NOT NULL
          AND link_id <> ''
          AND turn_dir_no IN (1, 2, 3)
          AND day_of_week BETWEEN 1 AND 7
          AND step_index BETWEEN 0 AND 287
    """
    params: list[Any] = []
    if inter_ids:
        placeholders = ", ".join(["%s"] * len(inter_ids))
        sql += f" AND inter_id IN ({placeholders})"
        params.extend(sorted(inter_ids))

    rows: list[dict[str, Any]] = []
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            inter_id = str(row.get("inter_id") or "").strip()
            link_id = str(row.get("link_id") or "").strip()
            turn_dir_no = _to_int(row.get("turn_dir_no"))
            day_of_week = _to_int(row.get("day_of_week"))
            step_index = _to_int(row.get("step_index"))
            turn_saturation = _to_float(row.get("turn_saturation"))
            if (
                not inter_id
                or not link_id
                or turn_dir_no not in {1, 2, 3}
                or day_of_week not in range(1, 8)
                or step_index not in range(0, 288)
            ):
                continue
            rows.append(
                {
                    "inter_id": inter_id,
                    "inter_name": str(row.get("inter_name") or "").strip() or None,
                    "link_id": link_id,
                    "turn_dir_no": turn_dir_no,
                    "day_of_week": day_of_week,
                    "step_index": step_index,
                    "turn_saturation": turn_saturation,
                }
            )
    return rows


def load_turn_green_utilization_rows(
    conn: Any,
    *,
    source_table: str = TABLE_SOURCE_UTILIZATION,
    inter_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    table_ident = _quote_identifier(source_table)
    sql = f"""
        SELECT inter_id, inter_name, link_id, turn_dir_no,
               day_of_week, step_index, green_utilization
        FROM {table_ident}
        WHERE COALESCE(is_deleted, 0) = 0
          AND link_id IS NOT NULL
          AND link_id <> ''
          AND turn_dir_no IN (1, 2, 3)
          AND day_of_week BETWEEN 1 AND 7
          AND step_index BETWEEN 0 AND 287
    """
    params: list[Any] = []
    if inter_ids:
        placeholders = ", ".join(["%s"] * len(inter_ids))
        sql += f" AND inter_id IN ({placeholders})"
        params.extend(sorted(inter_ids))

    rows: list[dict[str, Any]] = []
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            inter_id = str(row.get("inter_id") or "").strip()
            link_id = str(row.get("link_id") or "").strip()
            turn_dir_no = _to_int(row.get("turn_dir_no"))
            day_of_week = _to_int(row.get("day_of_week"))
            step_index = _to_int(row.get("step_index"))
            green_utilization = _to_float(row.get("green_utilization"))
            if (
                not inter_id
                or not link_id
                or turn_dir_no not in {1, 2, 3}
                or day_of_week not in range(1, 8)
                or step_index not in range(0, 288)
            ):
                continue
            rows.append(
                {
                    "inter_id": inter_id,
                    "inter_name": str(row.get("inter_name") or "").strip() or None,
                    "link_id": link_id,
                    "turn_dir_no": turn_dir_no,
                    "day_of_week": day_of_week,
                    "step_index": step_index,
                    "green_utilization": green_utilization,
                }
            )
    return rows


def _unbalance_index(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return round(statistics.stdev(values), 4)


def aggregate_inter_rows(
    turn_rows: list[dict[str, Any]],
    utilization_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    util_grouped: dict[tuple[str, int, int], list[float]] = defaultdict(list)
    for row in turn_rows:
        key = (row["inter_id"], row["day_of_week"], row["step_index"])
        grouped[key].append(row)
    for row in utilization_rows or []:
        key = (row["inter_id"], row["day_of_week"], row["step_index"])
        util_grouped[key].append(row["green_utilization"])

    target_rows: list[dict[str, Any]] = []
    for (inter_id, day_of_week, step_index), items in grouped.items():
        saturations = [item["turn_saturation"] for item in items]
        saturation_max = round(max(saturations), 4)
        saturation_avg = round(sum(saturations) / len(saturations), 4)
        inter_name = next(
            (item["inter_name"] for item in items if item.get("inter_name")),
            None,
        )
        target_rows.append(
            {
                "inter_id": inter_id,
                "day_of_week": day_of_week,
                "step_index": step_index,
                "inter_name": inter_name,
                "saturation_max": saturation_max,
                "saturation_avg": saturation_avg,
                "unbalance_index": _unbalance_index(
                    util_grouped.get((inter_id, day_of_week, step_index), [])
                ),
                "level_of_service": _level_of_service(saturation_max),
                "turn_count": len(items),
                "is_deleted": 0,
            }
        )

    target_rows.sort(
        key=lambda item: (
            item["inter_id"],
            item["day_of_week"],
            item["step_index"],
        )
    )
    return target_rows


def build_inter_evaluation_rows(
    conn: Any,
    *,
    source_table: str = TABLE_SOURCE,
    utilization_table: str = TABLE_SOURCE_UTILIZATION,
    inter_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    turn_rows = load_turn_saturation_rows(
        conn,
        source_table=source_table,
        inter_ids=inter_ids,
    )
    utilization_rows = load_turn_green_utilization_rows(
        conn,
        source_table=utilization_table,
        inter_ids=inter_ids,
    )
    target_rows = aggregate_inter_rows(turn_rows, utilization_rows)
    counts = {
        "source_turn_rows": len(turn_rows),
        "source_utilization_rows": len(utilization_rows),
        "target_rows": len(target_rows),
    }
    return target_rows, counts


def _build_upsert_sql(table_name: str) -> str:
    quoted_columns = ", ".join(_quote_identifier(col) for col in TARGET_COLUMNS)
    placeholders = ", ".join(["%s"] * len(TARGET_COLUMNS))
    update_columns = [
        col
        for col in TARGET_COLUMNS
        if col not in {"inter_id", "day_of_week", "step_index"}
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

    parser = argparse.ArgumentParser(description="生成路口综合评价表")
    parser.add_argument("--source-table", default=TABLE_SOURCE)
    parser.add_argument("--utilization-table", default=TABLE_SOURCE_UTILIZATION)
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
        target_rows, counts = build_inter_evaluation_rows(
            conn,
            source_table=args.source_table,
            utilization_table=args.utilization_table,
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
