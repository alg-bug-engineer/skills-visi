"""Case A only: downstream queue uses approach-direction avg; others keep max."""

from __future__ import annotations

from app.data.load_intersection_from_pg import _aggregate_metrics
from app.data.pg_adapters import enrich_downstream_metrics, metrics_for_diagnosis
from app.metrics.traffic import THRESHOLDS
from app.trace.downstream_trace import assess_downstream_capacity
from app.trace.intersection_profile import build_intersection_profile

CASE_A = "011wwe28fty00001"


def test_aggregate_metrics_queue_keeps_max_for_other_cases():
    perf = [
        {"queue_len_avg": 10.0, "queue_len_max": 100.0, "f_dir_8": 6, "turn_dir_no": 2},
        {"queue_len_avg": 30.0, "queue_len_max": 120.0, "f_dir_8": 6, "turn_dir_no": 2},
    ]
    metrics = _aggregate_metrics([], [], [], [], perf)
    assert metrics["queue_m"] == 120.0


def test_metrics_for_diagnosis_default_uses_whole_intersection_queue():
    pg_metrics = {
        "saturation": 0.5,
        "queue_m": 999.0,
        "storage_m": 300.0,
        "turn_perf_detail": [
            {"f_dir_8": 6, "turn_dir_no": 2, "queue_len_avg": 10.0, "queue_len_max": 80.0},
            {"f_dir_8": 2, "turn_dir_no": 2, "queue_len_avg": 200.0, "queue_len_max": 250.0},
        ],
    }
    out = metrics_for_diagnosis(pg_metrics, {"direction": "西向东", "movement": "直行"})
    assert out["queue_length_m"] == 999.0


def test_case_a_downstream_enrich_uses_approach_avg_queue():
    topology = {
        "downstream_nodes": [
            {
                "inter_id": "011wwe2948q00001",
                "inter_name": "坤顺路与礼耕路路口",
                "receiving_dir8": 6,
                "receiving_label": "西进口",
            }
        ]
    }

    def _load(_id: str):
        return {
            "saturation": 0.4,
            "queue_m": 999.0,
            "storage_m": 300.0,
            "volume": 600.0,
            "capacity": 1200.0,
            "has_dynamic_metrics": True,
            "turn_perf_detail": [
                {"f_dir_8": 6, "turn_dir_no": 2, "queue_len_avg": 10.0, "queue_len_max": 80.0},
                {"f_dir_8": 6, "turn_dir_no": 2, "queue_len_avg": 30.0, "queue_len_max": 90.0},
                {"f_dir_8": 2, "turn_dir_no": 2, "queue_len_avg": 200.0, "queue_len_max": 250.0},
            ],
            "turn_saturation_detail": [
                {"f_dir_8": 6, "turn_dir_no": 2, "turn_saturation": 0.4},
            ],
        }

    enrich_downstream_metrics(topology, load_pg_metrics=_load, target_inter_id=CASE_A)
    node = topology["downstream_nodes"][0]
    assert node["metrics_queue_mode"] == "approach_avg"
    assert node["queue_length_m"] == 20.0

    profile = build_intersection_profile({**node, "role": "downstream"})
    capacity = assess_downstream_capacity(
        saturation=profile["metrics"]["saturation_rate"],
        queue_ratio=profile["metrics"]["queue_storage_ratio_max"],
    )
    assert capacity["blocked"] is False
    assert profile["metrics"]["queue_storage_ratio_max"] < THRESHOLDS["queue_ratio_warning"]


def test_other_target_downstream_keeps_whole_intersection_queue():
    topology = {
        "downstream_nodes": [
            {
                "inter_id": "DOWN",
                "inter_name": "其他下游",
                "receiving_dir8": 6,
            }
        ]
    }

    def _load(_id: str):
        return {
            "saturation": 0.4,
            "queue_m": 999.0,
            "storage_m": 300.0,
            "volume": 600.0,
            "capacity": 1200.0,
            "has_dynamic_metrics": True,
            "turn_perf_detail": [
                {"f_dir_8": 6, "turn_dir_no": 2, "queue_len_avg": 10.0, "queue_len_max": 80.0},
            ],
        }

    enrich_downstream_metrics(topology, load_pg_metrics=_load, target_inter_id="011wwe294k300001")
    node = topology["downstream_nodes"][0]
    assert node.get("metrics_queue_mode") is None
    assert node["queue_length_m"] == 999.0
