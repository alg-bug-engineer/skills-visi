#!/usr/bin/env python3
"""生成干线协调 DWS 表：dws_corridor_coord_cfg / dws_corridor_coord_group。

判定标准（三条件同时满足）：
  日期类型相同、路口相邻（PG dim_link_info）、周期相同；时段不要求一致。

用法:
    python -m preprocessing.index_cal.dws_corridor_coord_info
    python -m preprocessing.index_cal.dws_corridor_coord_info --min-size 3
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from preprocessing.index_cal.corridor_coord_mine import (
    CALC_VERSION,
    CoordinationGroup,
    run_corridor_coord_mine,
)
from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_CFG = "dws_corridor_coord_cfg"
TABLE_GROUP = "dws_corridor_coord_group"

CFG_COLUMNS = [
    "corridor_id",
    "corridor_name",
    "primary_road_name",
    "intersection_count",
    "inter_ids_ordered_json",
    "inter_names_json",
    "topology_key_json",
    "connecting_link_ids_json",
    "schedule_summary_json",
    "calc_version",
    "is_deleted",
]

GROUP_COLUMNS = [
    "group_id",
    "corridor_id",
    "day_of_week",
    "period_start_sec",
    "period_end_sec",
    "cycle_len_sec",
    "intersection_count",
    "inter_ids_json",
    "inter_names_json",
    "plan_by_inter_json",
    "ctrl_mode_by_inter_json",
    "adjacency_edges_json",
    "connecting_link_ids_json",
    "is_deleted",
]


def _create_cfg_table_ddl(table_name: str) -> str:
    table_ident = _quote_identifier(table_name)
    return f"""
