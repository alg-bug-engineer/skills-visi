from app.trace.axis_roads import build_axis_roads


def test_axis_roads_uses_adjacent_intersections_instead_of_bearing_labels():
    result = build_axis_roads(
        intersection_name="解放东路与奥体中路路口",
        link_rows=[
            {
                "link_role": "entrance",
                "dir8_code": 0,
                "dir8_label": "北进口",
                "road_name": None,
                "adjacent_inter_name": "坤顺路与奥体中路路口",
            },
            {
                "link_role": "entrance",
                "dir8_code": 6,
                "dir8_label": "西进口",
                "road_name": None,
                "adjacent_inter_name": "解放东路与重德路路口",
            },
        ],
    )

    assert result["ew_road"] == "解放东路"
    assert result["ns_road"] == "奥体中路"
    assert result["source"] == "road_topology"
    assert "西" not in {result["ew_road"], result["ns_road"]}
    assert "北" not in {result["ew_road"], result["ns_road"]}


def test_axis_roads_keeps_name_pair_unordered_when_axis_has_no_evidence():
    result = build_axis_roads(intersection_name="解放东路与奥体中路路口")

    assert result["ew_road"] is None
    assert result["ns_road"] is None
    assert result["road_pair"] == ["解放东路", "奥体中路"]
    assert result["source"] == "intersection_name_unordered"


def test_axis_roads_ignores_ambiguous_adjacent_label_containing_both_target_roads():
    result = build_axis_roads(
        intersection_name="奥体中路与经十路路口",
        link_rows=[
            {
                "link_role": "entrance",
                "dir8_code": 0,
                "dir8_label": "北进口",
                "adjacent_inter_name": "解放东路与奥体中路路口",
            },
            {
                "link_role": "entrance",
                "dir8_code": 2,
                "dir8_label": "东进口",
                "adjacent_inter_name": "奥体中路与经十路路口",
            },
        ],
    )

    assert result["ew_road"] == "经十路"
    assert result["ns_road"] == "奥体中路"
