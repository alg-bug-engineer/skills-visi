"""Extract time-series insights from PG raw metrics for scene cognition interpretation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def _load_config_module():
    common_dir = Path(__file__).resolve().parents[2] / "common"
    spec = importlib.util.spec_from_file_location("intersection_load_config", common_dir / "load_config.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 intersection/common/load_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_metrics_logic_module():
    scripts_dir = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "intersection_traffic_metrics_logic",
        scripts_dir / "traffic_metrics_logic.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 scene-cognition/scripts/traffic_metrics_logic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CFG = _load_config_module()
_TH = _CFG.threshold
_TML = _load_metrics_logic_module()

HIGH_SATURATION = _TH("saturation.high")
OVERSATURATION = _TH("saturation.oversaturation")
LONG_QUEUE_M = _TH("queue.long_queue_m")
HIGH_DELAY_INDEX = _TH("delay.high_delay_index")
LOW_GREEN_UTIL = _TH("green.low_utilization_cognition")
HIGH_IMBALANCE = _TH("imbalance.high")
SHORT_SPACING_M = _TH("static.adjacent_spacing_m")

TURN_DIR_LABELS = {0: "方向聚合", 1: "左转", 2: "直行", 3: "右转"}
CARDINAL_PREFIXES = ("东南", "西南", "东北", "西北", "东", "西", "南", "北")
STATIC_FLAG_LABELS = {
    "funnel_effect": "进出口车道不匹配（漏斗效应）",
    "more_entrances_than_exits": "进口方向多于出口方向，出口承接空间偏紧",
}
WORST_LOS_RANK = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _time_label(step_index: int) -> str:
    minutes = int(step_index) * 5
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _movement_key(row: dict[str, Any]) -> str:
    link_id = str(row.get("link_id") or row.get("f_dir_8") or "")[-4:]
    turn = TURN_DIR_LABELS.get(int(_as_float(row.get("turn_dir_no"))), str(row.get("turn_dir_no")))
    return f"{link_id}_{turn}"


def _compact_dir_label(label: Any) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    for suffix in ("进口", "出口"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    for prefix in CARDINAL_PREFIXES:
        if text.startswith(prefix) or prefix in text[:3]:
            return prefix
    return text


def _build_dir_lookup(channel_rows: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in channel_rows or []:
        link_id = row.get("link_id")
        if not link_id:
            continue
        label = row.get("dir4_label") or row.get("dir8_label") or ""
        if not label:
            continue
        link_key = str(link_id)
        lookup[link_key] = str(label)
        lookup[link_key[-4:]] = str(label)
    return lookup


def _resolve_dir_label(row: dict[str, Any], dir_lookup: dict[str, str] | None = None) -> str:
    raw_label = row.get("f_dir_8_label") or row.get("dir8_label") or row.get("dir4_label")
    if raw_label:
        return _compact_dir_label(raw_label)
    if dir_lookup:
        link_id = str(row.get("link_id") or row.get("f_dir_8") or "")
        mapped = dir_lookup.get(link_id) or dir_lookup.get(link_id[-4:])
        if mapped:
            return _compact_dir_label(mapped)
    return ""


def _movement_label(row: dict[str, Any], dir_lookup: dict[str, str] | None = None) -> str:
    dir_label = _resolve_dir_label(row, dir_lookup)
    turn_label = row.get("turn_dir_label") or TURN_DIR_LABELS.get(int(_as_float(row.get("turn_dir_no"))))
    if dir_label and turn_label and turn_label != "方向聚合":
        return f"{dir_label}{turn_label}"
    if dir_label:
        return dir_label
    return _movement_key(row)


def _enrich_rows_with_directions(
    rows: list[dict[str, Any]],
    dir_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    if not dir_lookup:
        return rows
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if not (item.get("f_dir_8_label") or item.get("dir8_label") or item.get("dir4_label")):
            link_id = str(item.get("link_id") or item.get("f_dir_8") or "")
            label = dir_lookup.get(link_id) or dir_lookup.get(link_id[-4:])
            if label:
                item["dir8_label"] = label
        enriched.append(item)
    return enriched


def _merge_step_windows(step_indices: list[int]) -> list[dict[str, Any]]:
    if not step_indices:
        return []
    ordered = sorted(set(int(step) for step in step_indices))
    windows: list[dict[str, Any]] = []
    start = ordered[0]
    prev = ordered[0]
    for step in ordered[1:]:
        if step == prev + 1:
            prev = step
            continue
        windows.append({"start_step": start, "end_step": prev, "start": _time_label(start), "end": _time_label(prev + 1)})
        start = step
        prev = step
    windows.append({"start_step": start, "end_step": prev, "start": _time_label(start), "end": _time_label(prev + 1)})
    return windows


def _scalar_series(rows: list[dict[str, Any]], field: str, reducer=max) -> dict[int, float]:
    series: dict[int, float] = {}
    for row in rows:
        step = row.get("step_index")
        if step is None:
            continue
        value = _as_float(row.get(field))
        if value <= 0:
            continue
        step_index = int(step)
        series[step_index] = reducer(series.get(step_index, value), value)
    return series


def _intersection_series(evaluation_rows: list[dict[str, Any]]) -> dict[int, float]:
    series: dict[int, float] = {}
    for row in evaluation_rows:
        step = row.get("step_index")
        if step is None:
            continue
        saturation = _as_float(row.get("saturation_max") or row.get("saturation_avg"))
        if saturation <= 0:
            continue
        step_index = int(step)
        series[step_index] = max(series.get(step_index, saturation), saturation)
    return series


def _movement_series(
    rows: list[dict[str, Any]],
    field: str = "turn_saturation",
    *,
    dir_lookup: dict[str, str] | None = None,
) -> tuple[dict[str, dict[int, float]], dict[str, str]]:
    series: dict[str, dict[int, float]] = {}
    labels: dict[str, str] = {}
    for row in rows:
        step = row.get("step_index")
        if step is None:
            continue
        value = _as_float(row.get(field))
        if value <= 0:
            continue
        key = _movement_key(row)
        labels[key] = _movement_label(row, dir_lookup)
        step_index = int(step)
        bucket = series.setdefault(key, {})
        bucket[step_index] = max(bucket.get(step_index, value), value)
    return series, labels


def _windows_from_series(series: dict[int, float], threshold: float, *, above: bool = True) -> list[dict[str, Any]]:
    if above:
        steps = [step for step, value in series.items() if value >= threshold]
    else:
        steps = [step for step, value in series.items() if value <= threshold]
    windows = _merge_step_windows(steps)
    for window in windows:
        segment = [series[step] for step in range(window["start_step"], window["end_step"] + 1) if step in series]
        if segment:
            window["peak"] = round(max(segment) if above else min(segment), 3)
    return windows


def _peak_from_series(series: dict[int, float]) -> tuple[int | None, float]:
    if not series:
        return None, 0.0
    step, value = max(series.items(), key=lambda item: item[1])
    return step, round(value, 3)


def _movement_metric_blocks(
    rows: list[dict[str, Any]],
    field: str,
    *,
    window_threshold: float,
    above: bool = True,
    value_field: str | None = None,
    dir_lookup: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    series_map, labels = _movement_series(rows, field=value_field or field, dir_lookup=dir_lookup)
    blocks: list[dict[str, Any]] = []
    for key, series in series_map.items():
        peak_step, peak_value = _peak_from_series(series)
        blocks.append(
            {
                "movement": key,
                "label": labels.get(key, key),
                "peak_value": peak_value,
                "peak_time": _time_label(peak_step) if peak_step is not None else None,
                "alert_windows": _windows_from_series(series, window_threshold, above=above),
            }
        )
    blocks.sort(key=lambda item: item.get("peak_value") or 0, reverse=above)
    return blocks[:8]


def _stage_total(row: dict[str, Any]) -> float | None:
    explicit = row.get("stage_total_sec")
    if explicit is not None:
        return _as_float(explicit)
    values = [
        _as_float(row.get("green_sec")),
        _as_float(row.get("yellow_sec")),
        _as_float(row.get("all_red_sec")),
    ]
    total = sum(values)
    return round(total, 4) if total > 0 else None


def _cycle_consistency(cycle: float, phase_sequence: list[dict[str, Any]]) -> dict[str, Any]:
    stage_total = sum(
        _as_float(item.get("stage_total_sec"))
        for item in phase_sequence
        if item.get("stage_total_sec") is not None
    )
    if cycle <= 0 or stage_total <= 0:
        return {"stage_total_sec": round(stage_total, 4) if stage_total else None, "status": "unknown"}
    diff = round(stage_total - cycle, 4)
    return {
        "stage_total_sec": round(stage_total, 4),
        "cycle_sec": cycle,
        "diff_sec": diff,
        "status": "matched" if abs(diff) <= 1 else "mismatch",
    }


def _summarize_signal_timing(profile: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    control = profile.get("control_profile") or {}
    plan_rows = raw.get("plan") or []
    schedule_rows = raw.get("schedule_cfg") or []
    cycle = _as_float(control.get("current_cycle_s"))
    plan_nos = {row.get("plan_no") for row in plan_rows if row.get("plan_no")}
    schedule_nos = {row.get("schedule_no") for row in schedule_rows if row.get("schedule_no")}
    day_plans = {row.get("day_plan_no") for row in schedule_rows if row.get("day_plan_no")}
    stage_rows = list(control.get("stage_detail") or plan_rows or [])
    phase_sequence = [
        {
            "stage_no": row.get("stage_no"),
            "stage_seq_no": row.get("stage_seq_no"),
            "green_sec": row.get("green_sec"),
            "yellow_sec": row.get("yellow_sec"),
            "all_red_sec": row.get("all_red_sec"),
            "stage_total_sec": _stage_total(row),
            "min_green_sec": row.get("min_green_sec"),
            "max_green_sec": row.get("max_green_sec"),
            "green_ratio": round(_as_float(row.get("green_sec")) / cycle, 4) if cycle > 0 and row.get("green_sec") is not None else None,
        }
        for row in stage_rows
        if isinstance(row, dict)
    ]
    min_green_values = [
        _as_float(item.get("min_green_time") or item.get("min_green_sec"))
        for item in [*(control.get("min_green_detail") or []), *phase_sequence]
        if isinstance(item, dict) and (item.get("min_green_time") is not None or item.get("min_green_sec") is not None)
    ]
    schedules = [
        {
            "schedule_no": row.get("schedule_no"),
            "schedule_name": row.get("schedule_name"),
            "week_day_no": row.get("week_day_no"),
            "day_plan_no": row.get("day_plan_no"),
            "period_seq_no": row.get("period_seq_no"),
            "start_time": row.get("start_time"),
            "end_time": row.get("end_time"),
            "plan_no": row.get("period_plan_no") or row.get("plan_no"),
            "ctrl_mode": row.get("ctrl_mode"),
        }
        for row in schedule_rows
    ]
    movement_volume = (profile.get("demand_profile") or {}).get("movement_volume") or {}
    flow_green_items = _TML.build_flow_green_items(movement_volume, stage_rows)
    flow_green_consistency = _TML.flow_green_check(flow_green_items) if flow_green_items else None
    stage_conflicts = _TML.detect_stage_conflicts(stage_rows)
    cycle_check = _cycle_consistency(cycle, phase_sequence)
    return {
        "plan_count": len(plan_nos) or control.get("time_plan_count") or 0,
        "schedule_segment_count": len(schedule_nos) or len(schedule_rows) or control.get("time_plan_count") or 0,
        "day_plan_count": len(day_plans),
        "current_cycle_s": control.get("current_cycle_s"),
        "plan_no": control.get("plan_no"),
        "plan_name": control.get("plan_name"),
        "phase_count": len(phase_sequence) or len(control.get("phase_sequence") or []),
        "phase_sequence": phase_sequence[:12],
        "green_ratio_min": min((item["green_ratio"] for item in phase_sequence if item.get("green_ratio") is not None), default=None),
        "green_ratio_max": max((item["green_ratio"] for item in phase_sequence if item.get("green_ratio") is not None), default=None),
        "min_green_min_s": min(min_green_values) if min_green_values else None,
        "min_green_max_s": max(min_green_values) if min_green_values else None,
        "stage_total_sec": cycle_check.get("stage_total_sec"),
        "cycle_consistency": cycle_check,
        "schedules": schedules[:12],
        "flow_green_consistency": flow_green_consistency,
        "stage_conflicts": stage_conflicts[:8],
    }


def _summarize_queue_delay(perf_rows: list[dict[str, Any]], *, dir_lookup: dict[str, str] | None = None) -> dict[str, Any]:
    if not perf_rows:
        return {}
    step_queues: dict[int, float] = {}
    for row in perf_rows:
        step = row.get("step_index")
        if step is None:
            continue
        queue = _as_float(row.get("queue_len_max") or row.get("queue_len_avg"))
        if queue <= 0:
            continue
        step_index = int(step)
        step_queues[step_index] = max(step_queues.get(step_index, queue), queue)

    queue_field = "queue_len_max" if any(row.get("queue_len_max") is not None for row in perf_rows) else "queue_len_avg"
    movement_queues = _movement_metric_blocks(
        perf_rows, queue_field, window_threshold=LONG_QUEUE_M, above=True, dir_lookup=dir_lookup
    )

    peak_queue = max(step_queues.values()) if step_queues else 0.0
    peak_queue_step, _ = _peak_from_series(step_queues)
    delay_series = _scalar_series(perf_rows, "delay_index")
    peak_delay_step, peak_delay = _peak_from_series(delay_series)

    stop_avgs: dict[str, float] = {}
    labels: dict[str, str] = {}
    for row in perf_rows:
        key = _movement_key(row)
        labels[key] = _movement_label(row, dir_lookup)
        stops = _as_float(row.get("stop_times"))
        if stops > 0:
            stop_avgs[key] = max(stop_avgs.get(key, stops), stops)
    top_stop = max(stop_avgs.items(), key=lambda item: item[1]) if stop_avgs else None

    return {
        "peak_queue_m": round(peak_queue, 1),
        "peak_queue_time": _time_label(peak_queue_step) if peak_queue_step is not None else None,
        "peak_delay_index": peak_delay,
        "peak_delay_time": _time_label(peak_delay_step) if peak_delay_step is not None else None,
        "long_queue_threshold_m": LONG_QUEUE_M,
        "long_queue_movements": [item for item in movement_queues if item.get("alert_windows")][:6],
        "high_delay_movements": _movement_metric_blocks(
            perf_rows, "delay_index", window_threshold=HIGH_DELAY_INDEX, above=True, dir_lookup=dir_lookup
        )[:6],
        "top_stop_movement": (
            {"label": labels.get(top_stop[0], top_stop[0]), "stop_times": round(top_stop[1], 1)}
            if top_stop
            else None
        ),
    }


def _summarize_green_efficiency(
    util_rows: list[dict[str, Any]],
    profile: dict[str, Any],
    *,
    dir_lookup: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not util_rows:
        traffic = profile.get("traffic_state") or {}
        avg_util = _as_float(traffic.get("green_utilization"))
        if avg_util <= 0:
            return {}
        return {
            "avg_green_utilization": round(avg_util, 3),
            "empty_green_rate": round(_as_float(traffic.get("empty_green_rate")), 3),
            "low_util_threshold": LOW_GREEN_UTIL,
            "low_util_movements": [],
        }
    utils = [_as_float(row.get("green_utilization")) for row in util_rows if row.get("green_utilization") is not None]
    low_blocks = _movement_metric_blocks(
        util_rows, "green_utilization", window_threshold=LOW_GREEN_UTIL, above=False, dir_lookup=dir_lookup
    )
    return {
        "avg_green_utilization": round(sum(utils) / len(utils), 3) if utils else 0.0,
        "empty_green_rate": round(max(0.0, 1.0 - (sum(utils) / len(utils) if utils else 0.0)), 3),
        "low_util_threshold": LOW_GREEN_UTIL,
        "low_util_movements": [item for item in low_blocks if item.get("alert_windows")][:6],
    }


def _summarize_demand_pattern(flow_rows: list[dict[str, Any]], *, dir_lookup: dict[str, str] | None = None) -> dict[str, Any]:
    if not flow_rows:
        return {}
    filtered_rows = _dedupe_turn_flow_rows(flow_rows)
    totals: dict[str, float] = {}
    labels: dict[str, str] = {}
    step_totals: dict[int, float] = {}
    for row in filtered_rows:
        key = _movement_key(row)
        labels[key] = _movement_label(row, dir_lookup)
        flow_rate = _as_float(row.get("turn_flow_total"))
        # DWS 5-minute flow rows are stored as hourly-equivalent flow rates.
        # Convert each 5-minute sample to volume before accumulating daily total.
        volume = flow_rate / 12.0
        totals[key] = totals.get(key, 0.0) + volume
        step = row.get("step_index")
        if step is not None:
            step_totals[int(step)] = step_totals.get(int(step), 0.0) + flow_rate
    if not totals:
        return {}
    total_volume = sum(totals.values())
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    peak_step, peak_flow = _peak_from_series(step_totals)
    top_movements = [
        {
            "label": labels.get(key, key),
            "volume": round(value, 0),
            "share_pct": round(value / total_volume * 100, 1) if total_volume else 0.0,
        }
        for key, value in ranked[:5]
    ]
    am_peak = sum(step_totals.get(step, 0.0) for step in range(72, 108))
    pm_peak = sum(step_totals.get(step, 0.0) for step in range(204, 240))
    pattern = "均衡"
    if am_peak > pm_peak * 1.2:
        pattern = "早高峰型"
    elif pm_peak > am_peak * 1.2:
        pattern = "晚高峰型"
    elif am_peak > 0 and pm_peak > 0:
        pattern = "双高峰型"
    return {
        "total_volume": round(total_volume, 0),
        "peak_flow_time": _time_label(peak_step) if peak_step is not None else None,
        "peak_flow_volume": round(peak_flow, 0),
        "demand_pattern": pattern,
        "top_movements": top_movements,
    }


def _dedupe_turn_flow_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one row per step + movement, preferring explicit turn rows over direction totals."""
    explicit_rows = [row for row in rows if int(_as_float(row.get("turn_dir_no"))) != 0]
    candidates = explicit_rows or rows
    seen: dict[tuple[int, str, int], dict[str, Any]] = {}
    for row in candidates:
        step = row.get("step_index")
        if step is None:
            continue
        key = (
            int(step),
            str(row.get("link_id") or row.get("f_dir_8") or ""),
            int(_as_float(row.get("turn_dir_no"))),
        )
        current = seen.get(key)
        if current is None or _as_float(row.get("turn_flow_total")) > _as_float(current.get("turn_flow_total")):
            seen[key] = row
    if seen:
        return list(seen.values())
    return candidates


