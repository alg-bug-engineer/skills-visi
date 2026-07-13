"""需求 34：目标转向指标绑定，禁止进口 MAX 覆盖。"""

import pytest

from app.data.pg_adapters import metrics_for_diagnosis, _row_dir8


def test_row_dir8_prefers_code_and_exact_label():
    assert _row_dir8({"dir8_code": 4}) == 4
    assert _row_dir8({"dir8_label": "南进口"}) == 4
    assert _row_dir8({"dir8_label": "北进口"}) == 0
    # 不得把「南进口」误匹配到「东南进口」
    assert _row_dir8({"dir8_label": "东南进口"}) == 3


def test_target_saturation_binds_north_left_not_north_through_max():
    # E1：ticket 北左；北直 1.5446、北左 1.2365 → 必须取北左
    pg_metrics = {
        "saturation": 1.5446,
        "queue_m": 163.0,
        "storage_m": 195.68,
        "turn_saturation_detail": [
            {"dir8_code": 0, "turn_dir_no": 2, "turn_saturation": 1.5446},
            {"dir8_code": 0, "turn_dir_no": 1, "turn_saturation": 1.2365},
        ],
        "turn_perf_detail": [
            {"dir8_code": 0, "turn_dir_no": 1, "queue_len_avg": 40.0},
            {"dir8_code": 0, "turn_dir_no": 2, "queue_len_avg": 163.0},
        ],
        "movement_saturation": {},
        "movement_volume": {},
    }
    scope = {
        "adjacent_inter_spacing_detail": [
            {"dir8_code": 0, "dir8_label": "北进口", "spacing_m": 357.21, "link_id": "north"},
            {"dir8_code": 2, "dir8_label": "东进口", "spacing_m": 195.68, "link_id": "east"},
        ]
    }
    out = metrics_for_diagnosis(
        pg_metrics,
        {"direction": "北向南", "movement": "左转"},
        scope=scope,
    )
    assert out["metric_scope"] == "movement"
    assert out["target_movement_key"] == "d0_t1"
    assert out["saturation"] == pytest.approx(1.2365)
    assert out["storage_length_m"] == pytest.approx(357.21)
    assert out["storage_direction"] == "北进口"
    assert out["queue_length_m"] == pytest.approx(40.0)
    assert out["intersection_saturation_max"] == pytest.approx(1.5446)


def test_target_saturation_binds_south_through_not_south_left_peak():
    # E6：ticket 南直；南左≈1.76、南直≈1.06
    pg_metrics = {
        "saturation": 1.7734,
        "turn_saturation_detail": [
            {"dir8_label": "南进口", "turn_dir_no": 1, "turn_saturation": 1.7628},
            {"dir8_label": "南进口", "turn_dir_no": 2, "turn_saturation": 1.0641},
        ],
        "turn_perf_detail": [
            {"dir8_label": "南进口", "turn_dir_no": 2, "queue_len_avg": 80.0},
        ],
        "movement_saturation": {},
        "movement_volume": {},
    }
    scope = {
        "adjacent_inter_spacing_detail": [
            {"dir8_label": "南进口", "spacing_m": 280.0, "link_id": "south"},
        ]
    }
    out = metrics_for_diagnosis(
        pg_metrics,
        {"direction": "南向北", "movement": "直行"},
        scope=scope,
    )
    assert out["target_movement_key"] == "d4_t2"
    assert out["saturation"] == pytest.approx(1.0641)
    assert out["storage_length_m"] == pytest.approx(280.0)
