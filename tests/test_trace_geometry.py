"""流量溯源真实几何：WKT 解析/定向 + topology_from_pg_raw 上下游拓扑构建。

验证「几何为真源、占比来自 flow_correlate、禁止合成」的后端契约（docs/rule.md 约束19）。
"""

from __future__ import annotations

import json
from decimal import Decimal

from app.data.pg_adapters import topology_from_pg_raw
from app.trace.geometry import orient_path, parse_linestring_wkt, parse_point_wkt
from app.trace.map_scene import build_channelization_map_scene, build_flow_trace_links_sniff_map_scene


def test_parse_linestring_wkt():
    path = parse_linestring_wkt("LINESTRING(117.10 36.65, 117.11 36.66, 117.12 36.67)")
    assert path == [[117.10, 36.65], [117.11, 36.66], [117.12, 36.67]]


def test_parse_linestring_wkt_invalid():
    assert parse_linestring_wkt(None) == []
    assert parse_linestring_wkt("") == []
    assert parse_linestring_wkt("POINT(1 2)") == []


def test_parse_point_wkt():
    assert parse_point_wkt("POINT(117.10159 36.657529)") == [117.10159, 36.657529]
    assert parse_point_wkt("117.1,36.6") is None
    assert parse_point_wkt(None) is None


def test_orient_path_reverses_when_needed():
    # path 从 target(终) → upstream(起)，应翻转使 path[0] 靠近起点 upstream
    path = [[117.101, 36.657], [117.106, 36.658], [117.111, 36.659]]
    oriented = orient_path(path, 117.111, 36.659, 117.101, 36.657)
    assert oriented[0] == [117.111, 36.659]
    assert oriented[-1] == [117.101, 36.657]


def test_orient_path_keeps_short_path():
    assert orient_path([[1, 2]], 1, 2, 3, 4) == [[1, 2]]


def _demo_raw():
    return {
        "inter": {
            "inter_id": "TARGET",
            "inter_name": "经十路与转山西路路口",
            "geom_center": "POINT(117.10159 36.657529)",
        },
        "metrics": {},
        "trace_geometry": [
            {
                "link_id": "L_UP",
                "link_role": "entrance",
                "dir8_code": "2",
                "dir8_label": "东进口",
                "relation_direction": "upstream",
                "adjacent_inter_id": "UP1",
                "adjacent_inter_name": "奥体西路与经十路路口",
                "geom_wkt": "LINESTRING(117.111 36.659, 117.106 36.658, 117.10159 36.6575)",
                "adjacent_lng": 117.111,
                "adjacent_lat": 36.659,
            },
            {
                "link_id": "L_DOWN",
                "link_role": "exit",
                "dir8_code": "6",
                "dir8_label": "西出口",
                "relation_direction": "downstream",
                "adjacent_inter_id": "DOWN1",
                "adjacent_inter_name": "经十路辅路与海右路路口",
                "geom_wkt": "LINESTRING(117.10159 36.6575, 117.099 36.657, 117.0989 36.657)",
                "adjacent_lng": 117.0989,
                "adjacent_lat": 36.657,
            },
            {
                # 不在问题进口方向（dir8=4），应被忽略
                "link_id": "L_OTHER",
                "link_role": "entrance",
                "dir8_code": "4",
                "relation_direction": "upstream",
                "adjacent_inter_id": "OTHER",
                "adjacent_inter_name": "南向路口",
                "geom_wkt": "LINESTRING(117.101 36.655, 117.101 36.657)",
                "adjacent_lng": 117.101,
                "adjacent_lat": 36.655,
            },
        ],
        "flow_correlate": [
            # DB trace_type 经验性反转：东进口来向记录在 DOWNSTREAM，几何优先仍归为上游
            {"f_dir8_no": 2, "turn_dir_no": 2, "cor_inter_id": "UP1", "trace_type": "DOWNSTREAM", "flow_share_ratio": 71.63},
            {"f_dir8_no": 2, "turn_dir_no": 2, "cor_inter_id": "DOWN1", "trace_type": "UPSTREAM", "flow_share_ratio": 42.1},
        ],
    }


