"""干线协调聚合（build_coordination_diagram）单测。

只用注入数据验证确定性计算与降级判定，不触库。
"""

from __future__ import annotations

from app.trace.coordination import build_coordination_diagram


def _topology() -> dict:
    return {
        "target_inter_id": "T",
        "target_inter_name": "目标路口",
        "target_lng": 117.0,
        "target_lat": 36.6,
        "upstream_nodes": [
            {
                "upstream_inter_id": "U1",
                "upstream_inter_name": "上游路口",
                "upstream_lng": 116.99,
                "upstream_lat": 36.6,
                "link_id": "linkU",
                "upstream_movements": [{"turn": "直行", "share_pct": 60.0}],
            }
        ],
        "downstream_nodes": [
            {
                "inter_id": "D1",
                "inter_name": "下游路口",
                "lng": 117.01,
                "lat": 36.6,
                "link_id": "linkD",
                "share_pct": 40.0,
            }
        ],
    }


def test_available_with_full_real_sources():
    result = build_coordination_diagram(
        topology=_topology(),
        signal={"offset_s": 10, "current_cycle_s": 120},
        spacing_detail=[
            {"adjacent_inter_id": "U1", "relation_direction": "upstream", "spacing_m": 480},
            {"adjacent_inter_id": "D1", "relation_direction": "downstream", "spacing_m": 300},
        ],
        adjacent_offsets={"U1": 22, "D1": {"offset_s": 34}},
        speed_by_key={"linkU": {"speed_kmh": 40, "source": "line_index"}, "D1": 36},
    )

    assert result["available"] is True
    assert result["direction"] == "bidirectional"
    assert result["cycle_s"] == 120
    assert "reason" not in result

    nodes = {n["role"]: n for n in result["nodes"]}
    up = next(n for n in result["nodes"] if n["role"] == "upstream")
    assert up["spacing_m"] == 480
    assert up["spacing_source"] == "dim_link_info.length_m"
    assert up["offset_abs_s"] == 22
    assert up["phase_diff_s"] == 12.0  # (22-10) % 120
    assert up["travel_speed_kmh"] == 40
    assert up["travel_time_s"] == 43.2  # 480 / (40/3.6)
    assert up["travel_source"] == "line_index"

    assert nodes["target"]["phase_diff_s"] == 0.0
    assert nodes["target"]["offset_abs_s"] == 10
    assert "link_geom" in result["source"] and "pg_signal" in result["source"]


def test_degrade_missing_offset_and_speed():
    result = build_coordination_diagram(
        topology=_topology(),
        signal={"offset_s": 10, "current_cycle_s": 120},
        spacing_detail=[
            {"adjacent_inter_id": "U1", "relation_direction": "upstream", "spacing_m": 480},
        ],
        adjacent_offsets=None,
        speed_by_key=None,
    )
    assert result["available"] is False
    assert "缺少相邻路口绝对相位" in result["reason"]
    assert "缺少路段速度" in result["reason"]
    # 间距真实存在，不应报缺少节点间距
    assert "缺少节点间距" not in result["reason"]


def test_degrade_missing_spacing():
    result = build_coordination_diagram(
        topology=_topology(),
        signal={"offset_s": 10, "current_cycle_s": 120},
        spacing_detail=None,
        adjacent_offsets={"U1": 22},
        speed_by_key=None,
    )
    # 有相位差可算 → available True，但 spacing 缺失体现在节点字段
    assert result["available"] is True
    up = next(n for n in result["nodes"] if n["role"] == "upstream")
    assert up["spacing_m"] is None
    assert up["phase_diff_s"] == 12.0


def test_travel_only_makes_available():
    result = build_coordination_diagram(
        topology=_topology(),
        signal={"current_cycle_s": 120},  # 无目标 offset → 无相位差
        spacing_detail=[
            {"adjacent_inter_id": "U1", "relation_direction": "upstream", "spacing_m": 480},
        ],
        adjacent_offsets=None,
        speed_by_key={"linkU": 40},
    )
    assert result["available"] is True
    up = next(n for n in result["nodes"] if n["role"] == "upstream")
    assert up["phase_diff_s"] is None
    assert up["travel_time_s"] == 43.2


def test_single_node_unavailable():
    topo = {
        "target_inter_id": "T",
        "target_inter_name": "目标路口",
        "upstream_nodes": [],
        "downstream_nodes": [],
    }
    result = build_coordination_diagram(
        topology=topo,
        signal={"offset_s": 10, "current_cycle_s": 120},
    )
    assert result["available"] is False
    assert result["reason"] == "缺少相邻路口拓扑"
    assert result["direction"] == "unknown"


def test_direction_inbound_and_outbound():
    topo_in = {**_topology(), "downstream_nodes": []}
    topo_out = {**_topology(), "upstream_nodes": []}
    assert build_coordination_diagram(topology=topo_in)["direction"] == "inbound"
    assert build_coordination_diagram(topology=topo_out)["direction"] == "outbound"
