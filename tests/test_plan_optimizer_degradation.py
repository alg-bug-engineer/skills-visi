"""方案优化退化护栏与真实现状配时回退测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load(rel: str):
    path = PROJECT_ROOT / rel
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_degradation_reason_when_flow_binding_failed():
    mod = _load("skills/plan-generation/scripts/run_single_point_optimizer.py")
    signal = {"flow_binding": {"ok": False, "reason": "目标时段无可绑定的真实转向流量"}}
    reason = mod._degradation_reason(signal, {}, [{"phase_saturation": 0.8}], 120)
    assert reason == "目标时段无可绑定的真实转向流量"


def test_degradation_reason_when_zero_total_flow():
    mod = _load("skills/plan-generation/scripts/run_single_point_optimizer.py")
    signal = {"flow_binding": {"ok": True}}
    reason = mod._degradation_reason(
        signal, {"total_turn_flow_vph": 0}, [{"phase_saturation": None}], 42
    )
    assert reason and "无真实转向流量" in reason


def test_degradation_reason_when_no_saturation():
    mod = _load("skills/plan-generation/scripts/run_single_point_optimizer.py")
    signal = {"flow_binding": {"ok": True}}
    reason = mod._degradation_reason(
        signal, {"total_turn_flow_vph": 1500}, [{"phase_saturation": None}, {"phase_saturation": None}], 42
    )
    assert reason and "饱和度" in reason


def test_no_degradation_for_healthy_result():
    mod = _load("skills/plan-generation/scripts/run_single_point_optimizer.py")
    signal = {"flow_binding": {"ok": True}}
    reason = mod._degradation_reason(
        signal,
        {"total_turn_flow_vph": 1800, "max_phase_saturation": 0.82},
        [{"phase_saturation": 0.8}, {"phase_saturation": 0.7}],
        124,
    )
    assert reason is None


def _base_signal() -> dict:
    return {
        "inter_id": "T1",
        "plan_no": "1",
        "current_cycle_s": 130,
        "phase_stage_timing_list": [
            {"phase_stage_id": "1", "phase_stage_name": "西直", "greenTime": 60, "minGreenTime": 35, "maxGreenTime": 90},
            {"phase_stage_id": "2", "phase_stage_name": "东左", "greenTime": 12, "minGreenTime": 12, "maxGreenTime": 40},
        ],
        "flow_binding": {"ok": True, "unbound_stages": []},
    }


def test_build_candidates_falls_back_to_real_current_timing_when_degraded():
    build = _load("skills/plan-generation/scripts/build_candidates.py")
    timing = _load("skills/plan-generation/scripts/generate_timing_plan.py")
    adjust = _load("skills/plan-generation/scripts/adjust_phase_timing.py")
    guardrail = _load("skills/plan-generation/scripts/validate_plan_guardrails.py")

    def degraded_optimizer(**kwargs):
        return {"ok": False, "degraded": True, "reason": "优化输入无真实转向流量"}

    candidates, optimizer_engine = build.build_plan_candidates(
        {"strategy_package": "downstream_protection", "case_references": {}},
        {"direction": "东向西", "movement": "直行", "intersection_name": "T1"},
        {},
        signal=_base_signal(),
        constraints={"max_cycle_s": 160},
        generate_timing_plan=timing.generate_timing_plan,
        adjust_phase_timing=adjust.adjust_phase_timing,
        build_strategy_instruction=adjust.build_strategy_instruction,
        validate_plan_guardrails=guardrail.validate_plan_guardrails,
        run_single_point_optimizer=degraded_optimizer,
    )
    assert optimizer_engine is None
    for cand in candidates:
        if cand.get("status") == "rejected" and not cand.get("timing"):
            continue
        # 退化时回退真实现状配时调整，而非塌缩占位
        assert cand["timing_source"] == "adjust_phase_timing"
        assert cand["optimizer_degraded"] is True
        assert cand["optimizer_degraded_reason"] == "优化输入无真实转向流量"
        assert cand["timing"]["available"] is False
        assert cand["timing"]["reason"] == "优化输入无真实转向流量"
        assert "timing.meta.direction_intensity_list" in cand["timing"]["missing_fields"]
        # 基于现状 130s 周期，不会塌缩到 42s
        assert cand["timing"]["cycle_s"] > 60
