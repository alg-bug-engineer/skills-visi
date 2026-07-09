#!/usr/bin/env python3
"""生成进口转向级饱和度聚合表 dws_turn_saturation_5min_mm。

数据来源：
  - MySQL dws_lane_saturation_5min_mm：车道级饱和度

计算口径：
  turn_saturation = 该转向下所有车道饱和度的最大值
  lane_saturation_detail = 各车道饱和度 JSON 明细，便于下钻分析

更新策略：
  读取车道饱和度表有效记录，按 (inter_id, link_id, turn_dir_no, day_of_week, step_index)
  聚合后覆盖写入。
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any

from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_SOURCE = "dws_lane_saturation_5min_mm"
TABLE_TARGET = "dws_turn_saturation_5min_mm"

TARGET_COLUMNS = [
    "inter_id",
    "link_id",
    "turn_dir_no",
    "day_of_week",
    "step_index",
    "inter_name",
    "dir8_code",
    "dir4_code",
    "turn_saturation",
    "lane_saturation_detail",
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
    `dir8_code`         INT          DEFAULT NULL COMMENT '八方向编码：0-北, 1-东北, 2-东, 3-东南, 4-南, 5-西南, 6-西, 7-西北',
    `dir4_code`         INT          DEFAULT NULL COMMENT '四方向编码：0-北, 1-东, 2-南, 3-西',
    `turn_saturation`   DECIMAL(10,4) NOT NULL COMMENT '转向饱和度，取该转向下所有车道饱和度的最大值，无量纲',
    `lane_saturation_detail` JSON      NOT NULL COMMENT '车道饱和度明细，JSON数组格式：[{{"lane_id":"xxx","saturation":0.85,"lane_no":1}},...]',
    `create_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `update_time`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    `is_deleted`        TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除标记：0-有效，1-已删除',
    PRIMARY KEY (`inter_id`, `link_id`, `turn_dir_no`, `day_of_week`, `step_index`),
    INDEX `idx_inter_id` (`inter_id`) COMMENT '按路口维度查询加速',
    INDEX `idx_inter_id_day_step` (`inter_id`, `day_of_week`, `step_index`) COMMENT '按路口+星期+时间片联合查询加速',
    INDEX `idx_turn_dir_no` (`turn_dir_no`) COMMENT '按转向类型筛选加速',
    INDEX `idx_saturation_high` (`turn_saturation`) COMMENT '按饱和度值查询加速，便于筛选过饱和转向',
    INDEX `idx_lane_detail` ((CAST(lane_saturation_detail->>'$[0].lane_id' AS CHAR(20)))) COMMENT 'JSON字段虚拟列索引，加速按车道下钻查询'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='进口转向级饱和度聚合表 - 转向饱和度取车道饱和度最大值，JSON字段保存车道级明细'
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


def _dir4_from_dir8(dir8_code: int) -> int:
    return dir8_code // 2


def load_link_dir_codes(inter_ids: set[str]) -> dict[tuple[str, str], dict[str, int]]:
    """从 PG 渠化宽表读取 (inter_id, link_id) -> dir8_code / dir4_code。"""
    if not inter_ids:
        return {}

    from data.pg_reader import connect_pg, fetch_channelization

    mapping: dict[tuple[str, str], dict[str, int]] = {}
    pg_conn = connect_pg()
    try:
        for inter_id in sorted(inter_ids):
            channelization = fetch_channelization(pg_conn, inter_id)
            for approach in channelization.get("approaches") or []:
                link_id = str(approach.get("linkId") or "").strip()
                dir8_code = _to_int(approach.get("dir8Code"), default=None)
                if not link_id or dir8_code is None or dir8_code not in range(0, 8):
                    continue
                mapping[(inter_id, link_id)] = {
                    "dir8_code": dir8_code,
                    "dir4_code": _dir4_from_dir8(dir8_code),
                }
    finally:
        pg_conn.close()
    return mapping


def load_lane_saturation_rows(
    conn: Any,
    *,
    source_table: str = TABLE_SOURCE,
    inter_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    table_ident = _quote_identifier(source_table)
    sql = f"""
        SELECT lane_id, day_of_week, step_index, inter_id, inter_name,
               link_id, lane_no, turn_dir_no, lane_saturation
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
            lane_id = str(row.get("lane_id") or "").strip()
            inter_id = str(row.get("inter_id") or "").strip()
            link_id = str(row.get("link_id") or "").strip()
            turn_dir_no = _to_int(row.get("turn_dir_no"))
            day_of_week = _to_int(row.get("day_of_week"))
            step_index = _to_int(row.get("step_index"))
            lane_saturation = _to_float(row.get("lane_saturation"))
            if (
                not lane_id
                or not inter_id
                or not link_id
                or turn_dir_no not in {1, 2, 3}
                or day_of_week not in range(1, 8)
                or step_index not in range(0, 288)
            ):
                continue
            rows.append(
                {
                    "lane_id": lane_id,
                    "inter_id": inter_id,
                    "inter_name": str(row.get("inter_name") or "").strip() or None,
                    "link_id": link_id,
                    "lane_no": _to_int(row.get("lane_no")),
                    "turn_dir_no": turn_dir_no,
                    "day_of_week": day_of_week,
                    "step_index": step_index,
                    "lane_saturation": lane_saturation,
                }
            )
    return rows


