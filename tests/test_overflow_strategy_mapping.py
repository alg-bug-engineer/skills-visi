"""机制 → DecisionContract 确定性映射；方案候选只生成允许类型。"""

from pathlib import Path
import importlib.util

import pytest

from app.decision.overflow_mechanism import map_mechanism_to_decision


def _load_build_candidates():
    path = Path("skills/plan-generation/scripts/build_candidates.py")
    spec = importlib.util.spec_from_file_location("build_candidates", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _load_adjust():
    path = Path("skills/plan-generation/scripts/adjust_phase_timing.py")
    spec = importlib.util.spec_from_file_location("adjust_phase_timing", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_case_a_discharge_anomaly_maps_to_monitored_trial():
    decision = map_mechanism_to_decision(
        primary_mechanism="discharge_anomaly",
        verification_passed=False,
    )
    assert decision["decision_mode"] == "incremental_release_trial"
    assert decision["preconditions_satisfied"] is True
    assert decision["executable"] is True
    assert decision["plan_status"] == "trial_ready"
    assert decision["max_stage_change_ratio"] == 0.2
    assert "conditional_incremental_release" in decision["allowed_plan_types"]
    assert "verification_plan" not in decision["allowed_plan_types"]
    assert "downstream_protection" in decision["forbidden_plan_types"]
    assert "arterial_coordination" in decision["forbidden_plan_types"]


def test_discharge_anomaly_after_verification_allows_trial():
    decision = map_mechanism_to_decision(
        primary_mechanism="discharge_anomaly",
        verification_passed=True,
    )
    assert decision["decision_mode"] == "incremental_release_trial"
    assert decision["preconditions_satisfied"] is True
    assert "incremental_release" in decision["allowed_plan_types"] or (
        "conditional_incremental_release" in decision["allowed_plan_types"]
    )


def test_downstream_blocked_maps_to_protection():
    decision = map_mechanism_to_decision(primary_mechanism="downstream_blocked")
    assert decision["decision_mode"] == "downstream_protection"
    assert "downstream_protection" in decision["allowed_plan_types"]
    assert "incremental_release" not in decision["allowed_plan_types"]


def test_build_candidates_respects_allowed_plan_types():
    build = _load_build_candidates()
    adjust = _load_adjust()

    def generate_timing_plan(instruction, ctx, signal, diagnosis):
        return {
            "rollback_condition": instruction.get("rollback_condition", "rollback"),
            "timing": {},
        }

    def adjust_phase_timing(**kwargs):
        return {
            "ok": True,
            "timing": {"cycle_s": 90, "phase_stage_timing_list": []},
            "cycle_s": 90,
            "upstream_control": {"enabled": False},
            "phase_offset_sec": 0,
            "pedestrian_constraints": {"satisfied": True, "violations": []},
            "downstream_risk": {},
        }

    def validate_plan_guardrails(plan, constraints):
        return []

    strategy = {
        "strategy_package": "incremental_release",
        "decision": {
            "decision_mode": "incremental_release_trial",
            "allowed_plan_types": ["conditional_incremental_release"],
            "forbidden_plan_types": ["downstream_protection", "arterial_coordination"],
            "preconditions_satisfied": True,
            "executable": True,
            "plan_status": "trial_ready",
        },
        "case_references": {},
    }
    candidates, _ = build.build_plan_candidates(
        strategy,
        {"direction": "北向南", "movement": "直行"},
        {"downstream_diagnosis": {"primary_downstream": {"inter_name": "永绥路与齐音路路口"}}},
        signal={"phase_stage_timing_list": [{"greenTime": 30}], "cycle_s": 90},
        constraints={"max_cycle_s": 180},
        generate_timing_plan=generate_timing_plan,
        adjust_phase_timing=adjust_phase_timing,
        build_strategy_instruction=adjust.build_strategy_instruction,
        validate_plan_guardrails=validate_plan_guardrails,
    )
    ids = {c["plan_id"] for c in candidates}
    assert ids == {"conditional_incremental_release"}
    assert "downstream_protection" not in ids
    assert "arterial_coordination" not in ids
    for c in candidates:
        assert c.get("executable") is True
        assert c.get("plan_status") == "trial_ready"
        text = (c.get("scenario") or "") + (c.get("name") or "")
        assert "接不住" not in text
        assert "承接不足" not in text


@pytest.mark.parametrize("decision_mode", ["incremental_release", "incremental_release_trial"])
def test_incremental_release_never_uses_global_optimizer(decision_mode):
    """任何 incremental_release 都是 +5s 微调，不得被全局优化器改写。"""
    build = _load_build_candidates()
    adjust = _load_adjust()
    optimizer_calls = 0

    def generate_timing_plan(instruction, ctx, signal, diagnosis):
        return {"rollback_condition": "异常时回滚", "timing": {}}

    def fake_optimizer(**kwargs):
        nonlocal optimizer_calls
        optimizer_calls += 1
        return {
            "ok": True,
            "engine": "signal_optimization_engine",
            "cycle_s": 150,
            "timing": {
                "current_cycle_s": 150,
                "cycle_s": 150,
                "phase_stage_timing_list": [
                    {"phase_stage_id": "target", "green_time_s": 65, "green_delta_s": 25},
                    {"phase_stage_id": "donor", "green_time_s": 75, "green_delta_s": -20},
                ],
            },
        }

    strategy = {
        "strategy_package": "incremental_release",
        "strategy_instruction": {"target_green_delta": 5, "cycle_delta": 0},
        "decision": {
            "decision_mode": decision_mode,
            "allowed_plan_types": ["incremental_release"],
            "preconditions_satisfied": True,
            "executable": True,
            "plan_status": "trial_ready",
            "max_stage_change_ratio": 0.2,
        },
        "case_references": {},
    }
    signal = {
        "current_cycle_s": 135,
        "cycle_s": 135,
        "phase_stage_timing_list": [
            {
                "phase_stage_id": "target",
                "phase_stage_name": "北直",
                "source_stage_atoms": ["北直"],
                "greenTime": 40,
                "minGreenTime": 14,
                "maxGreenTime": 70,
                "yellowTime": 3,
                "allRedTime": 2,
                "phaseDirInfoDTOList": [{"dir8No": 0, "turnDirNo": 2}],
            },
            {
                "phase_stage_id": "donor",
                "phase_stage_name": "东西直行",
                "source_stage_atoms": ["东直", "西直"],
                "greenTime": 85,
                "minGreenTime": 30,
                "maxGreenTime": 60,  # 复现真实 PG 存量绿灯高于历史 max
                "yellowTime": 3,
                "allRedTime": 2,
                "phaseDirInfoDTOList": [{"dir8No": 2, "turnDirNo": 2}],
            },
        ],
    }

    def load_script(name):
        path = Path("skills/plan-generation/scripts") / name
        spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module

    guard = load_script("validate_plan_guardrails.py")
    semantic = load_script("validate_overflow_plan.py")

    candidates, optimizer_engine = build.build_plan_candidates(
        strategy,
        {"direction": "北向南", "movement": "直行", "dir8_code": 0, "turn_dir_no": 2},
        {"downstream_state": {"decision": "slack"}},
        signal=signal,
        constraints={"max_cycle_s": 180},
        generate_timing_plan=generate_timing_plan,
        adjust_phase_timing=adjust.adjust_phase_timing,
        build_strategy_instruction=adjust.build_strategy_instruction,
        validate_plan_guardrails=guard.validate_plan_guardrails,
        run_single_point_optimizer=fake_optimizer,
        validate_overflow_plan=semantic.validate_overflow_plan,
        build_plan_contract=semantic.build_plan_contract_from_strategy,
    )

    assert optimizer_calls == 0
    assert optimizer_engine is None
    assert len(candidates) == 1
    timing = candidates[0]["timing"]
    assert timing["target_green_delta_s"] == 5
    assert timing["donor_green_delta_s"] == -5
    assert timing["cycle_delta_s"] == 0
    assert candidates[0]["timing_source"] == "adjust_phase_timing"
    assert candidates[0]["guardrail_pass"] is True
    assert candidates[0]["executable"] is True
    assert candidates[0]["plan_status"] == "trial_ready"
    assert candidates[0]["validation_errors"] == []


def test_evidence_insufficient_candidate_has_baseline_only_without_proposed_plus_five():
    build = _load_build_candidates()
    adjust = _load_adjust()

    def generate_timing_plan(instruction, ctx, signal, diagnosis):
        return {"rollback_condition": "保持现状", "timing": {}}

    def adjust_phase_timing(**kwargs):
        return {
            "ok": True,
            "timing": {
                "current_cycle_s": 120,
                "cycle_s": 120,
                "phase_stage_timing_list": [
                    {
                        "phase_stage_id": "1",
                        "phase_stage_name": "北直",
                        "green_time_s": 30,
                        "current_timing": {"green_time_s": 30},
                        "optimized_timing": {"green_time_s": 30},
                        "green_delta_s": 0,
                    }
                ],
            },
            "cycle_s": 120,
            "upstream_control": {"enabled": False},
            "phase_offset_sec": 0,
            "pedestrian_constraints": {"satisfied": True, "violations": []},
            "downstream_risk": {},
        }

    strategy = {
        "strategy_package": "verification_plan",
        "decision": {
            "decision_mode": "verification_required",
            "allowed_plan_types": ["verification_plan"],
            "forbidden_plan_types": ["conditional_incremental_release", "incremental_release"],
            "preconditions_satisfied": False,
            "executable": False,
            "plan_status": "requires_verification",
        },
        "case_references": {},
    }
    candidates, _ = build.build_plan_candidates(
        strategy,
        {"direction": "南向北", "movement": "直行"},
        {"overflow_mechanism": {"primary": "evidence_insufficient"}},
        signal={"current_cycle_s": 120, "cycle_s": 120},
        constraints={"max_cycle_s": 180},
        generate_timing_plan=generate_timing_plan,
        adjust_phase_timing=adjust_phase_timing,
        build_strategy_instruction=adjust.build_strategy_instruction,
        validate_plan_guardrails=lambda plan, constraints: [],
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["plan_id"] == "verification_plan"
    assert candidate["executable"] is False
    assert candidate["timing"]["verification_baseline"] is True
    assert "proposed_timing" not in candidate


def test_build_strategy_instruction_uses_plan_id_not_shared_package():
    adjust = _load_adjust()
    strategy = {"strategy_package": "incremental_release"}
    instr = adjust.build_strategy_instruction(strategy, "downstream_protection")
    assert instr["package"] == "downstream_protection"
    assert instr["strategy"] == "downstream_protection"
    assert instr["target_green_delta"] == -2