CREATE TABLE IF NOT EXISTS {table_ident} (
    `corridor_id`              VARCHAR(16)  NOT NULL COMMENT '走廊ID，如 CR-0001',
    `corridor_name`            VARCHAR(256) NOT NULL COMMENT '走廊名称（主路名+起终点）',
    `primary_road_name`        VARCHAR(128) DEFAULT NULL COMMENT '主路名称',
    `intersection_count`       TINYINT      NOT NULL COMMENT '走廊内路口数量',
    `inter_ids_ordered_json`   JSON         NOT NULL COMMENT '链式排序后的路口ID列表',
    `inter_names_json`         JSON         NOT NULL COMMENT '路口ID到名称映射',
    `topology_key_json`        JSON         NOT NULL COMMENT '拓扑签名（排序后的路口ID）',
    `connecting_link_ids_json` JSON         DEFAULT NULL COMMENT '走廊内连接路段ID列表',
    `schedule_summary_json`    JSON         DEFAULT NULL COMMENT '调度汇总：组数/日型/时段/周期',
    `calc_version`             VARCHAR(64)  NOT NULL DEFAULT 'corridor_coord_v1',
    `create_time`              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `is_deleted`               TINYINT      NOT NULL DEFAULT 0,
    PRIMARY KEY (`corridor_id`),
    KEY `idx_intersection_count` (`intersection_count`),
    KEY `idx_primary_road` (`primary_road_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='干线协调走廊主表：按路口拓扑聚合的协调子区'
""".strip()


def _create_group_table_ddl(table_name: str) -> str:
    table_ident = _quote_identifier(table_name)
    return f"""
CREATE TABLE IF NOT EXISTS {table_ident} (
    `group_id`                 VARCHAR(16)  NOT NULL COMMENT '协调组ID，如 CG-0001',
    `corridor_id`              VARCHAR(16)  NOT NULL COMMENT '所属走廊ID',
    `day_of_week`              TINYINT      NOT NULL COMMENT '星期几：1-7',
    `period_start_sec`         INT          NOT NULL COMMENT '时段开始秒（当日0点起）',
    `period_end_sec`           INT          NOT NULL COMMENT '时段结束秒',
    `cycle_len_sec`            INT          NOT NULL COMMENT '公共周期长度（秒）',
    `intersection_count`       TINYINT      NOT NULL COMMENT '组内路口数量',
    `inter_ids_json`           JSON         NOT NULL COMMENT '组内路口ID列表',
    `inter_names_json`         JSON         NOT NULL COMMENT '组内路口名称映射',
    `plan_by_inter_json`       JSON         DEFAULT NULL COMMENT '各路口执行方案号',
    `ctrl_mode_by_inter_json`  JSON         DEFAULT NULL COMMENT '各路口控制方式',
    `adjacency_edges_json`     JSON         DEFAULT NULL COMMENT '组内相邻路口边',
    `connecting_link_ids_json` JSON         DEFAULT NULL COMMENT '组内连接路段ID',
    `create_time`              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `is_deleted`               TINYINT      NOT NULL DEFAULT 0,
    PRIMARY KEY (`group_id`),
    KEY `idx_corridor_id` (`corridor_id`),
    KEY `idx_day_period` (`day_of_week`, `period_start_sec`, `period_end_sec`),
    KEY `idx_corridor_day` (`corridor_id`, `day_of_week`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='干线协调组明细表：走廊+日型+时段+周期的协调实例'
""".strip()


def ensure_tables(conn: Any, *, cfg_table: str = TABLE_CFG, group_table: str = TABLE_GROUP) -> None:
    with conn.cursor() as cur:
        cur.execute(_create_cfg_table_ddl(cfg_table))
        cur.execute(_create_group_table_ddl(group_table))
    conn.commit()


def build_rows(
    corridors: list[dict[str, Any]],
    groups: list[CoordinationGroup],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cfg_rows: list[dict[str, Any]] = []
    for corridor in corridors:
        cfg_rows.append(
            {
                "corridor_id": corridor["corridor_id"],
                "corridor_name": corridor["corridor_name"],
                "primary_road_name": corridor.get("primary_road_name") or None,
                "intersection_count": corridor["intersection_count"],
                "inter_ids_ordered_json": json.dumps(corridor["inter_ids"], ensure_ascii=False),
                "inter_names_json": json.dumps(corridor["inter_names"], ensure_ascii=False),
                "topology_key_json": json.dumps(corridor["topology_key"], ensure_ascii=False),
                "connecting_link_ids_json": json.dumps(
                    corridor.get("connecting_link_ids") or [], ensure_ascii=False
                ),
                "schedule_summary_json": json.dumps(
                    corridor.get("schedule_summary") or {}, ensure_ascii=False
                ),
                "calc_version": CALC_VERSION,
                "is_deleted": 0,
            }
        )

    group_rows: list[dict[str, Any]] = []
    for group in groups:
        group_rows.append(
            {
                "group_id": group.group_id,
                "corridor_id": group.corridor_id,
                "day_of_week": group.day_of_week,
                "period_start_sec": group.start_sec,
                "period_end_sec": group.end_sec,
                "cycle_len_sec": group.cycle_len_sec,
                "intersection_count": len(group.inter_ids),
                "inter_ids_json": json.dumps(group.inter_ids, ensure_ascii=False),
                "inter_names_json": json.dumps(group.inter_names, ensure_ascii=False),
                "plan_by_inter_json": json.dumps(group.plan_by_inter, ensure_ascii=False),
                "ctrl_mode_by_inter_json": json.dumps(group.ctrl_mode_by_inter, ensure_ascii=False),
                "adjacency_edges_json": json.dumps(
                    [{"from": a, "to": b} for a, b in group.adjacency_edges],
                    ensure_ascii=False,
                ),
                "connecting_link_ids_json": json.dumps(group.link_ids, ensure_ascii=False),
                "is_deleted": 0,
            }
        )
    return cfg_rows, group_rows


def _replace_all_rows(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    table_name: str,
    columns: list[str],
) -> int:
    table_ident = _quote_identifier(table_name)
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table_ident}")
        if not rows:
            conn.commit()
            return 0
        col_sql = ", ".join(_quote_identifier(c) for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO {table_ident} ({col_sql}) VALUES ({placeholders})"
        values = [tuple(row.get(col) for col in columns) for row in rows]
        for offset in range(0, len(values), 1000):
            cur.executemany(sql, values[offset : offset + 1000])
    conn.commit()
    return len(rows)


def write_rows(
    conn: Any,
    cfg_rows: list[dict[str, Any]],
    group_rows: list[dict[str, Any]],
    *,
    cfg_table: str = TABLE_CFG,
    group_table: str = TABLE_GROUP,
) -> dict[str, int]:
    ensure_tables(conn, cfg_table=cfg_table, group_table=group_table)
    return {
        "cfg_rows": _replace_all_rows(conn, cfg_rows, table_name=cfg_table, columns=CFG_COLUMNS),
        "group_rows": _replace_all_rows(conn, group_rows, table_name=group_table, columns=GROUP_COLUMNS),
    }


def run_build(
    *,
    min_size: int = 2,
    require_ctrl_mode: str | None = None,
    cfg_table: str = TABLE_CFG,
    group_table: str = TABLE_GROUP,
    skip_db: bool = False,
) -> dict[str, int]:
    _slots, groups, corridors = run_corridor_coord_mine(
        min_size=min_size,
        require_ctrl_mode=require_ctrl_mode,
    )
    cfg_rows, group_rows = build_rows(corridors, groups)
    counts = {
        "timing_slots": len(_slots),
        "groups": len(groups),
        "corridors": len(corridors),
        "cfg_rows": len(cfg_rows),
        "group_rows": len(group_rows),
    }
    if not skip_db:
        conn = _get_mysql_connection()
        try:
            counts.update(
                write_rows(
                    conn,
                    cfg_rows,
                    group_rows,
                    cfg_table=cfg_table,
                    group_table=group_table,
                )
            )
        finally:
            conn.close()
    return counts


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass

    parser = argparse.ArgumentParser(description="生成干线协调 DWS 表")
    parser.add_argument("--min-size", type=int, default=2, help="协调组最少路口数")
    parser.add_argument(
        "--require-ctrl-mode",
        default=None,
        help="可选，仅保留指定控制方式（如 31=协调配时）",
    )
    parser.add_argument("--cfg-table", default=TABLE_CFG)
    parser.add_argument("--group-table", default=TABLE_GROUP)
    parser.add_argument("--skip-db", action="store_true", help="仅统计，不写入 MySQL")
    args = parser.parse_args()
    counts = run_build(
        min_size=args.min_size,
        require_ctrl_mode=args.require_ctrl_mode,
        cfg_table=args.cfg_table,
        group_table=args.group_table,
        skip_db=args.skip_db,
    )
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")


if __name__ == "__main__":
    main()
