"""Turn-level saturation markers in map scenes."""

from intersection_agent.models.domain import NluResult, TimePeriod
from intersection_agent.services.map_presentation_service import build_map_scene


def _cognition_with_turns() -> dict:
    return {
        "intersection": {"name": "测试路口", "lon": 117.1, "lat": 36.6},
        "links": [
            {
                "link_id": "e1",
                "link_role": "entrance",
                "dir4_label": "东进口",
                "path": [[117.101, 36.601], [117.100, 36.600]],
            },
            {
                "link_id": "w1",
                "link_role": "entrance",
                "dir4_label": "西进口",
                "path": [[117.099, 36.601], [117.100, 36.600]],
            },
            {
                "link_id": "s1",
                "link_role": "entrance",
                "dir4_label": "南进口",
                "path": [[117.100, 36.599], [117.100, 36.600]],
            },
            {
                "link_id": "n1",
                "link_role": "entrance",
                "dir4_label": "北进口",
                "path": [[117.100, 36.601], [117.100, 36.600]],
            },
        ],
        "direction_groups": [
            {"group": "东西向", "saturation_max": 1.83, "arm_labels": ["东", "西"]},
            {"group": "南北向", "saturation_max": 0.9, "arm_labels": ["南", "北"]},
        ],
        "metrics_by_turn": [
            {"label": "东左转", "dir4_label": "东", "turn_dir_no": 1, "turn_saturation": 1.83, "level": "high"},
            {"label": "西直行", "dir4_label": "西", "turn_dir_no": 2, "turn_saturation": 0.03, "level": "low"},
            {"label": "北直行", "dir4_label": "北", "turn_dir_no": 2, "turn_saturation": 0.9, "level": "high"},
        ],
        "arms": [],
    }


def test_traffic_phase_defers_turn_markers_to_direction():
    traffic = build_map_scene(
        "traffic",
        cognition=_cognition_with_turns(),
        data={"traffic_flow": {"saturation_rate": 1.83}, "evaluation": {"delay_index": 1.5}},
    )
    assert [m for m in traffic["markers"] if m.get("variant") == "turn"] == []

    direction = build_map_scene(
        "direction",
        cognition=_cognition_with_turns(),
        data={"traffic_flow": {"saturation_rate": 1.83}, "evaluation": {"delay_index": 1.5}},
    )
    turn_markers = [m for m in direction["markers"] if m.get("variant") == "turn"]
    assert len(turn_markers) >= 3
    by_title = {m["title"]: m["value"] for m in turn_markers}
    assert by_title["东左转"] == "1.83"
    assert by_title["西直行"] == "0.03"
    assert by_title["北直行"] == "0.90"
    south = next((m for m in turn_markers if m.get("dir") == "南"), None)
    assert south is None


def test_direction_phase_turn_markers_with_focus_prefix():
    nlu = NluResult(
        intersection="测试路口",
        problem_type="congestion",
        directions=["南北向"],
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
    )
    scene = build_map_scene(
        "direction",
        cognition=_cognition_with_turns(),
        data={"traffic_flow": {"saturation_rate": 1.83}},
        nlu=nlu,
    )
    turn_markers = [m for m in scene["markers"] if m.get("variant") == "turn"]
    north = next(m for m in turn_markers if m.get("dir") == "北")
    assert north["title"].startswith("关注·")
    assert "北直行" in north["title"]