def test_topology_builds_real_geometry_nodes():
    ticket = {"direction": "东向西", "movement": "直行", "intersection_name": "经十路与转山西路路口"}
    topo = topology_from_pg_raw(_demo_raw(), ticket, _demo_raw()["inter"])

    assert topo["target_lng"] == 117.10159
    assert topo["target_lat"] == 36.657529
    assert topo["exit_dir8"] == 6
    assert topo["geometry_source"] == "dim_link_info.geom"

    ups = topo["upstream_nodes"]
    assert len(ups) == 1  # dir8=4 的被过滤
    up = ups[0]
    assert up["upstream_inter_id"] == "UP1"
    assert len(up["path"]) == 3
    assert up["path_source"] == "link_geom"
    assert up["path"][0] == [117.111, 36.659]  # 起点靠近上游
    assert up["upstream_movements"][0]["share_pct"] == 71.63

    downs = topo["downstream_nodes"]
    assert len(downs) == 1
    down = downs[0]
    assert down["inter_id"] == "DOWN1"
    assert len(down["path"]) == 3
    assert down["path"][0] == [117.10159, 36.6575]  # 起点靠近目标
    assert down["share_pct"] == 42.1


def test_topology_combines_upstream_same_entry_turns_but_keeps_downstream_strict():
    raw = _demo_raw()
    raw["flow_correlate"] = [
        {
            "f_dir8_no": 2,
            "turn_dir_no": 2,
            "cor_inter_id": "UP1",
            "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 79.31,
        },
        {
            "f_dir8_no": 2,
            "turn_dir_no": 1,
            "cor_inter_id": "UP1",
            "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 11.57,
        },
        {
            "f_dir8_no": 2,
            "turn_dir_no": 2,
            "cor_inter_id": "DOWN1",
            "trace_type": "UPSTREAM",
            "flow_share_ratio": 42.1,
        },
        {
            "f_dir8_no": 2,
            "turn_dir_no": 1,
            "cor_inter_id": "DOWN1",
            "trace_type": "UPSTREAM",
            "flow_share_ratio": 20.0,
        },
    ]

    topo = topology_from_pg_raw(
        raw,
        {"direction": "东向西", "movement": "直行", "intersection_name": "经十路与转山西路路口"},
        raw["inter"],
    )

    assert topo["upstream_nodes"][0]["upstream_movements"][0]["share_pct"] == 90.88
    assert topo["downstream_nodes"][0]["share_pct"] == 42.1


def test_channelization_map_scene_joins_real_link_geometry():
    raw = {
        "channelization": [
            {
                "link_id": "L_IN",
                "link_role": "entrance",
                "dir8_code": "6",
                "dir8_label": "西进口",
                "dir4_label": "西进口",
                "lane_num": 3,
                "c_lane_num": 3,
                "lane_info": "B|C|D",
                "turn_move": "直行",
            },
            {
                "link_id": "L_OUT",
                "link_role": "exit",
                "dir8_code": "2",
                "dir8_label": "东出口",
                "dir4_label": "东出口",
                "lane_num": 2,
                "c_lane_num": 2,
                "lane_info": None,
                "turn_move": None,
            },
        ],
        "trace_geometry": [
            {
                "link_id": "L_IN",
                "geom_wkt": "LINESTRING(117.10 36.65, 117.11 36.65)",
                "adjacent_inter_id": "UP",
                "adjacent_inter_name": "上游路口",
                "adjacent_lng": 117.10,
                "adjacent_lat": 36.65,
                "relation_direction": "upstream",
            },
            {
                "link_id": "L_OUT",
                "geom_wkt": "LINESTRING(117.11 36.65, 117.12 36.65)",
                "adjacent_inter_id": "DOWN",
                "adjacent_inter_name": "下游路口",
                "adjacent_lng": 117.12,
                "adjacent_lat": 36.65,
                "relation_direction": "downstream",
            },
        ],
        "turn_saturation": [{"link_id": "L_IN", "turn_saturation": 0.86}],
        "green_utilization": [{"link_id": "L_IN", "green_utilization": 0.57}],
        "turn_perf": [{"link_id": "L_IN", "queue_len_max": 158}],
        "turn_flow": [{"link_id": "L_IN", "turn_flow_total": 620}],
        "lane_capacity": [{"link_id": "L_IN", "lane_capacity": 1500}],
    }

    scene = build_channelization_map_scene(
        pg_raw=raw,
        target_profile={"inter_id": "T", "inter_name": "目标", "lng": 117.11, "lat": 36.65},
        center=(117.11, 36.65),
    )

    assert scene["available"] is True
    assert scene["center"] == [117.11, 36.65]
    assert len(scene["links"]) == 2
    entrance = scene["links"][0]
    assert entrance["path"] == [[117.10, 36.65], [117.11, 36.65]]
    assert entrance["lane_info"] == "B|C|D"
    assert entrance["metrics"]["saturation"] == 0.86
    assert entrance["metrics"]["green_utilization"] == 0.57
    assert entrance["metrics"]["queue_m"] == 158
    assert scene["links"][1]["adjacent_inter_id"] == "DOWN"
    assert scene["links"][1]["adjacent_inter_name"] == "下游路口"


