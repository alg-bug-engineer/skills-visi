"""方案语义护栏：目标有效绿净变化、周期与条件性可执行。"""

from pathlib import Path
import importlib.util


def _load(name: str):
    path = Path("skills/plan-generation/scripts") / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_effective_green_sums_overlapping_stages():
    eg = _load("effective_green.py")
    before = [
        {
            "phase_stage_id": "s3",
            "green_time_s": 20,
            "movements": [{"dir8_code": 0, "turn_dir_no": 2}],
        },
        {
            "phase_stage_id": "s8",
            "green_time_s": 15,
            "movements": [{"dir8_code": 0, "turn_dir_no": 2}, {"dir8_code": 4, "turn_dir_no": 2}],
        },
        {
            "phase_stage_id": "s1",
            "green_time_s": 30,
            "movements": [{"dir8_code": 2, "turn_dir_no": 1}],
        },
    ]
    after = [
        {**before[0], "green_time_s": 26},
        {**before[1], "green_time_s": 2},  # 故意大幅减少搭接阶段
        before[2],
    ]
    # before 20+15=35, after 26+2=28 → 净减 7
    delta = eg.compute_target_effective_green_delta(
        before_stages=before,
        after_stages=after,
        movement_key="d0_t2",
    )
    assert delta["before_s"] == 35
    assert delta["after_s"] == 28
    assert delta["delta_s"] == -7


def test_validate_rejects_net_negative_when_contract_requires_plus_five():
    v = _load("validate_overflow_plan.py")
    before = [
        {"green_time_s": 20, "movements": [{"dir8_code": 0, "turn_dir_no": 2}]},
        {"green_time_s": 15, "movements": [{"dir8_code": 0, "turn_dir_no": 2}]},
    ]
    after = [
        {"green_time_s": 26, "movements": [{"dir8_code": 0, "turn_dir_no": 2}]},
        {"green_time_s": 2, "movements": [{"dir8_code": 0, "turn_dir_no": 2}]},
    ]
    errors = v.validate_overflow_plan(
        candidate={
            "plan_id": "incremental_release",
            "name": "小步释放",
            "scenario": "增绿试验",
            "timing": {"cycle_s": 100, "phase_stage_timing_list": after},
            "cycle_s": 100,
            "executable": True,
            "plan_status": "trial_ready",
        },
        baseline_signal={
            "cycle_s": 100,
            "phase_stage_timing_list": before,
        },
        decision={
            "decision_mode": "incremental_release_trial",
            "allowed_plan_types": ["incremental_release"],
            "preconditions_satisfied": True,
            "executable": True,
            "plan_status": "trial_ready",
        },
        plan_contract={
            "target_movement_key": "d0_t2",
            "target_effective_green_delta_s": 5,
            "cycle_delta_s": 0,
            "max_stage_change_ratio": 0.5,
        },
        diagnosis={"downstream_state": {"decision": "slack"}},
        ticket={"dir8_code": 0, "turn_dir_no": 2},
    )
    assert any("有效绿" in e for e in errors)


def test_validate_rejects_plus_twenty_five_when_contract_requires_plus_five():
    """策略的 +5s 是双向定量契约，不能只当作最低增绿量。"""
    v = _load("validate_overflow_plan.py")
    before = [
        {"phase_stage_id": "target", "green_time_s": 40, "movements": [{"dir8_code": 0, "turn_dir_no": 2}]},
        {"phase_stage_id": "donor", "green_time_s": 100, "movements": [{"dir8_code": 2, "turn_dir_no": 1}]},
    ]
    after = [
        {**before[0], "green_time_s": 65},
        {**before[1], "green_time_s": 75},
    ]

    errors = v.validate_overflow_plan(
        candidate={
            "plan_id": "incremental_release",
            "name": "小步增绿试运行方案",
            "scenario": "目标方向小步增绿",
            "timing": {"current_cycle_s": 150, "cycle_s": 150, "phase_stage_timing_list": after},
            "cycle_s": 150,
            "executable": True,
            "plan_status": "trial_ready",
        },
        baseline_signal={"cycle_s": 150, "phase_stage_timing_list": before},
        decision={
            "decision_mode": "incremental_release_trial",
            "allowed_plan_types": ["incremental_release"],
            "preconditions_satisfied": True,
            "executable": True,
            "plan_status": "trial_ready",
        },
        plan_contract={
            "target_movement_key": "d0_t2",
            "target_effective_green_delta_s": 5,
            "cycle_delta_s": 0,
            "max_stage_change_ratio": 1.0,
        },
        diagnosis={"downstream_state": {"decision": "slack"}},
        ticket={"dir8_code": 0, "turn_dir_no": 2},
    )

    assert any("期望 +5s" in e and "实际 +25.0s" in e for e in errors)


