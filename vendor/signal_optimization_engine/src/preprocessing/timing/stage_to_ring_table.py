#!/usr/bin/env python3
"""
阶段形式配时方案还原为海信 Ring-Barrier 结构方案。

阶段形式只描述“第几个阶段放哪些流向、持续多久”，通常已经丢失原始多环、
屏障、黄灯、全红和跟随相位等细节。本脚本采用可回放的保守还原：
  - 每个阶段生成一个相位；
  - 使用单 Ring 顺序相位结构：{"Cycle1": "1 2 3 ..."}；
  - 阶段全部流向编码到对应相位的 channelDim；
  - 默认将阶段时长写入 greenTime，yellowTime/redTime 为 0。

因此，生成结果再经过 timing_csv_to_stage_table.py 转换时，可复现阶段顺序、
阶段方向和阶段总时长，但不声称恢复原始厂家多环细节。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from preprocessing.timing.timing_csv_to_stage_table import (
    CYCLE_COLUMN_ALIASES,
    DIRECTION_NAME,
    OVERLAP_COLUMN_ALIASES,
    PHASE_COLUMN_ALIASES,
    TARGET_STAGE_DIRECTION_COLUMN,
    TARGET_STAGE_TIME_COLUMN,
    TURN_SHORT,
    _get_mysql_connection,
    _quote_identifier,
    turn_map,
)

DEFAULT_SOURCE_TABLE = "ods_ctl_inter_scheme_hisense_stage"
DEFAULT_TARGET_TABLE = "ods_ctl_inter_scheme_hisense_ring_rebuilt"

STAGE_DIRECTION_COLUMN_ALIASES = (TARGET_STAGE_DIRECTION_COLUMN, "阶段方向描述")
STAGE_TIME_COLUMN_ALIASES = (TARGET_STAGE_TIME_COLUMN, "阶段时间")
DEFAULT_CYCLE_COLUMN = CYCLE_COLUMN_ALIASES[0]
DEFAULT_PHASE_COLUMN = PHASE_COLUMN_ALIASES[0]
DEFAULT_OVERLAP_COLUMN = OVERLAP_COLUMN_ALIASES[0]

_DIRECTION_TO_INTERNAL_CODE = {name: code for code, name in DIRECTION_NAME.items()}
_VENDOR_DIRECTION_CODE_BY_INTERNAL = {
    internal_code: vendor_code
    for vendor_code, internal_code in {
        0: 0,
        1: 2,
        2: 4,
        3: 6,
        4: 1,
        5: 3,
        6: 5,
        7: 7,
    }.items()
}
_TURN_CODE_BY_SHORT = {short: code for code, short in TURN_SHORT.items()}
_CHANNEL_TURN_INDEX_BY_CODE = {turn_code: idx for idx, turn_code in turn_map.items()}
_DIRECTION_NAMES_BY_LENGTH = sorted(_DIRECTION_TO_INTERNAL_CODE, key=len, reverse=True)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    return False


def _clean(value: object) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _to_int(value: object, default: int = 0) -> int:
    text = _clean(value)
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def _resolve_column(fieldnames: list[str] | set[str], aliases: tuple[str, ...]) -> str | None:
    for name in aliases:
        if name in fieldnames:
            return name
    return None


def _parse_json_cell(value: object, *, default: Any) -> Any:
    if _is_missing(value):
        return default
    if isinstance(value, (list, dict)):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _normalize_stage_dirs(value: object) -> list[list[str]]:
    parsed = _parse_json_cell(value, default=[])
    if not isinstance(parsed, list):
        return []
    stages: list[list[str]] = []
    for item in parsed:
        if isinstance(item, list):
            stages.append([_clean(atom) for atom in item if _clean(atom)])
        elif isinstance(item, str):
            text = item.strip()
            stages.append([text] if text else [])
        else:
            stages.append([])
    return stages


def _normalize_stage_times(value: object, stage_count: int) -> list[int]:
    parsed = _parse_json_cell(value, default=[])
    if not isinstance(parsed, list):
        parsed = []
    times = [_to_int(item) for item in parsed]
    while len(times) < stage_count:
        times.append(0)
    return times[:stage_count]


def _split_atom(atom: str) -> tuple[str, str] | None:
    text = atom.strip()
    if not text:
        return None
    for direction in _DIRECTION_NAMES_BY_LENGTH:
        if text.startswith(direction):
            turn = text[len(direction) :]
            if turn:
                return direction, turn
    return None


def _channel_byte_for_atom(atom: str) -> int | None:
    split = _split_atom(atom)
    if not split:
        return None
    direction, turn_short = split
    internal_direction_code = _DIRECTION_TO_INTERNAL_CODE.get(direction)
    if internal_direction_code is None:
        return None
    vendor_direction_code = _VENDOR_DIRECTION_CODE_BY_INTERNAL.get(internal_direction_code)
    if vendor_direction_code is None:
        return None
    turn_code = _TURN_CODE_BY_SHORT.get(turn_short)
    if turn_code is None:
        return None
    turn_index = _CHANNEL_TURN_INDEX_BY_CODE.get(turn_code)
    if turn_index is None:
        return None
    return (vendor_direction_code << 5) | turn_index


def encode_channel_dim(atoms: list[str]) -> int:
    """把一个阶段内的多个流向原子编码为海信 channelDim 整数。"""
    value = 0
    seen: set[int] = set()
    for atom in atoms:
        byte = _channel_byte_for_atom(atom)
        if byte is None or byte in seen:
            continue
        seen.add(byte)
        value = (value << 8) | byte
    return value


def _format_fixed_width(values: list[object], size: int = 16) -> str:
    padded = values[:size] + [0] * max(0, size - len(values))
    return " ".join(str(v) for v in padded[:size])


def build_ring_fields(
    stage_dirs: list[list[str]],
    stage_times: list[int],
    *,
    yellow_sec: int = 0,
    all_red_sec: int = 0,
) -> tuple[str, str]:
    if len(stage_dirs) > 16:
        raise ValueError("海信 phase_list 仅支持 16 个相位，阶段数不能超过 16")

    phase_count = len(stage_dirs)
    cycle_json = json.dumps(
        {"Cycle1": " ".join(str(i) for i in range(1, phase_count + 1))},
        ensure_ascii=False,
    )

    channel_dims = [encode_channel_dim(stage) for stage in stage_dirs]
    yellow = max(0, yellow_sec)
    red = max(0, all_red_sec)
    green_times = [max(0, stage_times[i] - yellow - red) for i in range(phase_count)]
    yellow_times = [yellow if stage_times[i] > 0 else 0 for i in range(phase_count)]
    red_times = [red if stage_times[i] > 0 else 0 for i in range(phase_count)]
    directions = ["0" if channel_dims[i] else " ".join(stage_dirs[i]) for i in range(phase_count)]

    phase_json = json.dumps(
        [
            {
                "channelDim": _format_fixed_width(channel_dims),
                "direction": _format_fixed_width(directions, size=16),
                "greenTime": _format_fixed_width(green_times),
                "yellowTime": _format_fixed_width(yellow_times),
                "redTime": _format_fixed_width(red_times),
            }
        ],
        ensure_ascii=False,
    )
    return cycle_json, phase_json


def _split_fixed_width_ints(value: object, size: int = 16) -> list[int]:
    values = [_to_int(part) for part in _clean(value).split()]
    while len(values) < size:
        values.append(0)
    return values[:size]


def _stage_seq_no(row: dict[str, Any], default: int) -> int:
    return _to_int(row.get("stage_seq_no"), default=default)


def _stage_total(row: dict[str, Any]) -> tuple[int, int, int]:
    yellow = _to_int(row.get("yellow_sec"))
    red = _to_int(row.get("all_red_sec"))
    green = _to_int(row.get("green_sec"))
    if green <= 0:
        total = _to_int(row.get("stage_total_sec"))
        if total > 0:
            green = max(0, total - yellow - red)
    return green, yellow, red


def _is_active_green_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _to_int(value, default=1) != 0


def _phase_ref_ring_no(row: dict[str, Any]) -> int:
    ring_no = _to_int(row.get("ring_no"))
    return ring_no if ring_no > 0 else 1


def _phase_ref_phase_seq_no(row: dict[str, Any]) -> int:
    seq_no = _to_int(row.get("phase_seq_no"))
    if seq_no > 0:
        return seq_no
    return _to_int(row.get("source_no"))


def _dedupe_phase_refs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_phase: dict[int, dict[str, Any]] = {}
    for row in rows:
        phase_no = _to_int(row.get("source_no"))
        if not 1 <= phase_no <= 16:
            continue
        existing = by_phase.get(phase_no)
        if existing is None or (
            _is_active_green_value(row.get("is_active_green"))
            and not _is_active_green_value(existing.get("is_active_green"))
        ):
            by_phase[phase_no] = row
    return sorted(by_phase.values(), key=lambda item: (_phase_ref_phase_seq_no(item), _to_int(item.get("source_no"))))


def _allocate_int_by_weights(amount: int, phase_nos: list[int], weights: list[int]) -> dict[int, int]:
    if amount <= 0 or not phase_nos:
        return {}
    cleaned_weights = [max(0, int(weight)) for weight in weights]
    if sum(cleaned_weights) <= 0:
        cleaned_weights = [1] * len(phase_nos)
    total_weight = sum(cleaned_weights)
    raw_values = [amount * weight / total_weight for weight in cleaned_weights]
    allocations = [int(math.floor(value)) for value in raw_values]
    remainder = amount - sum(allocations)
    order = sorted(
        range(len(phase_nos)),
        key=lambda idx: (raw_values[idx] - allocations[idx], cleaned_weights[idx], -idx),
        reverse=True,
    )
    for idx in order[:remainder]:
        allocations[idx] += 1
    return {phase_no: allocations[idx] for idx, phase_no in enumerate(phase_nos)}


def _phase_total_from_arrays(
    phase_no: int,
    green_times: list[int],
    yellow_times: list[int],
    red_times: list[int],
) -> int:
    idx = phase_no - 1
    if idx < 0 or idx >= len(green_times):
        return 0
    yellow = yellow_times[idx] if idx < len(yellow_times) else 0
    red = red_times[idx] if idx < len(red_times) else 0
    return green_times[idx] + yellow + red


def _phase_refs_by_ring(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    refs_by_ring: dict[int, list[dict[str, Any]]] = {}
    for ref_row in rows:
        refs_by_ring.setdefault(_phase_ref_ring_no(ref_row), []).append(ref_row)
    return {
        ring_no: _dedupe_phase_refs(ref_rows)
        for ring_no, ref_rows in refs_by_ring.items()
        if ref_rows
    }


def _stage_dirs_from_rows(rows: list[dict[str, Any]]) -> list[list[str]]:
    stage_dirs: list[list[str]] = []
    for row in sorted(rows, key=lambda item: _stage_seq_no(item, len(stage_dirs) + 1)):
        for key in ("stage_desc", TARGET_STAGE_DIRECTION_COLUMN, "stage_direction_desc", "阶段方向描述"):
            if key not in row:
                continue
            value = row.get(key)
            if isinstance(value, list):
                if value and all(isinstance(item, str) for item in value):
                    stage_dirs.append([_clean(item) for item in value if _clean(item)])
                    break
                if value and all(isinstance(item, list) for item in value):
                    stage_dirs.extend(
                        [[_clean(atom) for atom in item if _clean(atom)] for item in value]
                    )
                    break
            parsed = _normalize_stage_dirs(value)
            if parsed:
                if len(rows) == 1:
                    stage_dirs.extend(parsed)
                else:
                    stage_dirs.append(parsed[0])
                break
    return stage_dirs


def _fallback_ring_fields_from_stage_rows(
    optimized_stage_rows: list[dict[str, Any]],
    *,
    yellow_sec: int = 0,
    all_red_sec: int = 0,
) -> tuple[str, str, str]:
    stage_dirs = _stage_dirs_from_rows(optimized_stage_rows)
    if not stage_dirs:
        raise ValueError("阶段相位映射不完整，且阶段行缺少可降级还原的方向描述")
    times: list[int] = []
    rows_by_seq = {
        _stage_seq_no(row, idx): row
        for idx, row in enumerate(optimized_stage_rows, start=1)
    }
    for seq_no in range(1, len(stage_dirs) + 1):
        row = rows_by_seq.get(seq_no, {})
        green, yellow, red = _stage_total(row)
        times.append(green + yellow + red)
    cycle_json, phase_json = build_ring_fields(
        stage_dirs,
        times,
        yellow_sec=yellow_sec,
        all_red_sec=all_red_sec,
    )
    return cycle_json, phase_json, "[]"


def build_ring_fields_from_stage_phase_rltn(
    original_row: dict[str, Any],
    optimized_stage_rows: list[dict[str, Any]],
    rltn_rows: list[dict[str, Any]],
    *,
    yellow_sec: int = 0,
    all_red_sec: int = 0,
) -> tuple[str, str, str]:
    """按阶段-原始相位映射回填优化时长，尽量保留原始多环和跟随相位结构。"""
    if not optimized_stage_rows:
        raise ValueError("缺少优化后的阶段时长行")

    phase_sources_by_stage: dict[int, list[dict[str, Any]]] = {}
    for row in rltn_rows:
        if _clean(row.get("source_type")).upper() != "PHASE":
            continue
        phase_no = _to_int(row.get("source_no"))
        if not 1 <= phase_no <= 16:
            continue
        seq_no = _stage_seq_no(row, default=0)
        if seq_no <= 0:
            continue
        phase_sources_by_stage.setdefault(seq_no, []).append(row)

    stage_rows = sorted(
        optimized_stage_rows,
        key=lambda item: _stage_seq_no(item, len(optimized_stage_rows) + 1),
    )
    if any(_stage_seq_no(row, idx) not in phase_sources_by_stage for idx, row in enumerate(stage_rows, 1)):
        return _fallback_ring_fields_from_stage_rows(
            optimized_stage_rows,
            yellow_sec=yellow_sec,
            all_red_sec=all_red_sec,
        )

    cycle_col = _resolve_column(set(original_row), CYCLE_COLUMN_ALIASES) or DEFAULT_CYCLE_COLUMN
    phase_col = _resolve_column(set(original_row), PHASE_COLUMN_ALIASES) or DEFAULT_PHASE_COLUMN
    overlap_col = _resolve_column(set(original_row), OVERLAP_COLUMN_ALIASES) or DEFAULT_OVERLAP_COLUMN

    cycle_json = json.dumps(
        _parse_json_cell(original_row.get(cycle_col), default={}),
        ensure_ascii=False,
    )
    phase_list = _parse_json_cell(original_row.get(phase_col), default=[])
    if not isinstance(phase_list, list) or not phase_list:
        phase_list = [{}]
    phase_data = dict(phase_list[0]) if isinstance(phase_list[0], dict) else {}

    green_times = _split_fixed_width_ints(phase_data.get("greenTime"))
    yellow_times = _split_fixed_width_ints(phase_data.get("yellowTime"))
    red_times = _split_fixed_width_ints(phase_data.get("redTime"))
    original_green_times = list(green_times)
    original_yellow_times = list(yellow_times)
    original_red_times = list(red_times)

    touched_phase_nos = {
        _to_int(ref_row.get("source_no"))
        for rows in phase_sources_by_stage.values()
        for ref_row in rows
    }
    for phase_no in touched_phase_nos:
        if 1 <= phase_no <= 16:
            phase_idx = phase_no - 1
            green_times[phase_idx] = 0
            yellow_times[phase_idx] = 0
            red_times[phase_idx] = 0

    optimized_green_by_phase: dict[int, int] = {}
    optimized_yellow_by_phase: dict[int, int] = {}
    optimized_red_by_phase: dict[int, int] = {}
    stage_seq_order = [_stage_seq_no(row, idx) for idx, row in enumerate(stage_rows, start=1)]
    refs_by_stage_ring = {
        seq_no: _phase_refs_by_ring(phase_sources_by_stage.get(seq_no) or [])
        for seq_no in stage_seq_order
    }

    for idx, row in enumerate(stage_rows, start=1):
        seq_no = _stage_seq_no(row, idx)
        green, yellow, red = _stage_total(row)
        stage_total = green + yellow + red
        next_seq_no = stage_seq_order[idx] if idx < len(stage_seq_order) else None
        next_refs_by_ring = refs_by_stage_ring.get(next_seq_no, {}) if next_seq_no is not None else {}

        for ring_no, refs in refs_by_stage_ring.get(seq_no, {}).items():
            if not refs:
                continue
            active_refs = [ref for ref in refs if _is_active_green_value(ref.get("is_active_green"))]
            if not active_refs:
                active_refs = refs
            active_phase_nos = [_to_int(ref.get("source_no")) for ref in active_refs]
            next_phase_nos = {
                _to_int(ref.get("source_no"))
                for ref in next_refs_by_ring.get(ring_no, [])
            }

            if len(active_phase_nos) == 1:
                phase_no = active_phase_nos[0]
                if phase_no in next_phase_nos:
                    optimized_green_by_phase[phase_no] = optimized_green_by_phase.get(phase_no, 0) + stage_total
                else:
                    optimized_green_by_phase[phase_no] = optimized_green_by_phase.get(phase_no, 0) + green
                    optimized_yellow_by_phase[phase_no] = max(optimized_yellow_by_phase.get(phase_no, 0), yellow)
                    optimized_red_by_phase[phase_no] = max(optimized_red_by_phase.get(phase_no, 0), red)
                continue

            active_weights = [
                _phase_total_from_arrays(
                    phase_no,
                    original_green_times,
                    original_yellow_times,
                    original_red_times,
                )
                for phase_no in active_phase_nos
            ]
            total_allocations = _allocate_int_by_weights(stage_total, active_phase_nos, active_weights)
            clearance_holder = active_phase_nos[-1]
            holder_continues = clearance_holder in next_phase_nos
            for phase_no in active_phase_nos:
                phase_total = total_allocations.get(phase_no, 0)
                if phase_no == clearance_holder and not holder_continues:
                    optimized_green_by_phase[phase_no] = optimized_green_by_phase.get(phase_no, 0) + max(0, phase_total - yellow - red)
                    optimized_yellow_by_phase[phase_no] = max(optimized_yellow_by_phase.get(phase_no, 0), yellow)
                    optimized_red_by_phase[phase_no] = max(optimized_red_by_phase.get(phase_no, 0), red)
                else:
                    optimized_green_by_phase[phase_no] = optimized_green_by_phase.get(phase_no, 0) + phase_total

    for phase_no, green in optimized_green_by_phase.items():
        phase_idx = phase_no - 1
        green_times[phase_idx] = green
    for phase_no, yellow in optimized_yellow_by_phase.items():
        if yellow > 0:
            phase_idx = phase_no - 1
            yellow_times[phase_idx] = yellow
    for phase_no, red in optimized_red_by_phase.items():
        if red > 0:
            phase_idx = phase_no - 1
            red_times[phase_idx] = red

    phase_data["greenTime"] = _format_fixed_width(green_times)
    phase_data["yellowTime"] = _format_fixed_width(yellow_times)
    phase_data["redTime"] = _format_fixed_width(red_times)
    phase_list[0] = phase_data
    phase_json = json.dumps(phase_list, ensure_ascii=False)
    overlap_json = json.dumps(
        _parse_json_cell(original_row.get(overlap_col), default=[]),
        ensure_ascii=False,
    )
    return cycle_json, phase_json, overlap_json


def transform_row(
    row: dict[str, Any],
    *,
    yellow_sec: int = 0,
    all_red_sec: int = 0,
) -> dict[str, Any]:
    result = dict(row)
    fields = set(result)
    stage_dir_col = _resolve_column(fields, STAGE_DIRECTION_COLUMN_ALIASES)
    stage_time_col = _resolve_column(fields, STAGE_TIME_COLUMN_ALIASES)
    if not stage_dir_col:
        raise ValueError(f"缺少阶段方向列（{' / '.join(STAGE_DIRECTION_COLUMN_ALIASES)}）")
    if not stage_time_col:
        raise ValueError(f"缺少阶段时间列（{' / '.join(STAGE_TIME_COLUMN_ALIASES)}）")

    stage_dirs = _normalize_stage_dirs(result.get(stage_dir_col))
    stage_times = _normalize_stage_times(result.get(stage_time_col), len(stage_dirs))
    cycle_json, phase_json = build_ring_fields(
        stage_dirs,
        stage_times,
        yellow_sec=yellow_sec,
        all_red_sec=all_red_sec,
    )
    result[DEFAULT_CYCLE_COLUMN] = cycle_json
    result[DEFAULT_PHASE_COLUMN] = phase_json
    return result


def convert_csv(
    input_path: Path,
    output_path: Path,
    *,
    yellow_sec: int = 0,
    all_red_sec: int = 0,
) -> None:
    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    output_fieldnames = fieldnames + [
        name for name in (DEFAULT_CYCLE_COLUMN, DEFAULT_PHASE_COLUMN) if name not in fieldnames
    ]
    transformed = [
        transform_row(row, yellow_sec=yellow_sec, all_red_sec=all_red_sec) for row in rows
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(transformed)


def _column_exists(conn: Any, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM {_quote_identifier(table_name)} LIKE %s", (column_name,))
        return cursor.fetchone() is not None


def _ensure_target_table(
    conn: Any,
    source_table: str,
    target_table: str,
    *,
    replace_target: bool = False,
) -> None:
    if source_table == target_table:
        raise ValueError("目标表必须与源表不同")
    with conn.cursor() as cursor:
        if replace_target:
            cursor.execute(f"DROP TABLE IF EXISTS {_quote_identifier(target_table)}")
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {_quote_identifier(target_table)} "
            f"LIKE {_quote_identifier(source_table)}"
        )
    conn.commit()

    extra_columns = {
        DEFAULT_CYCLE_COLUMN: "LONGTEXT NULL COMMENT '还原的 Ring-Barrier 相序(JSON)'",
        DEFAULT_PHASE_COLUMN: "LONGTEXT NULL COMMENT '还原的海信 phase_list(JSON)'",
    }
    for column_name, definition in extra_columns.items():
        if _column_exists(conn, target_table, column_name):
            continue
        with conn.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE {_quote_identifier(target_table)} "
                f"ADD COLUMN {_quote_identifier(column_name)} {definition}"
            )
        conn.commit()


def _build_upsert_sql(table_name: str, columns: list[str]) -> str:
    quoted_columns = ", ".join(_quote_identifier(col) for col in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_columns = [col for col in columns if col != "id"]
    update_clause = ", ".join(
        f"{_quote_identifier(col)}=VALUES({_quote_identifier(col)})" for col in update_columns
    )
    return (
        f"INSERT INTO {_quote_identifier(table_name)} ({quoted_columns}) "
        f"VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )


def convert_mysql_table(
    source_table: str = DEFAULT_SOURCE_TABLE,
    target_table: str = DEFAULT_TARGET_TABLE,
    *,
    batch_size: int = 500,
    replace_target: bool = False,
    yellow_sec: int = 0,
    all_red_sec: int = 0,
) -> int:
    read_conn = _get_mysql_connection(streaming=True)
    write_conn = _get_mysql_connection(streaming=False)
    processed = 0
    try:
        _ensure_target_table(
            write_conn,
            source_table,
            target_table,
            replace_target=replace_target,
        )
        where_clause = (
            "WHERE `is_deleted` = 0" if _column_exists(write_conn, source_table, "is_deleted") else ""
        )
        query = " ".join(
            part
            for part in (f"SELECT * FROM {_quote_identifier(source_table)}", where_clause)
            if part
        )
        with read_conn.cursor() as cursor:
            cursor.execute(query)
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                transformed = [
                    transform_row(row, yellow_sec=yellow_sec, all_red_sec=all_red_sec)
                    for row in rows
                ]
                columns = list(transformed[0].keys())
                values = [tuple(row.get(col) for col in columns) for row in transformed]
                with write_conn.cursor() as write_cursor:
                    write_cursor.executemany(_build_upsert_sql(target_table, columns), values)
                write_conn.commit()
                processed += len(transformed)
                print(f"已处理 {processed} 条")
    finally:
        read_conn.close()
        write_conn.close()
    return processed


def main() -> None:
    from env import load_project_env

    load_project_env()
    parser = argparse.ArgumentParser(description="阶段形式配时方案还原为海信环结构方案")
    parser.add_argument("-i", "--input", type=Path, help="CSV 输入文件；传入后启用 CSV 模式")
    parser.add_argument("-o", "--output", type=Path, help="CSV 输出文件；CSV 模式下默认自动推导")
    parser.add_argument("--source-table", default=DEFAULT_SOURCE_TABLE, help="MySQL 源表名")
    parser.add_argument("--target-table", default=DEFAULT_TARGET_TABLE, help="MySQL 目标表名")
    parser.add_argument("--batch-size", type=int, default=500, help="MySQL 批量写入大小")
    parser.add_argument("--replace-target", action="store_true", help="重建目标表")
    parser.add_argument("--yellow-sec", type=int, default=0, help="每阶段拆出的黄灯秒数")
    parser.add_argument("--all-red-sec", type=int, default=0, help="每阶段拆出的全红秒数")
    args = parser.parse_args()

    if args.input:
        output_path = args.output or args.input.with_name(f"{args.input.stem}_环结构{args.input.suffix}")
        convert_csv(
            args.input,
            output_path,
            yellow_sec=args.yellow_sec,
            all_red_sec=args.all_red_sec,
        )
        print(f"已写入 CSV: {output_path}")
        return

    processed = convert_mysql_table(
        source_table=args.source_table,
        target_table=args.target_table,
        batch_size=args.batch_size,
        replace_target=args.replace_target,
        yellow_sec=args.yellow_sec,
        all_red_sec=args.all_red_sec,
    )
    print(f"已写入数据表: {args.target_table}，共 {processed} 条")


if __name__ == "__main__":
    main()
