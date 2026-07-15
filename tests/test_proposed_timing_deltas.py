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