def test_channelization_map_scene_saturation_uses_max_per_link_and_approach():
    raw = {
        "channelization": [
            {
                "link_id": "L_N",
                "link_role": "entrance",
                "dir8_code": "1",
                "dir8_label": "北进口",
                "lane_info": "B|C",
            }
        ],
        "trace_geometry": [
            {
                "link_id": "L_N",
                "geom_wkt": "LINESTRING(117.11 36.66, 117.11 36.65)",
            }
        ],
        "turn_saturation": [
            {"link_id": "L_N", "dir8_label": "北进口", "turn_saturation": 0.59},
            {"link_id": "L_N", "dir8_label": "北进口", "turn_saturation": 1.54},
            {"link_id": "L_OTHER", "dir8_label": "北进口", "turn_saturation": 0.2},
        ],
    }
    scene = build_channelization_map_scene(
        pg_raw=raw,
        target_profile={"inter_id": "T", "inter_name": "目标", "lng": 117.11, "lat": 36.65},
    )
    assert scene["available"] is True
    assert scene["links"][0]["metrics"]["saturation"] == 1.54


def test_channelization_map_scene_requires_real_geometry():
    scene = build_channelization_map_scene(
        pg_raw={"channelization": [{"link_id": "L_IN", "link_role": "entrance"}], "trace_geometry": []},
        target_profile={"lng": 117.11, "lat": 36.65},
    )

    assert scene["available"] is False
    assert scene["reason"] == "no_channelization_geometry"


def test_flow_trace_links_sniff_map_scene_groups_real_links():
    raw = _demo_raw()
    raw["channelization"] = [
        {
            "link_id": "L_UP",
            "link_role": "entrance",
            "dir8_code": "2",
            "dir8_label": "东进口",
            "dir4_label": "东进口",
            "lane_num": 3,
        },
        {
            "link_id": "L_DOWN",
            "link_role": "exit",
            "dir8_code": "6",
            "dir8_label": "西出口",
            "dir4_label": "西出口",
            "lane_num": 2,
        },
    ]
    topology = topology_from_pg_raw(raw, {"direction": "东向西", "movement": "直行"}, raw["inter"])

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw,
        topology=topology,
        target_profile={
            "inter_id": "TARGET",
            "inter_name": "经十路与转山西路路口",
            "lng": 117.10159,
            "lat": 36.657529,
        },
        direction="东向西",
        movement="直行",
    )

    assert scene["available"] is True
    assert scene["phase"] == "flow_trace_links_sniff_map"
    assert scene["trace_direction"] == "upstream"
    assert scene["stats"]["rendered"] == 2
    assert scene["stats"]["main_corridor"] == 1
    assert scene["stats"]["hidden_non_main"] == 1
    assert scene["main_corridor_chain"][0]["inter_id"] == "UP1"

    target = scene["intersections"][0]
    assert target["role"] == "target"
    # 目标渲染完整 link「十字」：进/出口全集（L_UP/L_DOWN/L_OTHER），不再裁到单条。
    assert len(target["links"]) == 3
    assert target["links"][0]["path"] == [[117.111, 36.659], [117.106, 36.658], [117.10159, 36.6575]]

    peer = scene["intersections"][1]
    assert peer["role"] == "upstream"
    assert peer["in_main_corridor"] is True
    assert peer["path_coverage"] == 71.63
    assert peer["links"][0]["link_id"] == "L_UP"

    assert [n["inter_id"] for n in scene["intersections"][1:]] == ["UP1"]


