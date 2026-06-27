"""Tests for corridor geometry helpers."""

from intersection_agent.utils.corridor_geometry import (
    build_centerline_from_inter_chain,
    merge_paths,
    parse_linestring,
    snap_point_to_polyline,
)


def test_parse_linestring():
    pts = parse_linestring("LINESTRING(117.1 36.65, 117.11 36.66)")
    assert pts == [[117.1, 36.65], [117.11, 36.66]]


def test_merge_paths_dedupes_junction():
    a = [[0.0, 0.0], [1.0, 1.0]]
    b = [[1.0, 1.0], [2.0, 2.0]]
    merged = merge_paths([a, b])
    assert merged == [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]]


def test_build_centerline_from_inter_chain():
    links = [
        {
            "link_id": "l1",
            "f_inter_id": "a",
            "t_inter_id": "b",
            "road_name": "奥体西路:甲-乙(北向南)",
            "geom": "LINESTRING(117.0 36.68, 117.0 36.67)",
        },
        {
            "link_id": "l2",
            "f_inter_id": "b",
            "t_inter_id": "c",
            "road_name": "奥体西路:乙-丙(北向南)",
            "geom": "LINESTRING(117.0 36.67, 117.0 36.66)",
        },
    ]
    polyline, used = build_centerline_from_inter_chain(["a", "b", "c"], links, road_name_hint="奥体西路")
    assert len(used) == 2
    assert polyline == [[117.0, 36.68], [117.0, 36.67], [117.0, 36.66]]


def test_snap_point_to_polyline():
    line = [[117.0, 36.68], [117.0, 36.66]]
    snapped = snap_point_to_polyline(117.01, 36.67, line)
    assert abs(snapped[0] - 117.0) < 1e-6
    assert abs(snapped[1] - 36.67) < 1e-6
