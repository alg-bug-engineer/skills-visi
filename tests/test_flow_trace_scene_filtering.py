"""流量溯源 link 场景：进口道+转向走廊约束 + 每路口完整 link「十字」渲染（对齐参考 sniff）。

复刻 references/流量溯源/source/backend/services/correlate_sniff_map_service.py 口径：
- 以进口道(dir8)+转向(turn) 约束 correlate 走廊 peer；
- target 与每个 peer 渲染其真实进/出口 link 全集（不裁到单条）；
- 不塌缩为单一上游，保留多跳走廊链。
"""

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


def test_sniff_scene_renders_full_cross_links_for_target_and_peer():
    """target 与走廊 peer 均渲染其完整 link 十字（真实进/出口全集），不再裁到单条。"""
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
                "cor_f_dir8_no": 4,  # 同进口道(南)直行来向 → 在走廊内
                "cor_turn_dir_no": 2,
                "flow_share_ratio": 75.0,
            }
        ],
        "peer_link_geometry": [
            {"inter_id": "P1", "inter_name": "上游路口", "lng": 117.0, "lat": 36.6, **_row("peer-south-in", "entrance", 4, "上游")},
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
    # target 保留其全部进/出口 link（十字），不再只留进口 dir8 单条
    assert {link["link_id"] for link in target["links"]} == {
        "target-south-in",
        "target-west-in",
        "target-east-out",
    }
    # peer 保留其全部进/出口 link（十字），不再只留转向单条
    assert {link["link_id"] for link in peer["links"]} == {
        "peer-south-in",
        "peer-west-in",
        "peer-north-out",
        "peer-east-out",
    }
    assert peer["in_main_corridor"] is True


def test_sniff_scene_excludes_off_approach_peer():
    """进口道+转向约束：非本进口道直行的关联路口不属走廊，被排除（此前按占比隐藏，现按走廊约束排除）。"""
    raw = {
        "trace_geometry": [_row("target-south-in", "entrance", 4)],
        "channelization": [{"link_id": "target-south-in", "link_role": "entrance", "dir8_code": 4}],
        "flow_correlate": [
            {
                "f_dir8_no": 4,
                "turn_dir_no": 2,
                "trace_type": "DOWNSTREAM",
                "cor_inter_id": "OFF",
                "cor_inter_name": "非本进口路口",
                "cor_f_dir8_no": 2,  # 东进口，非本(南)进口道直行 → 不在走廊
                "cor_turn_dir_no": 3,
                "flow_share_ratio": 88.0,
            }
        ],
        "peer_link_geometry": [
            {"inter_id": "OFF", "inter_name": "非本进口路口", "lng": 117.0, "lat": 36.6, **_row("peer-east-in", "entrance", 2, "非本进口")},
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


def test_upstream_scene_keeps_full_corridor_chain():
    """来向溯源保留完整多跳走廊链：同进口道直行的 P1/P2 均渲染，不塌缩为单一上游。"""
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
                "cor_f_dir8_no": 4,
                "cor_turn_dir_no": 2,
                "flow_share_ratio": 60.0,
            },
            {
                "f_dir8_no": 4,
                "turn_dir_no": 2,
                "trace_type": "DOWNSTREAM",
                "cor_inter_id": "P2",
                "cor_inter_name": "上游B",
                "cor_f_dir8_no": 4,
                "cor_turn_dir_no": 2,
                "flow_share_ratio": 40.0,
            },
        ],
        "peer_link_geometry": [
            {"inter_id": "P1", "inter_name": "上游A", "lng": 117.0, "lat": 36.6, **_row("p1-south-in", "entrance", 4, "上游A")},
            {"inter_id": "P2", "inter_name": "上游B", "lng": 116.9, "lat": 36.6, **_row("p2-south-in", "entrance", 4, "上游B")},
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
    assert [p["inter_id"] for p in peers] == ["P1", "P2"]
    assert all(p["in_main_corridor"] for p in peers)
    assert "suppressed_secondary_upstream" not in scene["stats"]


def test_topological_one_hop_anchor_rendered_even_when_correlate_misses_it():
    """物理主上游一跳即便不在（单时段）correlate 命中，也必须作为拓扑锚点呈现。

    复刻 解放东路与奥体中路 早高峰回归：correlate 仅命中弱旁支（占比 13），而物理主上游
    （拓扑一跳、占比 77）不在 correlate 内。修复前主走廊物理来向缺席、溯源近乎空白；
    修复后拓扑一跳被注入并标记为 is_topo_anchor 主走廊。
    """
    raw = {
        "trace_geometry": [_row("target-south-in", "entrance", 4)],
        "channelization": [{"link_id": "target-south-in", "link_role": "entrance", "dir8_code": 4}],
        "flow_correlate": [
            {
                "f_dir8_no": 4,
                "turn_dir_no": 2,
                "trace_type": "DOWNSTREAM",
                "cor_inter_id": "WEAK",
                "cor_inter_name": "弱旁支路口",
                "cor_f_dir8_no": 4,
                "cor_turn_dir_no": 2,
                "flow_share_ratio": 13.0,
            }
        ],
        "peer_link_geometry": [
            {"inter_id": "WEAK", "inter_name": "弱旁支路口", "lng": 117.0, "lat": 36.6, **_row("weak-south-in", "entrance", 4, "弱旁支")},
            {"inter_id": "TOPO", "inter_name": "物理主上游", "lng": 116.95, "lat": 36.6, **_row("topo-south-in", "entrance", 4, "物理主上游")},
        ],
    }

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw,
        topology={
            "dir8_code": 4,
            "turn_dir_no": 2,
            "upstream_nodes": [
                {"inter_id": "TOPO", "upstream_inter_name": "物理主上游", "upstream_movements": [{"share_pct": 77.0}]}
            ],
        },
        target_profile={"inter_id": "T", "inter_name": "目标", "lng": 117.1, "lat": 36.6},
        direction="南向北",
        movement="直行",
        trace_direction="upstream",
    )

    upstream = {node["inter_id"]: node for node in scene["intersections"] if node["role"] == "upstream"}
    assert "TOPO" in upstream, "物理主上游一跳必须被注入渲染"
    assert upstream["TOPO"]["is_topo_anchor"] is True
    assert upstream["TOPO"]["in_main_corridor"] is True
    assert upstream["TOPO"]["path_coverage"] == 77.0
    # 弱旁支仍保留（同走廊约束命中），但锚点为物理主上游
    assert "WEAK" in upstream
    # 主走廊链 hop 连续、无重复
    hops = [item["hop"] for item in scene["main_corridor_chain"]]
    assert hops == sorted(set(hops)) == list(range(1, len(hops) + 1))


def test_downstream_turn_excludes_arterial_straight_keeps_turn_corridor():
    """去向左/右转：垂直出口走廊保留，排除进口直行 OD 蔓延（对齐参考 outgoing_row_in_corridor）。"""
    raw = {
        "trace_geometry": [_row("target-west-in", "entrance", 6)],
        "channelization": [{"link_id": "target-west-in", "link_role": "entrance", "dir8_code": 6}],
        "flow_correlate": [
            {
                # 进口直行 OD（cor_f_dir8==dir8 & cor_turn==2）在去向转向溯源中应被排除
                "f_dir8_no": 6,
                "turn_dir_no": 1,
                "trace_type": "DOWNSTREAM",
                "cor_inter_id": "STRAIGHT",
                "cor_inter_name": "干线直行路口",
                "cor_f_dir8_no": 6,
                "cor_turn_dir_no": 2,
                "flow_share_ratio": 70.0,
            },
            {
                # 该转向的垂直出口走廊 peer 应保留
                "f_dir8_no": 6,
                "turn_dir_no": 1,
                "trace_type": "DOWNSTREAM",
                "cor_inter_id": "TURN",
                "cor_inter_name": "左转去向路口",
                "cor_f_dir8_no": 0,
                "cor_turn_dir_no": 3,
                "flow_share_ratio": 55.0,
            },
        ],
        "peer_link_geometry": [
            {"inter_id": "STRAIGHT", "inter_name": "干线直行路口", "lng": 117.0, "lat": 36.6, **_row("s-in", "entrance", 6, "干线直行")},
            {"inter_id": "TURN", "inter_name": "左转去向路口", "lng": 117.1, "lat": 36.7, **_row("t-in", "entrance", 0, "左转去向")},
        ],
    }

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw,
        topology={"dir8_code": 6, "turn_dir_no": 1, "downstream_nodes": []},
        target_profile={"inter_id": "T", "inter_name": "目标", "lng": 117.1, "lat": 36.6},
        direction="西向东",
        movement="左转",
        trace_direction="downstream",
    )

    peers = [node["inter_id"] for node in scene["intersections"] if node["role"] == "downstream"]
    assert peers == ["TURN"]
    assert all(node["in_main_corridor"] for node in scene["intersections"] if node["role"] == "downstream")
