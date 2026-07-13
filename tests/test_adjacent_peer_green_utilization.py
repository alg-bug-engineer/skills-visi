"""Adjacent peer enrichment must not drop intersections with green-utilization-only PG data."""

from __future__ import annotations

from app.data.pg_adapters import (
    _pg_metrics_has_dynamic_data,
    enrich_downstream_trace_adjacent_peers,
)


def test_pg_metrics_has_dynamic_data_accepts_green_utilization() -> None:
    assert _pg_metrics_has_dynamic_data({"green_utilization": 0.41}) is True
    assert _pg_metrics_has_dynamic_data({"saturation": 0.0, "green_utilization": 0.0}) is False


def test_enrich_adjacent_peer_with_green_utilization_only() -> None:
    downstream_trace = {"adjacent_intersections": []}
    peer_hints = [
        {
            "inter_id": "peer-1",
            "inter_name": "奥体西路与解放东路路口",
            "lng": 117.11,
            "lat": 36.66,
            "receiving_dir8": 6,
        }
    ]

    def _load(_inter_id: str) -> dict:
        return {
            "has_dynamic_metrics": True,
            "green_utilization": 0.4137,
            "turn_saturation_detail": [
                {"dir8_code": 6, "turn_dir_no": 2, "turn_saturation": 0.0},
            ],
            "turn_perf_detail": [
                {"dir8_code": 6, "turn_dir_no": 2, "green_utilization": 0.4137},
            ],
        }

    out = enrich_downstream_trace_adjacent_peers(
        downstream_trace,
        peer_hints=peer_hints,
        load_pg_metrics=_load,
    )
    peer = out["adjacent_intersections"][0]
    assert peer["metrics_available"] is True
    assert peer["metrics"]["green_utilization"] == 0.4137
    assert peer["metrics"]["saturation"] == 0.0
