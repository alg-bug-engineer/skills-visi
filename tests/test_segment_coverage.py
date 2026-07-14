"""需求 33：路段覆盖流量溯源。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pandas as pd

from app.trace.segment_coverage import (
    DIR8_TO_APPROACH_LEG,
    IntersectionMeta,
    LinkMeta,
    CoverageRequest,
    SegmentCoverageService,
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


def test_trace_intersections_only_counts_path_corridor():
    svc = SegmentCoverageService.__new__(SegmentCoverageService)
    svc.intersections = {
        "T": IntersectionMeta("T", "目标", [117.0, 36.6]),
        "U1": IntersectionMeta("U1", "规划一号路", [117.01, 36.61]),
        "NOISE": IntersectionMeta("NOISE", "无关路口", [117.5, 36.9]),
    }
    req = CoverageRequest(
        inter_id="T",
        approach_leg="N_IN",
        turn_dir_no=2,
        start_time=datetime(2026, 6, 8, 6, 0, 0),
        end_time=datetime(2026, 6, 8, 10, 0, 0),
        direction="upstream",
    )
    target_events = pd.DataFrame(
        [
            {"trip_id": "trip1", "event_key": "trip1|t1"},
            {"trip_id": "trip2", "event_key": "trip2|t1"},
        ]
    )

    def fake_load(_target_events, _exclude):
        return {
            "trip1": (["U1", "T"], ["L1"]),
            "trip2": (["U1", "T"], ["L1"]),
        }

    svc._load_restored_trips = fake_load  # type: ignore[method-assign]
    rows = svc._trace_intersections(req, target_events, target_flow=2)

    by_id = {row["id"]: row for row in rows}
    assert "U1" in by_id
    assert by_id["U1"]["flow"] == 2
    assert by_id["U1"]["ratio"] == 1.0
    assert "NOISE" not in by_id


def test_trace_links_lazily_loads_only_ranked_path_ids():
    svc = SegmentCoverageService.__new__(SegmentCoverageService)
    svc.links = {}
    requested: list[str] = []
    req = CoverageRequest(
        inter_id="T",
        approach_leg="N_IN",
        turn_dir_no=2,
        start_time=datetime(2026, 6, 8, 6, 0, 0),
        end_time=datetime(2026, 6, 8, 10, 0, 0),
        direction="upstream",
        limit=1,
    )
    target_events = pd.DataFrame(
        [
            {"trip_id": "trip1", "event_key": "trip1|t1"},
            {"trip_id": "trip2", "event_key": "trip2|t1"},
        ]
    )

    def fake_load_trips(_target_events, _exclude):
        return {
            "trip1": (["U1", "T"], ["POPULAR"]),
            "trip2": (["U2", "T"], ["POPULAR", "OTHER"]),
        }

    def fake_load_links(link_ids):
        requested.extend(link_ids)
        svc.links["POPULAR"] = LinkMeta(
            "POPULAR", "主路", [[117.0, 36.6], [117.01, 36.61]], "U1", "T", "1", 100.0
        )

    svc._load_restored_trips = fake_load_trips  # type: ignore[method-assign]
    svc._load_link_metadata = fake_load_links  # type: ignore[method-assign]

    rows = svc._trace_links(req, target_events, target_flow=2)
    assert requested == ["POPULAR"]
    assert [row["id"] for row in rows] == ["POPULAR"]


def test_trace_reads_restored_trip_parquet_once():
    svc = SegmentCoverageService.__new__(SegmentCoverageService)
    svc._con = object()
    svc.intersections = {"T": IntersectionMeta("T", "目标", [117.0, 36.6])}
    svc.ensure_loaded = lambda: None  # type: ignore[method-assign]
    svc._target_events = lambda _req: pd.DataFrame(  # type: ignore[method-assign]
        [{"trip_id": "trip1", "event_key": "trip1|t1"}]
    )
    loads = 0
    restored = {"trip1": (["U1", "T"], ["L1"])}

    def fake_load(_events, _exclude):
        nonlocal loads
        loads += 1
        return restored

    seen: list[object] = []
    svc._load_restored_trips = fake_load  # type: ignore[method-assign]
    svc._trace_intersections = (  # type: ignore[method-assign]
        lambda _req, _events, _flow, *, restored_by_trip: seen.append(restored_by_trip) or []
    )
    svc._trace_links = (  # type: ignore[method-assign]
        lambda _req, _events, _flow, *, restored_by_trip: seen.append(restored_by_trip) or []
    )
    req = CoverageRequest(
        inter_id="T",
        approach_leg="N_IN",
        turn_dir_no=2,
        start_time=datetime(2026, 6, 8, 6, 0, 0),
        end_time=datetime(2026, 6, 8, 10, 0, 0),
        filter_spatial_outliers=False,
    )

    svc.trace(req)
    assert loads == 1
    assert seen == [restored, restored]
