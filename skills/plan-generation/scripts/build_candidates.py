from __future__ import annotations

from typing import Any


PLAN_DEFINITIONS = [
    {
        "plan_id": "downstream_protection",
        "name": "下游保护方案",
        "scenario_template": "{downstream}承接不足，目标路口不宜继续强放",
        "risk": "目标进口排队缓解速度较慢，需配合上游控流",
        "expected_effect": "抑制向下游继续送车，避免外溢扩散",
        "execution_order": ["先保护下游", "维持目标方向保守放行", "持续监测排队比"],
    },
    {
        "plan_id": "incremental_release",
        "name": "目标路口小步释放方案",
        "scenario_template": "下游仍有部分承接空间，{direction}排队较高",
        "risk": "下游排队继续增长需立即回滚",
        "expected_effect": "小幅缓解目标进口排队，保留回滚空间",
        "execution_order": ["确认下游余量", "小步增加目标方向有效绿", "监测下游饱和度"],
    },
    {
        "plan_id": "arterial_coordination",
        "name": "干线联控方案",
        "scenario_template": "{downstream}接不住，上游持续来车，目标路口接近溢出",
        "risk": "上游控流幅度不能过大，否则可能造成上游新溢出",
        "expected_effect": "上游削峰+目标小步释放，降低干线传导风险",
        "execution_order": ["先保护下游", "再平滑上游来车", "最后小步释放目标方向"],
    },
]


def build_plan_candidates(
    strategy: dict[str, Any],
    ticket: dict[str, Any],
    diagnosis: dict[str, Any] | None,
    *,
    signal: dict[str, Any],
    constraints: dict[str, Any],
    generate_timing_plan,
    adjust_phase_timing,
    build_strategy_instruction,
    validate_plan_guardrails,
) -> list[dict[str, Any]]:
    diagnosis = diagnosis or {}
    direction = ticket.get("direction", "东向西")
    downstream_name = (
        (diagnosis.get("downstream_diagnosis") or {}).get("primary_downstream", {}).get("inter_name")
        or "下游信控节点"
    )
    case_lessons = strategy.get("case_references") or {}

    candidates: list[dict[str, Any]] = []
    for definition in PLAN_DEFINITIONS:
        plan_id = definition["plan_id"]
        strategy_instruction = build_strategy_instruction(strategy, plan_id)
        draft = generate_timing_plan(
            strategy_instruction,
            {"context": ticket, "constraints": constraints},
            signal,
            diagnosis,
        )
        adjusted = adjust_phase_timing(
            signal=signal,
            strategy_instruction=strategy_instruction,
            ticket=ticket,
            diagnosis=diagnosis,
        )
        if not adjusted.get("ok"):
            candidates.append(
                _rejected_candidate(
                    definition,
                    direction,
                    downstream_name,
                    errors=[adjusted.get("reason", "配时调整失败")],
                )
            )
            continue

        plan_body = {
            **draft,
            "plan_id": plan_id,
            "timing": adjusted["timing"],
            "cycle_s": adjusted["cycle_s"],
            "rollback_condition": strategy_instruction.get("rollback_condition") or draft["rollback_condition"],
            "upstream_control": adjusted["upstream_control"],
            "phase_offset_sec": adjusted.get("phase_offset_sec", 0),
            "pedestrian_constraints": adjusted["pedestrian_constraints"],
            "downstream_risk": adjusted["downstream_risk"],
        }
        validation_errors = validate_plan_guardrails(plan_body, constraints)
        guardrail_pass = len(validation_errors) == 0

        candidates.append(
            {
                "plan_id": plan_id,
                "name": definition["name"],
                "status": "valid" if guardrail_pass else "rejected",
                "scenario": definition["scenario_template"].format(
                    downstream=downstream_name,
                    direction=direction,
                ),
                "case_basis": {
                    "failure_lesson": case_lessons.get("failure_lesson"),
                    "success_lesson": case_lessons.get("success_lesson"),
                    "matched_count": case_lessons.get("matched_count", 0),
                },
                "timing": adjusted["timing"],
                "upstream_control": adjusted["upstream_control"],
                "phase_offset_sec": adjusted.get("phase_offset_sec", 0),
                "pedestrian_constraints": adjusted["pedestrian_constraints"],
                "downstream_risk": adjusted["downstream_risk"],
                "expected_effect": definition["expected_effect"],
                "risk": definition["risk"],
                "rollback_condition": plan_body["rollback_condition"],
                "validation_errors": validation_errors,
                "guardrail_pass": guardrail_pass,
                "execution_order": definition.get("execution_order"),
            }
        )
    return candidates


def _rejected_candidate(
    definition: dict[str, Any],
    direction: str,
    downstream_name: str,
    *,
    errors: list[str],
) -> dict[str, Any]:
    return {
        "plan_id": definition["plan_id"],
        "name": definition["name"],
        "status": "rejected",
        "scenario": definition["scenario_template"].format(
            downstream=downstream_name,
            direction=direction,
        ),
        "validation_errors": errors,
        "guardrail_pass": False,
    }