def _summarize_imbalance(evaluation_rows: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    imbalance_series = _scalar_series(evaluation_rows, "unbalance_index")
    if not imbalance_series:
        idx = _as_float((profile.get("traffic_state") or {}).get("imbalance_index"))
        if idx <= 0:
            return {}
        return {"peak_imbalance_index": round(idx, 3), "high_imbalance_windows": []}
    peak_step, peak_value = _peak_from_series(imbalance_series)
    return {
        "peak_imbalance_index": peak_value,
        "peak_imbalance_time": _time_label(peak_step) if peak_step is not None else None,
        "high_imbalance_threshold": HIGH_IMBALANCE,
        "high_imbalance_windows": _windows_from_series(imbalance_series, HIGH_IMBALANCE),
    }


def _step_flow_total(flow_rows: list[dict[str, Any]], step: int) -> float:
    return sum(
        _as_float(row.get("turn_flow_total"))
        for row in _dedupe_turn_flow_rows(flow_rows)
        if row.get("step_index") is not None and int(row["step_index"]) == step
    )


def _step_delay_peak(perf_rows: list[dict[str, Any]], step: int) -> float:
    delays = [
        _as_float(row.get("delay_index"))
        for row in perf_rows
        if row.get("step_index") is not None and int(row["step_index"]) == step
    ]
    return max(delays) if delays else 0.0


def _step_saturation(evaluation_rows: list[dict[str, Any]], step: int) -> float:
    for row in evaluation_rows:
        if row.get("step_index") is not None and int(row["step_index"]) == step:
            return _as_float(row.get("saturation_max") or row.get("saturation_avg"))
    return 0.0


def _is_off_peak_step(step: int) -> bool:
    hour = (step * 5) // 60
    return hour < 6 or hour >= 22 or 10 <= hour < 16


def _is_los_anomaly(
    step: int,
    los: str,
    saturation: float,
    flow_total: float,
    delay_peak: float,
    *,
    median_flow: float,
) -> bool:
    los_rank = WORST_LOS_RANK.get(str(los).upper()[:1], 0)
    if los_rank < WORST_LOS_RANK["D"]:
        return False
    low_traffic = saturation < 0.55 and delay_peak < 1.0
    if median_flow > 0 and flow_total < median_flow * 0.35:
        low_traffic = True
    if _is_off_peak_step(step) and low_traffic:
        return True
    if saturation < 0.45 and delay_peak < 0.8:
        return True
    return False


def _summarize_service_level(
    evaluation_rows: list[dict[str, Any]],
    profile: dict[str, Any],
    *,
    perf_rows: list[dict[str, Any]] | None = None,
    flow_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    los_by_step: dict[int, str] = {}
    for row in evaluation_rows:
        step = row.get("step_index")
        los = row.get("level_of_service")
        if step is None or not los:
            continue
        los_by_step[int(step)] = str(los)
    if not los_by_step:
        los = (profile.get("traffic_state") or {}).get("los") or (profile.get("congestion_profile") or {}).get("los")
        if not los:
            return {}
        return {"worst_los": str(los), "worst_los_time": None, "los_d_or_worse_steps": 0}

    flow_rows = flow_rows or []
    perf_rows = perf_rows or []
    flow_totals = [_step_flow_total(flow_rows, step) for step in los_by_step]
    positive_flows = [value for value in flow_totals if value > 0]
    median_flow = sorted(positive_flows)[len(positive_flows) // 2] if positive_flows else 0.0

    original_step, original_los = max(
        los_by_step.items(),
        key=lambda item: WORST_LOS_RANK.get(item[1].upper()[:1], 0),
    )
    original_saturation = _step_saturation(evaluation_rows, original_step)
    original_flow = _step_flow_total(flow_rows, original_step)
    original_delay = _step_delay_peak(perf_rows, original_step)
    anomaly = _is_los_anomaly(
        original_step,
        original_los,
        original_saturation,
        original_flow,
        original_delay,
        median_flow=median_flow,
    )

    worst_step, worst_los = original_step, original_los
    anomaly_note: str | None = None
    if anomaly:
        candidates: list[tuple[int, str, int, float, float]] = []
        for step, los in los_by_step.items():
            saturation = _step_saturation(evaluation_rows, step)
            flow_total = _step_flow_total(flow_rows, step)
            delay_peak = _step_delay_peak(perf_rows, step)
            if _is_los_anomaly(step, los, saturation, flow_total, delay_peak, median_flow=median_flow):
                continue
            rank = WORST_LOS_RANK.get(los.upper()[:1], 0)
            candidates.append((step, los, rank, saturation, delay_peak))
        if candidates:
            worst_step, worst_los, _, sat, delay = max(candidates, key=lambda item: (item[2], item[3], item[4]))
            anomaly_note = (
                f"原始最差 LOS {original_los}（{_time_label(original_step)}）与低流量"
                f"（饱和度 {original_saturation:.2f}、延误 {original_delay:.2f}）不匹配，"
                f"已改按 {_time_label(worst_step)} 综合判定"
            )
        else:
            worst_step, worst_los = None, None
            anomaly_note = (
                f"原始最差 LOS {original_los}（{_time_label(original_step)}）与低流量/低延误不匹配，"
                "暂无法找到更可信的高峰 LOS 样本"
            )

    d_or_worse = sum(1 for value in los_by_step.values() if value.upper()[:1] in {"D", "E", "F"})
    result = {
        "worst_los": worst_los,
        "worst_los_time": _time_label(worst_step) if worst_step is not None else None,
        "los_d_or_worse_steps": d_or_worse,
    }
    if anomaly:
        result["anomaly_corrected"] = True
        result["original_worst_los"] = original_los
        result["original_worst_los_time"] = _time_label(original_step)
        result["original_saturation"] = round(original_saturation, 3)
        result["original_delay_index"] = round(original_delay, 3)
        result["original_flow_total"] = round(original_flow, 1)
        if anomaly_note:
            result["anomaly_note"] = anomaly_note
    return result


def _summarize_supply_constraints(profile: dict[str, Any], task: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    supply = profile.get("supply_profile") or {}
    context = task.get("context") or {}
    static_flags = [str(flag) for flag in (supply.get("static_flags") or []) if flag]
    spacing = supply.get("adjacent_inter_spacing_m")
    complaints = [
        str(row.get("core_problem_desc") or row.get("complaint_type") or "")
        for row in (raw.get("complaints") or [])
        if row
    ]
    complaints = [item for item in complaints if item] or list(context.get("complaints") or [])
    surveys = [
        str(row.get("issue_desc") or row.get("issue_type") or "")
        for row in (raw.get("field_survey") or [])
        if row
    ]
    surveys = [item for item in surveys if item] or list(context.get("field_survey_issues") or [])
    poi = list(context.get("poi") or profile.get("context_tags") or [])
    constraints: list[str] = []
    funnel_details = supply.get("funnel_details") or (task.get("scope") or {}).get("funnel_details") or []
    for flag in static_flags:
        label = STATIC_FLAG_LABELS.get(flag, flag)
        if flag == "funnel_effect" and funnel_details:
            label = f"{label}：{'；'.join(str(item) for item in funnel_details[:3])}"
        constraints.append(label)
    if spacing is not None and _as_float(spacing) > 0 and _as_float(spacing) < SHORT_SPACING_M:
        constraints.append(f"相邻路口间距仅 {_as_float(spacing):.0f} m，串联控制压力大")
    return {
        "static_flags": static_flags,
        "static_constraints": constraints,
        "funnel_details": funnel_details,
        "adjacent_inter_spacing_m": spacing,
        "poi_tags": poi[:6],
        "complaint_count": len(complaints),
        "complaint_samples": complaints[:3],
        "field_survey_count": len(surveys),
        "field_survey_samples": surveys[:3],
    }


def _management_attention(insights: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    inter = insights.get("intersection_saturation") or {}
    if inter.get("oversaturation_windows"):
        tags.append("路口过饱和")
    queue = insights.get("queue_delay") or {}
    if queue.get("long_queue_movements"):
        tags.append("长排队")
    green = insights.get("green_efficiency") or {}
    if green.get("low_util_movements"):
        tags.append("绿灯空放风险")
    imbalance = insights.get("imbalance") or {}
    if imbalance.get("high_imbalance_windows"):
        tags.append("转向失衡")
    supply = insights.get("supply_constraints") or {}
    if supply.get("static_constraints"):
        tags.append("渠化约束")
    if (supply.get("complaint_count") or 0) > 0:
        tags.append("投诉关注")
    service = insights.get("service_level") or {}
    if (service.get("los_d_or_worse_steps") or 0) > 0:
        tags.append("服务等级偏低")
    timing = insights.get("signal_timing") or {}
    consistency = timing.get("flow_green_consistency") or {}
    if consistency.get("verdict") == "mismatch":
        tags.append("流量-绿信比不匹配")
    if (timing.get("cycle_consistency") or {}).get("status") == "mismatch":
        tags.append("周期-阶段时长不一致")
    if timing.get("stage_conflicts"):
        tags.append("阶段冲突线索")
    return tags


def _make_fact(
    text: str,
    *,
    fact_id: str,
    checklist_item_id: str,
    metric: str | None = None,
) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "checklist_item_id": checklist_item_id,
        "text": text,
        "metric": metric,
    }


def _fact_text(fact: Any) -> str:
    if isinstance(fact, dict):
        return str(fact.get("text") or "")
    return str(fact)


def _build_facts(
    data_window: str,
    intersection: dict[str, Any],
    movements: list[dict[str, Any]],
    signal_timing: dict[str, Any],
    queue_delay: dict[str, Any],
    green_efficiency: dict[str, Any],
    demand_pattern: dict[str, Any],
    imbalance: dict[str, Any],
    service_level: dict[str, Any],
    supply_constraints: dict[str, Any],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    if intersection.get("peak_saturation"):
        facts.append(
            _make_fact(
                f"观测窗口 {data_window}，路口峰值饱和度 {intersection['peak_saturation']:.2f}，"
                f"出现在 {intersection.get('peak_time') or '未知时段'}。",
                fact_id="metrics.inter_evaluation.peak_saturation",
                checklist_item_id="inter_evaluation",
                metric="saturation",
            )
        )
    overs = intersection.get("oversaturation_windows") or []
    if overs:
        ranges = "、".join(f"{item['start']}-{item['end']}" for item in overs[:4])
        facts.append(
            _make_fact(
                f"路口在 {ranges} 等时段处于过饱和（≥{OVERSATURATION:.0%}）。",
                fact_id="metrics.inter_evaluation.oversaturation_windows",
                checklist_item_id="inter_evaluation",
                metric="saturation",
            )
        )
    elif intersection.get("high_saturation_windows"):
        ranges = "、".join(
            f"{item['start']}-{item['end']}" for item in intersection["high_saturation_windows"][:4]
        )
        facts.append(
            _make_fact(
                f"路口在 {ranges} 等时段处于高饱和（≥{HIGH_SATURATION:.0%}），但未观测到过饱和。",
                fact_id="metrics.inter_evaluation.high_saturation_windows",
                checklist_item_id="inter_evaluation",
                metric="saturation",
            )
        )
    elif intersection.get("peak_saturation") and intersection["peak_saturation"] < HIGH_SATURATION:
        facts.append(
            _make_fact(
                f"观测窗口内路口未达到高饱和（≥{HIGH_SATURATION:.0%}），整体运行相对平稳；"
                f"相对繁忙出现在 {intersection.get('peak_time') or '未知时段'}。",
                fact_id="metrics.inter_evaluation.stable",
                checklist_item_id="inter_evaluation",
                metric="saturation",
            )
        )

    hot_movements = [item for item in movements if item.get("oversaturation_windows")]
    if hot_movements:
        parts = []
        for item in hot_movements[:4]:
            window = item["oversaturation_windows"][0]
            parts.append(f"{item['label']}（{window['start']}-{window['end']}）")
        facts.append(
            _make_fact(
                f"进口方向过饱和集中在：{'；'.join(parts)}。",
                fact_id="metrics.turn_saturation.oversaturation",
                checklist_item_id="turn_saturation",
                metric="movement_saturation",
            )
        )
    elif movements:
        top = movements[0]
        if top.get("peak_saturation"):
            facts.append(
                _make_fact(
                    f"进口方向相对压力较大的是 {top['label']}，峰值饱和度 {top['peak_saturation']:.2f}"
                    f"（{top.get('peak_time') or '未知时段'}），未观测到过饱和。",
                    fact_id="metrics.turn_saturation.peak_movement",
                    checklist_item_id="turn_saturation",
                    metric="movement_saturation",
                )
            )

    if queue_delay.get("peak_queue_m"):
        facts.append(
            _make_fact(
                f"最大排队约 {queue_delay['peak_queue_m']:.0f} m"
                f"（{queue_delay.get('peak_queue_time') or '未知时段'}）。",
                fact_id="metrics.turn_perf.peak_queue",
                checklist_item_id="turn_perf",
                metric="queue_m",
            )
        )
    long_queue = queue_delay.get("long_queue_movements") or []
    if long_queue:
        item = long_queue[0]
        window = (item.get("alert_windows") or [{}])[0]
        facts.append(
            _make_fact(
                f"{item.get('label')} 在 {window.get('start', '?')}-{window.get('end', '?')} 出现长排队"
                f"（≥{LONG_QUEUE_M:.0f} m）。",
                fact_id="metrics.turn_perf.long_queue",
                checklist_item_id="turn_perf",
                metric="queue_m",
            )
        )
    if queue_delay.get("peak_delay_index"):
        facts.append(
            _make_fact(
                f"延误指数峰值 {queue_delay['peak_delay_index']:.2f}"
                f"（{queue_delay.get('peak_delay_time') or '未知时段'}）。",
                fact_id="metrics.turn_perf.peak_delay",
                checklist_item_id="turn_perf",
                metric="avg_delay_s",
            )
        )

    if green_efficiency.get("avg_green_utilization"):
        facts.append(
            _make_fact(
                f"平均绿灯利用率 {green_efficiency['avg_green_utilization']:.2f}。",
                fact_id="metrics.green_utilization.avg",
                checklist_item_id="green_utilization",
                metric="green_utilization",
            )
        )
    low_green = green_efficiency.get("low_util_movements") or []
    if low_green:
        item = low_green[0]
        facts.append(
            _make_fact(
                f"{item.get('label')} 存在绿灯利用率偏低时段，需关注空放。",
                fact_id="metrics.green_utilization.low_util",
                checklist_item_id="green_utilization",
                metric="green_utilization",
            )
        )

    if demand_pattern.get("total_volume"):
        top = (demand_pattern.get("top_movements") or [{}])[0]
        facts.append(
            _make_fact(
                f"总转向流量约 {demand_pattern['total_volume']:.0f}，"
                f"主流量为 {top.get('label', '-')}（占比 {top.get('share_pct', 0):.1f}%），"
                f"流量形态偏 {demand_pattern.get('demand_pattern', '未知')}。",
                fact_id="metrics.turn_flow.pattern",
                checklist_item_id="turn_flow",
                metric="volume",
            )
        )

    if imbalance.get("peak_imbalance_index"):
        if imbalance.get("high_imbalance_windows"):
            window = imbalance["high_imbalance_windows"][0]
            facts.append(
                _make_fact(
                    f"失衡指数峰值 {imbalance['peak_imbalance_index']:.2f}，"
                    f"在 {window.get('start')}-{window.get('end')} 转向需求明显不均。",
                    fact_id="metrics.inter_evaluation.imbalance_windows",
                    checklist_item_id="inter_evaluation",
                    metric="imbalance_index",
                )
            )
        elif imbalance["peak_imbalance_index"] >= HIGH_IMBALANCE:
            facts.append(
                _make_fact(
                    f"失衡指数峰值 {imbalance['peak_imbalance_index']:.2f}，进口间需求差异较大。",
                    fact_id="metrics.inter_evaluation.imbalance_peak",
                    checklist_item_id="inter_evaluation",
                    metric="imbalance_index",
                )
            )

    if service_level.get("worst_los"):
        los_text = (
            f"服务水平最差至 {service_level['worst_los']}"
            f"（{service_level.get('worst_los_time') or '全天综合'}）"
        )
        if service_level.get("anomaly_note"):
            los_text = f"{los_text}；{service_level['anomaly_note']}"
        facts.append(
            _make_fact(
                f"{los_text}。",
                fact_id="metrics.inter_evaluation.worst_los",
                checklist_item_id="inter_evaluation",
                metric="los",
            )
        )

    constraints = supply_constraints.get("static_constraints") or []
    if constraints:
        facts.append(
            _make_fact(
                f"设施约束：{'；'.join(constraints[:3])}。",
                fact_id="metrics.channelization.constraints",
                checklist_item_id="channelization",
            )
        )
    if (supply_constraints.get("complaint_count") or 0) > 0:
        sample = (supply_constraints.get("complaint_samples") or ["-"])[0]
        facts.append(
            _make_fact(
                f"近期投诉 {supply_constraints['complaint_count']} 条，如「{sample[:40]}」。",
                fact_id="metrics.complaint_records.sample",
                checklist_item_id="complaint_records",
            )
        )

    segment_count = signal_timing.get("schedule_segment_count") or 0
    plan_count = signal_timing.get("plan_count") or 0
    timing_parts = []
    if signal_timing.get("current_cycle_s"):
        timing_parts.append(f"当前周期 {signal_timing.get('current_cycle_s')}s")
    if signal_timing.get("phase_count"):
        timing_parts.append(f"相位/阶段 {signal_timing.get('phase_count')} 个")
    if signal_timing.get("green_ratio_min") is not None and signal_timing.get("green_ratio_max") is not None:
        timing_parts.append(
            f"绿信比 {signal_timing['green_ratio_min']:.2f}~{signal_timing['green_ratio_max']:.2f}"
        )
    if signal_timing.get("min_green_min_s") is not None and signal_timing.get("min_green_max_s") is not None:
        timing_parts.append(
            f"最小绿 {signal_timing['min_green_min_s']:.0f}~{signal_timing['min_green_max_s']:.0f}s"
        )
    cycle_check = signal_timing.get("cycle_consistency") or {}
    if cycle_check.get("stage_total_sec") is not None:
        timing_parts.append(f"阶段总时长 {cycle_check['stage_total_sec']:.0f}s")
    if cycle_check.get("status") == "mismatch":
        timing_parts.append(f"周期校验不一致（差值 {cycle_check.get('diff_sec')}s）")
    timing_suffix = f"，{'，'.join(timing_parts)}" if timing_parts else ""
    if segment_count:
        facts.append(
            _make_fact(
                f"配时方案共 {plan_count} 套，时段调度划分 {segment_count} 段"
                f"（日方案 {signal_timing.get('day_plan_count') or '-'} 个）{timing_suffix}。",
                fact_id="metrics.schedule_cfg.segments",
                checklist_item_id="schedule_cfg",
            )
        )
    elif plan_count:
        facts.append(
            _make_fact(
                f"配时方案共 {plan_count} 套{timing_suffix}。",
                fact_id="metrics.plan_cfg.count",
                checklist_item_id="plan_cfg",
            )
        )
    consistency = signal_timing.get("flow_green_consistency") or {}
    if consistency.get("verdict") in {"mismatch", "weak"}:
        facts.append(
            _make_fact(
                f"流量份额与有效绿时间份额一致性为 {consistency.get('verdict')}，"
                f"Spearman 相关系数 {consistency.get('spearmanTau')}。",
                fact_id="metrics.signal_timing.flow_green_consistency",
                checklist_item_id="plan_cfg",
            )
        )
    conflicts = signal_timing.get("stage_conflicts") or []
    if conflicts:
        first = conflicts[0]
        facts.append(
            _make_fact(
                f"阶段放行存在冲突线索：{first.get('冲突流向')}。",
                fact_id="metrics.signal_timing.stage_conflicts",
                checklist_item_id="signal_lane_mapping",
            )
        )
    return facts


def _fact_by_keyword(facts: list[Any], keywords: tuple[str, ...]) -> str | None:
    for fact in facts:
        text = _fact_text(fact)
        if any(keyword in text for keyword in keywords):
            return text
    return None


def _detect_conclusion_anomalies(insights: dict[str, Any]) -> list[dict[str, str]]:
    anomalies: list[dict[str, str]] = []
    service = insights.get("service_level") or {}
    if service.get("anomaly_corrected"):
        anomalies.append(
            {
                "topic": "服务水平",
                "issue": service.get("anomaly_note") or "最差 LOS 与流量/延误不匹配",
                "suggestion": "结合流量、延误与饱和度重新表述，避免将低流量时段误判为极差服务。",
            }
        )
    for item in insights.get("movement_saturation") or []:
        label = str(item.get("label") or "")
        if "_" in label and any(ch.isdigit() for ch in label.split("_", 1)[0]):
            anomalies.append(
                {
                    "topic": "进口方向描述",
                    "issue": f"仍使用编号型方向标签：{label}",
                    "suggestion": "应改写为东直行、西左转等中文方位描述。",
                }
            )
            break
    supply = insights.get("supply_constraints") or {}
    if "funnel_effect" in (supply.get("static_flags") or []) and not supply.get("funnel_details"):
        anomalies.append(
            {
                "topic": "设施约束",
                "issue": "标记漏斗效应但未给出直行进口与出口车道对比明细",
                "suggestion": "说明具体哪个进口直行车道数大于对应出口车道数。",
            }
        )
    return anomalies


def extract_metrics_insights(
    profile: dict[str, Any],
    raw: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build structured time-series insights from profile and optional PG raw rows."""
    raw = raw or {}
    task = task or {}
    context = task.get("context") or {}
    supply = profile.get("supply_profile") or {}
    channel_rows = list(supply.get("channelization") or (task.get("scope") or {}).get("channelization") or [])
    dir_lookup = _build_dir_lookup(channel_rows)
    congestion = profile.get("congestion_profile") or {}
    data_window = str(context.get("time_window") or congestion.get("time_window") or "全天")

    evaluation_rows = list(raw.get("evaluation") or raw.get("inter_evaluation") or [])
    sat_rows = _enrich_rows_with_directions(list(raw.get("turn_saturation") or []), dir_lookup)
    perf_rows = _enrich_rows_with_directions(list(raw.get("turn_perf") or []), dir_lookup)
    util_rows = _enrich_rows_with_directions(list(raw.get("green_utilization") or []), dir_lookup)
    flow_rows = _enrich_rows_with_directions(list(raw.get("turn_flow") or []), dir_lookup)

    inter_series = _intersection_series(evaluation_rows)
    peak_step, peak_value = _peak_from_series(inter_series)
    intersection_block = {
        "peak_saturation": peak_value or _as_float((profile.get("traffic_state") or {}).get("saturation")),
        "peak_time": _time_label(peak_step) if peak_step is not None else None,
        "high_saturation_windows": _windows_from_series(inter_series, HIGH_SATURATION),
        "oversaturation_windows": _windows_from_series(inter_series, OVERSATURATION),
    }

    movement_series, movement_labels = _movement_series(sat_rows, dir_lookup=dir_lookup)
    movement_blocks: list[dict[str, Any]] = []
    for key, series in movement_series.items():
        peak_move_step, peak_move_value = _peak_from_series(series)
        movement_blocks.append(
            {
                "movement": key,
                "label": movement_labels.get(key, key),
                "peak_saturation": peak_move_value,
                "peak_time": _time_label(peak_move_step) if peak_move_step is not None else None,
                "high_saturation_windows": _windows_from_series(series, HIGH_SATURATION),
                "oversaturation_windows": _windows_from_series(series, OVERSATURATION),
            }
        )
    movement_blocks.sort(key=lambda item: item.get("peak_saturation") or 0, reverse=True)

    signal_timing = _summarize_signal_timing(profile, raw)
    queue_delay = _summarize_queue_delay(perf_rows, dir_lookup=dir_lookup)
    green_efficiency = _summarize_green_efficiency(util_rows, profile, dir_lookup=dir_lookup)
    demand_pattern = _summarize_demand_pattern(flow_rows, dir_lookup=dir_lookup)
    imbalance = _summarize_imbalance(evaluation_rows, profile)
    service_level = _summarize_service_level(
        evaluation_rows,
        profile,
        perf_rows=perf_rows,
        flow_rows=flow_rows,
    )
    supply_constraints = _summarize_supply_constraints(profile, task, raw)

    insights_body = {
        "data_window": data_window,
        "thresholds": {
            "high_saturation": HIGH_SATURATION,
            "oversaturation": OVERSATURATION,
            "long_queue_m": LONG_QUEUE_M,
            "high_delay_index": HIGH_DELAY_INDEX,
            "low_green_utilization": LOW_GREEN_UTIL,
            "high_imbalance": HIGH_IMBALANCE,
        },
        "intersection_saturation": intersection_block,
        "movement_saturation": movement_blocks[:8],
        "queue_delay": queue_delay,
        "green_efficiency": green_efficiency,
        "demand_pattern": demand_pattern,
        "imbalance": imbalance,
        "service_level": service_level,
        "supply_constraints": supply_constraints,
        "signal_timing": signal_timing,
        "management_attention": _management_attention(
            {
                "intersection_saturation": intersection_block,
                "queue_delay": queue_delay,
                "green_efficiency": green_efficiency,
                "imbalance": imbalance,
                "supply_constraints": supply_constraints,
                "service_level": service_level,
                "signal_timing": signal_timing,
            }
        ),
    }
    insights_body["facts"] = _build_facts(
        data_window,
        intersection_block,
        movement_blocks,
        signal_timing,
        queue_delay,
        green_efficiency,
        demand_pattern,
        imbalance,
        service_level,
        supply_constraints,
    )
    insights_body["conclusion_anomalies"] = _detect_conclusion_anomalies(insights_body)
    return insights_body


def build_template_interpretation(insights: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Rule-based narrative when LLM is unavailable."""
    supply = profile.get("supply_profile") or {}
    name = str(supply.get("name") or "该路口")
    facts = insights.get("facts") or []
    highlights: list[dict[str, str]] = []

    def add_highlight(topic: str, keywords: tuple[str, ...], fallback: str) -> None:
        text = _fact_by_keyword(facts, keywords) or fallback
        if text and text != fallback:
            highlights.append({"topic": topic, "text": text})

    intersection = insights.get("intersection_saturation") or {}
    if intersection.get("oversaturation_windows") or intersection.get("high_saturation_windows") or intersection.get("peak_saturation"):
        add_highlight("路口运行", ("观测窗口", "路口在", "相对平稳"), "暂无路口饱和时序。")
    if insights.get("movement_saturation"):
        add_highlight("进口压力", ("进口方向",), "进口方向压力分布相对均匀。")
    if insights.get("queue_delay"):
        add_highlight("排队延误", ("排队", "延误", "长排队"), "排队延误时序信息有限。")
    if insights.get("green_efficiency"):
        add_highlight("绿灯利用", ("绿灯利用率", "空放"), "绿灯利用整体正常。")
    if insights.get("demand_pattern"):
        add_highlight("流量结构", ("总转向流量", "主流量"), "流量结构信息有限。")
    if insights.get("imbalance", {}).get("peak_imbalance_index"):
        add_highlight("需求失衡", ("失衡指数",), "进口间需求相对均衡。")
    if insights.get("supply_constraints", {}).get("static_constraints") or insights.get("supply_constraints", {}).get("complaint_count"):
        add_highlight("设施与反馈", ("设施约束", "投诉"), "未发现明显设施约束或投诉。")
    if insights.get("signal_timing", {}).get("plan_count"):
        add_highlight("配时方案", ("配时方案",), "已加载配时方案信息。")

    narrative = f"{name}在{insights.get('data_window', '观测窗口')}的运行特征如下：" + " ".join(_fact_text(fact) for fact in facts)
    if not facts:
        narrative = f"{name}缺少 5 分钟时序评价数据，无法推断运行时段特征，请补采 DWS 表后再解读。"
    return {
        "source": "template",
        "narrative": narrative,
        "highlights": highlights[:6],
        "metrics_insights": insights,
    }


def interpret_key_metrics(
    profile: dict[str, Any],
    raw: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Public entry: structured insights plus template interpretation."""
    insights = extract_metrics_insights(profile, raw=raw, task=task)
    interpretation = build_template_interpretation(insights, profile)
    profile_refs = _CFG.build_profile_evidence_refs({"metrics_insights": insights, "evidence": profile.get("evidence") or []})
    return {
        "metrics_insights": insights,
        "metrics_interpretation": interpretation,
        "evidence_chain": profile_refs,
    }
