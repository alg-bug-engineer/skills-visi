from __future__ import annotations

from app.data.pg_adapters import (
    load_cross_week_mean_movement_metrics,
    load_cross_week_peak_movement_metrics,
)


def _metrics(*queues: float):
    return {
        "turn_perf_detail": [
            {"f_dir_8": 0, "turn_dir_no": 1, "queue_len_avg": queue}
            for queue in queues
        ],
        "turn_saturation_detail": [],
        "turn_flow_detail": [],
        "green_utilization_detail": [],
    }


def test_cross_week_peak_and_mean_share_one_all_days_query(monkeypatch):
    calls: list[int | None] = []

    def _load(**kwargs):
        calls.append(kwargs.get("day_of_week"))
        return {
            "ok": True,
            "metrics": _metrics(10.0, 20.0, 30.0),
            "metrics_by_day": {1: _metrics(10.0), 2: _metrics(30.0)},
        }

    monkeypatch.setattr(
        "app.data.load_intersection_from_pg.load_intersection_metrics_only", _load
    )
    args = {
        "inter_id": "cross-week-test",
        "direction": "北向南",
        "movement": "左转",
        "time_range": "17:00-19:00",
    }

    peak = load_cross_week_peak_movement_metrics(**args)
    mean = load_cross_week_mean_movement_metrics(**args)

    assert calls == [None]
    assert peak["selected_day_of_week"] == 2
    assert peak["selected_movement_queue_peak_m"] == 30.0
    assert mean["included_day_of_week"] == [1, 2]
    assert mean["selected_movement_queue_mean_m"] == 20.0
