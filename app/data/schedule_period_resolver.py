"""从用户时段表达解析 schedule 配时方案与优化流量窗口。

对齐参考项目 ``extractSchedulePeriods`` + ``target_periods`` 口径：
- 显式 ``17:30-18:30`` → 直接作为 target_periods；
- ``早高峰/晚高峰/平峰`` → hour_ranges 与 schedule 时段最大重叠匹配；
- 输出 ``period_plan_no`` 供切换日计划方案。
"""

from __future__ import annotations

import re
from typing import Any

from app.data.pg_adapters import parse_time_step_range
from app.data.ticket_nlu_schema import load_ticket_nlu_schema, resolve_period_label


def normalize_hhmm(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    match = re.search(r"(\d{1,2})[:：](\d{2})", text)
    if not match:
        return None
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def period_key_from_times(start: str, end: str) -> str:
    return f"{start}-{end}"


def minutes_from_hhmm(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def parse_explicit_period_key(text: str | None) -> str | None:
    """解析 ``07:00-09:00`` / ``07:00–09:00`` 形式。"""
    if not text:
        return None
    normalized = str(text).replace("–", "-").replace("—", "-").strip()
    matches = re.findall(r"(\d{1,2})[:：](\d{2})", normalized)
    if len(matches) < 2:
        return None
    start = f"{int(matches[0][0]):02d}:{matches[0][1]}"
    end = f"{int(matches[1][0]):02d}:{matches[1][1]}"
    return period_key_from_times(start, end)


def extract_schedule_periods(
    schedule_rows: list[dict[str, Any]] | None,
    *,
    day_of_week: int | None = None,
) -> list[dict[str, Any]]:
    """从 PG schedule_cfg 行提取日计划时段列表。"""
    rows = [row for row in (schedule_rows or []) if isinstance(row, dict)]
    if day_of_week is not None:
        rows = [
            row
            for row in rows
            if row.get("week_day_no") is None or int(row.get("week_day_no")) == int(day_of_week)
        ]

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(
        rows,
        key=lambda item: (
            int(item.get("period_seq_no") or 999),
            minutes_from_hhmm(normalize_hhmm(item.get("start_time")) or "00:00"),
        ),
    ):
        start = normalize_hhmm(row.get("start_time"))
        end = normalize_hhmm(row.get("end_time"))
        if not start or not end:
            continue
        key = period_key_from_times(start, end)
        if key in seen:
            continue
        seen.add(key)
        plan_no = row.get("period_plan_no") or row.get("plan_no")
        items.append(
            {
                "key": key,
                "label": key.replace("-", "–"),
                "start_time": start,
                "end_time": end,
                "plan_no": str(plan_no).strip() if plan_no not in (None, "") else None,
                "period_seq_no": row.get("period_seq_no"),
                "day_plan_no": row.get("day_plan_no"),
            }
        )
    items.sort(key=lambda item: minutes_from_hhmm(item["start_time"]))
    return items


def _window_minutes(start: str, end: str) -> tuple[int, int]:
    lo = minutes_from_hhmm(start)
    hi = minutes_from_hhmm(end)
    if hi <= lo:
        hi += 24 * 60
    return lo, hi


def _overlap_minutes(a_start: str, a_end: str, b_start: str, b_end: str) -> int:
    a_lo, a_hi = _window_minutes(a_start, a_end)
    b_lo, b_hi = _window_minutes(b_start, b_end)
    return max(0, min(a_hi, b_hi) - max(a_lo, b_lo))


def _peak_window_from_label(label: str | None) -> tuple[str, str] | None:
    if not label:
        return None
    schema = load_ticket_nlu_schema()
    hour_ranges = (schema.get("period") or {}).get("hour_ranges") or {}
    bounds = hour_ranges.get(label)
    if not isinstance(bounds, list) or len(bounds) != 2:
        return None
    lo, hi = int(bounds[0]), int(bounds[1])
    return f"{lo:02d}:00", f"{hi:02d}:00"


def resolve_timing_period(
    ticket: dict[str, Any],
    schedule_rows: list[dict[str, Any]] | None,
    *,
    day_of_week: int | None = None,
) -> dict[str, Any]:
    """解析用户时段表达 → 优化器 target_periods 与 schedule plan_no。"""
    periods = extract_schedule_periods(schedule_rows, day_of_week=day_of_week)
    time_range = str(ticket.get("time_range") or "").strip()
    period_label = resolve_period_label(ticket.get("period"), time_range) or ticket.get("period")

    explicit_key = parse_explicit_period_key(time_range)
    match_method = "fallback"
    target_key: str | None = None
    query_start: str | None = None
    query_end: str | None = None

    if explicit_key:
        target_key = explicit_key
        match_method = "explicit_time_range"
        query_start, query_end = explicit_key.split("-", 1)
    elif period_label:
        peak_window = _peak_window_from_label(str(period_label))
        if peak_window:
            query_start, query_end = peak_window
            match_method = "peak_label"
            best_overlap = -1
            for item in periods:
                overlap = _overlap_minutes(
                    query_start,
                    query_end,
                    item["start_time"],
                    item["end_time"],
                )
                if overlap > best_overlap:
                    best_overlap = overlap
                    target_key = item["key"]
            if target_key is None and periods:
                target_key = periods[0]["key"]
                match_method = "peak_label_fallback_first"

    if target_key is None and periods:
        if time_range:
            hhmm = normalize_hhmm(time_range)
            if hhmm:
                query_start = hhmm
                query_end = hhmm
                best_overlap = -1
                for item in periods:
                    overlap = _overlap_minutes(
                        hhmm,
                        hhmm,
                        item["start_time"],
                        item["end_time"],
                    )
                    if overlap > best_overlap:
                        best_overlap = overlap
                        target_key = item["key"]
                match_method = "schedule_overlap"
        if target_key is None:
            target_key = periods[0]["key"]
            match_method = "fallback_first_period"

    if not target_key:
        step_lo, step_hi = parse_time_step_range(time_range or None)
        return {
            "ok": False,
            "reason": "缺少 schedule 时段且无法从 ticket 解析 time_range",
            "target_periods": [time_range] if time_range else [],
            "period_plan_no": None,
            "period_label": period_label,
            "step_index": step_lo,
            "step_index_end": step_hi,
            "match_method": "unresolved",
        }

    if query_start is None or query_end is None:
        query_start, query_end = target_key.split("-", 1)

    matched = next((item for item in periods if item["key"] == target_key), None)
    if matched is None and query_start and query_end:
        best_overlap = -1
        for item in periods:
            overlap = _overlap_minutes(
                query_start,
                query_end,
                item["start_time"],
                item["end_time"],
            )
            if overlap > best_overlap:
                best_overlap = overlap
                matched = item
        if matched and match_method == "explicit_time_range":
            match_method = "explicit_time_range_schedule_overlap"

    schedule_key = matched["key"] if matched else target_key
    flow_window_key = explicit_key or schedule_key
    step_lo, step_hi = parse_time_step_range(flow_window_key)

    return {
        "ok": True,
        "target_periods": [schedule_key],
        "flow_window": flow_window_key,
        "period_plan_no": matched.get("plan_no") if matched else None,
        "period_label": period_label or (matched.get("label") if matched else schedule_key),
        "schedule_period_key": schedule_key,
        "step_index": step_lo,
        "step_index_end": step_hi,
        "match_method": match_method,
        "schedule_periods": periods,
    }


def prepare_signal_for_ticket(
    signal: dict[str, Any],
    ticket: dict[str, Any],
    pg_raw: dict[str, Any] | None,
    *,
    day_of_week: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """按 ticket 时段切换日计划方案并重绑流量；返回 (signal, resolved)。"""
    pg_raw = pg_raw or {}
    schedule_rows = pg_raw.get("schedule_cfg") or []
    resolved = resolve_timing_period(ticket, schedule_rows, day_of_week=day_of_week)
    if not resolved.get("ok"):
        patched = dict(signal)
        patched["timing_period"] = resolved
        return patched, resolved

    plan_no = resolved.get("period_plan_no")
    plan_rows = pg_raw.get("plan") or []
    if not plan_rows or not plan_no:
        patched = dict(signal)
        patched["timing_period"] = resolved
        return patched, resolved

    from app.data.load_intersection_from_pg import rebuild_signal_for_period

    rebuilt = rebuild_signal_for_period(
        plan_rows=plan_rows,
        schedule_rows=schedule_rows,
        min_green_rows=pg_raw.get("min_green") or [],
        signal_lane_mapping_rows=pg_raw.get("signal_lane_mapping") or [],
        stage_cfg_rows=pg_raw.get("stage_cfg") or [],
        stage_motor_flow_rows=pg_raw.get("stage_motor_flow") or [],
        flow_rows=pg_raw.get("turn_flow") or [],
        saturation_rows=pg_raw.get("turn_saturation") or [],
        channel_rows=pg_raw.get("channelization") or [],
        period_plan_no=str(plan_no),
        step_index=resolved.get("step_index"),
        step_index_end=resolved.get("step_index_end"),
    )
    if not rebuilt:
        patched = dict(signal)
        patched["timing_period"] = {**resolved, "rebuild_ok": False}
        return patched, resolved

    rebuilt["timing_period"] = {**resolved, "rebuild_ok": True}
    rebuilt["schedule_periods"] = resolved.get("schedule_periods") or []
    return rebuilt, resolved
