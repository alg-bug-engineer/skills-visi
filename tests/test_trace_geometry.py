"""流量溯源真实几何：WKT 解析/定向 + topology_from_pg_raw 上下游拓扑构建。

验证「几何为真源、占比来自 flow_correlate、禁止合成」的后端契约（docs/rule.md 约束19）。
"""

from __future__ import annotations

from app.data.pg_adapters import topology_from_pg_raw
from app.trace.geometry import orient_path, parse_linestring_wkt, parse_point_wkt


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


def test_topology_no_synthesis_when_geometry_missing():
    raw = _demo_raw()
    raw["trace_geometry"] = []
    ticket = {"direction": "东向西", "movement": "直行", "intersection_name": "x"}
    topo = topology_from_pg_raw(raw, ticket, raw["inter"])
    assert topo["upstream_nodes"] == []
    assert topo["downstream_nodes"] == []
    assert topo["geometry_source"] == "unavailable"
