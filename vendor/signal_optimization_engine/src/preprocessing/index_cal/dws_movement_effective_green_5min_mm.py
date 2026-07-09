#!/usr/bin/env python3
"""生成 movementKey 级有效绿灯表 dws_movement_effective_green_5min_mm。"""

from __future__ import annotations

import argparse
import json
from typing import Any

from data.mysql_reader import fetch_phase_plan_request, fetch_plan_periods
from preprocessing.timing.flow_green_consistency import effective_green_by_movement
from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection, _quote_identifier

TABLE_TARGET = "dws_movement_effective_green_5min_mm"
TABLE_LANE_PHASE_MAPPING = "dwd_ctl_inter_plan_lane_phase_mapping"
TARGET_COLUMNS = [
    "inter_id",
    "movement_key",
    "day_of_week",
    "step_index",
    "plan_no",
    "link_id",
    "turn_dir_no",
    "effective_green_s",
    "stage_nos_json",
    "green_source",
    "calc_version",
    "is_deleted",
]


def ensure_target_table(conn: Any, table_name: str = TABLE_TARGET) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
CREATE TABLE IF NOT EXISTS {_quote_identifier(table_name)} (
  `inter_id` varchar(16) NOT NULL,
  `movement_key` varchar(128) NOT NULL,
  `day_of_week` tinyint NOT NULL,
  `step_index` smallint NOT NULL,
  `plan_no` int DEFAULT NULL,
  `link_id` varchar(32) DEFAULT NULL,
  `turn_dir_no` tinyint DEFAULT NULL,
  `effective_green_s` decimal(8,1) NOT NULL,
  `stage_nos_json` json DEFAULT NULL,
  `green_source` varchar(32) NOT NULL DEFAULT 'plan',
  `calc_version` varchar(64) NOT NULL DEFAULT 'movement_effective_green_v1',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_deleted` tinyint NOT NULL DEFAULT 0,
  PRIMARY KEY (`inter_id`, `movement_key`, `day_of_week`, `step_index`),
  KEY `idx_inter_day_step` (`inter_id`, `day_of_week`, `step_index`),
  KEY `idx_inter_plan` (`inter_id`, `plan_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='movementKey 级有效绿灯聚合表'
""".strip()
        )
    conn.commit()


def build_rows(conn: Any, *, inter_id: str | None = None, green_source: str = "plan") -> list[dict[str, Any]]:
    inter_ids = [inter_id] if inter_id else _list_inter_ids(conn)
    rows: list[dict[str, Any]] = []
    for iid in inter_ids:
        periods = fetch_plan_periods(conn, iid)
        lane_phase_rows = _build_rows_from_lane_phase_mapping(
            conn,
            inter_id=iid,
            periods=periods,
            green_source="lane_phase_mapping" if green_source == "plan" else green_source,
        )
        if lane_phase_rows:
            rows.extend(lane_phase_rows)
            continue

        request = fetch_phase_plan_request(conn, iid)
        for plan in request.get("phasePlanOfTimeList") or []:
            plan_no = plan.get("planNo")
            movement_green = effective_green_by_movement(plan.get("phaseStageInfoList") or [])
            movement_meta = _movement_meta(plan.get("phaseStageInfoList") or [])
            steps = sorted(_windows_to_steps(periods.get(plan_no) or [("00:00", "24:00")]))
            for day_of_week in range(1, 8):
                for step_index in steps:
                    for movement_key, green_s in movement_green.items():
                        meta = movement_meta.get(movement_key) or {}
                        rows.append(
                            {
                                "inter_id": iid,
                                "movement_key": movement_key,
                                "day_of_week": day_of_week,
                                "step_index": step_index,
                                "plan_no": plan_no,
                                "link_id": meta.get("link_id"),
                                "turn_dir_no": meta.get("turn_dir_no"),
                                "effective_green_s": round(green_s, 1),
                                "stage_nos_json": json.dumps(meta.get("stage_nos") or [], ensure_ascii=False),
                                "green_source": green_source,
                                "calc_version": "movement_effective_green_v1",
                                "is_deleted": 0,
                            }
                        )
    return rows


def _build_rows_from_lane_phase_mapping(
    conn: Any,
    *,
    inter_id: str,
    periods: dict[int, list[tuple[str, str]]],
    green_source: str,
) -> list[dict[str, Any]]:
    if not _table_exists(conn, TABLE_LANE_PHASE_MAPPING):
        return []
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT plan_no, movement_key, link_id, turn_dir_no,
                   CAST(stage_nos_json AS CHAR) AS stage_nos_json
            FROM {_quote_identifier(TABLE_LANE_PHASE_MAPPING)}
            WHERE COALESCE(is_deleted, 0) = 0
              AND inter_id = %s
              AND is_controlled = 1
              AND confidence IN ('high', 'medium')
              AND COALESCE(movement_key, '') <> ''
            ORDER BY plan_no, movement_key
            """,
            (inter_id,),
        )
        mapping_rows = list(cur.fetchall())
        cur.execute(
            """
            SELECT plan_no, stage_no, green_sec
            FROM dwd_ctl_inter_plan_stage_timing
            WHERE COALESCE(is_deleted, 0) = 0
              AND inter_id = %s
            """,
            (inter_id,),
        )
        timing_rows = list(cur.fetchall())
    if not mapping_rows:
        return []

    green_by_plan_stage = {
        (_to_int(row.get("plan_no")), _to_int(row.get("stage_no"))): float(row.get("green_sec") or 0)
        for row in timing_rows
        if _to_int(row.get("plan_no")) is not None and _to_int(row.get("stage_no")) is not None
    }
    movement_meta: dict[tuple[int, str], dict[str, Any]] = {}
    for row in mapping_rows:
        plan_no = _to_int(row.get("plan_no"))
        movement_key = str(row.get("movement_key") or "")
        if plan_no is None or not movement_key:
            continue
        meta = movement_meta.setdefault(
            (plan_no, movement_key),
            {
                "link_id": row.get("link_id"),
                "turn_dir_no": _to_int(row.get("turn_dir_no")),
                "stage_nos": set(),
            },
        )
        for stage_no in _parse_json_int_list(row.get("stage_nos_json")):
            meta["stage_nos"].add(stage_no)
    rows: list[dict[str, Any]] = []
    for (plan_no, movement_key), meta in movement_meta.items():
        stage_nos = sorted(meta["stage_nos"])
        effective_green_s = sum(green_by_plan_stage.get((plan_no, stage_no), 0.0) for stage_no in stage_nos)
        steps = sorted(_windows_to_steps(periods.get(plan_no) or [("00:00", "24:00")]))
        for day_of_week in range(1, 8):
            for step_index in steps:
                rows.append(
                    {
                        "inter_id": inter_id,
                        "movement_key": movement_key,
                        "day_of_week": day_of_week,
                        "step_index": step_index,
                        "plan_no": plan_no,
                        "link_id": meta.get("link_id"),
                        "turn_dir_no": meta.get("turn_dir_no"),
                        "effective_green_s": round(effective_green_s, 1),
                        "stage_nos_json": json.dumps(stage_nos, ensure_ascii=False),
                        "green_source": green_source,
                        "calc_version": "movement_effective_green_v2",
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
        if col not in {"inter_id", "movement_key", "day_of_week", "step_index"}
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


def _movement_meta(stages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for stage in stages:
        for item in stage.get("phaseDirInfoDTOList") or []:
            movement_key = item.get("movementKey")
            if not movement_key:
                continue
            meta = out.setdefault(
                str(movement_key),
                {
                    "link_id": item.get("fromLinkId"),
                    "turn_dir_no": item.get("turnDirNo"),
                    "stage_nos": [],
                },
            )
            stage_no = stage.get("stageNo")
            if stage_no not in meta["stage_nos"]:
                meta["stage_nos"].append(stage_no)
    return out


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
    return int(parts[0]) * 60 + int(parts[1])


def _table_exists(conn: Any, table_name: str) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE %s", (table_name,))
            return cur.fetchone() is not None
    except Exception:
        return False


def _parse_json_int_list(value: Any) -> list[int]:
    if value in (None, ""):
        return []
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[int] = []
    for item in parsed:
        parsed_int = _to_int(item)
        if parsed_int is not None:
            out.append(parsed_int)
    return out


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass
    parser = argparse.ArgumentParser(description="生成 movementKey 级有效绿灯表")
    parser.add_argument("--inter-id")
    parser.add_argument("--green-source", choices=["plan", "lane_phase_mapping", "exec_history"], default="plan")
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()
    conn = _get_mysql_connection(streaming=False)
    try:
        rows = build_rows(conn, inter_id=args.inter_id, green_source=args.green_source)
        count = 0 if args.skip_db else upsert_rows(conn, rows, target_table=args.target_table)
        print(f"target_rows: {len(rows)}")
        print(f"upsert_rows: {count}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
