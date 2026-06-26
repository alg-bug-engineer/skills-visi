"""Data query window resolution (Plan D: DWD rolling window + DWS fallback)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from intersection_agent.models.domain import TimePeriod

DEFAULT_WINDOW_DAYS = 7
DEFAULT_TZ = ZoneInfo("Asia/Shanghai")

WEEKDAY_LABELS = frozenset({"早高峰", "晚高峰", "平峰", "工作日"})
WEEKEND_LABELS = frozenset({"周末", "周六", "周日"})


@dataclass(frozen=True)
class DataWindow:
    """Resolved time window for intersection metrics queries."""

    type: str
    reference_date: str
    date_from: str
    date_to: str
    time_slot_start: str
    time_slot_end: str
    time_label: str
    dow_filter: tuple[int, ...]
    primary_dow: int
    step_start: int
    step_end: int
    window_days: int = DEFAULT_WINDOW_DAYS

    def to_meta(
        self,
        *,
        source_tier: str | None = None,
        sample_count: int | None = None,
        dws_dow_filter: tuple[int, ...] | None = None,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        """Serialize for API / execution hooks."""
        payload: dict[str, Any] = {
            "type": self.type,
            "reference_date": self.reference_date,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "time_slot": f"{self.time_slot_start}-{self.time_slot_end}",
            "time_label": self.time_label,
            "dow_filter": list(self.dow_filter),
            "primary_dow": self.primary_dow,
            "step_index_range": [self.step_start, self.step_end],
            "window_days": self.window_days,
        }
        if source_tier:
            payload["source_tier"] = source_tier
        if sample_count is not None:
            payload["sample_count"] = sample_count
        if dws_dow_filter is not None:
            payload["dws_dow_filter"] = list(dws_dow_filter)
        if fallback_reason:
            payload["fallback_reason"] = fallback_reason
        return payload

    @property
    def date_from_value(self) -> date:
        """Parse date_from as date object for asyncpg."""
        return date.fromisoformat(self.date_from)

    @property
    def date_to_value(self) -> date:
        """Parse date_to as date object for asyncpg."""
        return date.fromisoformat(self.date_to)


def build_data_window(
    time_period: TimePeriod,
    *,
    reference_date: date | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    tz: ZoneInfo = DEFAULT_TZ,
) -> DataWindow:
    """Build rolling calendar window ending on reference_date (inclusive)."""
    ref = reference_date or datetime.now(tz).date()
    date_from = ref - timedelta(days=window_days - 1)
    start_h, start_m = _parse_hhmm(time_period.start)
    end_h, end_m = _parse_hhmm(time_period.end)
    start_step = (start_h * 60 + start_m) // 5
    end_step = max(start_step, (end_h * 60 + end_m) // 5 - 1)
    dow_filter = _resolve_dow_filter(time_period.label, ref, window_days)
    primary_dow = ref.isoweekday()

    return DataWindow(
        type="rolling_7d",
        reference_date=ref.isoformat(),
        date_from=date_from.isoformat(),
        date_to=ref.isoformat(),
        time_slot_start=time_period.start,
        time_slot_end=time_period.end,
        time_label=time_period.label,
        dow_filter=dow_filter,
        primary_dow=primary_dow,
        step_start=start_step,
        step_end=end_step,
        window_days=window_days,
    )


def time_to_step_range(
    time_period: TimePeriod,
    reference_date: date | None = None,
) -> tuple[int, int, int]:
    """Map time period to step range and primary day_of_week (PG: 1=Mon … 7=Sun)."""
    window = build_data_window(time_period, reference_date=reference_date)
    return window.step_start, window.step_end, window.primary_dow


def time_to_hour_range(time_period: TimePeriod) -> tuple[int, int]:
    """Map time period to hour range for DWD stat_time filters."""
    start_h, _ = _parse_hhmm(time_period.start)
    end_h, end_m = _parse_hhmm(time_period.end)
    end_hour_exclusive = end_h if end_m == 0 else end_h + 1
    return start_h, max(start_h + 1, end_hour_exclusive)


def slot_times(time_period: TimePeriod) -> tuple[time, time]:
    """Return slot start (inclusive) and end (exclusive) as time objects."""
    start_h, start_m = _parse_hhmm(time_period.start)
    end_h, end_m = _parse_hhmm(time_period.end)
    start_t = time(start_h, start_m)
    end_exclusive = time(end_h, end_m if end_m else 0)
    return start_t, end_exclusive


def _resolve_dow_filter(label: str, reference_date: date, window_days: int) -> tuple[int, ...]:
    """Infer PostgreSQL day_of_week filter from NLU label and calendar window."""
    if any(token in label for token in WEEKEND_LABELS):
        return (6, 7)
    if label in WEEKDAY_LABELS or "高峰" in label:
        return (1, 2, 3, 4, 5)

    calendar_dows = {
        (reference_date - timedelta(days=offset)).isoweekday()
        for offset in range(window_days)
    }
    return tuple(sorted(calendar_dows))


def _parse_hhmm(value: str) -> tuple[int, int]:
    """Parse HH:MM string."""
    parts = value.split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
