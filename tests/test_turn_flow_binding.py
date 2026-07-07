"""真实转向流量绑定到信号相位的单元测试。"""

from __future__ import annotations

from app.data.turn_flow_binding import bind_turn_flows_to_signal


def _signal() -> dict:
    return {
        "plan_no": "1",
        "current_cycle_s": 130.0,
        "phase_stage_timing_list": [
            {"phase_stage_id": "1", "phase_stage_name": "西直、东直", "greenTime": 60, "minGreenTime": 35},
            {"phase_stage_id": "2", "phase_stage_name": "东左、西左", "greenTime": 12, "minGreenTime": 12},
            {"phase_stage_id": "3", "phase_stage_name": "南直", "greenTime": 49, "minGreenTime": 35},
        ],
    }


def _channel() -> list[dict]:
    return [
        {"link_id": "L_W", "link_role": "entrance", "dir8_code": 6},
        {"link_id": "L_E", "link_role": "entrance", "dir8_code": 2},
        {"link_id": "L_S", "link_role": "entrance", "dir8_code": 4},
    ]


def _mapping() -> list[dict]:
    return [
        {"plan_no": "1", "stage_no": "1", "link_id": "L_W", "turn_dir_no": 2},
        {"plan_no": "1", "stage_no": "1", "link_id": "L_E", "turn_dir_no": 2},
        {"plan_no": "1", "stage_no": "2", "link_id": "L_E", "turn_dir_no": 1},
        {"plan_no": "1", "stage_no": "2", "link_id": "L_W", "turn_dir_no": 1},
        {"plan_no": "1", "stage_no": "3", "link_id": "L_S", "turn_dir_no": 2},
    ]


def _flows() -> list[dict]:
    # 两个 step 切片，绑定后按均值折算 vph
    return [
        {"link_id": "L_W", "turn_dir_no": 2, "step_index": 216, "turn_flow_total": 800, "lane_count": 3},
        {"link_id": "L_W", "turn_dir_no": 2, "step_index": 217, "turn_flow_total": 900, "lane_count": 3},
        {"link_id": "L_E", "turn_dir_no": 2, "step_index": 216, "turn_flow_total": 700, "lane_count": 3},
        {"link_id": "L_E", "turn_dir_no": 1, "step_index": 216, "turn_flow_total": 300, "lane_count": 2},
        {"link_id": "L_W", "turn_dir_no": 1, "step_index": 216, "turn_flow_total": 260, "lane_count": 2},
        {"link_id": "L_S", "turn_dir_no": 2, "step_index": 216, "turn_flow_total": 500, "lane_count": 2},
    ]


def _saturation() -> list[dict]:
    return [
        {"link_id": "L_W", "turn_dir_no": 2, "turn_saturation": 0.9},
        {"link_id": "L_S", "turn_dir_no": 2, "turn_saturation": 0.7},
    ]


def test_bind_uses_real_flow_and_multi_movement_expansion():
    signal = _signal()
    bind_turn_flows_to_signal(
        signal,
        flow_rows=_flows(),
        saturation_rows=_saturation(),
        signal_lane_mapping_rows=_mapping(),
        channel_rows=_channel(),
        period="step:216-217",
    )

    stage1 = signal["phase_stage_timing_list"][0]
    dir_infos = stage1["phaseDirInfoDTOList"]
    # 多转向阶段展开为两条（西直 + 东直），无占位 500
    assert len(dir_infos) == 2
    flows = {d["linkId"]: d["turnFlowTotal"] for d in dir_infos}
    assert flows["L_W"] == 850  # (800+900)/2
    assert flows["L_E"] == 700
    assert all(d["flow_available"] for d in dir_infos)
    # dir8/turn 映射正确（西=6/东=2，直行=2）
    assert {d["dir8No"] for d in dir_infos} == {6, 2}
    assert {d["turnDirNo"] for d in dir_infos} == {2}
    # 车道数来自真实数据而非写死 2
    assert {d["laneCount"] for d in dir_infos} == {3}
    # 饱和度绑定
    west = next(d for d in dir_infos if d["linkId"] == "L_W")
    assert west["turnSaturation"] == 0.9
    # 无占位常量
    assert all(d["turnFlowTotal"] != 500 for d in dir_infos)

    assert signal["flow_binding"]["ok"] is True
    assert signal["flow_binding"]["unbound_stages"] == []
    assert signal["flow_binding"]["source"] == "pg_turn_flow"


def test_bind_marks_unbound_stage_without_fabrication():
    signal = _signal()
    # 只提供阶段1的流量，阶段2/3 无真实流量
    flows = [
        {"link_id": "L_W", "turn_dir_no": 2, "turn_flow_total": 850, "lane_count": 3},
        {"link_id": "L_E", "turn_dir_no": 2, "turn_flow_total": 700, "lane_count": 3},
    ]
    bind_turn_flows_to_signal(
        signal,
        flow_rows=flows,
        saturation_rows=[],
        signal_lane_mapping_rows=_mapping(),
        channel_rows=_channel(),
    )
    binding = signal["flow_binding"]
    assert binding["ok"] is True
    assert set(binding["unbound_stages"]) == {"2", "3"}
    # 未绑定阶段不编造流量
    stage3 = signal["phase_stage_timing_list"][2]
    assert stage3["stage_flow_vph"] is None
    assert all(d["turnFlowTotal"] is None for d in stage3["phaseDirInfoDTOList"])


def test_bind_degrades_when_no_flow():
    signal = _signal()
    bind_turn_flows_to_signal(
        signal,
        flow_rows=[],
        saturation_rows=[],
        signal_lane_mapping_rows=_mapping(),
        channel_rows=_channel(),
    )
    binding = signal["flow_binding"]
    assert binding["ok"] is False
    assert binding["source"] == "none"
    assert binding["reason"]


def test_bind_falls_back_to_motor_flow_mapping():
    signal = _signal()
    # 无 signal_lane_mapping，走 stage_motor_flow 回退
    motor = [
        {"stage_no": "1", "f_dir8_no": 6, "flow_type_no": 1},  # 西直
        {"stage_no": "1", "f_dir8_no": 2, "flow_type_no": 1},  # 东直
        {"stage_no": "3", "f_dir8_no": 4, "flow_type_no": 1},  # 南直
    ]
    bind_turn_flows_to_signal(
        signal,
        flow_rows=_flows(),
        saturation_rows=[],
        signal_lane_mapping_rows=[],
        channel_rows=_channel(),
        stage_motor_flow_rows=motor,
    )
    stage1 = signal["phase_stage_timing_list"][0]
    assert len(stage1["phaseDirInfoDTOList"]) == 2
    assert signal["flow_binding"]["ok"] is True


def test_bind_no_stages():
    signal = {"plan_no": "1", "phase_stage_timing_list": []}
    bind_turn_flows_to_signal(
        signal,
        flow_rows=_flows(),
        saturation_rows=[],
        signal_lane_mapping_rows=_mapping(),
        channel_rows=_channel(),
    )
    assert signal["flow_binding"]["ok"] is False
