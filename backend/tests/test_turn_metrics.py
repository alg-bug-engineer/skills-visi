"""Tests for turn-level saturation normalization."""

from intersection_agent.utils.turn_metrics import (
    attach_turn_metrics_to_cognition,
    build_direction_groups_from_turns,
    normalize_turn_metrics,
)


def test_normalize_turn_metrics_from_by_turn():
    rows = normalize_turn_metrics(
        [
            {"label": "东左转", "dir8_code": 2, "turn_dir_no": 1, "turn_saturation": 1.83, "green_utilization": 1.84},
            {"label": "西直行", "dir8_code": 6, "turn_dir_no": 2, "turn_saturation": 0.0295, "green_utilization": 0.35},
        ]
    )
    assert len(rows) == 2
    assert rows[0]["label"] == "东左转"
    assert rows[0]["dir4_label"] == "东"
    assert rows[0]["turn"] == "左"
    west = next(r for r in rows if r["label"] == "西直行")
    assert west["dir4_label"] == "西"
    assert west["turn_saturation"] == 0.0295


def test_build_direction_groups_from_turns():
    arms = [{"dir4_label": "东"}, {"dir4_label": "西"}]
    turns = normalize_turn_metrics(
        [
            {"label": "东左转", "turn_saturation": 1.8},
            {"label": "西直行", "turn_saturation": 0.03},
        ]
    )
    groups = build_direction_groups_from_turns(arms, turns)
    ew = next(g for g in groups if g["group"] == "东西向")
    assert ew["saturation_max"] == 1.8


def test_attach_turn_metrics_to_cognition():
    cognition = {"arms": [{"dir4_label": "东"}, {"dir4_label": "西"}]}
    data = {
        "granularity": {
            "by_turn": [
                {"label": "东左转", "turn_saturation": 1.5},
                {"label": "西直行", "turn_saturation": 0.04},
            ]
        }
    }
    metrics = attach_turn_metrics_to_cognition(cognition, data)
    assert len(metrics) == 2
    assert cognition["metrics_by_turn"]
    assert any(g["group"] == "东西向" for g in cognition["direction_groups"])
