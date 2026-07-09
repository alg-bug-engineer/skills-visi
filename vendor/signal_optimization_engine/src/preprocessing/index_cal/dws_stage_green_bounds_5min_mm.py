#!/usr/bin/env python3
"""生成阶段级优化绿界表 dws_stage_green_bounds_5min_mm。"""

from __future__ import annotations

import argparse
import json
from typing import Any

from data.mysql_reader import fetch_phase_plan_request, fetch_plan_periods, fill_stage_green_bounds
from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_TARGET = "dws_stage_green_bounds_5min_mm"
TARGET_COLUMNS = [
    "inter_id",
    "plan_no",
    "stage_no",
    "stage_seq_no",
    "day_of_week",
    "step_index",
    "inter_name",
    "cycle_len_sec",
    "history_green_s",
    "history_min_green_s",
    "history_max_green_s",
    "min_green_s",
    "max_green_s",
    "pinned_to_history",
    "has_motor_flow",
    "has_pedestrian_flow",
    "green_bounds_json",
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
  `stage_no` int NOT NULL,
  `stage_seq_no` int NOT NULL,
  `day_of_week` tinyint NOT NULL,
  `step_index` smallint NOT NULL,
  `inter_name` varchar(128) DEFAULT NULL,
  `cycle_len_sec` int NOT NULL,
  `history_green_s` decimal(8,1) DEFAULT NULL,
  `history_min_green_s` decimal(8,1) DEFAULT NULL,
  `history_max_green_s` decimal(8,1) DEFAULT NULL,
  `min_green_s` decimal(8,1) NOT NULL,
  `max_green_s` decimal(8,1) DEFAULT NULL,
  `pinned_to_history` tinyint NOT NULL DEFAULT 0,
  `has_motor_flow` tinyint NOT NULL DEFAULT 0,
  `has_pedestrian_flow` tinyint NOT NULL DEFAULT 0,
  `green_bounds_json` json DEFAULT NULL,
  `calc_version` varchar(64) NOT NULL DEFAULT 'stage_green_bounds_v1',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_deleted` tinyint NOT NULL DEFAULT 0,
  PRIMARY KEY (`inter_id`, `plan_no`, `stage_no`, `day_of_week`, `step_index`),
  KEY `idx_inter_day_step` (`inter_id`, `day_of_week`, `step_index`),
  KEY `idx_plan_stage` (`inter_id`, `plan_no`, `stage_seq_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='阶段级优化绿界表：按方案+阶段+5分钟时间片存储最小绿/最大绿约束'
""".strip()
        )
    conn.commit()


def build_rows(conn: Any, *, inter_id: str | None = None) -> list[dict[str, Any]]:
    inter_ids = [inter_id] if inter_id else _list_inter_ids(conn)
    rows: list[dict[str, Any]] = []
    for iid in inter_ids:
        request = fetch_phase_plan_request(conn, iid)
        fill_stage_green_bounds(request, conn, prefer_precomputed=False)
        periods = fetch_plan_periods(conn, iid)
        for plan in request.get("phasePlanOfTimeList") or []:
            plan_no = plan.get("planNo")
            windows = periods.get(plan_no) or [("00:00", "24:00")]
            steps = sorted(_windows_to_steps(windows))
            if not steps:
                steps = list(range(288))
            for day_of_week in range(1, 8):
                for step_index in steps:
                    for stage in plan.get("phaseStageInfoList") or []:
                        timing = stage.get("currentTiming") or {}
                        bounds = stage.get("greenBounds") or {}
                        rows.append(
                            {
                                "inter_id": iid,
                                "plan_no": plan_no,
                                "stage_no": stage.get("stageNo"),
                                "stage_seq_no": stage.get("stageSeqNo"),
                                "day_of_week": day_of_week,
                                "step_index": step_index,
                                "inter_name": request.get("interName"),
                                "cycle_len_sec": plan.get("cycleLenSec") or 0,
                                "history_green_s": timing.get("greenSec"),
                                "history_min_green_s": stage.get("min_green_s"),
                                "history_max_green_s": stage.get("max_green_s"),
                                "min_green_s": bounds.get("minGreenS") if bounds else stage.get("min_green_s"),
                                "max_green_s": bounds.get("maxGreenS") if bounds else stage.get("max_green_s"),
                                "pinned_to_history": 1 if bounds.get("pinnedToHistory") else 0,
                                "has_motor_flow": 1 if stage.get("phaseDirInfoDTOList") else 0,
                                "has_pedestrian_flow": 1 if stage.get("pedDirList") else 0,
                                "green_bounds_json": json.dumps(bounds, ensure_ascii=False),
                                "calc_version": "stage_green_bounds_v1",
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
        if col not in {"inter_id", "plan_no", "stage_no", "day_of_week", "step_index"}
    )
    updates += ", `update_time`=CURRENT_TIMESTAMP"
    sql = (
        f"INSERT INTO {_quote_identifier(target_table)} ({columns}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
    values = [tuple(row.get(col) for col in TARGET_COLUMNS) for row in rows]
    with conn.cursor() as cur:
        for offset in range(0, len(values), 2000):
            cur.executemany(sql, values[offset : offset + 2000])
    conn.commit()
    return len(rows)


def _list_inter_ids(conn: Any) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT inter_id FROM dwd_ctl_inter_plan_cfg WHERE is_deleted = 0 ORDER BY inter_id")
        return [str(row["inter_id"]) for row in cur.fetchall()]


def _windows_to_steps(windows: list[tuple[str, str]]) -> set[int]:
    steps: set[int] = set()
    for start, end in windows:
        start_min = _hhmm_to_minutes(start)
        end_min = _hhmm_to_minutes(end)
        if start_min is None or end_min is None:
            continue
        start_step = start_min // 5
        end_step = min(-(-end_min // 5), 288)
        if end_min <= start_min:
            steps.update(range(start_step, 288))
            steps.update(range(0, end_step))
        else:
            steps.update(range(start_step, end_step))
    return steps


def _hhmm_to_minutes(value: str) -> int | None:
    parts = str(value or "").split(":")
    if len(parts) < 2:
        return None
    hour, minute = int(parts[0]), int(parts[1])
    return hour * 60 + minute


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass
    parser = argparse.ArgumentParser(description="生成阶段级优化绿界表")
    parser.add_argument("--inter-id")
    parser.add_argument("--source-plan-table", default="dwd_ctl_inter_plan_cfg")
    parser.add_argument("--source-stage-table", default="dwd_ctl_inter_plan_stage_timing")
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()
    conn = _get_mysql_connection(streaming=False)
    try:
        rows = build_rows(conn, inter_id=args.inter_id)
        count = 0 if args.skip_db else upsert_rows(conn, rows, target_table=args.target_table)
        print(f"target_rows: {len(rows)}")
        print(f"upsert_rows: {count}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
