"""Sustained threshold windows for 5-minute DWS time series (checklist-aligned)."""

from __future__ import annotations

from typing import Any


def time_label(step_index: int) -> str:
    minutes = int(step_index) * 5
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def find_sustained_windows(
    series: dict[int, float],
    threshold: float,
    *,
    min_steps: int,
    above: bool = True,
) -> list[dict[str, Any]]:
    """Return windows where consecutive steps meet threshold for at least min_steps."""
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
                    "start": time_label(run_steps[0]),
                    "end": time_label(run_steps[-1] + 1),
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


def min_sustained_steps(sustained_minutes: int, step_minutes: int = 5) -> int:
    if step_minutes <= 0:
        step_minutes = 5
    return max(1, int(sustained_minutes) // step_minutes)


def scalar_series(rows: list[dict[str, Any]], field: str) -> dict[int, float]:
    series: dict[int, float] = {}
    for row in rows:
        step = row.get("step_index")
        if step is None:
            continue
        try:
            value = float(row.get(field) or 0)
        except (TypeError, ValueError):
            continue
        if value <= 0 and field not in ("unbalance_index",):
            continue
        step_index = int(step)
        series[step_index] = max(series.get(step_index, value), value)
    return series


def movement_saturation_gap_series(rows: list[dict[str, Any]]) -> dict[int, float]:
    buckets: dict[int, list[float]] = {}
    for row in rows:
        step = row.get("step_index")
        if step is None:
            continue
        try:
            value = float(row.get("turn_saturation") or 0)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        buckets.setdefault(int(step), []).append(value)
    return {
        step: round(max(values) - min(values), 4)
        for step, values in buckets.items()
        if len(values) >= 2
    }
