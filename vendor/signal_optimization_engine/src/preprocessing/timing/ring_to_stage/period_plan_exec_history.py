#!/usr/bin/env python3
"""
将海信配时方案 CSV 解析为 dwd_ctl_inter_period_plan_exec_his 标准表，并可写入 MySQL。

默认读取：
  - ../配时方案_2026-04-01.csv

默认输出：
  - standard_tables/dwd_ctl_inter_period_plan_exec_his.csv
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from preprocessing.timing.ring_to_stage.cycle_stage_exec_history import (
    _build_stage_exec_json,
    _format_timestamp,
    _parse_timestamp,
    _read_csv,
    _row_cross_id,
    _row_inter_id,
    _row_signal_controller_id,
)
from preprocessing.timing.ring_to_stage.standard_timing_tables import (
    COMMON_COLUMNS,
    CTRL_MODE_COORD_TIMING,
    CTRL_MODE_TIMING,
    _clean,
    _common,
    _hash_payload,
    _json_dumps,
    _load_stage_timings,
    _pattern_to_plan_no,
    _to_int,
)
from preprocessing.timing.timing_csv_to_stage_table import (
    _get_mysql_connection,
    _quote_identifier,
)

TABLE_CYCLE_STAGE_EXEC_HIS = "dwd_ctl_inter_cycle_stage_exec_his"
TABLE_PERIOD_PLAN_EXEC_HIS = "dwd_ctl_inter_period_plan_exec_his"

PRIMARY_KEY_COLUMNS = {"inter_id", "period_start_time"}

TABLE_COLUMNS = [
    "inter_id",
    "cross_id",
    "signal_controller_id",
    "period_start_time",
    "period_end_time",
    "cycle_len_sec",
    "plan_no",
    "ctrl_mode",
    "stage_exec_json",
    "stage_flow_combo_json",
    "data_source_no",
    "remark",
] + COMMON_COLUMNS


@dataclass(frozen=True)
class PeriodSourceRow:
    row: dict[str, str]
    inter_id: str
    period_start: datetime
    raw_hash: str


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TABLE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _next_midnight(value: datetime) -> datetime:
    return (value + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _load_db_inter_id_map() -> dict[str, str]:
    mapping = {}
    try:
        conn = _get_mysql_connection(streaming=False)
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT inter_id, cross_id, signal_controller_id FROM dwd_ctl_inter_stage_cfg")
            rows = cursor.fetchall()
            for r in rows:
                inter_id = r["inter_id"] if isinstance(r, dict) else r[0]
                cross_id = r["cross_id"] if isinstance(r, dict) else r[1]
                sig_id = r["signal_controller_id"] if isinstance(r, dict) else r[2]
                if inter_id:
                    inter_id = _clean(inter_id)
                    if cross_id:
                        c_id = _clean(cross_id).lstrip("0")
                        if c_id:
                            mapping[c_id] = inter_id
                    if sig_id:
                        s_id = _clean(sig_id).lstrip("0")
                        if s_id:
                            mapping[s_id] = inter_id
        conn.close()
    except Exception as e:
        print("警告：无法从数据库加载路口ID映射关系：", e)
    return mapping


def _load_period_source_rows(
    rows: list[dict[str, str]],
) -> tuple[dict[str, list[PeriodSourceRow]], int, int, int]:
    db_map = _load_db_inter_id_map()
    rows_by_inter: dict[str, list[PeriodSourceRow]] = defaultdict(list)
    seen_pk: set[tuple[str, str]] = set()
    duplicate_count = 0
    inter_id_missing_count = 0
    parse_failed_count = 0

    for row in rows:
        inter_id = _row_inter_id(row)
        if not inter_id:
            for key in ["control_id", "cross_id", "海信id"]:
                val = _clean(row.get(key))
                if val:
                    val_clean = val.lstrip("0")
                    if val_clean in db_map:
                        inter_id = db_map[val_clean]
                        break

        if not inter_id:
            inter_id_missing_count += 1
            continue
        period_start = _parse_timestamp(row.get("request_time") or row.get("sink_time"))
        if period_start is None:
            parse_failed_count += 1
            continue

        period_start_text = _format_timestamp(period_start)
        pk = (inter_id, period_start_text)
        if pk in seen_pk:
            duplicate_count += 1
            continue
        seen_pk.add(pk)

        rows_by_inter[inter_id].append(
            PeriodSourceRow(
                row=row,
                inter_id=inter_id,
                period_start=period_start,
                raw_hash=_hash_payload(row),
            )
        )

    for inter_rows in rows_by_inter.values():
        inter_rows.sort(key=lambda item: item.period_start)

    return rows_by_inter, duplicate_count, inter_id_missing_count, parse_failed_count


def build_period_plan_exec_history_rows(
    input_csv: Path,
    *,
    batch_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ts = _now()
    batch_id = batch_id or f"period_plan_exec_his_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    rows = _read_csv(input_csv)

    rows_by_inter, duplicate_count, inter_id_missing_count, parse_failed_count = _load_period_source_rows(rows)
    output_rows: list[dict[str, Any]] = []
    stage_no_by_inter_and_identity: dict[str, dict[str, int]] = defaultdict(dict)
    mismatch_count = 0

    for inter_id, inter_rows in rows_by_inter.items():
        for idx, source in enumerate(inter_rows):
            row = source.row
            period_start = source.period_start
            next_period_start = (
                inter_rows[idx + 1].period_start
                if idx + 1 < len(inter_rows)
                else _next_midnight(period_start)
            )
            period_end = (
                next_period_start if next_period_start > period_start else _next_midnight(period_start)
            )

            pattern = _to_int(row.get("pattern"))
            plan_no = _pattern_to_plan_no(pattern)
            declared_cycle_len = _to_int(row.get("cycle_len"))
            offset = _to_int(row.get("offset"))
            common = _common(batch_id, source.raw_hash, ts)

            try:
                stage_timings = _load_stage_timings(row)
            except Exception:  # noqa: BLE001
                stage_timings = []
                parse_failed_count += 1

            stage_exec_json, stage_flow_combo_json, stage_total = _build_stage_exec_json(
                cycle_start=period_start,
                stage_timings=stage_timings,
                stage_no_by_identity=stage_no_by_inter_and_identity[inter_id],
            )

            cycle_len = declared_cycle_len or stage_total
            period_len_sec = int((period_end - period_start).total_seconds())
            remarks = [
                f"海信控制ID={_clean(row.get('control_id'))}",
                f"路口名称={_clean(row.get('name'))}",
                f"pattern={pattern}",
                f"period_len_sec={period_len_sec}",
                "由配时方案CSV按同一路口相邻request_time生成时段方案执行历史",
            ]
            if declared_cycle_len and stage_total and declared_cycle_len != stage_total:
                mismatch_count += 1
                remarks.append(f"cycle_len={declared_cycle_len}, stage_total_sum={stage_total}")
            if not stage_timings:
                remarks.append("未解析出阶段执行明细")

            output_rows.append(
                {
                    "inter_id": inter_id,
                    "cross_id": _row_cross_id(row),
                    "signal_controller_id": _row_signal_controller_id(row),
                    "period_start_time": _format_timestamp(period_start),
                    "period_end_time": _format_timestamp(period_end),
                    "cycle_len_sec": cycle_len,
                    "plan_no": plan_no,
                    "ctrl_mode": CTRL_MODE_COORD_TIMING if offset > 0 else CTRL_MODE_TIMING,
                    "stage_exec_json": _json_dumps(stage_exec_json),
                    "stage_flow_combo_json": _json_dumps(stage_flow_combo_json),
                    "data_source_no": 2,
                    "remark": "; ".join(part for part in remarks if part),
                    **common,
                }
            )

    return output_rows, {
        TABLE_PERIOD_PLAN_EXEC_HIS: len(output_rows),
        "input_rows": len(rows),
        "duplicate_rows_skipped": duplicate_count,
        "inter_id_missing_rows_skipped": inter_id_missing_count,
        "parse_failed_rows": parse_failed_count,
        "cycle_stage_sum_mismatch_rows": mismatch_count,
    }


def build_period_plan_exec_history(
    input_csv: Path,
    output_csv: Path,
    *,
    batch_id: str | None = None,
) -> dict[str, int]:
    output_rows, counts = build_period_plan_exec_history_rows(input_csv, batch_id=batch_id)
    _write_csv(output_csv, output_rows)
    return counts


def _build_upsert_sql(table_name: str, columns: list[str]) -> str:
    quoted_columns = ", ".join(_quote_identifier(col) for col in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_columns = [col for col in columns if col not in PRIMARY_KEY_COLUMNS]
    update_clause = ", ".join(
        f"{_quote_identifier(col)}=VALUES({_quote_identifier(col)})" for col in update_columns
    )
    return (
        f"INSERT INTO {_quote_identifier(table_name)} ({quoted_columns}) "
        f"VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )


def _create_period_table_ddl(table_name: str) -> str:
    table_ident = _quote_identifier(table_name)
    return f"""