def test_flow_trace_links_sniff_map_scene_uses_correlate_peer_link_geometry():
    raw = _demo_raw()
    raw["flow_correlate"] = [
        {
            "f_dir8_no": 6,
            "turn_dir_no": 2,
            "cor_inter_id": "P1",
            "cor_inter_name": "主链一",
            "cor_f_dir8_no": 6,
            "cor_turn_dir_no": 2,
            "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 90.1,
        },
        {
            "f_dir8_no": 6,
            "turn_dir_no": 2,
            "cor_inter_id": "P2",
            "cor_inter_name": "主链二",
            "cor_f_dir8_no": 6,
            "cor_turn_dir_no": 2,
            "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 76.5,
        },
        {
            "f_dir8_no": 6,
            "turn_dir_no": 2,
            "cor_inter_id": "P3",
            "cor_inter_name": "其他来向",
            "cor_f_dir8_no": 0,
            "cor_turn_dir_no": 2,
            "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 35.6,
        },
    ]
    raw["peer_link_geometry"] = [
        {
            "inter_id": "P1",
            "inter_name": "主链一",
            "lng": 117.09,
            "lat": 36.65,
            "link_id": "P1_L",
            "link_role": "entrance",
            "lane_num": Decimal("3"),
            "geom_wkt": "LINESTRING(117.08 36.65, 117.09 36.65)",
        },
        {
            "inter_id": "P2",
            "inter_name": "主链二",
            "lng": 117.08,
            "lat": 36.65,
            "link_id": "P2_L",
            "link_role": "entrance",
            "geom_wkt": "LINESTRING(117.07 36.65, 117.08 36.65)",
        },
        {
            "inter_id": "P3",
            "inter_name": "其他来向",
            "lng": 117.08,
            "lat": 36.66,
            "link_id": "P3_L",
            "link_role": "entrance",
            "geom_wkt": "LINESTRING(117.08 36.66, 117.08 36.67)",
        },
    ]
    topology = {
        "target_inter_id": "TARGET",
        "target_inter_name": "目标",
        "target_lng": 117.10159,
        "target_lat": 36.657529,
        "dir8_code": 6,
        "turn_dir_no": 2,
        "upstream_nodes": [],
        "downstream_nodes": [],
    }

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw,
        topology=topology,
        target_profile={"inter_id": "TARGET", "inter_name": "目标", "lng": 117.10159, "lat": 36.657529},
        direction="西向东",
        movement="直行",
    )

    assert scene["available"] is True
    # 复刻参考：同进口道直行走廊多跳全量保留（P1/P2 均在主走廊）；P3(cor_f_dir8=0) 非本进口道，
    # 被进口道+转向约束排除，不再塌缩为单一上游。
    assert scene["stats"]["distinct_peers"] == 2
    assert scene["stats"]["main_corridor"] == 2
    assert "suppressed_secondary_upstream" not in scene["stats"]
    upstream = [n for n in scene["intersections"] if n["role"] == "upstream"]
    assert [n["inter_id"] for n in upstream] == ["P1", "P2"]
    assert all(n["in_main_corridor"] for n in upstream)
    assert upstream[0]["path_coverage"] == 90.1
    assert upstream[0]["links"][0]["link_id"] == "P1_L"
    assert upstream[1]["path_coverage"] == 76.5
    json.dumps(scene, ensure_ascii=False)


