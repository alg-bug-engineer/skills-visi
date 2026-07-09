#!/usr/bin/env python3
"""
将海信配时方案 CSV 解析为 dwd_ctl_inter_cycle_stage_exec_his 标准表 CSV。

默认读取：
  - ../配时方案_2026-04-01.csv

默认输出：
  - standard_tables/dwd_ctl_inter_cycle_stage_exec_his.csv
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from preprocessing.timing.ring_to_stage.standard_timing_tables import (
    COMMON_COLUMNS,
    CTRL_MODE_COORD_TIMING,
    CTRL_MODE_TIMING,
    StageTiming,
    _clean,
    _common,
    _cross_id,
    _hash_payload,
    _json_dumps,
    _load_stage_timings,
    _pattern_to_plan_no,
    _source_inter_id,
    _stage_flow_combo,
    _stage_identity,
    _to_int,
)

TABLE_CYCLE_STAGE_EXEC_HIS = "dwd_ctl_inter_cycle_stage_exec_his"

TABLE_COLUMNS = [
    "inter_id",
    "cross_id",
    "signal_controller_id",
    "cycle_start_time",
    "cycle_end_time",
    "cycle_len_sec",
    "plan_no",
    "ctrl_mode",
    "stage_exec_json",
    "stage_flow_combo_json",
    "data_source_no",
    "remark",
] + COMMON_COLUMNS


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TABLE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _parse_timestamp(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _row_inter_id(row: dict[str, str]) -> str:
    return _source_inter_id(row, "control_id", "海信id", "cross_id")


def _row_cross_id(row: dict[str, str]) -> str:
    source = row.get("cross_id") or row.get("control_id") or row.get("海信id")
    text = _clean(source)
    if text and not text.isdigit():
        return text[:12]
    return _cross_id(text)


def _row_signal_controller_id(row: dict[str, str]) -> str:
    return _clean(row.get("control_id") or row.get("signal_controller_id"))


def _build_stage_exec_json(
    *,
    cycle_start: datetime,
    stage_timings: list[StageTiming],
    stage_no_by_identity: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    stage_exec_rows: list[dict[str, Any]] = []
    stage_flow_rows: list[dict[str, Any]] = []
    elapsed = 0

    for seq_no, stage_timing in enumerate(stage_timings, start=1):
        identity = _stage_identity(stage_timing.desc)
        if identity not in stage_no_by_identity:
            stage_no_by_identity[identity] = len(stage_no_by_identity) + 1
        stage_no = stage_no_by_identity[identity]

        stage_len = stage_timing.total_sec
        stage_start = cycle_start + timedelta(seconds=elapsed)
        stage_end = stage_start + timedelta(seconds=stage_len)
        elapsed += stage_len

        stage_exec_rows.append(
            {
                "stage_exec_seq_no": seq_no,
                "stage_no": stage_no,
                "stage_start_time": _format_timestamp(stage_start),
                "stage_end_time": _format_timestamp(stage_end),
                "stage_exec_len_sec": stage_len,
                "green_exec_sec": stage_timing.green_sec,
                "yellow_exec_sec": stage_timing.yellow_sec,
                "all_red_exec_sec": stage_timing.all_red_sec,
            }
        )
        stage_flow_rows.append(
            {
                "stage_exec_seq_no": seq_no,
                "stage_no": stage_no,
                "flow_combo": _stage_flow_combo(stage_timing.desc),
            }
        )

    return stage_exec_rows, stage_flow_rows, elapsed


def build_cycle_stage_exec_history(
    input_csv: Path,
    output_csv: Path,
    *,
    batch_id: str | None = None,
) -> dict[str, int]:
    ts = _now()
    batch_id = batch_id or f"cycle_stage_exec_his_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    rows = _read_csv(input_csv)

    output_rows: list[dict[str, Any]] = []
    stage_no_by_inter_and_identity: dict[str, dict[str, int]] = defaultdict(dict)
    seen_pk: set[tuple[str, str]] = set()
    duplicate_count = 0
    inter_id_missing_count = 0
    parse_failed_count = 0
    mismatch_count = 0

    for row in rows:
        raw_hash = _hash_payload(row)
        common = _common(batch_id, raw_hash, ts)
        inter_id = _row_inter_id(row)
        if not inter_id:
            inter_id_missing_count += 1
            continue
        cross_id = _row_cross_id(row)
        cycle_start = _parse_timestamp(row.get("request_time") or row.get("sink_time"))
        if cycle_start is None:
            parse_failed_count += 1
            continue

        cycle_start_text = _format_timestamp(cycle_start)
        pk = (inter_id, cycle_start_text)
        if pk in seen_pk:
            duplicate_count += 1
            continue
        seen_pk.add(pk)

        pattern = _to_int(row.get("pattern"))
        plan_no = _pattern_to_plan_no(pattern)
        declared_cycle_len = _to_int(row.get("cycle_len"))
        offset = _to_int(row.get("offset"))

        try:
            stage_timings = _load_stage_timings(row)
        except Exception:  # noqa: BLE001
            stage_timings = []
            parse_failed_count += 1

        stage_exec_json, stage_flow_combo_json, stage_total = _build_stage_exec_json(
            cycle_start=cycle_start,
            stage_timings=stage_timings,
            stage_no_by_identity=stage_no_by_inter_and_identity[inter_id],
        )

        cycle_len = declared_cycle_len or stage_total
        cycle_end = cycle_start + timedelta(seconds=cycle_len)

        remarks = [
            f"海信控制ID={_clean(row.get('control_id'))}",
            f"路口名称={_clean(row.get('name'))}",
            f"pattern={pattern}",
            "由配时方案CSV按request_time和Ring-Barrier阶段仿真生成",
        ]
        if declared_cycle_len and stage_total and declared_cycle_len != stage_total:
            mismatch_count += 1
            remarks.append(f"cycle_len={declared_cycle_len}, stage_total_sum={stage_total}")
        if not stage_timings:
            remarks.append("未解析出阶段执行明细")

        output_rows.append(
            {
                "inter_id": inter_id,
                "cross_id": cross_id,
                "signal_controller_id": _row_signal_controller_id(row),
                "cycle_start_time": cycle_start_text,
                "cycle_end_time": _format_timestamp(cycle_end),
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

    _write_csv(output_csv, output_rows)
    return {
        TABLE_CYCLE_STAGE_EXEC_HIS: len(output_rows),
        "input_rows": len(rows),
        "duplicate_rows_skipped": duplicate_count,
        "inter_id_missing_rows_skipped": inter_id_missing_count,
        "parse_failed_rows": parse_failed_count,
        "cycle_stage_sum_mismatch_rows": mismatch_count,
    }


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="海信配时方案CSV解析为路口周期阶段实际执行历史标准表CSV"
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
        default=base_dir / "standard_tables" / f"{TABLE_CYCLE_STAGE_EXEC_HIS}.csv",
        help="标准表CSV输出路径",
    )
    parser.add_argument("--batch-id", help="批次ID；默认按运行时间生成")
    args = parser.parse_args()

    counts = build_cycle_stage_exec_history(
        args.input_csv,
        args.output_csv,
        batch_id=args.batch_id,
    )
    print(f"已写入标准表: {args.output_csv}")
    for name, count in counts.items():
        print(f"- {name}: {count}")


if __name__ == "__main__":
    main()
