from intersection_agent.services.flow_trace_service import one_hop_for_approach


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
