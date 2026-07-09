"""优化请求构建：真实约束透传、多转向展开、去占位。"""

from __future__ import annotations

from app.optimization.request_builder import build_optimizer_request


def _signal_with_binding() -> dict:
    return {
        "inter_id": "TEST01",
        "plan_no": "1",
        "plan_name": "现状方案",
        "current_cycle_s": 130,
        "max_cycle_s": 160,
        "phase_stage_timing_list": [
            {
                "phase_stage_id": "1",
                "phase_stage_name": "西直、东直",
                "greenTime": 60,
                "yellowTime": 3,
                "allRedTime": 2,
                "minGreenTime": 35,
                "maxGreenTime": 90,
                "phaseDirInfoDTOList": [
                    {"dir8No": 6, "turnDirNo": 2, "turnFlowTotal": 850, "laneCount": 3, "flow_available": True},
                    {
                        "movementKey": "d2_t2",
                        "label": "东直",
                        "dir8No": 2,
                        "turnDirNo": 2,
                        "turnFlowTotal": 700,
                        "laneCount": 3,
                        "saturation": 0.82,
                        "flow_available": True,
                        "source": "pg_turn_flow",
                    },
                ],
            },
            {
                "phase_stage_id": "2",
                "phase_stage_name": "东左、西左",
                "greenTime": 12,
                "minGreenTime": 12,
                "maxGreenTime": 40,
                "phaseDirInfoDTOList": [
                    {"dir8No": 2, "turnDirNo": 1, "turnFlowTotal": 300, "laneCount": 2, "flow_available": True},
                ],
            },
        ],
    }


def _base_args(signal):
    return dict(
        signal=signal,
        ticket={"direction": "东向西", "movement": "直行", "inter_id": "TEST01", "time_range": "18:00-18:30"},
        diagnosis={},
        strategy_instruction={"package": "downstream_protection"},
        constraints={"max_cycle_s": 160, "default_cycle_s": 130},
    )


def test_request_passes_current_timing_and_green_bounds():
    req = build_optimizer_request(**_base_args(_signal_with_binding()))
    stages = req["phasePlanOfTimeList"][0]["phaseStageInfoList"]
    assert len(stages) == 2
    s1 = stages[0]
    # 现状绿 + 真实最小绿透传（引擎据此避免回落默认 14s）
    assert s1["currentTiming"]["greenSec"] == 60
    assert s1["currentTiming"]["stageTotalSec"] == 65
    assert s1["greenBounds"]["minGreenS"] == 35
    assert s1["greenBounds"]["maxGreenS"] == 90
    assert s1["min_green_s"] == 35


def test_request_expands_multi_movement_and_uses_real_flow():
    req = build_optimizer_request(**_base_args(_signal_with_binding()))
    s1 = req["phasePlanOfTimeList"][0]["phaseStageInfoList"][0]
    dir_infos = s1["phaseDirInfoDTOList"]
    # 多转向阶段展开为两条真实转向
    assert len(dir_infos) == 2
    flows = sorted(d["turnFlowTotal"] for d in dir_infos)
    assert flows == [700.0, 850.0]
    # 无占位常量 500 / 写死车道 2
    assert all(d["turnFlowTotal"] != 500 for d in dir_infos)
    assert {d["laneCount"] for d in dir_infos} == {3}
    assert {d["dir8No"] for d in dir_infos} == {6, 2}
    east = next(d for d in dir_infos if d["dir8No"] == 2)
    assert east["movementKey"] == "d2_t2"
    assert east["label"] == "东直"
    assert east["saturation"] == 0.82
    assert east["flow_available"] is True
    assert east["source"] == "pg_turn_flow"


def test_request_skips_unlocatable_movement():
    signal = _signal_with_binding()
    signal["phase_stage_timing_list"][0]["phaseDirInfoDTOList"].append(
        {"dir8No": None, "turnDirNo": 2, "turnFlowTotal": 100}
    )
    req = build_optimizer_request(**_base_args(signal))
    s1 = req["phasePlanOfTimeList"][0]["phaseStageInfoList"][0]
    # 无法定位方向的转向不下发
    assert len(s1["phaseDirInfoDTOList"]) == 2


def test_request_includes_resolved_target_periods_and_plan_no():
    req = build_optimizer_request(**_base_args(_signal_with_binding()))
    assert req["target_periods"] == ["18:00-18:30"]
    assert req.get("planNo") == "1"
    assert req.get("obj_intensity") is not None
    assert req["meta"]["period_match_method"] is not None


def test_request_legacy_signal_without_binding_has_no_placeholder_500():
    signal = {
        "inter_id": "TEST01",
        "plan_no": "1",
        "phase_stage_timing_list": [
            {"phase_stage_id": "1", "phase_stage_name": "西直", "greenTime": 40, "minGreenTime": 15},
        ],
    }
    req = build_optimizer_request(**_base_args(signal))
    s1 = req["phasePlanOfTimeList"][0]["phaseStageInfoList"][0]
    info = s1["phaseDirInfoDTOList"][0]
    # 降级路径不再注入占位流量 500
    assert "turnFlowTotal" not in info or info["turnFlowTotal"] != 500
