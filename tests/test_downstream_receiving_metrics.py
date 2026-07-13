"""下游承接：接收进口方向与缺饱和度不得静默填 0。"""

from app.data.pg_adapters import (
    _receiving_dir8_from_exit,
    enrich_downstream_metrics,
    topology_from_pg_raw,
)


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
    assert "西进口" in (down.get("receiving_label") or "")


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
        }

    out = enrich_downstream_metrics(topo, load_pg_metrics=_load, target_inter_id="011wwe28fty00001")
    node = out["downstream_nodes"][0]
    assert node.get("metrics_available") is False
    assert "无转向饱和度" in (node.get("metrics_reason") or "")
    assert node.get("saturation") in (None, 0, 0.0) or "saturation" not in node or node.get("metrics_available") is False