def aggregate_turn_rows(
    lane_rows: list[dict[str, Any]],
    *,
    link_dir_codes: dict[tuple[str, str], dict[str, int]] | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in lane_rows:
        key = (
            row["inter_id"],
            row["link_id"],
            row["turn_dir_no"],
            row["day_of_week"],
            row["step_index"],
        )
        grouped[key].append(row)

    target_rows: list[dict[str, Any]] = []
    link_dir_codes = link_dir_codes or {}
    for key, items in grouped.items():
        inter_id, link_id, turn_dir_no, day_of_week, step_index = key
        lane_details = sorted(
            [
                {
                    "lane_id": item["lane_id"],
                    "saturation": round(item["lane_saturation"], 4),
                    "lane_no": item["lane_no"],
                }
                for item in items
            ],
            key=lambda detail: (
                detail["lane_no"] is None,
                detail["lane_no"] if detail["lane_no"] is not None else 0,
                detail["lane_id"],
            ),
        )
        turn_saturation = round(max(item["lane_saturation"] for item in items), 4)
        inter_name = next(
            (item["inter_name"] for item in items if item.get("inter_name")),
            None,
        )
        dir_codes = link_dir_codes.get((inter_id, link_id), {})
        target_rows.append(
            {
                "inter_id": inter_id,
                "link_id": link_id,
                "turn_dir_no": turn_dir_no,
                "day_of_week": day_of_week,
                "step_index": step_index,
                "inter_name": inter_name,
                "dir8_code": dir_codes.get("dir8_code"),
                "dir4_code": dir_codes.get("dir4_code"),
                "turn_saturation": turn_saturation,
                "lane_saturation_detail": json.dumps(lane_details, ensure_ascii=False),
                "is_deleted": 0,
            }
        )

    target_rows.sort(
        key=lambda item: (
            item["inter_id"],
            item["link_id"],
            item["turn_dir_no"],
            item["day_of_week"],
            item["step_index"],
        )
    )
    return target_rows


def build_turn_saturation_rows(
    conn: Any,
    *,
    source_table: str = TABLE_SOURCE,
    inter_ids: set[str] | None = None,
    fill_dir_from_pg: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    lane_rows = load_lane_saturation_rows(
        conn,
        source_table=source_table,
        inter_ids=inter_ids,
    )
    link_dir_codes: dict[tuple[str, str], dict[str, int]] = {}
    if fill_dir_from_pg and lane_rows:
        inter_id_set = {row["inter_id"] for row in lane_rows}
        if inter_ids:
            inter_id_set &= inter_ids
        link_dir_codes = load_link_dir_codes(inter_id_set)

    target_rows = aggregate_turn_rows(lane_rows, link_dir_codes=link_dir_codes)
    counts = {
        "source_lane_rows": len(lane_rows),
        "link_dir_mappings": len(link_dir_codes),
        "target_rows": len(target_rows),
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

    parser = argparse.ArgumentParser(description="生成进口转向级饱和度聚合表")
    parser.add_argument("--source-table", default=TABLE_SOURCE)
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument(
        "--inter-ids",
        help="仅处理指定路口（逗号分隔 inter_id）",
    )
    parser.add_argument(
        "--skip-pg-dir",
        action="store_true",
        help="不从 PG 渠化宽表回填 dir8_code / dir4_code",
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
        target_rows, counts = build_turn_saturation_rows(
            conn,
            source_table=args.source_table,
            inter_ids=inter_ids,
            fill_dir_from_pg=not args.skip_pg_dir,
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
