"""需求 33：路段覆盖流量溯源。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from app.trace.segment_coverage import (
    DIR8_TO_APPROACH_LEG,
    build_flow_trace_segment_coverage_map_scene,
    dir8_to_approach_leg,
    reset_segment_coverage_service,
    resolve_coverage_time_window,
)


def test_dir8_to_approach_leg_mapping():
    assert dir8_to_approach_leg(0) == "N_IN"
    assert dir8_to_approach_leg(6) == "W_IN"
    assert dir8_to_approach_leg(7) == "NW_IN"
    assert dir8_to_approach_leg(None) is None
    assert dir8_to_approach_leg("x") is None
    assert len(DIR8_TO_APPROACH_LEG) == 8


def test_resolve_coverage_time_window_evening_peak():
    pmin = datetime(2026, 6, 10, 0, 0, 0)
    pmax = datetime(2026, 6, 10, 23, 59, 0)
    start, end, fallback = resolve_coverage_time_window(
        period="晚高峰",
        parquet_min=pmin,
        parquet_max=pmax,
    )
    assert start == datetime(2026, 6, 10, 16, 0, 0)
    assert end == datetime(2026, 6, 10, 19, 0, 1)
    assert fallback is None


def test_resolve_coverage_time_window_period_code():
    pmin = datetime(2026, 6, 10, 0, 0, 0)
    pmax = datetime(2026, 6, 10, 23, 0, 0)
    start, end, fallback = resolve_coverage_time_window(
        period="EVENING_PEAK",
        parquet_min=pmin,
        parquet_max=pmax,
    )
    assert start.hour == 16
    assert end.hour == 19
    assert end.minute == 0
    assert end.second == 1
    assert fallback is None


def test_resolve_coverage_time_window_falls_back_when_outside_parquet():
    # 本批恢复轨迹仅早高峰样本：晚高峰窗与 parquet 无交集 → 回退全窗
    pmin = datetime(2026, 6, 8, 6, 0, 0)
    pmax = datetime(2026, 6, 8, 9, 59, 59)
    start, end, fallback = resolve_coverage_time_window(
        period="晚高峰",
        parquet_min=pmin,
        parquet_max=pmax,
    )
    assert start == pmin
    assert end == pmax + __import__("datetime").timedelta(seconds=1)
    assert fallback and "outside_parquet" in fallback


def test_builder_missing_parquet_returns_unavailable(monkeypatch):
    reset_segment_coverage_service()
    monkeypatch.setenv("FLOW_TRACE_INTER_PARQUET", "")
    monkeypatch.setenv("FLOW_TRACE_TRIPS_PARQUET", "")
    from app.config import get_settings

    get_settings.cache_clear()
    reset_segment_coverage_service()

    with patch("app.trace.segment_coverage.get_settings") as gs:
        settings = gs.return_value
        settings.flow_trace_inter_parquet = ""
        settings.flow_trace_trips_parquet = ""
        settings.pg_dsn = ""
        settings.pg_schema = "road6"
        reset_segment_coverage_service()
        # force get_segment_coverage_service to see empty paths via patched get_settings
        scene = build_flow_trace_segment_coverage_map_scene(
            topology={"dir8_code": 6, "turn_dir_no": 2, "period_type": "EVENING_PEAK"},
            target_profile={"inter_id": "X", "lng": 117.0, "lat": 36.6},
            direction="西向东",
            movement="直行",
        )
    assert scene["available"] is False
    assert scene["phase"] == "flow_trace_segment_coverage_map"
    assert scene["reason"] in {"missing_parquet", "missing_pg_dsn", "missing_duckdb"}


def test_builder_approach_unmap():
    reset_segment_coverage_service()
    with patch("app.trace.segment_coverage.get_segment_coverage_service") as get_svc:
        svc = get_svc.return_value
        svc.ensure_loaded.return_value = None
        scene = build_flow_trace_segment_coverage_map_scene(
            topology={"dir8_code": 99, "turn_dir_no": 2},
            target_profile={"inter_id": "X", "lng": 117.0, "lat": 36.6},
            direction="",
            movement="直行",
        )
    assert scene["available"] is False
    assert scene["reason"] == "approach_unmap"
