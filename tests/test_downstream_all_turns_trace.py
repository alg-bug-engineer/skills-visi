"""目标进口左/直/右下游一跳溯源契约。"""

from app.data.pg_adapters import enrich_downstream_metrics, topology_from_pg_raw
from app.trace.downstream_trace import build_downstream_trace
from app.trace.map_scene import build_downstream_map_scene
from app.trace.topology import resolve_dir8_turn


def _raw_three_exits() -> dict:
    rows = []
    specs = (
        (0, "down-left", "北侧下游", 36.67),
        (2, "down-through", "东侧下游", 36.66),
        (4, "down-right", "南侧下游", 36.65),
    )
    for exit_dir8, inter_id, name, lat in specs:
        rows.append(
            {
                "relation_direction": "downstream",
                "dir8_code": exit_dir8,
                "adjacent_inter_id": inter_id,
                "adjacent_inter_name": name,
                "adjacent_lng": 117.12,
                "adjacent_lat": lat,
                "geom_wkt": f"LINESTRING(117.10 36.66, 117.12 {lat})",
                "link_id": f"exit-{exit_dir8}",
            }
        )
    correlate = [
        {
            "f_dir8_no": 6,
            "turn_dir_no": turn,
            "trace_type": "UPSTREAM" if turn == 2 else "DOWNSTREAM",
            "cor_inter_id": inter_id,
            "flow_share_ratio": share,
        }
        for turn, inter_id, share in (
            (1, "down-left", 21.0),
            (2, "down-through", 63.0),
            (3, "down-right", 16.0),
        )
    ]
    return {"trace_geometry": rows, "flow_correlate": correlate}


def test_pg_topology_keeps_selected_view_and_builds_all_turns():
    topology = topology_from_pg_raw(
        _raw_three_exits(),
        {"direction": "西进口", "movement": "直行"},
        {"inter_id": "target", "geom_center": "POINT(117.10 36.66)"},
    )

    assert [node["inter_id"] for node in topology["downstream_nodes"]] == ["down-through"]
    assert [node["origin_turn_dir_no"] for node in topology["downstream_turn_nodes"]] == [1, 2, 3]
    assert [node["exit_dir8"] for node in topology["downstream_turn_nodes"]] == [0, 2, 4]
    assert [node["receiving_dir8"] for node in topology["downstream_turn_nodes"]] == [4, 6, 0]
    assert [node["share_pct"] for node in topology["downstream_turn_nodes"]] == [21.0, 63.0, 16.0]
    assert all(len(node["path"]) == 2 for node in topology["downstream_turn_nodes"])
    assert topology["downstream_nodes"][0] is topology["downstream_turn_nodes"][1]


def test_enrichment_covers_all_turn_nodes_once():
    topology = topology_from_pg_raw(
        _raw_three_exits(),
        {"direction": "西进口", "movement": "直行"},
        {"inter_id": "target", "geom_center": "POINT(117.10 36.66)"},
    )
    calls: list[tuple[str, str, str]] = []

    def _load(inter_id: str, *, direction: str, movement: str) -> dict:
        calls.append((inter_id, direction, movement))
        dir8, turn = resolve_dir8_turn(direction, movement)
        return {
            "has_dynamic_metrics": True,
            "turn_saturation_detail": [
                {"dir8_code": dir8, "turn_dir_no": turn, "turn_saturation": 0.6},
            ],
            "turn_perf_detail": [
                {"dir8_code": dir8, "turn_dir_no": turn, "queue_len_avg": 10.0},
            ],
            "turn_flow_detail": [],
            "adjacent_inter_spacing_detail": [
                {"dir8_code": dir8, "link_role": "entrance", "spacing_m": 100.0},
            ],
        }

    enrich_downstream_metrics(topology, load_pg_metrics=_load)

    assert len(calls) == 3
    assert {movement for _, _, movement in calls} == {"左转", "直行", "右转"}
    assert all(node["metrics_available"] is True for node in topology["downstream_turn_nodes"])
    assert all(node["queue_length_m"] == 10.0 for node in topology["downstream_turn_nodes"])


def test_trace_and_map_scene_present_all_turns_but_govern_selected_turn():
    topology = topology_from_pg_raw(
        _raw_three_exits(),
        {"direction": "西进口", "movement": "直行"},
        {"inter_id": "target", "geom_center": "POINT(117.10 36.66)"},
    )
    for node in topology["downstream_turn_nodes"]:
        node.update(
            {
                "metrics_available": True,
                "queue_length_m": 90.0 if node["origin_turn_dir_no"] == 1 else 10.0,
                "storage_length_m": 100.0,
                "saturation": 0.9 if node["origin_turn_dir_no"] == 1 else 0.6,
            }
        )

    target_profile = {"inter_id": "target", "inter_name": "奥体西路与经十路", "lng": 117.1, "lat": 36.66}
    trace = build_downstream_trace(
        target_profile=target_profile,
        topology=topology,
        dir8_code=6,
        turn_dir_no=2,
    )

    assert trace["scope"] == "target_approach_all_turns"
    assert [item["turn_label"] for item in trace["turn_traces"]] == ["直行", "左转", "右转"]
    assert sum(1 for item in trace["turn_traces"] if item["selected"]) == 1
    assert trace["governance"]["downstream_blocked"] is False
    assert trace["governance"]["all_turns_downstream_blocked"] is True
    assert {item["turn_label"] for item in trace["movement_summary"] if item["available"]} == {
        "左转",
        "直行",
        "右转",
    }

    scene = build_downstream_map_scene(downstream_trace=trace, target_profile=target_profile)
    assert scene["scope"] == "target_approach_all_turns"
    assert len(scene["turn_traces"]) == 3
    assert all("receiving_dir8" in item and "downstream_metrics" in item for item in scene["turn_traces"])
    assert scene["hud"]["metrics"][0]["value"] == "左转/直行/右转"
