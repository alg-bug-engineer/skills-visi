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
    run_single_point_optimizer=None,
) -> tuple[list[dict[str, Any]], str | None]:
    diagnosis = diagnosis or {}
    direction = ticket.get("direction", "东向西")
    downstream_name = (
        (diagnosis.get("downstream_diagnosis") or {}).get("primary_downstream", {}).get("inter_name")
        or "下游信控节点"
    )
    case_lessons = strategy.get("case_references") or {}

    candidates: list[dict[str, Any]] = []
    optimizer_engine: str | None = None
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

        timing_source = "adjust_phase_timing"
        optimizer_degraded_reason: str | None = None
        if run_single_point_optimizer is not None:
            optimized = run_single_point_optimizer(
                signal=signal,
                ticket=ticket,
                diagnosis=diagnosis,
                strategy_instruction=strategy_instruction,
                constraints=constraints,
            )
            if optimized.get("ok"):
                adjusted["timing"] = optimized["timing"]
                adjusted["cycle_s"] = optimized["cycle_s"]
                timing_source = optimized.get("engine") or "signal_optimization_engine"
                optimizer_engine = timing_source
            elif optimized.get("degraded"):
                # 优化输入缺失/结果塌缩：回退真实现状配时调整（adjust_phase_timing），
                # 不以退化占位配时冒充优化结果，并透传降级原因供审计。
                optimizer_degraded_reason = optimized.get("reason")
                adjusted["timing"] = _mark_timing_unavailable(
                    adjusted.get("timing") or {},
                    reason=optimizer_degraded_reason or "优化器结果退化，无法生产级展示",
                    missing_fields=optimized.get("missing_fields"),
                )

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
                "timing_source": timing_source,
                "optimizer_degraded": optimizer_degraded_reason is not None,
                "optimizer_degraded_reason": optimizer_degraded_reason,
            }
        )
    return candidates, optimizer_engine


def _mark_timing_unavailable(
    timing: dict[str, Any],
    *,
    reason: str,
    missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    fields = list(missing_fields or [])
    if "timing.meta.direction_intensity_list" not in fields:
        fields.append("timing.meta.direction_intensity_list")
    return {
        **timing,
        "available": False,
        "reason": reason,
        "missing_fields": fields,
    }


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
