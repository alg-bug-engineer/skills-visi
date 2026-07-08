from app.trace.map_scene import build_flow_trace_links_sniff_map_scene


def _row(link_id: str, role: str, dir8: int, name: str = "目标") -> dict:
    return {
        "link_id": link_id,
        "link_role": role,
        "dir8_code": dir8,
        "dir8_label": f"{dir8}",
        "adjacent_inter_id": "A",
        "adjacent_inter_name": name,
        "adjacent_lng": 117.0,
        "adjacent_lat": 36.6,
        "geom_wkt": "LINESTRING(117.0 36.6,117.1 36.6)",
    }


def test_sniff_scene_keeps_only_target_movement_links_and_peer_turn_path():
    raw = {
        "trace_geometry": [
            _row("target-south-in", "entrance", 4),
            _row("target-west-in", "entrance", 6),
            _row("target-east-out", "exit", 2),
        ],
        "channelization": [
            {"link_id": "target-south-in", "link_role": "entrance", "dir8_code": 4},
            {"link_id": "target-west-in", "link_role": "entrance", "dir8_code": 6},
            {"link_id": "target-east-out", "link_role": "exit", "dir8_code": 2},
        ],
        "flow_correlate": [
            {
                "f_dir8_no": 4,
                "turn_dir_no": 2,
                "trace_type": "DOWNSTREAM",
                "cor_inter_id": "P1",
                "cor_inter_name": "上游路口",
                "cor_f_dir8_no": 2,
                "cor_turn_dir_no": 3,
                "flow_share_ratio": 75.0,
            }
        ],
        "peer_link_geometry": [
            {"inter_id": "P1", "inter_name": "上游路口", "lng": 117.0, "lat": 36.6, **_row("peer-east-in", "entrance", 2, "上游")},
            {"inter_id": "P1", "inter_name": "上游路口", "lng": 117.0, "lat": 36.6, **_row("peer-west-in", "entrance", 6, "上游")},
            {"inter_id": "P1", "inter_name": "上游路口", "lng": 117.0, "lat": 36.6, **_row("peer-north-out", "exit", 0, "上游")},
            {"inter_id": "P1", "inter_name": "上游路口", "lng": 117.0, "lat": 36.6, **_row("peer-east-out", "exit", 2, "上游")},
        ],
    }

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw,
        topology={"dir8_code": 4, "turn_dir_no": 2, "upstream_nodes": []},
        target_profile={"inter_id": "T", "inter_name": "目标", "lng": 117.1, "lat": 36.6},
        direction="南向北",
        movement="直行",
        trace_direction="upstream",
    )

    target, peer = scene["intersections"]
    assert [link["link_id"] for link in target["links"]] == ["target-south-in"]
    assert [link["link_id"] for link in peer["links"]] == ["peer-east-in", "peer-north-out"]


def test_sniff_scene_hides_peers_below_ten_percent():
    raw = {
        "trace_geometry": [_row("target-south-in", "entrance", 4)],
        "channelization": [{"link_id": "target-south-in", "link_role": "entrance", "dir8_code": 4}],
        "flow_correlate": [
            {
                "f_dir8_no": 4,
                "turn_dir_no": 2,
                "trace_type": "DOWNSTREAM",
                "cor_inter_id": "LOW",
                "cor_inter_name": "低占比路口",
                "cor_f_dir8_no": 2,
                "cor_turn_dir_no": 3,
                "flow_share_ratio": 9.9,
            }
        ],
        "peer_link_geometry": [
            {"inter_id": "LOW", "inter_name": "低占比路口", "lng": 117.0, "lat": 36.6, **_row("peer-east-in", "entrance", 2, "低占比")},
        ],
    }

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw,
        topology={"dir8_code": 4, "turn_dir_no": 2, "upstream_nodes": []},
        target_profile={"inter_id": "T", "inter_name": "目标", "lng": 117.1, "lat": 36.6},
        direction="南向北",
        movement="直行",
        trace_direction="upstream",
    )

    assert [node["role"] for node in scene["intersections"]] == ["target"]


def test_upstream_scene_keeps_only_single_primary_upstream():
    """来向溯源只保留唯一上游，其余关联路口不作上游溯源渲染。"""
    raw = {
        "trace_geometry": [_row("target-south-in", "entrance", 4)],
        "channelization": [{"link_id": "target-south-in", "link_role": "entrance", "dir8_code": 4}],
        "flow_correlate": [
            {
                "f_dir8_no": 4,
                "turn_dir_no": 2,
                "trace_type": "DOWNSTREAM",
                "cor_inter_id": "P1",
                "cor_inter_name": "上游A",
                "cor_f_dir8_no": 2,
                "cor_turn_dir_no": 3,
                "flow_share_ratio": 60.0,
            },
            {
                "f_dir8_no": 4,
                "turn_dir_no": 2,
                "trace_type": "DOWNSTREAM",
                "cor_inter_id": "P2",
                "cor_inter_name": "上游B",
                "cor_f_dir8_no": 6,
                "cor_turn_dir_no": 1,
                "flow_share_ratio": 40.0,
            },
        ],
        "peer_link_geometry": [
            {"inter_id": "P1", "inter_name": "上游A", "lng": 117.0, "lat": 36.6, **_row("p1-east-in", "entrance", 2, "上游A")},
            {"inter_id": "P2", "inter_name": "上游B", "lng": 116.9, "lat": 36.6, **_row("p2-west-in", "entrance", 6, "上游B")},
        ],
    }

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw,
        topology={"dir8_code": 4, "turn_dir_no": 2, "upstream_nodes": []},
        target_profile={"inter_id": "T", "inter_name": "目标", "lng": 117.1, "lat": 36.6},
        direction="南向北",
        movement="直行",
        trace_direction="upstream",
    )

    peers = [node for node in scene["intersections"] if node["role"] == "upstream"]
    assert len(peers) == 1
    assert peers[0]["inter_id"] == "P1"
    assert scene["stats"]["suppressed_secondary_upstream"] == 1
