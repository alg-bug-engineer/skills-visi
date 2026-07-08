import pytest

from app.data.pg_adapters import metrics_for_diagnosis
from app.trace.intersection_profile import build_intersection_profile


def test_metrics_for_diagnosis_uses_structured_target_turn_rows():
    metrics = metrics_for_diagnosis(
        {
            "saturation": 0.2,
            "volume": 100,
            "capacity": 2000,
            "turn_saturation_detail": [
                {"f_dir_8": 6, "turn_dir_no": 2, "turn_saturation": 0.41},
                {"f_dir_8": 2, "turn_dir_no": 2, "turn_saturation": 0.91},
            ],
            "turn_flow_detail": [
                {"f_dir_8": 6, "turn_dir_no": 2, "turn_flow_total": 500},
                {"f_dir_8": 2, "turn_dir_no": 2, "turn_flow_total": 1200},
            ],
        },
        {"direction": "东向西", "movement": "直行"},
    )

    assert metrics["saturation"] == pytest.approx(0.91)
    assert metrics["saturation_rate"] == pytest.approx(0.91)
    assert metrics["volume_vph"] == pytest.approx(1200)


def test_metrics_for_diagnosis_does_not_use_unrelated_first_movement():
    metrics = metrics_for_diagnosis(
        {
            "saturation": 0.2,
            "volume": 100,
            "movement_saturation": {
                "30005_左转": 0.71,
                "30006_右转": 0.82,
            },
            "movement_volume": {
                "30005_左转": 710,
                "30006_右转": 820,
            },
        },
        {"direction": "东向西", "movement": "直行"},
    )

    assert metrics["saturation"] == pytest.approx(0.2)
    assert metrics["volume_vph"] == pytest.approx(100)


def test_intersection_profile_exposes_saturation_aliases():
    profile = build_intersection_profile(
        {
            "queue_length_m": 90,
            "storage_length_m": 200,
            "volume_vph": 900,
            "capacity_vph": 1000,
        }
    )

    assert profile["metrics"]["saturation"] == pytest.approx(0.9)
    assert profile["metrics"]["saturation_rate"] == pytest.approx(0.9)