def test_flow_trace_links_sniff_map_scene_uses_best_share_not_cross_turn_sum():
    """对齐参考：只取目标 movement(turn=2) 走廊行的占比，不跨目标转向求和。"""
    raw = _demo_raw()
    raw["flow_correlate"] = [
        {
            "f_dir8_no": 6,
            "turn_dir_no": 2,
            "cor_inter_id": "P1",
            "cor_inter_name": "主链一",
            "cor_f_dir8_no": 6,
            "cor_turn_dir_no": 2,
            "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 79.31,
        },
        {
            # 目标左转(turn=1) 行不并入直行(turn=2) 溯源占比
            "f_dir8_no": 6,
            "turn_dir_no": 1,
            "cor_inter_id": "P1",
            "cor_inter_name": "主链一",
            "cor_f_dir8_no": 6,
            "cor_turn_dir_no": 2,
            "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 11.57,
        },
    ]
    raw["peer_link_geometry"] = [
        {
            "inter_id": "P1",
            "inter_name": "主链一",
            "lng": 117.09,
            "lat": 36.65,
            "link_id": "P1_L",
            "link_role": "entrance",
            "geom_wkt": "LINESTRING(117.08 36.65, 117.09 36.65)",
        }
    ]
    topology = {
        "target_inter_id": "TARGET",
        "target_inter_name": "目标",
        "target_lng": 117.10159,
        "target_lat": 36.657529,
        "dir8_code": 6,
        "turn_dir_no": 2,
        "upstream_nodes": [],
        "downstream_nodes": [],
    }

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw,
        topology=topology,
        target_profile={"inter_id": "TARGET", "inter_name": "目标", "lng": 117.10159, "lat": 36.657529},
        direction="西向东",
        movement="直行",
    )

    assert scene["available"] is True
    assert scene["intersections"][1]["path_coverage"] == 79.31


def test_flow_trace_links_sniff_map_scene_keeps_downstream_single_turn():
    raw = _demo_raw()
    raw["flow_correlate"] = [
        {
            "f_dir8_no": 6,
            "turn_dir_no": 2,
            "cor_inter_id": "D1",
            "cor_inter_name": "下游一跳",
            "cor_f_dir8_no": 6,
            "cor_turn_dir_no": 2,
            "trace_type": "UPSTREAM",
            "flow_share_ratio": 42.1,
        },
        {
            "f_dir8_no": 6,
            "turn_dir_no": 1,
            "cor_inter_id": "D1",
            "cor_inter_name": "下游一跳",
            "cor_f_dir8_no": 6,
            "cor_turn_dir_no": 2,
            "trace_type": "UPSTREAM",
            "flow_share_ratio": 20.0,
        },
    ]
    raw["peer_link_geometry"] = [
        {
            "inter_id": "D1",
            "inter_name": "下游一跳",
            "lng": 117.09,
            "lat": 36.65,
            "link_id": "D1_L",
            "link_role": "exit",
            "geom_wkt": "LINESTRING(117.10 36.65, 117.09 36.65)",
        }
    ]
    topology = {
        "target_inter_id": "TARGET",
        "target_inter_name": "目标",
        "target_lng": 117.10159,
        "target_lat": 36.657529,
        "dir8_code": 6,
        "turn_dir_no": 2,
        "upstream_nodes": [],
        "downstream_nodes": [],
    }

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw,
        topology=topology,
        target_profile={"inter_id": "TARGET", "inter_name": "目标", "lng": 117.10159, "lat": 36.657529},
        direction="西向东",
        movement="直行",
        trace_direction="downstream",
    )

    assert scene["available"] is True
    assert scene["intersections"][1]["path_coverage"] == 42.1


