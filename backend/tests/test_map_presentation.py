"""Map presentation: scene markers and NLU direction preference."""

from intersection_agent.models.domain import DiagnosisResult, NluResult, TimePeriod
from intersection_agent.services.map_presentation_service import (
    axis_roads_summary,
    build_flow_sources_action,
    build_links_narration_payload,
    build_map_scene,
    build_narration_steps,
)


def _flow_trace_payload() -> dict:
    return {
        "available": True,
        "entry_traces": [
            {
                "entry": "东进口",
                "dir8_code": 2,
                "upstream_inter_id": "U1",
                "upstream_inter_name": "岔口",
                "upstream_lng": 117.11,
                "upstream_lat": 36.65,
                "narrative": "东进口约100辆过境车中，约82辆来自上一路口岔口，以直行为主（82辆）",
                "dominant_movement": {
                    "turn": "直行",
                    "vehicles_of_100": 82,
                    "feed_direction": "东南进口直行",
                },
                "upstream_movements": [
                    {"turn": "直行", "vehicles_of_100": 82, "feed_direction": "东南进口直行"},
                ],
            },
            {
                "entry": "西进口",
                "dir8_code": 6,
                "upstream_inter_id": "U2",
                "upstream_inter_name": "无坐标点",
                "upstream_lng": None,
                "upstream_lat": None,
                "narrative": "西进口暂无坐标",
            },
        ],
    }


def test_flow_sources_action_builds_road_paths_with_center():
    cognition = _cognition()
    action = build_flow_sources_action(_flow_trace_payload(), cognition)
    assert action is not None
    assert action["phase"] == "flow_trace"
    assert action["source_center"] == {"lon": 117.1, "lat": 36.6}
    # 无坐标进口道被过滤
    assert len(action["entry_traces"]) == 1
    trace = action["entry_traces"][0]
    assert trace["upstream_inter_id"] == "U1"
    assert trace["vehicles_of_100"] == 82
    assert trace.get("path")
    assert len(trace["path"]) >= 2
    assert "100辆" in action["text"]


