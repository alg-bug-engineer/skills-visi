from intersection_agent.services.map_presentation_service import build_upstream_storyboard


def _tree(tree_id, approach):
    return {
        "tree_id": tree_id, "approach": approach,
        "root": {
            "inter_id": "U1", "inter_name": "U1", "decision": "继续上溯",
            "hop": 1, "approach_profiles": [], "children": [
                {"inter_id": "A", "inter_name": "A", "decision": "治理落点",
                 "hop": 2, "approach_profiles": [], "children": [],
                 "feeding_dir8": 2, "lng": 1, "lat": 1},
            ], "feeding_dir8": 0, "lng": 1, "lat": 1,
        },
        "target": {"inter_id": "T", "name": "目标", "approach": approach,
                   "lon": 0, "lat": 0, "dir8_code": 0},
    }


def test_frames_are_tree_serialized_and_reveal_is_cumulative():
    sb = build_upstream_storyboard([_tree("N", "北进口"), _tree("E", "东进口")], cognition={})
    # 逐树串讲：所有 N 帧在 E 帧之前
    trees_in_order = [f["tree"] for f in sb["frames"]]
    assert trees_in_order == sorted(trees_in_order, key=lambda t: 0 if t == "N" else 1)
    assert trees_in_order[0] == "N" and trees_in_order[-1] == "E"
    # 第一帧 thesis，reveal 为空
    assert sb["frames"][0]["kind"] == "thesis"
    assert sb["frames"][0]["reveal"] == []
    # 存在 resolve 帧且 focus 含落点
    assert any(f["kind"] == "resolve" for f in sb["frames"])
