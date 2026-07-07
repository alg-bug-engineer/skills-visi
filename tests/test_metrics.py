from app.metrics.traffic import (
    assess_overflow_risk,
    calculate_queue_ratio,
    calculate_saturation,
    classify_release_bottleneck,
)


def test_queue_ratio_calculation():
    assert calculate_queue_ratio(160, 200) == 0.8
    assert calculate_queue_ratio(200, 200) == 1.0
    assert calculate_queue_ratio(100, 0) is None


def test_overflow_risk_levels():
    assert assess_overflow_risk(0.5)["risk_level"] == "low"
    assert assess_overflow_risk(0.85)["risk_level"] == "warning"
    assert assess_overflow_risk(1.05)["risk_level"] == "high"


def test_saturation():
    assert calculate_saturation(800, 1000) == 0.8


def test_bottleneck_downstream_capacity():
    result = classify_release_bottleneck(
        target_saturation=0.9,
        target_green_utilization=0.9,
        downstream_queue_ratio=0.9,
        downstream_saturation=0.85,
    )
    assert result["bottleneck_type"] == "downstream_capacity"
    assert result["can_simple_add_green"] is False


def test_bottleneck_local_release():
    result = classify_release_bottleneck(
        target_saturation=0.9,
        target_green_utilization=0.9,
        downstream_queue_ratio=0.5,
        downstream_saturation=0.6,
    )
    assert result["bottleneck_type"] == "local_release"
    assert result["can_simple_add_green"] is True
