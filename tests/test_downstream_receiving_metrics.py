"""下游承接：接收进口方向与缺饱和度不得静默填 0。"""

from app.data.pg_adapters import (
    _adjacent_profile_has_metrics,
    _receiving_dir8_from_exit,
    enrich_downstream_metrics,
    topology_from_pg_raw,
)
from app.trace.intersection_profile import build_intersection_profile


def test_receiving_dir8_is_opposite_of_exit():
    assert _receiving_dir8_from_exit(2) == 6  # 东出口 → 西进口
    assert _receiving_dir8_from_exit(0) == 4
    assert _receiving_dir8_from_exit(6) == 2


def test_topology_north_left_downstream_receiving_is_west():
    # 北左 exit_dir8=2；下游礼耕承接应为西进口 6
    raw = {
        "trace_geometry": [
            {
                "relation_direction": "downstream",
                "dir8_code": 2,
                "adjacent_inter_id": "011wwe2948q00001",
                "adjacent_inter_name": "坤顺路与礼耕路路口",
                "adjacent_lng": 117.11,
                "adjacent_lat": 36.66,
                "geom_wkt": "LINESTRING(117.11 36.66, 117.12 36.66)",
                "link_id": "exit-east",
            }
        ],
        "flow_correlate": [],
    }
    topo = topology_from_pg_raw(
        raw,
        {"direction": "北向南", "movement": "左转"},
        {"geom_center": "POINT(117.10 36.66)"},
    )
    down = (topo.get("downstream_nodes") or [])[0]
    assert down["receiving_dir8"] == 6
    assert down["receiving_turn_dir_no"] == 1
    assert "西进口" in (down.get("receiving_label") or "")
    assert "左转" in (down.get("receiving_label") or "")


def test_enrich_downstream_does_not_claim_zero_sat_when_missing():
    topo = {
        "downstream_nodes": [
            {
                "inter_id": "adj-1",
                "inter_name": "下游",
                "receiving_dir8": 6,
            }
        ]
    }

    def _load(_inter_id: str):
        # 有排队/流量，但无转向饱和度明细 → 旧逻辑会 metrics_available=True + sat=0
        return {
            "has_dynamic_metrics": True,
            "saturation": 0.0,
            "queue_m": 20.0,
            "volume": 300.0,
            "turn_saturation_detail": [],
            "turn_perf_detail": [
                {"dir8_code": 6, "turn_dir_no": 2, "queue_len_avg": 12.0},
            ],
            "turn_flow_detail": [],
            "movement_saturation": {},
            "movement_volume": {},
            "metric_selection_policy": "cross_week_movement_mean",
            "selected_movement_queue_peak_m": 20.0,
        }

    out = enrich_downstream_metrics(topo, load_pg_metrics=_load, target_inter_id="011wwe28fty00001")
    node = out["downstream_nodes"][0]
    assert node.get("metrics_available") is False
    assert "无转向饱和度" in (node.get("metrics_reason") or "")
    # 即使路口级 MAX=20，下游也只能使用真实接收进口直行的 12m。
    assert node.get("queue_length_m") == 12.0
    assert node.get("metric_selection_policy") == "cross_week_movement_mean"
    assert node.get("queue_safety_peak_m") == 20.0
    assert node.get("saturation") in (None, 0, 0.0) or "saturation" not in node or node.get("metrics_available") is False


def test_queue_ratio_remains_available_when_saturation_is_missing():
    profile = build_intersection_profile(
        {
            "metrics_available": False,
            "metrics_reason": "缺少转向饱和度",
            "queue_length_m": 70.6,
            "storage_length_m": 288.64,
        }
    )
    assert profile["metrics"]["saturation"] is None
    assert profile["metrics"]["queue_storage_ratio_max"] == 0.2446
    assert profile["overflow_verification"]["verified"] is True
    assert _adjacent_profile_has_metrics(profile) is True


def test_downstream_left_uses_receiving_left_not_through():
    topo = {
        "downstream_nodes": [
            {
                "inter_id": "adj-left",
                "receiving_dir8": 4,
                "receiving_turn_dir_no": 1,
            }
        ]
    }

    def _load(_inter_id: str):
        return {
            "has_dynamic_metrics": True,
            "turn_saturation_detail": [
                {"dir8_code": 4, "turn_dir_no": 1, "turn_saturation": 0.3},
            ],
            "turn_perf_detail": [
                {"dir8_code": 4, "turn_dir_no": 1, "queue_len_avg": 3.44},
                {"dir8_code": 4, "turn_dir_no": 2, "queue_len_avg": 25.24},
            ],
            "adjacent_inter_spacing_detail": [
                {"dir8_code": 4, "link_role": "entrance", "spacing_m": 390.86},
            ],
        }

    node = enrich_downstream_metrics(topo, load_pg_metrics=_load)["downstream_nodes"][0]
    assert node["queue_length_m"] == 3.44
    assert node["storage_length_m"] == 390.86
    assert node["metrics_receiving_turn_dir_no"] == 1
