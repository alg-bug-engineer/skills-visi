"""Tests for unified thresholds loading."""

from intersection_agent.utils.thresholds_loader import load_thresholds, threshold_value


def test_green_utilization_diagnosis_threshold():
    assert threshold_value("green", "low_utilization_diagnosis", default=0.0) == 0.60


def test_movement_saturation_gap_threshold():
    assert threshold_value("imbalance", "movement_saturation_gap", default=0.0) == 0.60


def test_plan_min_time_plans():
    assert threshold_value("plan", "min_time_plans", default=0) == 5


def test_chronic_extension_merged():
    thresholds = load_thresholds()
    assert thresholds.get("chronic", {}).get("min_congested_days") == 4
    assert thresholds.get("saturation", {}).get("high") == 0.8
