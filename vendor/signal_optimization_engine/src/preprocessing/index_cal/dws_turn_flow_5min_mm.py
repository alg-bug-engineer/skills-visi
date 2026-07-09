#!/usr/bin/env python3
"""生成优化输入转向流量表 dws_turn_flow_5min_mm。"""

from __future__ import annotations

import argparse
import os
from typing import Any

from preprocessing.timing.dir8_encoding import dir4_code_from_dir8_no
from data.mysql_reader import connect_mysql
from data.pg_reader import connect_pg, fetch_turn_flow_stats
from preprocessing.timing.timing_csv_to_stage_table import _quote_identifier

FIVE_MIN_TO_HOURLY = 12.0


def _pg_qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

TABLE_TARGET = "dws_turn_flow_5min_mm"
TARGET_COLUMNS = [
    "inter_id",
    "link_id",
    "turn_dir_no",
    "day_of_week",
    "step_index",
    "inter_name",
    "dir8_code",
    "dir4_code",
    "lane_count",
    "turn_flow_total",
    "critical_lane_flow",
    "sample_count",
    "flow_date_start",
    "flow_date_end",
    "aggregation_method",
    "calc_version",
    "is_deleted",
]


def ensure_target_table(conn: Any, table_name: str = TABLE_TARGET) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
CREATE TABLE IF NOT EXISTS {_quote_identifier(table_name)} (
  `inter_id` varchar(16) NOT NULL,
  `link_id` varchar(32) NOT NULL,
  `turn_dir_no` tinyint NOT NULL,
  `day_of_week` tinyint NOT NULL,
  `step_index` smallint NOT NULL,
  `inter_name` varchar(128) DEFAULT NULL,
  `dir8_code` int DEFAULT NULL,
  `dir4_code` int DEFAULT NULL,
  `lane_count` int DEFAULT NULL,
  `turn_flow_total` decimal(10,1) NOT NULL,
  `critical_lane_flow` decimal(10,1) DEFAULT NULL,
  `sample_count` int NOT NULL DEFAULT 0,
  `flow_date_start` varchar(8) DEFAULT NULL,
  `flow_date_end` varchar(8) DEFAULT NULL,
  `aggregation_method` varchar(64) NOT NULL DEFAULT 'historical_mean_5min',
  `calc_version` varchar(64) NOT NULL DEFAULT 'turn_flow_v1',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_deleted` tinyint NOT NULL DEFAULT 0,
  PRIMARY KEY (`inter_id`, `link_id`, `turn_dir_no`, `day_of_week`, `step_index`),
  KEY `idx_inter_day_step` (`inter_id`, `day_of_week`, `step_index`),
  KEY `idx_inter_turn` (`inter_id`, `link_id`, `turn_dir_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='优化输入转向流量表：按进口转向+5分钟时间片存储总流量与关键车道流量'
""".strip()
        )
    conn.commit()


def build_rows_from_inter_link_turn_flow(
    pg_conn: Any,
    *,
    inter_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """从 PG dws_inter_link_turn_flow_5min_mm 同步（历史均值口径，单次查询）。"""
    flow_schema = os.getenv("PG_FLOW_SCHEMA", "xianchang")
    turn_flow_table = os.getenv("PG_TURN_FLOW_TABLE", "dws_inter_link_turn_flow_5min_mm")
    qualified = f"{_pg_qident(flow_schema)}.{_pg_qident(turn_flow_table)}"
    clause = ""
    params: list[Any] = []
    if inter_ids:
        clause = " AND inter_id::text = ANY(%s)"
        params.append(inter_ids)
    with pg_conn.cursor() as cur:
        cur.execute(
            f"""
SELECT
    inter_id::text AS inter_id,
    link_id::text AS link_id,
    turn_dir_no::int AS turn_dir_no,
    day_of_week::int AS day_of_week,
    step_index::int AS step_index,
    inter_name,
    dir8_code::int AS dir8_code,
    turn_flow_total::float AS turn_flow_total,
    avg_lane_flow_5min::float AS avg_lane_flow_5min,
    lane_count::int AS lane_count,
    sample_count::int AS sample_count,
    flow_date_start::text AS flow_date_start,
    flow_date_end::text AS flow_date_end
FROM {qualified}
WHERE COALESCE(is_deleted, 0) = 0
  AND turn_dir_no IN (1, 2, 3)
  {clause}
ORDER BY inter_id, link_id, turn_dir_no, day_of_week, step_index
""".strip(),
            params,
        )
        source_rows = cur.fetchall()

    rows: list[dict[str, Any]] = []
    for row in source_rows:
        avg_lane_flow = float(row.get("avg_lane_flow_5min") or 0)
        rows.append(
            {
                "inter_id": row["inter_id"],
                "link_id": row["link_id"],
                "turn_dir_no": row["turn_dir_no"],
                "day_of_week": row["day_of_week"],
                "step_index": row["step_index"],
                "inter_name": row.get("inter_name"),
                "dir8_code": row.get("dir8_code"),
                "dir4_code": dir4_code_from_dir8_no(row.get("dir8_code")),
                "lane_count": row.get("lane_count"),
                "turn_flow_total": round(float(row.get("turn_flow_total") or 0), 1),
                "critical_lane_flow": round(avg_lane_flow * FIVE_MIN_TO_HOURLY, 1) if avg_lane_flow > 0 else None,
                "sample_count": int(row.get("sample_count") or 0),
                "flow_date_start": row.get("flow_date_start"),
                "flow_date_end": row.get("flow_date_end"),
                "aggregation_method": "historical_mean_5min",
                "calc_version": "turn_flow_v1",
                "is_deleted": 0,
            }
        )
    return rows


def build_rows_live(
    pg_conn: Any,
    *,
    inter_ids: list[str],
    date: str | None = None,
    day_of_week: int = 1,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for inter_id in inter_ids:
        for step_index in range(288):
            start = _step_to_hhmm(step_index)
            end = _step_to_hhmm(step_index + 1)
            stats = fetch_turn_flow_stats(pg_conn, inter_id, date=date, windows=[(start, end)])
            for item in stats.get("flows") or []:
                link_id = _link_id_for_dir(stats.get("laneGroups") or [], item.get("dir8No"), item.get("turnDirNo"))
                if not link_id:
                    link_id = f"dir8:{item.get('dir8Code')}"
                rows.append(
                    {
                        "inter_id": inter_id,
                        "link_id": link_id,
                        "turn_dir_no": item.get("turnDirNo"),
                        "day_of_week": day_of_week,
                        "step_index": step_index,
                        "inter_name": stats.get("interName"),
                        "dir8_code": item.get("dir8Code"),
                        "dir4_code": dir4_code_from_dir8_no(item.get("dir8Code")),
                        "lane_count": item.get("observedLaneCount"),
                        "turn_flow_total": item.get("flowVph") or 0,
                        "critical_lane_flow": item.get("criticalLaneVph"),
                        "sample_count": 1 if stats.get("observedMinutes") else 0,
                        "flow_date_start": stats.get("date"),
                        "flow_date_end": stats.get("date"),
                        "aggregation_method": "historical_mean_5min",
                        "calc_version": "turn_flow_v1",
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
        if col not in {"inter_id", "link_id", "turn_dir_no", "day_of_week", "step_index"}
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


def _link_id_for_dir(lane_groups: list[dict[str, Any]], dir8_no: Any, turn_dir_no: Any) -> str:
    for group in lane_groups:
        if group.get("dir8No") == dir8_no and group.get("turnDirNo") == turn_dir_no:
            return str(group.get("linkId") or "")
    return ""


def _step_to_hhmm(step: int) -> str:
    minutes = min(max(step, 0), 288) * 5
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _list_inter_ids(conn: Any) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT inter_id FROM dwd_ctl_inter_plan_cfg WHERE is_deleted = 0 ORDER BY inter_id")
        return [str(row["inter_id"]) for row in cur.fetchall()]


def main() -> None:
    try:
        from env import load_project_env

        load_project_env()
    except ModuleNotFoundError:
        pass
    parser = argparse.ArgumentParser(description="生成优化输入转向流量表")
    parser.add_argument("--inter-id", action="append")
    parser.add_argument(
        "--source",
        choices=("inter-link-flow", "live-pg-lanes"),
        default="inter-link-flow",
        help="inter-link-flow=从 PG dws_inter_link_turn_flow_5min_mm 同步（默认）；"
        "live-pg-lanes=逐时间片查 PG 原始车道流量（慢）",
    )
    parser.add_argument("--date", help="live-pg-lanes 模式：流量日期 YYYYMMDD")
    parser.add_argument("--day-of-week", type=int, default=1, help="live-pg-lanes 模式：星期几")
    parser.add_argument("--target-table", default=TABLE_TARGET)
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()
    mysql_conn = connect_mysql()
    pg_conn = connect_pg()
    try:
        inter_ids = args.inter_id or _list_inter_ids(mysql_conn)
        if args.source == "inter-link-flow":
            rows = build_rows_from_inter_link_turn_flow(pg_conn, inter_ids=inter_ids or None)
        else:
            rows = build_rows_live(
                pg_conn,
                inter_ids=inter_ids,
                date=args.date,
                day_of_week=args.day_of_week,
            )
        count = 0 if args.skip_db else upsert_rows(mysql_conn, rows, target_table=args.target_table)
        print(f"source: {args.source}")
        print(f"target_rows: {len(rows)}")
        print(f"upsert_rows: {count}")
    finally:
        mysql_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
