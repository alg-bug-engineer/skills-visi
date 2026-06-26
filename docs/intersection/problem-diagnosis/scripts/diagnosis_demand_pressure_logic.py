"""Demand pressure from sustained intersection high saturation (inter_evaluation series)."""

from __future__ import annotations

import importlib.util
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
_raw_from_profile = _IMB._raw_from_profile


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_number(*values: Any, default: float = 0.0) -> float:
    for value in values:
        if value is not None and value != "":
            return _as_float(value, default)
    return default


def _intersection_series(evaluation_rows: list[dict[str, Any]]) -> dict[int, float]:
    series: dict[int, float] = {}
    for row in evaluation_rows:
        step = row.get("step_index")
        if step is None:
            continue
        saturation = _as_float(row.get("saturation_max") or row.get("saturation_avg") or row.get("saturation"))
        if saturation <= 0:
            continue
        step_index = int(step)
        series[step_index] = max(series.get(step_index, saturation), saturation)
    return series


def _min_sustained_steps(duration_h: float, step_minutes: int = 5) -> int:
    if duration_h <= 0:
        return 1
    return max(1, int(round(duration_h * 60 / step_minutes)))


def analyze_demand_pressure(profile: dict[str, Any], threshold_fn: Callable[[str], float]) -> dict[str, Any]:
    """Detect demand pressure when intersection saturation stays above saturation.high."""
    sat_threshold = threshold_fn("saturation.high")
    duration_h_threshold = threshold_fn("demand.high_saturation_duration_h")
    min_steps = _min_sustained_steps(duration_h_threshold)

    raw = _raw_from_profile(profile)
    evaluation_rows = list(raw.get("evaluation") or raw.get("inter_evaluation") or [])
    series = _intersection_series(evaluation_rows)

    if series:
        windows = find_sustained_windows(series, sat_threshold, min_steps=min_steps, above=True)
        longest_min = 0
        if windows:
            longest = max(windows, key=lambda item: item["duration_min"])
            longest_min = int(longest["duration_min"])
        elif series:
            longest_min = _longest_contiguous_minutes(series, sat_threshold)
        duration_h = longest_min / 60.0
        triggered = bool(windows)
        summary_window = windows[0] if windows else None
        return {
            "has_data": True,
            "triggered": triggered,
            "duration_h": round(duration_h, 2),
            "saturation_threshold": sat_threshold,
            "duration_h_threshold": duration_h_threshold,
            "windows": windows[:3],
            "summary_window": summary_window,
            "source": "inter_evaluation",
            "step_count": len(series),
        }

    state = profile.get("traffic_state") if isinstance(profile.get("traffic_state"), dict) else {}
    metrics = profile.get("metrics_summary") or profile.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    duration_h = _first_number(state.get("high_saturation_duration_h"), metrics.get("high_saturation_duration_h"))
    if duration_h > 0:
        return {
            "has_data": True,
            "triggered": duration_h >= duration_h_threshold,
            "duration_h": round(duration_h, 2),
            "saturation_threshold": sat_threshold,
            "duration_h_threshold": duration_h_threshold,
            "windows": [],
            "summary_window": None,
            "source": "traffic_state",
            "step_count": 0,
        }

    return {
        "has_data": False,
        "triggered": False,
        "duration_h": 0.0,
        "saturation_threshold": sat_threshold,
        "duration_h_threshold": duration_h_threshold,
        "windows": [],
        "summary_window": None,
        "source": "",
        "step_count": 0,
    }


def _longest_contiguous_minutes(series: dict[int, float], threshold: float) -> int:
    longest = 0
    run = 0
    prev_step: int | None = None
    for step, value in sorted(series.items()):
        if value >= threshold and (prev_step is None or step == prev_step + 1):
            run += 1
        else:
            if value >= threshold:
                run = 1
            else:
                run = 0
        prev_step = step
        longest = max(longest, run)
    return longest * 5


def format_demand_pressure_summary(analysis: dict[str, Any]) -> str:
    sat_threshold = analysis.get("saturation_threshold", 0.8)
    duration_h = _as_float(analysis.get("duration_h"))
    duration_h_threshold = _as_float(analysis.get("duration_h_threshold"), 2.0)
    window = analysis.get("summary_window")
    if window:
        return (
            f"路口饱和度在 {window['start']}-{window['end']} 连续 ≥{sat_threshold:.0%} 持续 "
            f"{window['duration_min'] / 60:.1f}h（阈值 {duration_h_threshold:.0f}h）"
        )
    return (
        f"最长连续高饱和 {duration_h:.1f}h（饱和度 ≥{sat_threshold:.0%}，阈值 {duration_h_threshold:.0f}h）"
    )
