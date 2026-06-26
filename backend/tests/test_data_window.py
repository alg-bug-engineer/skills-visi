"""Data window resolution tests."""

from datetime import date

from intersection_agent.models.domain import TimePeriod
from intersection_agent.utils.data_window import build_data_window, time_to_step_range


def test_rolling_window_ends_on_reference_date():
    tp = TimePeriod(start="16:00", end="18:00", label="晚高峰")
    window = build_data_window(tp, reference_date=date(2026, 6, 24))
    assert window.reference_date == "2026-06-24"
    assert window.date_from == "2026-06-18"
    assert window.date_to == "2026-06-24"
    assert window.time_slot_start == "16:00"
    assert window.dow_filter == (1, 2, 3, 4, 5)


def test_weekend_label_uses_sat_sun():
    tp = TimePeriod(start="10:00", end="12:00", label="周末")
    window = build_data_window(tp, reference_date=date(2026, 6, 24))
    assert window.dow_filter == (6, 7)


def test_step_range_uses_reference_weekday():
    tp = TimePeriod(start="16:00", end="18:00", label="下午")
    start, end, dow = time_to_step_range(tp, reference_date=date(2026, 6, 24))
    assert start == 192
    assert end == 215
    assert dow == 3  # 2026-06-24 周三


def test_data_window_meta_serialization():
    tp = TimePeriod(start="07:00", end="09:00", label="早高峰")
    window = build_data_window(tp, reference_date=date(2026, 6, 24))
    meta = window.to_meta(source_tier="dwd_rolling_7d", sample_count=10)
    assert meta["type"] == "rolling_7d"
    assert meta["source_tier"] == "dwd_rolling_7d"
    assert meta["sample_count"] == 10
    assert meta["time_slot"] == "07:00-09:00"