def test_flow_sources_action_none_when_unavailable_or_no_coords():
    assert build_flow_sources_action({"available": False}, {}) is None
    no_coords = {
        "available": True,
        "entry_traces": [
            {
                "entry": "东进口",
                "dir8_code": 2,
                "upstream_lng": None,
                "upstream_lat": None,
            },
        ],
    }
    assert build_flow_sources_action(no_coords, {"intersection": {}}) is None


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
                "road_name": "经十路:甲-乙(东向西)",
                "path": [[117.101, 36.601], [117.100, 36.600]],
            },
            {
                "link_id": "w1",
                "link_role": "entrance",
                "dir4_label": "西进口",
                "road_name": "经十路:乙-甲(西向东)",
                "path": [[117.099, 36.601], [117.100, 36.600]],
            },
            {
                "link_id": "s1",
                "link_role": "entrance",
                "dir4_label": "南进口",
                "road_name": "奥体西路:丙-丁(南向北)",
                "path": [[117.100, 36.599], [117.100, 36.600]],
            },
            {
                "link_id": "n1",
                "link_role": "entrance",
                "dir4_label": "北进口",
                "road_name": "奥体西路:丁-丙(北向南)",
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


def test_build_map_scene_traffic_shows_delay_not_saturation_on_map():
    scene = build_map_scene(
        "traffic",
        cognition=_cognition(),
        data={"traffic_flow": {"saturation_rate": 1.14}, "evaluation": {"delay_index": 1.47}},
    )
    assert scene["action"] == "map_scene"
    assert scene["hud"] is not None
    hud_labels = [m["label"] for m in scene["hud"]["metrics"]]
    assert "饱和度" not in hud_labels
    assert "延误指数" in hud_labels
    sat_markers = [m for m in scene["markers"] if m.get("variant") == "saturation"]
    turn_markers = [m for m in scene["markers"] if m.get("variant") == "turn"]
    assert sat_markers == []
    assert turn_markers == []
    assert any(m.get("variant") == "delay" for m in scene["markers"])


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


def test_axis_roads_summary_groups_road_names():
    axis = axis_roads_summary(_cognition())
    assert axis.get("东西向") == "经十路"
    assert axis.get("南北向") == "奥体西路"


def test_build_links_narration_payload_includes_speakable():
    payload = build_links_narration_payload(_cognition())
    assert payload["axis_roads"]["东西向"] == "经十路"
    assert "东西向为经十路" in payload["speakable"]
    assert "南北向为奥体西路" in payload["speakable"]
    assert "进口" not in payload["speakable"]
    assert "车道" not in payload["speakable"]
    assert payload["speakable"].endswith("。")


def test_build_map_scene_direction_roles_with_nlu():
    nlu = NluResult(
        intersection="测试路口",
        problem_type="congestion",
        directions=["南北向"],
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
    )
    scene = build_map_scene(
        "direction",
        cognition=_cognition(),
        data={"traffic_flow": {"saturation_rate": 1.14}},
        nlu=nlu,
    )
    assert scene["focus_groups"] == ["南北向"]
    assert scene["protected_groups"] == ["东西向"]
    roles = {item["group"]: item["role"] for item in scene["direction_roles"]}
    assert roles["南北向"] == "focus"
    assert roles["东西向"] == "protect"


def test_direction_metric_lines_role_prefix():
    nlu = NluResult(
        intersection="测试路口",
        problem_type="congestion",
        directions=["南北向"],
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
    )
    steps = build_narration_steps(
        cognition=_cognition(),
        data={"traffic_flow": {"saturation_rate": 1.0}, "evaluation": {}},
        nlu=nlu,
    )
    direction = next(step for step in steps if step["phase"] == "direction")
    assert "【关注】南北向" in direction["text"]
    assert "【保护】东西向" in direction["text"]


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


def test_narration_steps_include_step_summary_rt_pres_summary():
    """RT-PRES-SUMMARY: narration steps carry step_summary ≤40 chars."""
    steps = build_narration_steps(
        cognition=_cognition(),
        data={
            "traffic_flow": {"saturation_rate": 0.92},
            "evaluation": {"delay_index": 1.2, "imbalance_index": 0.35, "green_utilization": 0.55},
        },
    )
    direction = next(s for s in steps if s["phase"] == "direction")
    assert direction.get("step_summary")
    assert len(direction["step_summary"]) <= 40
    assert direction.get("focus_step_index") == 3

    links_payload = build_links_narration_payload(_cognition())
    assert links_payload.get("step_summary")
    assert links_payload.get("focus_step_index") == 2


def test_build_map_scene_direction_includes_all_groups():
    nlu = NluResult(
        intersection="测试路口",
        problem_type="congestion",
        directions=["东西向"],
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
    )
    scene = build_map_scene(
        "direction",
        cognition=_cognition(),
        data={"traffic_flow": {"saturation_rate": 1.14}},
        nlu=nlu,
    )
    dirs = {m["dir"] for m in scene["markers"]}
    assert dirs == {"东", "西", "南", "北"}
    by_dir = {m["dir"]: m for m in scene["markers"]}
    assert "南北向" in by_dir["南"]["title"] or by_dir["南"]["title"] == "南北向"
    assert by_dir["南"]["value"] == "1.20"


def test_timing_narration_reports_duration_only():
    steps = build_narration_steps(
        cognition=_cognition(),
        data={
            "timing_profile": {
                "cycle_length": 130.0,
                "period_count": 6,
                "narrative": "当前方案周期约 130s，日计划时段 6 个",
                "deficit_turns": [{"label": "东直行", "deficit_ratio": 0.2}],
                "flow_green_fit": {"verdict": "mismatch", "narrative": "流量与绿信比不匹配"},
            }
        },
    )
    timing = next(step for step in steps if step["phase"] == "timing")
    assert "130" in timing["text"]
    assert "不匹配" not in timing["text"]
    assert "最小绿" not in timing["text"]


def test_build_map_scene_traffic_defers_turn_saturation_to_direction_phase():
    cognition = _cognition()
    cognition["metrics_by_arm"] = [
        {"dir4_label": "东进口", "link_id": "e1", "saturation": 1.5},
        {"dir4_label": "西进口", "link_id": "w1", "saturation": 1.44},
    ]
    cognition["metrics_by_turn"] = [
        {"label": "东左转", "dir4_label": "东", "turn_dir_no": 1, "turn_saturation": 1.5},
        {"label": "西左转", "dir4_label": "西", "turn_dir_no": 1, "turn_saturation": 1.44},
        {"label": "南直行", "dir4_label": "南", "turn_dir_no": 2, "turn_saturation": 1.2},
        {"label": "北直行", "dir4_label": "北", "turn_dir_no": 2, "turn_saturation": 1.2},
    ]
    traffic = build_map_scene(
        "traffic",
        cognition=cognition,
        data={"traffic_flow": {"saturation_rate": 1.5}, "evaluation": {"delay_index": 1.47}},
    )
    turn_markers = [m for m in traffic["markers"] if m.get("variant") == "turn"]
    assert turn_markers == []

    direction = build_map_scene(
        "direction",
        cognition=cognition,
        data={"traffic_flow": {"saturation_rate": 1.5}, "evaluation": {"delay_index": 1.47}},
    )
    dir_turn = [m for m in direction["markers"] if m.get("variant") == "turn"]
    assert len(dir_turn) == 4
    by_dir = {m["dir"]: m for m in dir_turn}
    assert by_dir["东"]["value"] == "1.50"
    assert by_dir["南"]["value"] == "1.20"


def test_build_map_scene_traffic_has_no_turn_markers_even_with_partial_groups():
    cognition = _cognition()
    cognition["direction_groups"] = [
        {
            "group": "东西向",
            "saturation_max": 1.05,
            "saturation_avg": 0.95,
            "level": "high",
            "arm_labels": ["东", "西"],
        },
    ]
    cognition["metrics_by_arm"] = [
        {"dir4_label": "东进口", "link_id": "e1", "saturation": 1.5},
        {"dir4_label": "西进口", "link_id": "w1", "saturation": 1.44},
    ]
    cognition["metrics_by_turn"] = [
        {"label": "东左转", "dir4_label": "东", "turn_dir_no": 1, "turn_saturation": 1.5},
        {"label": "西左转", "dir4_label": "西", "turn_dir_no": 1, "turn_saturation": 1.44},
    ]
    scene = build_map_scene(
        "traffic",
        cognition=cognition,
        data={"traffic_flow": {"saturation_rate": 1.5}, "evaluation": {"delay_index": 1.47}},
    )
    turn_markers = [m for m in scene["markers"] if m.get("variant") == "turn"]
    assert turn_markers == []


def test_build_map_scene_timing_has_cycle_hud_only():
    scene = build_map_scene(
        "timing",
        cognition=_cognition(),
        data={"timing_profile": {"cycle_length": 130.0, "period_count": 6}},
    )
    assert scene["markers"] == []
    labels = [m["label"] for m in scene["hud"]["metrics"]]
    assert labels == ["周期"]
