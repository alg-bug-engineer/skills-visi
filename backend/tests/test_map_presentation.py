"""Map presentation: scene markers and NLU direction preference."""

from intersection_agent.models.domain import DiagnosisResult, NluResult, TimePeriod
from intersection_agent.services.map_presentation_service import (
    build_map_scene,
    build_narration_steps,
)


def _cognition() -> dict:
    return {
        "intersection": {
            "name": "测试路口",
            "lon": 117.1,
            "lat": 36.6,
            "arm_count": 4,
            "total_lanes": 8,
        },
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
            {
                "group": "东西向",
                "saturation_max": 1.05,
                "saturation_avg": 0.95,
                "level": "high",
                "arm_labels": ["东", "西"],
            },
            {
                "group": "南北向",
                "saturation_max": 1.20,
                "saturation_avg": 1.10,
                "level": "high",
                "arm_labels": ["南", "北"],
            },
        ],
        "arms": [],
    }


def test_build_map_scene_traffic_has_hud_and_marker():
    scene = build_map_scene(
        "traffic",
        cognition=_cognition(),
        data={"traffic_flow": {"saturation_rate": 1.14}, "evaluation": {"delay_index": 1.47}},
    )
    assert scene["action"] == "map_scene"
    assert scene["hud"] is not None
    assert len(scene["markers"]) >= 1


def test_build_map_scene_prefers_nlu_direction_over_worst_saturation():
    nlu = NluResult(
        intersection="测试路口",
        problem_type="congestion",
        directions=["东西向"],
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
    )
    scene = build_map_scene(
        "direction",
        cognition=_cognition(),
        data={"traffic_flow": {"saturation_rate": 1.14}, "evaluation": {"delay_index": 1.47}},
        nlu=nlu,
    )
    assert scene["highlight_dirs"] == ["东", "西"]


def test_rule_narration_strips_suggestion_wording_before_confirmation():
    diagnosis = DiagnosisResult(
        diagnosed=True,
        matched_rules=[
            {
                "id": "rule_oversaturation",
                "name": "过饱和需增加绿灯",
                "conclusion": "关键方向过饱和，建议增加绿灯时长",
            }
        ],
    )
    steps = build_narration_steps(cognition=_cognition(), data={}, diagnosis=diagnosis)
    rule_step = next(step for step in steps if step["phase"] == "rule")
    assert "关键方向过饱和" in rule_step["text"]
    assert "建议增加绿灯时长" not in rule_step["text"]
