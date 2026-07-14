"""典型路口取数配置与策略解析测试。"""

from __future__ import annotations

import json
from pathlib import Path

from app.data.pg_adapters import metrics_for_diagnosis
from app.data.typical_intersection_profiles import (
    clear_typical_profile_cache,
    metric_options_from_profile,
    resolve_typical_profile,
)


def test_resolve_typical_profiles_for_configured_movements():
    clear_typical_profile_cache()
    west_through = resolve_typical_profile(
        {
            "inter_id": "011wwe28fty00001",
            "direction": "西进口",
            "movement": "直行",
        }
    )
    assert west_through is not None
    assert west_through["id"] == "point_kunshun_aotixi_west_through"
    assert west_through["target_queue_field"] == "queue_len_max"

    west_left = resolve_typical_profile(
        {
            "inter_id": "011wwe28fty00001",
            "direction": "西向东",
            "movement": "左转",
        }
    )
    assert west_left is not None
    assert west_left["id"] == "point_kunshun_aotixi_west_left"

    line = resolve_typical_profile(
        {
            "inter_id": "011wwe22xn400001",
            "direction": "东进口",
            "movement": "直行",
        }
    )
    assert line is not None
    assert line["opt_type"] == "TYPE2_LINE"
    assert line["downstream_peak_disclose_field"] == "queue_len_max"


def test_case_a_keeps_project_fixed_logic():
    clear_typical_profile_cache()
    case_a = resolve_typical_profile(
        {
            "inter_id": "011wwe28f7c00001",
            "intersection_name": "解放东路与齐川路路口",
            "direction": "北进口",
            "movement": "直行",
        }
    )
    assert case_a is None
    opts = metric_options_from_profile(case_a)
    assert opts["use_typical_policy"] is False
    assert opts["target_queue_field"] == "queue_len_avg"


def test_unconfigured_intersection_uses_fixed_defaults():
    clear_typical_profile_cache()
    opts = metric_options_from_profile(
        resolve_typical_profile(
            {
                "inter_id": "unknown_inter",
                "direction": "东进口",
                "movement": "直行",
            }
        )
    )
    assert opts["use_typical_policy"] is False
    assert opts["downstream_approach_queue_avg"] is False


def test_metrics_for_diagnosis_respects_queue_len_max_policy():
    """典型策略注入 queue_len_max 后，诊断队列取该字段峰值。"""
    pg_metrics = {
        "metric_selection_policy": "cross_week_movement_peak",
        "target_queue_field": "queue_len_max",
        "selected_day_of_week": 3,
        "selected_movement_queue_peak_m": 108.0,
        "typical_profile_id": "point_kunshun_aotixi_west_through",
        "turn_perf_detail": [
            {
                "f_dir_8": 6,
                "turn_dir_no": 2,
                "queue_len_avg": 54.8,
                "queue_len_max": 108.0,
                "step_index": 210,
            },
            {
                "f_dir_8": 6,
                "turn_dir_no": 2,
                "queue_len_avg": 40.0,
                "queue_len_max": 90.0,
                "step_index": 211,
            },
        ],
        "turn_saturation_detail": [
            {"dir8_code": 6, "turn_dir_no": 2, "turn_saturation": 1.28},
        ],
        "adjacent_inter_spacing_detail": [
            {"dir8_code": 6, "spacing_m": 112.76, "version_id": "20260501"},
        ],
    }
    scope = {
        "adjacent_inter_spacing_detail": pg_metrics["adjacent_inter_spacing_detail"],
    }
    out = metrics_for_diagnosis(
        pg_metrics,
        {"direction": "西进口", "movement": "直行"},
        scope=scope,
    )
    assert out["queue_length_m"] == 108.0
    assert out["storage_length_m"] == 112.76
    assert abs(out["queue_length_m"] / out["storage_length_m"] - 0.9578) < 0.001
    assert out["target_queue_field"] == "queue_len_max"
    assert out["typical_profile_id"] == "point_kunshun_aotixi_west_through"


def test_typical_intersections_json_lists_expected_ids():
    path = Path(__file__).resolve().parents[1] / "data" / "typical_intersections.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    ids = {p["id"] for p in catalog["profiles"]}
    assert "point_kunshun_aotixi_west_through" in ids
    assert "point_kunshun_aotixi_west_left" in ids
    assert "point_huizhan_aotizhong_east_through" in ids
    assert "line_caoshanling_north_through" in ids
    assert "line_caoshanling_south_left" in ids
    assert "line_lvyou_zhuanshanxi_east_through" in ids
    # Case A 明确不写入覆盖 profile
    assert "case_a" not in "".join(ids).lower()
    assert "28f7c00001" not in json.dumps(catalog["profiles"])
