from intersection_agent.services.upstream_governance_trace_service import build_tree

FAKE_PROFILES = {
    "U1": [{"dir8_code": d, "turn_saturation_max": 0.95, "green_util_min": 0.6} for d in (0, 2, 4, 6)],
    "A": [{"dir8_code": 0, "turn_saturation_max": 0.70, "green_util_min": 0.6}]
          + [{"dir8_code": d, "turn_saturation_max": 0.95, "green_util_min": 0.6} for d in (2, 4, 6)],
}
FAKE_UP = {
    ("U1", 2): {
        "cor_inter_id": "A",
        "feeding_dir8": 2,
        "cor_inter_name": "A",
        "coverage": 70,
        "lng": 1,
        "lat": 1,
        "hop_path": [[1.0, 1.0], [0.5, 0.5], [0.0, 0.0]],
        "path_source": "link_geom",
    },
}


def fake_profiles(inter_id, window):
    return FAKE_PROFILES[inter_id]


def fake_upstream(inter_id, dir8, turn_no):
    return FAKE_UP.get((inter_id, dir8))


def test_tree_single_chain_along_corridor():
    node = build_tree(
        "U1",
        corridor_dir8=2,
        feeding_dir8=0,
        hop=1,
        window=None,
        get_profiles=fake_profiles,
        get_upstream=fake_upstream,
        full_sat=0.85,
        green_util=0.5,
        max_hops=2,
    )
    assert node["decision"] == "继续上溯"
    assert len(node["children"]) == 1
    assert node["children"][0]["inter_id"] == "A"
    assert node["children"][0]["decision"] == "治理落点"


def test_governable_node_stops_immediately():
    node = build_tree(
        "A",
        corridor_dir8=2,
        feeding_dir8=2,
        hop=1,
        window=None,
        get_profiles=fake_profiles,
        get_upstream=fake_upstream,
        full_sat=0.85,
        green_util=0.5,
        max_hops=2,
    )
    assert node["decision"] == "治理落点"
    assert node["children"] == []
