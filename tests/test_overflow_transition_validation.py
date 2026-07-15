"""阶段转换校验：对象/下游/机制/决策/可执行不得漂移或冲突。"""

from app.domain.overflow_case_state import OverflowCaseState, seed_overflow_state_from_artifacts
from app.runtime.overflow_transition_validation import validate_overflow_transition
from app.runtime.skill_types import SkillContext


def _base_context(**artifact_updates):
    artifacts = {
        "intent_understanding": {
            "diagnosis_ticket": {
                "inter_id": "011wwe28f7c00001",
                "intersection_name": "解放东路与齐川路路口",
                "direction": "北向南",
                "movement": "直行",
                "dir8_code": 0,
                "turn_dir_no": 2,
            }
        },
        "data_analysis_diagnosis": {
            "downstream_state": {
                "decision": "slack",
                "direct_downstream_inter_id": "011wwe28f5f00001",
                "direct_downstream_inter_name": "永绥路与齐音路路口",
            },
            "overflow_mechanism": {
                "primary": "discharge_anomaly",
                "status": "hypothesis",
            },
            "target": {
                "dir8_code": 0,
                "turn_dir_no": 2,
            },
        },
    }
    artifacts.update(artifact_updates)
    ctx = SkillContext(trace_id="t1", user_input="x", task={}, artifacts=artifacts)
    ctx.overflow_state = seed_overflow_state_from_artifacts(artifacts)
    return ctx


def test_seed_case_a_state():
    ctx = _base_context()
    assert isinstance(ctx.overflow_state, OverflowCaseState)
    assert ctx.overflow_state.identity["inter_id"] == "011wwe28f7c00001"
    assert ctx.overflow_state.downstream_state["decision"] == "slack"
    assert ctx.overflow_state.mechanism["primary"] == "discharge_anomaly"


def test_rejects_mechanism_rewrite_in_cause_stage():
    ctx = _base_context()
    bad = {
        "cause_analysis": {"primary_cause": "下游接不住"},
        "overflow_mechanism": {"primary": "downstream_blocked"},  # 改机制
    }
    errors = validate_overflow_transition(context=ctx, skill_id="cause_analysis", output=bad)
    assert any("机制" in e for e in errors)


def test_rejects_strategy_decision_mismatch():
    ctx = _base_context()
    errors = validate_overflow_transition(
        context=ctx,
        skill_id="strategy_generation",
        output={
            "decision": {
                "decision_mode": "downstream_protection",
                "allowed_plan_types": ["downstream_protection"],
                "executable": True,
                "strategy_package": "downstream_protection",
            },
            "strategy_package": "downstream_protection",
        },
    )
    assert any("决策" in e or "机制" in e for e in errors)


def test_rejects_executable_plan_under_verify_then_adjust():
    ctx = _base_context()
    # 先写入正确决策
    ctx.overflow_state.decision = {
        "decision_mode": "verify_then_adjust",
        "allowed_plan_types": ["verification_plan", "conditional_incremental_release"],
        "preconditions_satisfied": False,
        "executable": False,
        "plan_status": "conditional",
        "strategy_package": "incremental_release",
    }
    errors = validate_overflow_transition(
        context=ctx,
        skill_id="plan_generation",
        output={
            "recommended": {
                "plan_id": "conditional_incremental_release",
                "executable": True,
                "plan_status": "trial_ready",
                "guardrail_pass": True,
            },
            "candidates": [
                {
                    "plan_id": "conditional_incremental_release",
                    "executable": True,
                    "guardrail_pass": True,
                }
            ],
        },
    )
    assert any("可执行" in e or "executable" in e.lower() or "核验" in e for e in errors)


def test_accepts_consistent_verify_then_adjust_chain():
    ctx = _base_context()
    ok_strategy = validate_overflow_transition(
        context=ctx,
        skill_id="strategy_generation",
        output={
            "decision": {
                "decision_mode": "verify_then_adjust",
                "allowed_plan_types": ["verification_plan", "conditional_incremental_release"],
                "preconditions_satisfied": False,
                "executable": False,
                "plan_status": "conditional",
                "strategy_package": "incremental_release",
            },
            "strategy_package": "incremental_release",
        },
    )
    assert ok_strategy == []
    ok_plan = validate_overflow_transition(
        context=ctx,
        skill_id="plan_generation",
        output={
            "recommended": {
                "plan_id": "verification_plan",
                "executable": False,
                "plan_status": "conditional",
                "guardrail_pass": True,
            },
            "candidates": [
                {"plan_id": "verification_plan", "executable": False, "guardrail_pass": True},
                {
                    "plan_id": "conditional_incremental_release",
                    "executable": False,
                    "plan_status": "conditional",
                    "guardrail_pass": True,
                },
            ],
        },
    )
    assert ok_plan == []
