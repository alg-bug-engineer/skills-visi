"""机制 → DecisionContract 确定性映射；方案候选只生成允许类型。"""

from pathlib import Path
import importlib.util

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


def test_case_a_verify_then_adjust_contract():
    decision = map_mechanism_to_decision(
        primary_mechanism="discharge_anomaly",
        verification_passed=False,
    )
    assert decision["decision_mode"] == "verify_then_adjust"
    assert decision["preconditions_satisfied"] is False
    assert decision["executable"] is False
    assert decision["plan_status"] == "conditional"
    assert "verification_plan" in decision["allowed_plan_types"]
    assert "conditional_incremental_release" in decision["allowed_plan_types"]
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
            "decision_mode": "verify_then_adjust",
            "allowed_plan_types": ["verification_plan", "conditional_incremental_release"],
            "forbidden_plan_types": ["downstream_protection", "arterial_coordination"],
            "preconditions_satisfied": False,
            "executable": False,
            "plan_status": "conditional",
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
    assert ids == {"verification_plan", "conditional_incremental_release"}
    assert "downstream_protection" not in ids
    assert "arterial_coordination" not in ids
    for c in candidates:
        assert c.get("executable") is False or c.get("plan_status") == "conditional"
        text = (c.get("scenario") or "") + (c.get("name") or "")
        assert "接不住" not in text
        assert "承接不足" not in text


def test_build_strategy_instruction_uses_plan_id_not_shared_package():
    adjust = _load_adjust()
    strategy = {"strategy_package": "incremental_release"}
    instr = adjust.build_strategy_instruction(strategy, "downstream_protection")
    assert instr["package"] == "downstream_protection"
    assert instr["strategy"] == "downstream_protection"
    assert instr["target_green_delta"] == -2
