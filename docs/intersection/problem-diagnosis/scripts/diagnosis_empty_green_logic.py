"""Empty green detection: sustained low green_utilization windows per movement."""

from __future__ import annotations

import importlib.util
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable


def _load_imbalance_helpers():
    spec = importlib.util.spec_from_file_location(
        "diagnosis_imbalance_logic",
        Path(__file__).resolve().parent / "diagnosis_imbalance_logic.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 diagnosis_imbalance_logic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_IMB = _load_imbalance_helpers()
find_sustained_windows = _IMB.find_sustained_windows
min_sustained_steps = _IMB.min_sustained_steps
_raw_from_profile = _IMB._raw_from_profile

TURN_DIR_LABELS = {1: "左转", 2: "直行", 3: "右转"}
CARDINAL_PREFIXES = ("东", "南", "西", "北", "东北", "东南", "西南", "西北")


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compact_dir_label(label: Any) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    for suffix in ("进口", "出口"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    for prefix in CARDINAL_PREFIXES:
        if text.startswith(prefix) or prefix in text[:3]:
            return prefix
    return text


def _build_dir_lookup(profile: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    scope = profile.get("scope") or {}
    supply = profile.get("supply_profile") or {}
    channel_rows = (
        list(supply.get("channelization") or [])
        + list(scope.get("channelization") or [])
        + list(supply.get("approaches") or scope.get("approaches") or [])
    )
    for row in channel_rows:
        if not isinstance(row, dict):
            continue
        link_id = row.get("link_id")
        label = row.get("dir4_label") or row.get("dir8_label") or ""
        if not link_id or not label:
            continue
        link_key = str(link_id)
        lookup[link_key] = str(label)
        lookup[link_key[-4:]] = str(label)
    return lookup


def _resolve_dir_label(row: dict[str, Any], dir_lookup: dict[str, str]) -> str:
    raw_label = row.get("f_dir_8_label") or row.get("dir8_label") or row.get("dir4_label")
    if raw_label:
        return _compact_dir_label(raw_label)
    link_id = str(row.get("link_id") or row.get("f_dir_8") or "")
    mapped = dir_lookup.get(link_id) or dir_lookup.get(link_id[-4:])
    return _compact_dir_label(mapped) if mapped else ""


def _movement_key(row: dict[str, Any]) -> str:
    link_id = str(row.get("link_id") or row.get("f_dir_8") or "")[-4:]
    turn_no = row.get("turn_dir_no")
    if turn_no is None or turn_no == "":
        turn = "聚合"
    else:
        turn = TURN_DIR_LABELS.get(int(_as_float(turn_no)), str(turn_no))
    return f"{link_id}_{turn}"


def _movement_label(row: dict[str, Any], dir_lookup: dict[str, str]) -> str:
    dir_label = _resolve_dir_label(row, dir_lookup)
    turn_label = row.get("turn_dir_label") or TURN_DIR_LABELS.get(int(_as_float(row.get("turn_dir_no"))))
    if dir_label and turn_label and turn_label != "方向聚合":
        return f"{dir_label}{turn_label}"
    if dir_label and str(row.get("turn_dir_no") or "") == "":
        return dir_label
    if dir_label:
        return f"{dir_label}{turn_label or '流向'}"
    if turn_label:
        return str(turn_label)
    return _movement_key(row)


def _movement_green_series(
    rows: list[dict[str, Any]],
    dir_lookup: dict[str, str],
) -> tuple[dict[str, dict[int, float]], dict[str, str]]:
    series_map: dict[str, dict[int, float]] = {}
    labels: dict[str, str] = {}
    for row in rows:
        step = row.get("step_index")
        if step is None:
            continue
        value = _as_float(row.get("green_utilization"))
        if value <= 0:
            continue
        key = _movement_key(row)
        labels[key] = _movement_label(row, dir_lookup)
        step_index = int(step)
        bucket = series_map.setdefault(key, {})
        bucket[step_index] = max(bucket.get(step_index, value), value)
    return series_map, labels


def _movement_weight_key(row: dict[str, Any]) -> tuple[str, int]:
    link_id = str(row.get("link_id") or row.get("f_dir_8") or "")
    turn_no = int(_as_float(row.get("turn_dir_no")))
    return link_id, turn_no


def _green_time_seconds(row: dict[str, Any]) -> float:
    return _as_float(row.get("green_time_plan") or row.get("min_green_time") or row.get("green_sec"))


def _build_green_time_lookups(
    raw: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[dict[tuple[int, str, int], float], dict[tuple[str, int], float]]:
    """Return step-specific and static green-time weights for import×turn movements."""
    step_lookup: dict[tuple[int, str, int], float] = {}
    for row in raw.get("min_green") or []:
        step = row.get("step_index")
        if step is None:
            continue
        weight = _green_time_seconds(row)
        if weight <= 0:
            continue
        link_id, turn_no = _movement_weight_key(row)
        key = (int(step), link_id, turn_no)
        step_lookup[key] = max(step_lookup.get(key, 0.0), weight)

    static_lookup: dict[tuple[str, int], float] = {}
    control = profile.get("control_profile") or profile.get("signal") or {}
    for row in control.get("min_green_detail") or []:
        if not isinstance(row, dict):
            continue
        weight = _green_time_seconds(row)
        if weight <= 0:
            continue
        link_id, turn_no = _movement_weight_key(row)
        for link_key in {link_id, link_id[-4:]}:
            static_lookup[(link_key, turn_no)] = max(static_lookup.get((link_key, turn_no), 0.0), weight)

    min_green_map = control.get("min_green_s") or {}
    if isinstance(min_green_map, dict):
        for movement_key, weight in min_green_map.items():
            weight_value = _as_float(weight)
            if weight_value <= 0:
                continue
            text = str(movement_key)
            if "_" in text:
                link_part, turn_text = text.rsplit("_", 1)
                turn_no = next((code for code, label in TURN_DIR_LABELS.items() if label == turn_text), 0)
                static_lookup[(link_part[-4:], turn_no)] = max(
                    static_lookup.get((link_part[-4:], turn_no), 0.0),
                    weight_value,
                )

    return step_lookup, static_lookup


def _row_green_time_weight(
    row: dict[str, Any],
    step_lookup: dict[tuple[int, str, int], float],
    static_lookup: dict[tuple[str, int], float],
) -> float:
    weight = _green_time_seconds(row)
    if weight > 0:
        return weight
    step = row.get("step_index")
    link_id, turn_no = _movement_weight_key(row)
    if step is not None:
        for link_key in {link_id, link_id[-4:]}:
            matched = step_lookup.get((int(step), link_key, turn_no))
            if matched and matched > 0:
                return matched
    for link_key in {link_id, link_id[-4:]}:
        matched = static_lookup.get((link_key, turn_no))
        if matched and matched > 0:
            return matched
    return 0.0


def _weighted_average(pairs: list[tuple[float, float]]) -> float:
    total_weight = sum(weight for _, weight in pairs)
    if total_weight <= 0:
        return 0.0
    return sum(value * weight for value, weight in pairs) / total_weight


def _intersection_green_series(
    rows: list[dict[str, Any]],
    *,
    step_lookup: dict[tuple[int, str, int], float],
    static_lookup: dict[tuple[str, int], float],
) -> dict[int, float]:
    buckets: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        step = row.get("step_index")
        if step is None:
            continue
        value = _as_float(row.get("green_utilization"))
        if value <= 0:
            continue
        weight = _row_green_time_weight(row, step_lookup, static_lookup)
        if weight <= 0:
            continue
        buckets[int(step)].append((value, weight))
    return {step: round(_weighted_average(pairs), 4) for step, pairs in buckets.items() if pairs}


def _window_identity(window: dict[str, Any]) -> tuple[Any, ...]:
    return (window.get("movement"), window.get("start_step"), window.get("end_step"))


def _dedupe_windows(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for window in windows:
        key = _window_identity(window)
        current = deduped.get(key)
        if current is None or window.get("average", 1.0) < current.get("average", 1.0):
            deduped[key] = window
    return list(deduped.values())


def _format_movement_window(window: dict[str, Any]) -> str:
    return (
        f"{window['start']}-{window['end']} {window['movement_label']} "
        f"绿灯利用率平均 {window['average']:.2f}（阈值 {window['threshold']:.2f}）"
    )


def _movement_window(
    *,
    movement: str,
    movement_label: str,
    window: dict[str, Any],
    util_threshold: float,
) -> dict[str, Any]:
    return {
        **window,
        "metric": "green_utilization",
        "metric_label": "绿灯利用率",
        "movement": movement,
        "movement_label": movement_label,
        "threshold": util_threshold,
    }


def _collect_movement_windows(
    movement_series: dict[str, dict[int, float]],
    movement_labels: dict[str, str],
    *,
    util_threshold: float,
    min_steps: int,
) -> list[dict[str, Any]]:
    trigger_windows: list[dict[str, Any]] = []
    for movement, series in movement_series.items():
        label = movement_labels.get(movement, movement)
        for window in find_sustained_windows(series, util_threshold, min_steps=min_steps, above=False):
            trigger_windows.append(
                _movement_window(
                    movement=movement,
                    movement_label=label,
                    window=window,
                    util_threshold=util_threshold,
                )
            )
    return trigger_windows


def _movements_in_util_window(
    window: dict[str, Any],
    movement_series: dict[str, dict[int, float]],
    movement_labels: dict[str, str],
    *,
    util_threshold: float,
    min_steps: int,
) -> list[dict[str, Any]]:
    start_step = int(window["start_step"])
    end_step = int(window["end_step"])
    results: list[dict[str, Any]] = []
    for movement, series in movement_series.items():
        segment = {step: value for step, value in series.items() if start_step <= step <= end_step}
        if len(segment) < min_steps:
            continue
        avg_util = round(sum(segment.values()) / len(segment), 3)
        if avg_util >= util_threshold:
            continue
        label = movement_labels.get(movement, movement)
        results.append(
            _movement_window(
                movement=movement,
                movement_label=label,
                window={
                    "start_step": start_step,
                    "end_step": end_step,
                    "start": window["start"],
                    "end": window["end"],
                    "duration_min": window["duration_min"],
                    "average": avg_util,
                    "peak": round(min(segment.values()), 3),
                    "threshold": util_threshold,
                },
                util_threshold=util_threshold,
            )
        )
    results.sort(key=lambda item: item["average"])
    return results


def evaluate_empty_green(
    profile: dict[str, Any],
    threshold_fn: Callable[[str], float],
) -> dict[str, Any]:
    raw = _raw_from_profile(profile)
    util_rows = list(raw.get("green_utilization") or [])
    dir_lookup = _build_dir_lookup(profile)
    step_lookup, static_lookup = _build_green_time_lookups(raw, profile)
    min_steps = min_sustained_steps(threshold_fn)
    util_threshold = threshold_fn("green.low_utilization_diagnosis")

    movement_series, movement_labels = _movement_green_series(util_rows, dir_lookup)
    intersection_series = _intersection_green_series(
        util_rows,
        step_lookup=step_lookup,
        static_lookup=static_lookup,
    )

    trigger_windows = _collect_movement_windows(
        movement_series,
        movement_labels,
        util_threshold=util_threshold,
        min_steps=min_steps,
    )

    if not trigger_windows and intersection_series and movement_series:
        for window in find_sustained_windows(
            intersection_series,
            util_threshold,
            min_steps=min_steps,
            above=False,
        ):
            trigger_windows.extend(
                _movements_in_util_window(
                    window,
                    movement_series,
                    movement_labels,
                    util_threshold=util_threshold,
                    min_steps=min_steps,
                )
            )

    if not trigger_windows and intersection_series and not movement_series:
        for window in find_sustained_windows(
            intersection_series,
            util_threshold,
            min_steps=min_steps,
            above=False,
        ):
            trigger_windows.append(
                _movement_window(
                    movement="intersection",
                    movement_label="路口整体",
                    window=window,
                    util_threshold=util_threshold,
                )
            )

    trigger_windows = _dedupe_windows(trigger_windows)
    trigger_windows.sort(key=lambda item: (item["average"], -item["duration_min"]))

    has_series = bool(util_rows)
    triggered = bool(trigger_windows)

    if not has_series:
        summary = "缺少绿灯利用率时序数据"
    elif triggered:
        detail_lines = build_empty_green_detail_lines(trigger_windows, util_threshold)
        summary = "；".join(detail_lines[:3])
    else:
        peak_util = min(intersection_series.values()) if intersection_series else 1.0
        summary = (
            f"路口最低绿灯利用率={peak_util:.2f}（按进口转向绿灯时间加权），"
            f"未出现连续{min_steps * 5}分钟低于阈值 {util_threshold:.2f} 的时段"
        )

    evidence: list[dict[str, Any]] = []
    for window in trigger_windows[:8]:
        evidence.append(
            {
                "metric": "green_utilization",
                "value": window["average"],
                "threshold": util_threshold,
                "time_window": f"{window['start']}-{window['end']}",
                "duration_min": window["duration_min"],
                "movement": window["movement_label"],
            }
        )

    best = trigger_windows[0] if trigger_windows else None
    score = max(0.5, 1.0 - best["average"]) if best else 0.0

    return {
        "triggered": triggered,
        "has_data": has_series,
        "summary": summary,
        "root_cause": build_empty_green_root_cause(trigger_windows, util_threshold),
        "detail_lines": build_empty_green_detail_lines(trigger_windows, util_threshold),
        "description": build_empty_green_root_cause(trigger_windows, util_threshold),
        "evidence": evidence,
        "trigger_windows": trigger_windows,
        "score": round(min(1.0, score), 3) if triggered else 0.0,
    }


def _window_sort_key(window: dict[str, Any]) -> tuple[int, str]:
    return (int(window.get("start_step") or 0), str(window.get("start") or ""))


def _format_period_value(index: int, window: dict[str, Any]) -> str:
    period = f"{window['start']}-{window['end']}"
    value = f"{window['average']:.2f}"
    if index == 0:
        return f"{period} 数值 {value}"
    return f"{period} 数值为 {value}"


def _summarize_movement_windows(
    movement_label: str,
    windows: list[dict[str, Any]],
    util_threshold: float,
) -> str:
    ordered = sorted(windows, key=_window_sort_key)
    period_text = "，".join(_format_period_value(index, window) for index, window in enumerate(ordered))
    return (
        f"{movement_label}存在 {len(ordered)} 段持续低绿灯利用率（<{util_threshold:.2f}），"
        f"分别为{period_text}。"
    )


def build_empty_green_root_cause(trigger_windows: list[dict[str, Any]], util_threshold: float) -> str:
    if not trigger_windows:
        return "绿灯时间与实际到达不匹配，存在绿灯利用率偏低的空放损失。"
    return "绿灯时间与实际到达不匹配。"


def build_empty_green_detail_lines(trigger_windows: list[dict[str, Any]], util_threshold: float) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    movement_order: list[str] = []
    for window in trigger_windows:
        label = str(window.get("movement_label") or window.get("movement") or "未知方向")
        if label not in grouped:
            movement_order.append(label)
            grouped[label] = []
        grouped[label].append(window)
    return [
        _summarize_movement_windows(label, grouped[label], util_threshold)
        for label in movement_order[:6]
    ]


def build_empty_green_description(trigger_windows: list[dict[str, Any]], util_threshold: float) -> str:
    """Backward-compatible single string; prefer root_cause + detail_lines."""
    return build_empty_green_root_cause(trigger_windows, util_threshold)
