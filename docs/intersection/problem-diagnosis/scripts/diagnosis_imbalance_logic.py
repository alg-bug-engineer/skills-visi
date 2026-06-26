"""Service imbalance detection with sustained 5-minute time-series windows."""

from __future__ import annotations

from typing import Any, Callable

TURN_DIR_LABELS = {1: "左转", 2: "直行", 3: "右转"}
CARDINAL_PREFIXES = ("东", "南", "西", "北", "东北", "东南", "西南", "西北")


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


def _scalar_series(rows: list[dict[str, Any]], field: str) -> dict[int, float]:
    series: dict[int, float] = {}
    for row in rows:
        step = row.get("step_index")
        if step is None:
            continue
        value = _as_float(row.get(field))
        if value <= 0:
            continue
        step_index = int(step)
        series[step_index] = max(series.get(step_index, value), value)
    return series


def movement_saturation_gap_series(rows: list[dict[str, Any]]) -> dict[int, float]:
    """Per 5-min step: max(turn_saturation) - min(turn_saturation) across movements."""
    buckets: dict[int, list[float]] = {}
    for row in rows:
        step = row.get("step_index")
        if step is None:
            continue
        value = _as_float(row.get("turn_saturation"))
        if value <= 0:
            continue
        buckets.setdefault(int(step), []).append(value)
    return {
        step: round(max(values) - min(values), 4)
        for step, values in buckets.items()
        if len(values) >= 2
    }


def find_sustained_windows(
    series: dict[int, float],
    threshold: float,
    *,
    min_steps: int,
    above: bool = True,
) -> list[dict[str, Any]]:
    """Return windows where consecutive steps all meet threshold for at least min_steps."""
    if not series or min_steps <= 0:
        return []
    ordered = sorted(series.items())
    windows: list[dict[str, Any]] = []
    run_steps: list[int] = []
    run_values: list[float] = []

    def meets(value: float) -> bool:
        return value >= threshold if above else 0 < value < threshold

    def flush() -> None:
        if len(run_steps) >= min_steps:
            windows.append(
                {
                    "start_step": run_steps[0],
                    "end_step": run_steps[-1],
                    "start": _time_label(run_steps[0]),
                    "end": _time_label(run_steps[-1] + 1),
                    "duration_min": len(run_steps) * 5,
                    "average": round(sum(run_values) / len(run_values), 3),
                    "peak": round(max(run_values), 3),
                    "threshold": threshold,
                    "above": above,
                }
            )
        run_steps.clear()
        run_values.clear()

    prev_step: int | None = None
    for step, value in ordered:
        if meets(value) and (prev_step is None or step == prev_step + 1):
            run_steps.append(step)
            run_values.append(value)
        else:
            flush()
            if meets(value):
                run_steps = [step]
                run_values = [value]
            prev_step = step
            continue
        prev_step = step
    flush()
    return windows