CREATE TABLE IF NOT EXISTS {table_ident} (
  `inter_id` varchar(16) NOT NULL COMMENT '易出行16位路口编码',
  `cross_id` varchar(12) NOT NULL COMMENT 'GA/T 1049.2路口编号',
  `signal_controller_id` varchar(32) DEFAULT NULL COMMENT '信号机设备编号',
  `period_start_time` timestamp NOT NULL COMMENT '时段开始时间',
  `period_end_time` timestamp NOT NULL COMMENT '时段结束时间',
  `cycle_len_sec` int NOT NULL COMMENT '时段内执行方案周期长度，单位秒',
  `plan_no` int DEFAULT NULL COMMENT '时段执行方案号',
  `ctrl_mode` varchar(2) DEFAULT NULL COMMENT '时段控制方式',
  `stage_exec_json` json NOT NULL COMMENT '时段内单周期阶段执行顺序及各阶段时长快照',
  `stage_flow_combo_json` json DEFAULT NULL COMMENT '时段内各阶段交通流组合快照',
  `data_source_no` tinyint DEFAULT NULL COMMENT '数据来源：1-信控运行信息，2-信号机日志解析，3-灯态反推，9-其他',
  `remark` varchar(512) DEFAULT NULL COMMENT '备注',
  `create_time` datetime DEFAULT NULL,
  `update_time` datetime DEFAULT NULL,
  `is_deleted` tinyint DEFAULT 0,
  PRIMARY KEY (`inter_id`, `period_start_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='路口时段方案执行历史表'
""".strip()


def ensure_period_plan_exec_his_table(
    conn: Any,
    *,
    source_table: str = TABLE_CYCLE_STAGE_EXEC_HIS,
    target_table: str = TABLE_PERIOD_PLAN_EXEC_HIS,
) -> None:
    target_ident = _quote_identifier(target_table)
    with conn.cursor() as cursor:
        try:
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {target_ident} LIKE {_quote_identifier(source_table)}"
            )
        except Exception:  # noqa: BLE001
            cursor.execute(_create_period_table_ddl(target_table))

        cursor.execute(f"SHOW COLUMNS FROM {target_ident}")
        columns = {row["Field"] for row in cursor.fetchall()}
        if "cycle_start_time" in columns and "period_start_time" not in columns:
            cursor.execute(
                f"ALTER TABLE {target_ident} "
                "CHANGE COLUMN `cycle_start_time` `period_start_time` timestamp NOT NULL "
                "COMMENT '时段开始时间'"
            )
        if "cycle_end_time" in columns and "period_end_time" not in columns:
            cursor.execute(
                f"ALTER TABLE {target_ident} "
                "CHANGE COLUMN `cycle_end_time` `period_end_time` timestamp NOT NULL "
                "COMMENT '时段结束时间'"
            )
        cursor.execute(
            f"ALTER TABLE {target_ident} COMMENT = '路口时段方案执行历史表'"
        )
    conn.commit()


def upsert_period_plan_exec_his_rows(
    rows: list[dict[str, Any]],
    *,
    source_table: str = TABLE_CYCLE_STAGE_EXEC_HIS,
    target_table: str = TABLE_PERIOD_PLAN_EXEC_HIS,
) -> int:
    if not rows:
        return 0

    conn = _get_mysql_connection(streaming=False)
    try:
        ensure_period_plan_exec_his_table(
            conn,
            source_table=source_table,
            target_table=target_table,
        )
        values = [tuple(row.get(col) for col in TABLE_COLUMNS) for row in rows]
        sql = _build_upsert_sql(target_table, TABLE_COLUMNS)
        with conn.cursor() as cursor:
            cursor.executemany(sql, values)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def main() -> None:
    from env import load_project_env

    load_project_env()
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="海信配时方案CSV解析为路口时段方案执行历史表，并写入MySQL"
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=base_dir.parent / "配时方案_2026-04-01.csv",
        help="配时方案CSV路径",
    )
    parser.add_argument(
        "-o",
        "--output-csv",
        type=Path,
        default=base_dir / "standard_tables" / f"{TABLE_PERIOD_PLAN_EXEC_HIS}.csv",
        help="标准表CSV输出路径",
    )
    parser.add_argument("--batch-id", help="批次ID；默认按运行时间生成")
    parser.add_argument(
        "--source-table",
        default=TABLE_CYCLE_STAGE_EXEC_HIS,
        help="参考建表的周期阶段执行历史表名",
    )
    parser.add_argument(
        "--target-table",
        default=TABLE_PERIOD_PLAN_EXEC_HIS,
        help="写入的时段方案执行历史表名",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="仅生成CSV，不写入MySQL",
    )
    args = parser.parse_args()

    rows, counts = build_period_plan_exec_history_rows(args.input_csv, batch_id=args.batch_id)
    _write_csv(args.output_csv, rows)
    print(f"已写入标准表: {args.output_csv}")
    for name, count in counts.items():
        print(f"- {name}: {count}")

    if args.skip_db:
        return

    db_count = upsert_period_plan_exec_his_rows(
        rows,
        source_table=args.source_table,
        target_table=args.target_table,
    )
    print(f"已写入MySQL表: {args.target_table}，共 {db_count} 条")


if __name__ == "__main__":
    main()