def test_flow_trace_links_sniff_map_scene_excludes_off_approach_peer():
    """进口道约束：非本进口道直行的关联路口(P2, cor_f_dir8=0) 不属走廊，被排除。"""
    raw = _demo_raw()
    raw["flow_correlate"] = [
        {
            "f_dir8_no": 6,
            "turn_dir_no": 2,
            "cor_inter_id": "P1",
            "cor_inter_name": "主链一",
            "cor_f_dir8_no": 6,
            "cor_turn_dir_no": 2,
            "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 90.1,
        },
        {
            "f_dir8_no": 6,
            "turn_dir_no": 2,
            "cor_inter_id": "P2",
            "cor_inter_name": "其他来向",
            "cor_f_dir8_no": 0,
            "cor_turn_dir_no": 2,
            "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 35.6,
        },
    ]
    raw["peer_link_geometry"] = [
        {
            "inter_id": "P1",
            "inter_name": "主链一",
            "lng": 117.09,
            "lat": 36.65,
            "link_id": "P1_L",
            "link_role": "entrance",
            "geom_wkt": "LINESTRING(117.08 36.65, 117.09 36.65)",
        },
        {
            "inter_id": "P2",
            "inter_name": "其他来向",
            "lng": 117.08,
            "lat": 36.66,
            "link_id": "P2_L",
            "link_role": "entrance",
            "geom_wkt": "LINESTRING(117.08 36.66, 117.08 36.67)",
        },
    ]
    topology = {
        "target_inter_id": "TARGET",
        "target_inter_name": "目标",
        "target_lng": 117.10159,
        "target_lat": 36.657529,
        "dir8_code": 6,
        "turn_dir_no": 2,
        "upstream_nodes": [],
        "downstream_nodes": [],
    }

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw,
        topology=topology,
        target_profile={"inter_id": "TARGET", "inter_name": "目标", "lng": 117.10159, "lat": 36.657529},
        direction="西向东",
        movement="直行",
    )

    assert scene["available"] is True
    assert scene["stats"]["distinct_peers"] == 1
    assert scene["stats"]["rendered"] == 2
    assert "suppressed_secondary_upstream" not in scene["stats"]
    assert [n["inter_id"] for n in scene["intersections"][1:]] == ["P1"]


def test_flow_trace_links_sniff_scene_skips_period_filter_while_single_day_sample():
    """单日 flow_correlate 样本期暂不卡 period_type，应渲染各时段 peer。"""
    raw = _demo_raw()
    raw["flow_correlate"] = [
        {
            "f_dir8_no": 6, "turn_dir_no": 2, "cor_inter_id": "P1", "cor_inter_name": "晚高峰主链",
            "cor_f_dir8_no": 6, "cor_turn_dir_no": 2, "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 90.1, "period_type": "EVENING_PEAK",
        },
        {
            "f_dir8_no": 6, "turn_dir_no": 2, "cor_inter_id": "P2", "cor_inter_name": "早高峰额外",
            "cor_f_dir8_no": 6, "cor_turn_dir_no": 2, "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 80.0, "period_type": "MORNING_PEAK",
        },
        {
            "f_dir8_no": 6, "turn_dir_no": 2, "cor_inter_id": "P3", "cor_inter_name": "平峰额外",
            "cor_f_dir8_no": 6, "cor_turn_dir_no": 2, "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 70.0, "period_type": "OFF_PEAK",
        },
    ]
    raw["peer_link_geometry"] = [
        {"inter_id": pid, "inter_name": pid, "lng": 117.09, "lat": 36.65, "link_id": f"{pid}_L",
         "link_role": "entrance", "geom_wkt": "LINESTRING(117.08 36.65, 117.09 36.65)"}
        for pid in ("P1", "P2", "P3")
    ]
    topology = {
        "target_inter_id": "TARGET", "target_inter_name": "目标",
        "target_lng": 117.10159, "target_lat": 36.657529,
        "dir8_code": 6, "turn_dir_no": 2, "period_type": "EVENING_PEAK",
        "upstream_nodes": [], "downstream_nodes": [],
    }

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw, topology=topology,
        target_profile={"inter_id": "TARGET", "inter_name": "目标", "lng": 117.10159, "lat": 36.657529},
        direction="西向东", movement="直行",
    )

    assert scene["available"] is True
    assert scene["stats"]["period_type"] is None
    assert scene["stats"]["period_filter_enabled"] is False
    assert scene["stats"]["period_filter_caveat"]
    assert scene["stats"]["distinct_peers"] == 3
    assert [n["inter_id"] for n in scene["intersections"][1:]] == ["P1", "P2", "P3"]


