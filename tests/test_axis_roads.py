from app.trace.axis_roads import build_axis_roads, parse_road_pair_from_intersection


def test_parse_road_pair_from_intersection():
    assert parse_road_pair_from_intersection("坤顺路与奥体西路路口") == ("坤顺路", "奥体西路")
    assert parse_road_pair_from_intersection(None) == (None, None)


def test_build_axis_roads_from_channel_links():
    links = [
        {
            "link_role": "entrance",
            "dir8_code": "2",
            "dir8_label": "东进口",
            "road_name": "坤顺路:礼耕路-奥体西路(东向西)",
        },
        {
            "link_role": "entrance",
            "dir8_code": "0",
            "dir8_label": "北进口",
            "road_name": "奥体西路:安成街-坤顺路(北向南)",
        },
    ]
    axis = build_axis_roads(intersection_name="坤顺路与奥体西路路口", link_rows=links)
    assert axis["available"] is True
    assert axis["ew_road"] == "坤顺路"
    assert axis["ns_road"] == "奥体西路"
    assert axis["source"] == "channelization"


def test_build_axis_roads_name_fallback():
    axis = build_axis_roads(intersection_name="二环东路与浆水泉西路路口")
    assert axis["available"] is True
    assert axis["ew_road"] == "二环东路"
    assert axis["ns_road"] == "浆水泉西路"
    assert axis["source"] == "intersection_name"
