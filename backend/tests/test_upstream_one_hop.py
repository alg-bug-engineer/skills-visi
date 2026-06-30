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


def test_turn_split_groups_by_upstream_turn_and_normalizes():
    rows = [
        # 上游 U1 经直行/左转/右转 汇入本路口北进口(0)
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 2, "flow_share_ratio": 60.0},
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 1, "flow_share_ratio": 30.0},
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 3, "flow_share_ratio": 10.0},
        # 另一上游路口，应被忽略
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U2", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 2, "flow_share_ratio": 99.0},
    ]
    split = turn_split_for_upstream(rows, dir8=0, cor_inter_id="U1")
    assert [s["turn"] for s in split] == ["左转", "直行", "右转"]
    by_turn = {s["turn"]: s for s in split}
    assert by_turn["直行"]["share_pct"] == 60.0
    assert by_turn["左转"]["share_pct"] == 30.0
    assert by_turn["右转"]["share_pct"] == 10.0
    assert round(sum(s["share_pct"] for s in split if s.get("share_pct") is not None)) == 100


def test_turn_split_empty_when_no_match():
    split = turn_split_for_upstream([], dir8=0, cor_inter_id="U1")
    assert len(split) == 3
    assert all(s.get("data_gap") for s in split)


def test_turn_split_fills_missing_left_turn():
    rows = [
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 2, "flow_share_ratio": 70.0},
        {"f_dir8_no": 0, "turn_dir_no": 2, "cor_inter_id": "U1", "cor_f_dir8_no": 0,
         "cor_turn_dir_no": 3, "flow_share_ratio": 30.0},
    ]
    split = turn_split_for_upstream(rows, dir8=0, cor_inter_id="U1")
    turns = [s["turn"] for s in split]
    assert "左转" in turns
    left = next(s for s in split if s["turn"] == "左转")
    assert left.get("data_gap") is True