def test_flow_trace_links_sniff_scene_period_falls_back_when_empty():
    """关闭时间片过滤时，早高峰 peer 直接参与渲染。"""
    raw = _demo_raw()
    raw["flow_correlate"] = [
        {
            "f_dir8_no": 6, "turn_dir_no": 2, "cor_inter_id": "P1", "cor_inter_name": "早高峰主链",
            "cor_f_dir8_no": 6, "cor_turn_dir_no": 2, "trace_type": "DOWNSTREAM",
            "flow_share_ratio": 90.1, "period_type": "MORNING_PEAK",
        },
    ]
    raw["peer_link_geometry"] = [
        {"inter_id": "P1", "inter_name": "P1", "lng": 117.09, "lat": 36.65, "link_id": "P1_L",
         "link_role": "entrance", "geom_wkt": "LINESTRING(117.08 36.65, 117.09 36.65)"}
    ]
    topology = {
        "target_inter_id": "TARGET", "target_inter_name": "目标",
        "target_lng": 117.10159, "target_lat": 36.657529,
        "dir8_code": 6, "turn_dir_no": 2, "period_type": "EVENING_PEAK",
        "upstream_nodes": [], "downstream_nodes": [],
    }

    scene = build_flow_trace_links_sniff_map_scene(
        pg_raw=raw, topology=topology,
        target_profile={"inter_id": "TARGET", "inter_name": "目标", "lng": 117.10159, "lat": 36.657529},
        direction="西向东", movement="直行",
    )

    assert scene["available"] is True
    assert scene["stats"]["period_type"] is None  # 回退到全时段
    assert [n["inter_id"] for n in scene["intersections"][1:]] == ["P1"]


def test_topology_resolves_period_from_ticket():
    raw = _demo_raw()
    topo_am = topology_from_pg_raw(raw, {"direction": "东向西", "movement": "直行", "period": "早高峰"}, raw["inter"])
    topo_pm = topology_from_pg_raw(raw, {"direction": "东向西", "movement": "直行", "period": "晚高峰"}, raw["inter"])
    topo_default = topology_from_pg_raw(raw, {"direction": "东向西", "movement": "直行"}, raw["inter"])
    assert topo_am["period_type"] == "MORNING_PEAK"
    assert topo_pm["period_type"] == "EVENING_PEAK"
    topo_morning_time = topology_from_pg_raw(
        raw, {"direction": "东向西", "movement": "直行", "time_range": "07:30-07:50"}, raw["inter"]
    )
    assert topo_morning_time["period_type"] == "MORNING_PEAK"
    assert topo_default["period_type"] is None


def test_topology_no_synthesis_when_geometry_missing():
    raw = _demo_raw()
    raw["trace_geometry"] = []
    ticket = {"direction": "东向西", "movement": "直行", "intersection_name": "x"}
    topo = topology_from_pg_raw(raw, ticket, raw["inter"])
    assert topo["upstream_nodes"] == []
    assert topo["downstream_nodes"] == []
    assert topo["geometry_source"] == "unavailable"


def test_topology_left_turn_falls_back_to_correlate_exit_link():
    """北进口左转：compass exit_dir8 无匹配出口时，用 flow_correlate + 真实 exit link 绑定下游。"""
    raw = _demo_raw()
    raw["trace_geometry"] = [
        {
            "link_id": "N_IN",
            "dir8_code": "0",
            "relation_direction": "upstream",
            "adjacent_inter_id": "UP_N",
            "adjacent_inter_name": "上游北口",
            "adjacent_lng": 117.12,
            "adjacent_lat": 36.665,
            "geom_wkt": "LINESTRING(117.12 36.665, 117.12 36.663)",
            "length_m": 200,
        },
        {
            "link_id": "W_OUT",
            "dir8_code": "6",
            "relation_direction": "downstream",
            "adjacent_inter_id": "DOWN_W",
            "adjacent_inter_name": "西向下一口",
            "adjacent_lng": 117.118,
            "adjacent_lat": 36.663,
            "geom_wkt": "LINESTRING(117.12 36.663, 117.118 36.663)",
            "length_m": 180,
        },
    ]
    raw["flow_correlate"] = [
        {
            "f_dir8_no": 0,
            "turn_dir_no": 1,
            "trace_type": "DOWNSTREAM",
            "cor_inter_id": "DOWN_W",
            "cor_inter_name": "西向下一口",
            "flow_share_ratio": 88.5,
        },
    ]
    topo = topology_from_pg_raw(
        raw,
        {"direction": "北向南", "movement": "左转", "intersection_name": "目标"},
        raw["inter"],
    )
    assert len(topo["downstream_nodes"]) == 1
    down = topo["downstream_nodes"][0]
    assert down["inter_id"] == "DOWN_W"
    assert down["receiving_dir8"] == 6
    assert down["share_pct"] == 88.5