def test_validate_accepts_case_a_plus_five_cycle_unchanged():
    v = _load("validate_overflow_plan.py")
    before = [
        {"phase_stage_id": "a", "green_time_s": 20, "movements": [{"dir8_code": 0, "turn_dir_no": 2}]},
        {"phase_stage_id": "b", "green_time_s": 15, "movements": [{"dir8_code": 0, "turn_dir_no": 2}]},
        {"phase_stage_id": "c", "green_time_s": 40, "greenTime": 40, "minGreenTime": 10, "movements": [{"dir8_code": 2, "turn_dir_no": 1}]},
    ]
    after = [
        {**before[0], "green_time_s": 23},
        {**before[1], "green_time_s": 17},
        {**before[2], "green_time_s": 35, "greenTime": 35},
    ]
    errors = v.validate_overflow_plan(
        candidate={
            "plan_id": "conditional_incremental_release",
            "name": "条件性小步增绿方案",
            "scenario": "核验后北向南直行小步增绿；监测永绥路与齐音路路口",
            "timing": {"cycle_s": 90, "phase_stage_timing_list": after},
            "cycle_s": 90,
            "executable": False,
            "plan_status": "conditional",
        },
        baseline_signal={"cycle_s": 90, "phase_stage_timing_list": before},
        decision={
            "decision_mode": "verify_then_adjust",
            "allowed_plan_types": ["verification_plan", "conditional_incremental_release"],
            "preconditions_satisfied": False,
            "executable": False,
            "plan_status": "conditional",
        },
        plan_contract={
            "target_movement_key": "d0_t2",
            "target_effective_green_delta_s": 5,
            "cycle_delta_s": 0,
            "max_stage_change_ratio": 0.2,
            "direct_downstream_inter_id": "011wwe28f5f00001",
        },
        diagnosis={
            "downstream_state": {
                "decision": "slack",
                "direct_downstream_inter_id": "011wwe28f5f00001",
                "direct_downstream_inter_name": "永绥路与齐音路路口",
            }
        },
        ticket={"dir8_code": 0, "turn_dir_no": 2, "direction": "北向南", "movement": "直行"},
    )
    assert errors == []


def test_validate_rejects_executable_without_verification():
    v = _load("validate_overflow_plan.py")
    errors = v.validate_overflow_plan(
        candidate={
            "plan_id": "conditional_incremental_release",
            "name": "条件性方案",
            "scenario": "先验后调",
            "timing": {"cycle_s": 90, "phase_stage_timing_list": []},
            "cycle_s": 90,
            "executable": True,
            "plan_status": "trial_ready",
        },
        baseline_signal={"cycle_s": 90, "phase_stage_timing_list": []},
        decision={
            "decision_mode": "verify_then_adjust",
            "preconditions_satisfied": False,
            "executable": False,
            "plan_status": "conditional",
            "allowed_plan_types": ["conditional_incremental_release"],
        },
        plan_contract={"target_movement_key": "d0_t2", "skip_timing_check": True},
        diagnosis={"downstream_state": {"decision": "slack"}},
        ticket={"dir8_code": 0, "turn_dir_no": 2},
    )
    assert any("可执行" in e or "executable" in e.lower() or "核验" in e for e in errors)


def test_validate_rejects_slack_with_接不住_scenario():
    v = _load("validate_overflow_plan.py")
    errors = v.validate_overflow_plan(
        candidate={
            "plan_id": "downstream_protection",
            "name": "下游保护",
            "scenario": "永绥路与齐音路路口接不住",
            "timing": {"cycle_s": 90, "phase_stage_timing_list": []},
            "cycle_s": 90,
            "executable": False,
            "plan_status": "conditional",
        },
        baseline_signal={"cycle_s": 90, "phase_stage_timing_list": []},
        decision={
            "decision_mode": "verify_then_adjust",
            "preconditions_satisfied": False,
            "executable": False,
            "allowed_plan_types": ["downstream_protection"],
        },
        plan_contract={"skip_timing_check": True},
        diagnosis={"downstream_state": {"decision": "slack"}},
        ticket={},
    )
    assert any("接不住" in e or "承接" in e or "下游" in e for e in errors)
