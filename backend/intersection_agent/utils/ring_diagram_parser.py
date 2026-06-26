"""Ring-Barrier timing record parser (ported from signal ring_timing_visualizer_v2, no matplotlib)."""

from __future__ import annotations

import json
from typing import Any

DEFAULT_STAGE_TABLE = "ods_ctl_inter_scheme_hisense_stage"

direction_map = {0: 0, 1: 2, 2: 4, 3: 6, 4: 1, 5: 3, 6: 5, 7: 7}
turn_map = {
    1: 12, 2: 11, 3: 13, 4: 31, 5: 42, 6: 21, 7: 23, 8: 22, 9: 24, 10: 41,
    11: 101, 12: 102, 13: 100, 14: 14, 15: 15, 16: 16, 17: 17, 18: 18,
}


def channel_dim_analysis(channel_list: list[int]) -> list[list[tuple[int, int]]]:
    result: list[list[tuple[int, int]]] = []
    for num in channel_list:
        if num == 0:
            result.append([])
            continue
        binary_num = bin(num)[2:]
        zero_count = (8 - len(binary_num) % 8) % 8
        binary_num = "0" * zero_count + binary_num
        group_list: list[tuple[int, int]] = []
        for group in [binary_num[i : i + 8] for i in range(0, len(binary_num), 8)]:
            first_three = int(group[:3], 2)
            last_five = int(group[3:], 2)
            if last_five in turn_map:
                group_list.append((direction_map.get(first_three, first_three), turn_map[last_five]))
        result.append(group_list)
    return result


def phase_mask_to_list(mask_value: int, max_phase: int = 16) -> list[int]:
    return [i + 1 for i in range(max_phase) if int(mask_value) & (1 << i)]


def parse_cycle_list(cycle_list_input: Any) -> list[dict[str, Any]]:
    if isinstance(cycle_list_input, dict):
        cycle_dict = cycle_list_input
    else:
        cycle_dict = json.loads(str(cycle_list_input).replace('""', '"'))
    rings: list[dict[str, Any]] = []
    for i in range(1, len(cycle_dict) + 1):
        ring_key = f"Cycle{i}"
        if ring_key not in cycle_dict:
            continue
        ring_str = str(cycle_dict[ring_key])
        phases: list[int] = []
        barriers: list[int] = []
        parts = ring_str.replace("_", " _ ").split()
        phase_idx = 0
        for part in parts:
            if part == "_":
                if phases:
                    barriers.append(phase_idx - 1)
            elif part.strip():
                phases.append(int(part))
                phase_idx += 1
        rings.append({"phases": phases, "barriers": barriers})
    return rings


def _int_list_from_phase_data(phase_data: dict[str, Any], key: str, default_count: int = 16) -> list[int]:
    default_value = " ".join(["0"] * default_count)
    return [int(x) for x in str(phase_data.get(key, default_value)).split()]


def build_follow_phase_info(
    phase_data: dict[str, Any], overlap_data: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    follow_source = overlap_data if overlap_data is not None else phase_data
    direction_key = "channelDim" if overlap_data is not None else "direction"
    included_values = _int_list_from_phase_data(follow_source, "includedPhases")
    modifier_values = _int_list_from_phase_data(follow_source, "modifierPhases")
    direction_values = _int_list_from_phase_data(follow_source, direction_key)
    follow_direction_info = channel_dim_analysis(direction_values)
    follow_phase_info: list[dict[str, Any]] = []
    max_follow_count = max(len(included_values), len(modifier_values), len(direction_values))
    for i in range(max_follow_count):
        included_value = included_values[i] if i < len(included_values) else 0
        if included_value == 0:
            continue
        modifier_value = modifier_values[i] if i < len(modifier_values) else 0
        direction_info = follow_direction_info[i] if i < len(follow_direction_info) else []
        follow_phase_info.append(
            {
                "follow_phase_no": i + 1,
                "included_phases": phase_mask_to_list(included_value),
                "modifier_phases": phase_mask_to_list(modifier_value),
                "direction_info": [list(m) for m in direction_info],
            }
        )
    return follow_phase_info


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value).replace('""', '"'))
    except (TypeError, json.JSONDecodeError):
        return default


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def build_timing_record(
    cycle_list_input: Any,
    phase_data: dict[str, Any],
    *,
    overlap_data: dict[str, Any] | None = None,
    pattern: str = "direct",
    cycle_len: Any = None,
    ring_count: Any = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    green_times = [int(x) for x in phase_data["greenTime"].split()]
    yellow_times = [int(x) for x in phase_data["yellowTime"].split()]
    red_times = [int(x) for x in phase_data["redTime"].split()]
    channel_dims = [int(x) for x in phase_data["channelDim"].split()]
    channel_info = channel_dim_analysis(channel_dims)
    rings = parse_cycle_list(cycle_list_input)
    follow_phase_info = build_follow_phase_info(phase_data, overlap_data)

    if cycle_len is None:
        ring_lengths: list[int] = []
        for ring in rings:
            total = 0
            for phase_no in ring["phases"]:
                idx = phase_no - 1
                if idx < len(green_times):
                    g = green_times[idx]
                    y = yellow_times[idx] if idx < len(yellow_times) else 0
                    r = red_times[idx] if idx < len(red_times) else 0
                    total += g + y + r
            ring_lengths.append(total)
        cycle_len = max(ring_lengths) if ring_lengths else 0

    record: dict[str, Any] = {
        "pattern": pattern,
        "cycle_len": int(cycle_len or 0),
        "ring_count": int(ring_count) if ring_count is not None else len(rings),
        "green_times": green_times,
        "yellow_times": yellow_times,
        "red_times": red_times,
        "channel_info": channel_info,
        "follow_phase_info": follow_phase_info,
        "rings": rings,
    }
    if extra:
        record.update(extra)
    return record


def parse_ods_scheme_row(row: dict[str, Any], *, source_table: str = DEFAULT_STAGE_TABLE) -> dict[str, Any]:
    phase_list = _json_loads(_first_present(row, "phase_list_json", "phase_list"), [])
    if not phase_list or not isinstance(phase_list, list):
        raise ValueError("phase_list_json 为空或格式错误")
    phase_data = phase_list[0]
    if not isinstance(phase_data, dict):
        raise ValueError("phase_list_json[0] 不是对象")

    cycle_list_input = _first_present(row, "cycle_json", "cycle_list")
    if cycle_list_input in (None, ""):
        raise ValueError("cycle_json 为空")

    overlap_list = _json_loads(_first_present(row, "over_lap_phase_json", "over_lap_phase_list"), [])
    overlap_data = overlap_list[0] if overlap_list else None
    plan_no = row.get("plan_no")
    pattern_no = row.get("pattern_no")
    pattern_label = (
        f"plan{plan_no}/pattern{pattern_no}"
        if plan_no is not None and pattern_no is not None
        else str(pattern_no or plan_no or "unknown")
    )
    extra = {
        "inter_id": row.get("inter_id"),
        "cross_id": row.get("cross_id"),
        "cross_name": row.get("cross_name"),
        "inter_name": row.get("inter_name"),
        "plan_no": plan_no,
        "pattern_no": pattern_no,
        "offset_sec": row.get("offset_sec"),
        "source_table": source_table,
    }
    return build_timing_record(
        cycle_list_input,
        phase_data,
        overlap_data=overlap_data if isinstance(overlap_data, dict) else None,
        pattern=pattern_label,
        cycle_len=row.get("cycle_len_sec") or row.get("cycle_len"),
        ring_count=row.get("ring_count"),
        extra=extra,
    )
