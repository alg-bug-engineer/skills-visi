"""顶层业务完成状态机（不等于 artifacts 齐全）。"""

from app.runtime.overflow_completion import derive_completion_status, build_trial_loop


def test_healthy_is_no_action():
    assert (
        derive_completion_status(
            completed=True,
            healthy=True,
            decision=None,
            plan=None,
        )
        == "completed_no_action"
    )


def test_failed_when_not_completed():
    assert (
        derive_completion_status(
            completed=False,
            healthy=False,
            decision={"decision_mode": "verify_then_adjust"},
            plan={},
        )
        == "failed"
    )


def test_case_a_conditional():
    assert (
        derive_completion_status(
            completed=True,
            healthy=False,
            decision={
                "decision_mode": "verify_then_adjust",
                "plan_status": "conditional",
                "executable": False,
            },
            plan={
                "recommended": {
                    "plan_id": "verification_plan",
                    "plan_status": "conditional",
                    "executable": False,
                }
            },
        )
        == "completed_conditional"
    )


def test_requires_verification():
    assert (
        derive_completion_status(
            completed=True,
            healthy=False,
            decision={
                "decision_mode": "verification_required",
                "plan_status": "requires_verification",
                "executable": False,
            },
            plan={"recommended": {"plan_id": "verification_plan"}},
        )
        == "completed_requires_verification"
    )


def test_trial_ready():
    assert (
        derive_completion_status(
            completed=True,
            healthy=False,
            decision={
                "decision_mode": "incremental_release_trial",
                "plan_status": "trial_ready",
                "executable": True,
            },
            plan={
                "recommended": {
                    "plan_id": "incremental_release",
                    "plan_status": "trial_ready",
                    "executable": True,
                }
            },
        )
        == "completed_with_trial_plan"
    )


def test_build_trial_loop_case_a():
    loop = build_trial_loop(
        decision={
            "decision_mode": "verify_then_adjust",
            "plan_status": "conditional",
            "executable": False,
            "preconditions_satisfied": False,
        },
        diagnosis={
            "downstream_state": {
                "decision": "slack",
                "direct_downstream_inter_id": "011wwe28f5f00001",
                "direct_downstream_inter_name": "永绥路与齐音路路口",
            },
            "overflow_mechanism": {"primary": "discharge_anomaly"},
        },
        recommended={
            "plan_id": "conditional_incremental_release",
            "rollback_condition": "下游排队比持续上升时回滚",
            "plan_contract": {
                "target_effective_green_delta_s": 5,
                "cycle_delta_s": 0,
                "max_stage_change_ratio": 0.15,
            },
        },
        ticket={"dir8_code": 0, "turn_dir_no": 2, "direction": "北向南", "movement": "直行"},
    )
    assert loop["plan_status"] == "conditional"
    assert loop["executable"] is False
    assert loop["observation_cycles"] == 5
    assert "目标进口排队比" in loop["monitoring_metrics"]
    assert any("下游" in r for r in loop["rollback_rules"])
    assert loop["direct_downstream_inter_name"] == "永绥路与齐音路路口"
    assert loop["preconditions"]
