#!/usr/bin/env python3
"""生成配时方案搭接结构缓存表 dwd_ctl_inter_plan_overlap_cfg。"""

from __future__ import annotations

import argparse
import json
from typing import Any

from data.mysql_reader import fetch_phase_plan_request
from optimization.solvers.single_intersection import _normalize_stages
from preprocessing.timing.overlap_structure import (
    detect_overlap_structure,
    structure_stage_indices_to_nos,
)
from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_TARGET = "dwd_ctl_inter_plan_overlap_cfg"
TARGET_COLUMNS = [
    "inter_id",
    "plan_no",
    "overlap_type",
    "depth_terms_json",
    "ratio_groups_json",
    "slice_stage_nos_json",
    "structure_json",
    "calc_version",
    "is_deleted",
]


def ensure_target_table(conn: Any, table_name: str = TABLE_TARGET) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
CREATE TABLE IF NOT EXISTS {_quote_identifier(table_name)} (
  `inter_id` varchar(16) NOT NULL,
  `plan_no` int NOT NULL,
  `overlap_type` varchar(32) NOT NULL DEFAULT 'stage_movement_arc',
  `depth_terms_json` json DEFAULT NULL,
  `ratio_groups_json` json DEFAULT NULL,
  `slice_stage_nos_json` json DEFAULT NULL,
  `structure_json` json DEFAULT NULL COMMENT '完整结构快照',
  `calc_version` varchar(64) NOT NULL DEFAULT 'overlap_structure_v1',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_deleted` tinyint NOT NULL DEFAULT 0,
  PRIMARY KEY (`inter_id`, `plan_no`),
  KEY `idx_inter_id` (`inter_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='配时方案搭接结构配置表'
""".strip()
        )
    conn.commit()


def build_rows(conn: Any, *, inter_id: str | None = None) -> list[dict[str, Any]]:
    inter_ids = [inter_id] if inter_id else _list_inter_ids(conn)
    rows: list[dict[str, Any]] = []
    for iid in inter_ids:
        request = fetch_phase_plan_request(conn, iid)
        for plan in request.get("phasePlanOfTimeList") or []:
            plan_no = plan.get("planNo")
            stage_defs, _ = _normalize_stages({"phasePlanOfTimeList": [plan]}, {})
            stage_nos = [stage.get("stage_no") for stage in stage_defs]
            if not stage_defs:
                structure = {
                    "depth_terms": [],
                    "ratio_groups": [],
                    "slice_stage_nos": [],
                    "notes": ["缺少阶段流向或历史绿灯，写入空结构"],
                }
            else:
                detected = detect_overlap_structure(stage_defs)
                structure = structure_stage_indices_to_nos(detected, stage_nos)
            rows.append(
                {
                    "inter_id": iid,
                    "plan_no": plan_no,
                    "overlap_type": "stage_movement_arc",
                    "depth_terms_json": json.dumps(structure.get("depth_terms") or [], ensure_ascii=False),
                    "ratio_groups_json": json.dumps(structure.get("ratio_groups") or [], ensure_ascii=False),
                    "slice_stage_nos_json": json.dumps(structure.get("slice_stage_nos") or [], ensure_ascii=False),
                    "structure_json": json.dumps(structure, ensure_ascii=False),
                    "calc_version": "overlap_structure_v1",
                    "is_deleted": 0,
                }
            )
    return rows


def upsert_rows(conn: Any, rows: list[dict[str, Any]], *, target_table: str = TABLE_TARGET) -> int:
    if not rows:
        return 0
    ensure_target_table(conn, target_table)
    columns = ", ".join(_quote_identifier(col) for col in TARGET_COLUMNS)
    placeholders = ", ".join(["%s"] * len(TARGET_COLUMNS))
    updates = ", ".join(
        f"{_quote_identifier(col)}=VALUES({_quote_identifier(col)})"
        for col in TARGET_COLUMNS
        if col not in {"inter_id", "plan_no"}
    )
    updates += ", `update_time`=CURRENT_TIMESTAMP"
    sql = (
        f"INSERT INTO {_quote_identifier(target_table)} ({columns}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
    values = [tuple(row.get(col) for col in TARGET_COLUMNS) for row in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)
    conn.commit()
    return len(rows)


def _list_inter_ids(conn: Any) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT inter_id
            FROM dwd_ctl_inter_plan_cfg
            WHERE is_deleted = 0
            ORDER BY inter_id
            """
        )
        return [str(row["inter_id"]) for row in cur.fetchall()]


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass
    parser = argparse.ArgumentParser(description="生成配时方案搭接结构缓存表")
    parser.add_argument("--inter-id")
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()
    conn = _get_mysql_connection(streaming=False)
    try:
        rows = build_rows(conn, inter_id=args.inter_id)
        if not args.skip_db:
            count = upsert_rows(conn, rows, target_table=args.target_table)
        else:
            count = len(rows)
        print(f"target_rows: {len(rows)}")
        print(f"upsert_rows: {0 if args.skip_db else count}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
