from intersection_agent.services.upstream_governance_trace_service import build_tree

# 构造确定性拓扑：target(北) → U1(全饱和) → U1的其它3进口各有一个上游，其中A可治理
FAKE_PROFILES = {
    "U1": [{"dir8_code": d, "turn_saturation_max": 0.95, "green_util_min": 0.6} for d in (0, 2, 4, 6)],
    "A":  [{"dir8_code": 0, "turn_saturation_max": 0.70, "green_util_min": 0.6}] +
          [{"dir8_code": d, "turn_saturation_max": 0.95, "green_util_min": 0.6} for d in (2, 4, 6)],
    "B":  [{"dir8_code": d, "turn_saturation_max": 0.95, "green_util_min": 0.6} for d in (0, 2, 4, 6)],
    "C":  [{"dir8_code": d, "turn_saturation_max": 0.95, "green_util_min": 0.6} for d in (0, 2, 4, 6)],
}
FAKE_UP = {
    ("U1", 2): {"cor_inter_id": "A", "feeding_dir8": 2, "cor_inter_name": "A", "coverage": 70, "lng": 1, "lat": 1},
    ("U1", 4): {"cor_inter_id": "B", "feeding_dir8": 4, "cor_inter_name": "B", "coverage": 60, "lng": 1, "lat": 1},
    ("U1", 6): {"cor_inter_id": "C", "feeding_dir8": 6, "cor_inter_name": "C", "coverage": 50, "lng": 1, "lat": 1},
}


def fake_profiles(inter_id, window):
    return FAKE_PROFILES[inter_id]

def fake_upstream(inter_id, dir8, window):
    return FAKE_UP.get((inter_id, dir8))

def fake_approaches(inter_id, exclude):
    return [d for d in (0, 2, 4, 6) if d != exclude]


def test_tree_recurses_to_hop2_and_marks_governance_point():
    node = build_tree(
        "U1", feeding_dir8=0, hop=1,
        window=None, get_profiles=fake_profiles, get_upstream=fake_upstream,
        get_other_approaches=fake_approaches,
        full_sat=0.85, green_util=0.5, max_hops=2,
    )
    assert node["decision"] == "继续上溯"
    children = {c["inter_id"]: c for c in node["children"]}
    assert children["A"]["decision"] == "治理落点"
    assert children["B"]["decision"] == "二跳截止"   # 全饱和但已到 hop2
    assert children["A"]["hop"] == 2


def test_governable_node_stops_immediately():
    node = build_tree(
        "A", feeding_dir8=2, hop=1,
        window=None, get_profiles=fake_profiles, get_upstream=fake_upstream,
        get_other_approaches=fake_approaches,
        full_sat=0.85, green_util=0.5, max_hops=2,
    )
    assert node["decision"] == "治理落点"
    assert node["children"] == []
