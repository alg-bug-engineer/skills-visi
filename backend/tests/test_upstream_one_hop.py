from intersection_agent.services.flow_trace_service import (
    one_hop_for_approach,
    turn_split_for_upstream,
)


def test_one_hop_picks_max_coverage_same_direction():
    rows = [
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 2, "flow_share_ratio": 88.0, "cor_inter_name": "上游A",
         "cor_lng": 117.1, "cor_lat": 36.65},
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U2", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 2, "flow_share_ratio": 40.0, "cor_inter_name": "上游B",
         "cor_lng": 117.2, "cor_lat": 36.66},
    ]
    hop = one_hop_for_approach(rows, dir8=0)
    assert hop is not None
    assert hop["cor_inter_id"] == "U1"
    assert hop["feeding_dir8"] == 0


def test_one_hop_returns_none_when_no_rows_for_dir8():
    assert one_hop_for_approach([], dir8=4) is None


def test_turn_split_groups_by_upstream_dir_and_turn():
    rows = [
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 2, "flow_share_ratio": 60.0},
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 1, "flow_share_ratio": 30.0},
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 3, "flow_share_ratio": 10.0},
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U2", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 2, "flow_share_ratio": 99.0},
    ]
    split = turn_split_for_upstream(rows, dir8=0, cor_inter_id="U1")
    assert [s["feed_direction"] for s in split] == ["北直行", "北左转", "北右转"]
    by_label = {s["feed_direction"]: s for s in split}
    assert by_label["北直行"]["share_pct"] == 60.0
    assert by_label["北左转"]["share_pct"] == 30.0
    assert by_label["北右转"]["share_pct"] == 10.0
    assert round(sum(s["share_pct"] for s in split if s.get("share_pct") is not None)) == 100


def test_turn_split_includes_distinct_corridor_feeders():
    """西进口（东向西走廊）上游：北右转、东直行、西左转。"""
    rows = [
        {"f_dir8_no": 6, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 3, "flow_share_ratio": 16.0},
        {"f_dir8_no": 6, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 2,
         "cor_turn_dir_no": 2, "flow_share_ratio": 76.0},
        {"f_dir8_no": 6, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 6,
         "cor_turn_dir_no": 1, "flow_share_ratio": 8.0},
    ]
    split = turn_split_for_upstream(rows, dir8=6, cor_inter_id="U1")
    labels = {s["feed_direction"] for s in split}
    assert labels == {"北右转", "东直行", "西左转"}


def test_turn_split_empty_when_no_match():
    split = turn_split_for_upstream([], dir8=0, cor_inter_id="U1")
    assert split == []


def test_turn_split_omits_missing_movements_instead_of_data_gap_fill():
    rows = [
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 2,
         "cor_turn_dir_no": 2, "flow_share_ratio": 70.0},
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 4,
         "cor_turn_dir_no": 3, "flow_share_ratio": 30.0},
    ]
    split = turn_split_for_upstream(rows, dir8=0, cor_inter_id="U1")
    labels = [s["feed_direction"] for s in split]
    assert labels == ["东直行", "南右转"]
    assert all(not s.get("data_gap") for s in split)