def min_sustained_steps(threshold_fn: Callable[[str], float]) -> int:
    minutes = int(threshold_fn("imbalance.sustained_minutes"))
    step_minutes = int(threshold_fn("imbalance.sustained_step_minutes"))
    if step_minutes <= 0:
        step_minutes = 5
    return max(1, minutes // step_minutes)


def _raw_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    raw = profile.get("source_raw") or profile.get("raw") or {}
    return raw if isinstance(raw, dict) else {}


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
    if dir_label:
        return dir_label
    return _movement_key(row)


def _window_steps(window: dict[str, Any]) -> list[int]:
    start = int(window.get("start_step") or 0)
    end = int(window.get("end_step") or start)
    return list(range(start, end + 1))


def _movement_values_at_step(
    turn_saturation_rows: list[dict[str, Any]],
    step: int,
    dir_lookup: dict[str, str],
) -> dict[str, float]:
    values: dict[str, float] = {}
    for row in turn_saturation_rows:
        if int(row.get("step_index") or -1) != step:
            continue
        value = _as_float(row.get("turn_saturation"))
        if value <= 0:
            continue
        label = _movement_label(row, dir_lookup)
        values[label] = max(values.get(label, value), value)
    return values


def _peak_gap_extremes_in_window(
    turn_saturation_rows: list[dict[str, Any]],
    steps: list[int],
    dir_lookup: dict[str, str],
    *,
    min_gap: float,
) -> tuple[int, str, float, str, float, float] | None:
    """Find the step with largest turn_saturation spread inside the window."""
    best: tuple[int, str, float, str, float, float] | None = None
    for step in steps:
        values = _movement_values_at_step(turn_saturation_rows, step, dir_lookup)
        if len(values) < 2:
            continue
        ordered = sorted(values.items(), key=lambda item: item[1])
        low_label, low_value = ordered[0]
        high_label, high_value = ordered[-1]
        gap = round(high_value - low_value, 4)
        if gap < min_gap:
            continue
        if best is None or gap > best[5]:
            best = (step, high_label, high_value, low_label, low_value, gap)
    return best


def _format_window_text(window: dict[str, Any], metric_label: str) -> str:
    return (
        f"{window['start']}-{window['end']} 连续{window['duration_min']}分钟"
        f"{metric_label}平均 {window['average']:.2f}（阈值 {window['threshold']:.2f}）"
    )


def evaluate_service_imbalance(
    profile: dict[str, Any],
    threshold_fn: Callable[[str], float],
) -> dict[str, Any]:
    raw = _raw_from_profile(profile)
    evaluation_rows = list(raw.get("evaluation") or raw.get("inter_evaluation") or [])
    turn_saturation_rows = list(raw.get("turn_saturation") or [])

    imbalance_series = _scalar_series(evaluation_rows, "unbalance_index")
    gap_series = movement_saturation_gap_series(turn_saturation_rows)
    min_steps = min_sustained_steps(threshold_fn)

    imbalance_threshold = threshold_fn("imbalance.diagnosis")
    gap_threshold = threshold_fn("imbalance.movement_saturation_gap")

    imbalance_windows = find_sustained_windows(
        imbalance_series,
        imbalance_threshold,
        min_steps=min_steps,
    )
    gap_windows = find_sustained_windows(
        gap_series,
        gap_threshold,
        min_steps=min_steps,
    )

    trigger_windows: list[dict[str, Any]] = []
    for window in imbalance_windows:
        trigger_windows.append({**window, "metric": "imbalance_index", "metric_label": "失衡指数"})
    for window in gap_windows:
        trigger_windows.append(
            {**window, "metric": "movement_saturation_gap", "metric_label": "转向车流饱和度极差"}
        )

    has_series = bool(imbalance_series or gap_series)
    triggered = bool(trigger_windows)

    summary_parts: list[str] = []
    if not has_series:
        summary = "缺少失衡时序数据"
    else:
        if triggered:
            summary_parts.append("存在持续服务失衡时段")
            summary_parts.extend(_format_window_text(item, item["metric_label"]) for item in trigger_windows[:3])
            summary = "；".join(summary_parts)
        else:
            imbalance_peak = max(imbalance_series.values()) if imbalance_series else 0.0
            gap_peak = max(gap_series.values()) if gap_series else 0.0
            summary = (
                f"失衡指数峰值={imbalance_peak:.2f}，转向车流饱和度极差峰值={gap_peak:.2f}，"
                f"未出现连续{min_steps * 5}分钟超阈值时段"
            )

    evidence: list[dict[str, Any]] = []
    if imbalance_series:
        evidence.append(
            {
                "metric": "imbalance_index",
                "value": round(max(imbalance_series.values()), 3),
                "threshold": imbalance_threshold,
                "sustained_minutes": min_steps * 5,
            }
        )
    if gap_series:
        evidence.append(
            {
                "metric": "movement_saturation_gap",
                "value": round(max(gap_series.values()), 3),
                "threshold": gap_threshold,
                "sustained_minutes": min_steps * 5,
            }
        )
    for window in trigger_windows[:4]:
        evidence.append(
            {
                "metric": window["metric"],
                "value": window["average"],
                "threshold": window["threshold"],
                "time_window": f"{window['start']}-{window['end']}",
                "duration_min": window["duration_min"],
            }
        )

    best_window = max(trigger_windows, key=lambda item: item["average"]) if trigger_windows else None
    score_base = 0.0
    if best_window:
        score_base = max(0.55 + best_window["average"], 0.5 + best_window["average"])

    return {
        "triggered": triggered,
        "has_data": has_series,
        "summary": summary,
        "root_cause": build_service_imbalance_root_cause(trigger_windows),
        "detail_lines": build_service_imbalance_detail_lines(
            profile, trigger_windows, turn_saturation_rows, gap_threshold=gap_threshold
        ),
        "description": build_service_imbalance_root_cause(trigger_windows),
        "evidence": evidence,
        "trigger_windows": trigger_windows,
        "score": round(min(1.0, score_base), 3) if triggered else 0.0,
        "imbalance_index_peak": round(max(imbalance_series.values()), 3) if imbalance_series else 0.0,
        "movement_saturation_gap_peak": round(max(gap_series.values()), 3) if gap_series else 0.0,
    }


def build_service_imbalance_root_cause(trigger_windows: list[dict[str, Any]]) -> str:
    return "各进口、流向或相位绿时供给与需求分布不匹配。"


def build_service_imbalance_detail_lines(
    profile: dict[str, Any],
    trigger_windows: list[dict[str, Any]],
    turn_saturation_rows: list[dict[str, Any]],
    *,
    gap_threshold: float = 0.60,
) -> list[str]:
    if not trigger_windows:
        return []
    dir_lookup = _build_dir_lookup(profile)
    # 仅当同一时刻转向饱和度极差足够大时才展示方向对比，避免窗口均值掩盖真实失衡。
    min_gap = max(0.30, gap_threshold * 0.5)
    lines: list[str] = []
    for window in sorted(trigger_windows, key=lambda item: int(item.get("start_step") or 0))[:6]:
        line = _format_window_text(window, window["metric_label"])
        steps = _window_steps(window)
        peak = _peak_gap_extremes_in_window(
            turn_saturation_rows, steps, dir_lookup, min_gap=min_gap
        )
        if peak:
            peak_step, high_label, high_value, low_label, low_value, gap = peak
            peak_time = _time_label(peak_step)
            line += (
                f"；极差峰值 {gap:.2f} 出现在 {peak_time}，"
                f"最饱和方向为{high_label}（饱和度 {high_value:.2f}），"
                f"最不饱和方向为{low_label}（饱和度 {low_value:.2f}）"
            )
        lines.append(line + "。")
    return lines


def build_service_imbalance_description(trigger_windows: list[dict[str, Any]]) -> str:
    """Backward-compatible single string; prefer root_cause + detail_lines."""
    return build_service_imbalance_root_cause(trigger_windows)
