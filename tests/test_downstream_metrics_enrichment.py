"""需求 20·R6 / BUG-004：PG 下游相邻节点注入真实运行指标，杜绝饱和度/排队恒为 0。"""

from app.data.pg_adapters import (
    enrich_downstream_metrics,
    enrich_downstream_trace_adjacent_peers,
)
from app.trace.downstream_trace import build_downstream_trace
from app.trace.intersection_profile import build_intersection_profile
from app.trace.map_scene import collect_map_adjacent_peer_hints


def _topology_with_downstream():
    return {
        "downstream_nodes": [
            {
                "inter_id": "011wwe291ey00001",
                "inter_name": "奥体中路与经十路路口",
                "role": "downstream",
                "receiving_dir8": 4,
                "receiving_label": "南进口",
                "share_pct": 62.0,
                "path": [[117.0, 36.6], [117.1, 36.6]],
            }
        ],
        "upstream_nodes": [],
    }


def _fake_pg_metrics(_inter_id):
    # 相邻路口真实聚合指标（含承接进口高饱和），模拟典型输入案例的下游过载。
    return {
        "saturation": 1.06,
        "queue_m": 130.0,
        "storage_m": 200.0,
        "volume": 1500.0,
        "capacity": 1400.0,
        "green_utilization": 0.9,
        "has_dynamic_metrics": True,
    }


def test_enrich_attaches_real_downstream_metrics():
    topology = _topology_with_downstream()
    enrich_downstream_metrics(topology, load_pg_metrics=_fake_pg_metrics)
    node = topology["downstream_nodes"][0]
    assert node["metrics_available"] is True
    assert node["queue_length_m"] == 130.0
    assert node["volume_vph"] == 1500.0
    assert node["capacity_vph"] == 1400.0
    assert node["saturation"] > 1.0

    profile = build_intersection_profile(node)
    assert profile["metrics_available"] is True
    assert profile["metrics"]["saturation"] > 1.0
    assert profile["metrics"]["queue_storage_ratio_max"] and profile["metrics"]["queue_storage_ratio_max"] > 0


def test_downstream_trace_reflects_real_metrics_not_zero():
    topology = _topology_with_downstream()
    enrich_downstream_metrics(topology, load_pg_metrics=_fake_pg_metrics)
    trace = build_downstream_trace(
        target_profile={"metrics": {"saturation_rate": 1.9}},
        topology=topology,
        dir8_code=4,
        turn_dir_no=2,
    )
    primary = trace["adjacent_intersections"][0]
    assert primary["metrics"]["saturation"] > 0
    assert trace["governance"]["downstream_blocked"] is True


def test_missing_pg_metrics_degrades_without_fake_zero():
    topology = _topology_with_downstream()
    enrich_downstream_metrics(topology, load_pg_metrics=lambda _id: None)
    node = topology["downstream_nodes"][0]
    assert node["metrics_available"] is False
    assert node["metrics_reason"]

    profile = build_intersection_profile(node)
    assert profile["metrics_available"] is False
    # 不再伪造 0：饱和度/排队为 None，前端据此降级为「暂无数据」
    assert profile["metrics"]["saturation"] is None
    assert profile["metrics"]["queue_storage_ratio_max"] is None
    assert profile["overflow_verification"]["risk_level"] == "unknown"


def test_enrich_map_adjacent_peers_adds_missing_exit_neighbors():
    pg_raw = {
        "trace_geometry": [
            {
                "link_id": "L_E1",
                "relation_direction": "downstream",
                "adjacent_inter_id": "PEER_A",
                "adjacent_inter_name": "礼耕路路口",
                "adjacent_lng": 117.12,
                "adjacent_lat": 36.65,
                "dir8_code": "3",
            },
            {
                "link_id": "L_E2",
                "relation_direction": "downstream",
                "adjacent_inter_id": "PEER_B",
                "adjacent_inter_name": "解放东路路口",
                "adjacent_lng": 117.11,
                "adjacent_lat": 36.64,
                "dir8_code": "5",
            },
        ],
        "channelization": [
            {"link_id": "L_E1", "link_role": "exit", "dir8_code": "3", "dir8_label": "东出口"},
            {"link_id": "L_E2", "link_role": "exit", "dir8_code": "5", "dir8_label": "南出口"},
        ],
    }
    hints = collect_map_adjacent_peer_hints(pg_raw)
    assert {h["inter_id"] for h in hints} == {"PEER_A", "PEER_B"}

    downstream_trace = {
        "available": True,
        "adjacent_intersections": [],
        "turn_traces": [],
    }

    def _loader(inter_id: str):
        if inter_id == "PEER_A":
            return {"saturation": 0.72, "queue_m": 40.0, "storage_m": 120.0, "volume": 900.0, "capacity": 1200.0, "has_dynamic_metrics": True}
        return None

    enrich_downstream_trace_adjacent_peers(
        downstream_trace,
        peer_hints=hints,
        load_pg_metrics=_loader,
    )
    by_id = {item["inter_id"]: item for item in downstream_trace["adjacent_intersections"]}
    assert by_id["PEER_A"]["metrics"]["saturation"] == 0.75
    assert by_id["PEER_A"]["metrics_available"] is True
    assert by_id["PEER_B"]["metrics_available"] is False
    assert by_id["PEER_B"]["metrics"]["saturation"] is None
