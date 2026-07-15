"""拟实施借绿：实际绿差摘要 + 目标相位匹配失败显式降级。"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load():
    path = Path("skills/plan-generation/scripts/adjust_phase_timing.py")
    spec = importlib.util.spec_from_file_location("adjust_phase_timing", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unmatched_target_phase_fails_explicitly():
    mod = _load()
    result = mod.adjust_phase_timing(
        signal={
            "phase_stage_timing_list": [
                {
                    "phase_stage_name": "相位A",
                    "greenTime": 60,
                    "minGreenTime": 20,
                    "maxGreenTime": 90,
                    "yellowTime": 3,
                    "allRedTime": 2,
                },
                {
                    "phase_stage_name": "相位B",
                    "greenTime": 40,
                    "minGreenTime": 20,
                    "maxGreenTime": 90,
                    "yellowTime": 3,
                    "allRedTime": 2,
                },
            ]
        },
        strategy_instruction=mod.build_strategy_instruction({}, "conditional_incremental_release"),
        ticket={"direction": "北向南", "movement": "直行"},
    )
    assert result["ok"] is False
    assert "未找到目标相位" in str(result.get("reason") or "")


def test_borrow_summary_uses_actual_deltas_not_requested():
    mod = _load()
    # donor 仅能借 3s（min 边界），请求 +5 → 实际目标/借绿均为 ±3，周期 ±0
    result = mod.adjust_phase_timing(
        signal={
            "phase_stage_timing_list": [
                {
                    "phase_stage_name": "西直、东直",
                    "source_stage_atoms": ["西直", "东直"],
                    "greenTime": 23,
                    "minGreenTime": 20,
                    "maxGreenTime": 90,
                    "yellowTime": 3,
                    "allRedTime": 2,
                },
                {
                    "phase_stage_name": "北直",
                    "source_stage_atoms": ["北直"],
                    "greenTime": 30,
                    "minGreenTime": 14,
                    "maxGreenTime": 60,
                    "yellowTime": 3,
                    "allRedTime": 2,
                },
            ]
        },
        strategy_instruction=mod.build_strategy_instruction({}, "conditional_incremental_release"),
        ticket={"direction": "北向南", "movement": "直行"},
    )
    assert result["ok"] is True
    timing = result["timing"]
    assert timing["requested_target_green_delta_s"] == 5
    assert timing["target_green_delta_s"] == 3
    assert timing["donor_green_delta_s"] == -3
    assert timing["cycle_delta_s"] == 0
    attached = mod.attach_proposed_timing_fields(timing, requested_target_green_delta=5)
    assert attached["target_green_delta_s"] == 3
    assert attached["donor_green_delta_s"] == -3
    assert attached["cycle_delta_s"] == 0
    assert attached["requested_target_green_delta_s"] == 5


def test_trial_does_not_clamp_preexisting_donor_above_stale_max_green():
    mod = _load()
    result = mod.adjust_phase_timing(
        signal={
            "phase_stage_timing_list": [
                {
                    "phase_stage_id": "1",
                    "phase_stage_name": "西直、东直",
                    "source_stage_atoms": ["西直", "东直"],
                    "greenTime": 85,
                    "minGreenTime": 7,
                    "maxGreenTime": 60,  # PG 存量边界小于真实现状
                    "yellowTime": 3,
                    "allRedTime": 2,
                },
                {
                    "phase_stage_id": "3",
                    "phase_stage_name": "南直、北直、北左",
                    "source_stage_atoms": ["南直", "北直", "北左"],
                    "greenTime": 34,
                    "minGreenTime": 14,
                    "maxGreenTime": 60,
                    "yellowTime": 3,
                    "allRedTime": 2,
                },
            ]
        },
        strategy_instruction=mod.build_strategy_instruction({}, "conditional_incremental_release"),
        ticket={"direction": "北向南", "movement": "直行"},
    )

    assert result["ok"] is True
    timing = result["timing"]
    assert timing["target_green_delta_s"] == 5
    assert timing["donor_green_delta_s"] == -5
    assert timing["cycle_delta_s"] == 0
    stages = timing["phase_stage_timing_list"]
    assert stages[0]["current_timing"]["green_time_s"] == 85
    assert stages[0]["optimized_timing"]["green_time_s"] == 80


def test_pg_phase_dir_fields_are_kept_as_auditable_trial_evidence():
    mod = _load()
    result = mod.adjust_phase_timing(
        signal={
            "current_cycle_s": 90,
            "phase_stage_timing_list": [
                {
                    "phase_stage_id": "1",
                    "phase_stage_name": "东西直行",
                    "source_stage_atoms": ["东直", "西直"],
                    "greenTime": 45,
                    "minGreenTime": 20,
                    "maxGreenTime": 60,
                    "yellowTime": 3,
                    "allRedTime": 2,
                    "phaseDirInfoDTOList": [
                        {
                            "dir8No": 2,
                            "turnDirNo": 2,
                            "turnFlowTotal": 360,
                            "laneCount": 2,
                            "turnSaturation": 0.62,
                            "flow_available": True,
                        }
                    ],
                },
                {
                    "phase_stage_id": "2",
                    "phase_stage_name": "北直",
                    "source_stage_atoms": ["北直"],
                    "greenTime": 35,
                    "minGreenTime": 14,
                    "maxGreenTime": 60,
                    "yellowTime": 3,
                    "allRedTime": 2,
                    "phaseDirInfoDTOList": [
                        {
                            "dir8No": 0,
                            "turnDirNo": 2,
                            "turnFlowTotal": 420,
                            "laneCount": 2,
                            "turnSaturation": 0.79,
                            "flow_available": True,
                        }
                    ],
                },
            ],
        },
        strategy_instruction=mod.build_strategy_instruction({}, "conditional_incremental_release"),
        ticket={"direction": "北向南", "movement": "直行"},
    )

    assert result["ok"] is True
    timing = result["timing"]
    assert timing["available"] is True
    assert timing["phase_stage_timing_list"][0]["movements"][0]["movementKey"] == "d2_t2"
    assert timing["phase_stage_timing_list"][1]["movements"][0]["label"] == "北进口直行"
    intensity = timing["meta"]["direction_intensity_list"]
    assert {row["movementKey"]: row["intensity"] for row in intensity} == {
        "d2_t2": 0.62,
        "d0_t2": 0.79,
    }
    assert timing["meta"]["total_turn_flow_vph"] == 780
