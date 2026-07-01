"""Tests for canonical saturation granularity summary."""

from intersection_agent.utils.saturation_granularity import (
    apply_canonical_saturation_to_payload,
    canonical_saturation_summary,
)


def test_turn_granularity_uses_avg_per_movement_not_raw_peak():
    """[RT-DIA-13] Headline saturation must match left-panel by_turn rows (AVG), not global MAX."""
    summary = canonical_saturation_summary(
        by_turn=[
            {"label": "东左转", "turn_saturation": 0.55},
            {"label": "东直行", "turn_saturation": 0.38},
            {"label": "北直行", "turn_saturation": 0.73},
        ],
        inter_saturation_max=1.15,
    )
    assert summary["granularity"] == "turn"
    assert summary["saturation_rate"] == 0.73
    assert summary["turn_saturation_max"] == 0.73
    assert summary["turn_saturation_spread"] == 0.35


def test_apply_canonical_saturation_overwrites_stale_traffic_flow():
    """[RT-DIA-17] apply_canonical_saturation_to_payload overwrites stale traffic_flow."""
    data = {
        "traffic_flow": {
            "saturation_rate": 1.146,
            "turn_saturation_max": 1.146,
            "turn_saturation_spread": 0.986,
        },
        "granularity": {
            "by_turn": [
                {"label": "北直行", "turn_saturation": 0.73},
                {"label": "东左转", "turn_saturation": 0.38},
            ],
        },
        "evaluation": {"saturation_max": 1.15, "saturation_avg": 0.84},
    }
    summary = apply_canonical_saturation_to_payload(data)
    assert summary["granularity"] == "turn"
    assert data["traffic_flow"]["saturation_rate"] == 0.73
    assert data["traffic_flow"]["turn_saturation_max"] == 0.73
    assert data["traffic_flow"]["turn_saturation_spread"] == 0.35


def test_lane_fallback_when_no_turn_rows():
    """[RT-DIA-14] Fallback to lane-level granularity when turn-level is missing."""
    summary = canonical_saturation_summary(
        by_turn=[],
        by_lane=[{"lane_saturation": 0.88}, {"lane_saturation": 0.62}],
        inter_saturation_max=1.1,
    )
    assert summary["granularity"] == "lane"
    assert summary["saturation_rate"] == 0.88


def test_intersection_fallback_when_no_granularity():
    """[RT-DIA-15] Fallback to intersection-level granularity when both turn and lane-level are missing."""
    summary = canonical_saturation_summary(
        by_turn=[],
        by_lane=[],
        inter_saturation_max=0.95,
    )
    assert summary["granularity"] == "intersection"
    assert summary["saturation_rate"] == 0.95
