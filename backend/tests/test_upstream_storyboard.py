from intersection_agent.services.map_presentation_service import build_upstream_storyboard


def _tree(tree_id, approach):
    return {
        "tree_id": tree_id, "approach": approach,
        "root": {
            "inter_id": "U1", "inter_name": "上游U1", "decision": "继续上溯",
            "hop": 1, "lng": 1.0, "lat": 1.0, "feeding_dir8": 0,
            "approach_profiles": [{"dir8_code": 0, "turn_saturation_max": 0.95}],
            "turn_split": [
                {"turn": "直行", "share_pct": 60.0},
                {"turn": "左转", "share_pct": 40.0},
            ],
            "children": [
                {"inter_id": "A", "inter_name": "上游A", "decision": "治理落点",
                 "hop": 2, "lng": 2.0, "lat": 2.0, "feeding_dir8": 2,
                 "approach_profiles": [{"dir8_code": 2, "turn_saturation_max": 0.70}],
                 "turn_split": [
                     {"turn": "直行", "share_pct": 80.0},
                     {"turn": "右转", "share_pct": 20.0},
                 ],
                 "children": []},
            ],
        },
        "target": {"inter_id": "T", "name": "目标", "approach": approach,
                   "lon": 0.0, "lat": 0.0, "dir8_code": 0},
    }


def test_frames_parallel_when_multiple_approaches():
    sb = build_upstream_storyboard([_tree("N", "北进口"), _tree("E", "东进口")], cognition={})
    assert sb["parallel"] is True
    frames = sb["frames"]
    assert frames[0]["tree"] == "*"
    assert frames[0]["frame_type"] == "pullback"
    # 并行合并后帧数远少于两树串行（每树约 7 帧 → 合并后约 7 帧）
    sb_n = build_upstream_storyboard([_tree("N", "北进口")], cognition={})
    assert len(frames) <= len(sb_n["frames"]) + 2
    assert frames[-1]["frame_type"] == "fit"
    assert frames[-1]["tree"] == "*"


def test_frames_single_tree_serial():
    sb = build_upstream_storyboard([_tree("N", "北进口")], cognition={})
    assert sb.get("parallel") is False
    frames = sb["frames"]
    trees_in_order = [f["tree"] for f in frames]
    assert all(t == "N" for t in trees_in_order)

    n_frames = frames
    assert n_frames[0]["frame_type"] == "pullback"
    assert n_frames[0]["zoom"] == 17
    assert n_frames[0]["show_labels"] is False

    target_frame = next(f for f in n_frames if f["frame_type"] == "target")
    assert target_frame["focus"] == "T"
    assert target_frame["reveal"] == ["T"]

    spread_frame = next(f for f in n_frames if f["frame_type"] == "spread")
    assert any(r.startswith("edge:N:") for r in spread_frame["reveal"])
    assert spread_frame["show_labels"] is False

    up_frame = next(f for f in n_frames if f["frame_type"] == "node" and f["focus"] == "U1")
    assert up_frame["center"] == [1.0, 1.0]
    assert "饱和0.95" in up_frame["narration"]
    assert "直行60.0%" in up_frame["narration"]
    assert up_frame["show_labels"] is True

    a_frame = next(f for f in n_frames if f["frame_type"] == "node" and f["focus"] == "A")
    assert "治理落点" in a_frame["narration"]

    assert n_frames[-1]["frame_type"] == "fit"
    assert n_frames[-1]["fit"] is True
    assert n_frames[-1]["center"] is None


def test_nodes_carry_saturation_and_turn_split():
    sb = build_upstream_storyboard([_tree("N", "北进口")], cognition={})
    n_tree = next(t for t in sb["trees"] if t["tree_id"] == "N")
    u1 = next(n for n in n_tree["nodes"] if n["id"] == "U1")
    assert u1["saturation"] == 0.95
    assert u1["turn_split"][0]["turn"] == "直行"
    target = next(n for n in n_tree["nodes"] if n["id"] == "T")
    assert target["role"] == "target"
    assert target["saturation"] is None
