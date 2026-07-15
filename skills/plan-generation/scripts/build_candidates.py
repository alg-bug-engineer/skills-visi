from __future__ import annotations

from typing import Any


PLAN_DEFINITIONS = [
    {
        "plan_id": "downstream_protection",
        "name": "下游保护方案",
        "scenario_template": "{downstream}承接空间不足，目标路口不宜继续强放",
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
        "scenario_template": "上游持续来车且目标接近溢出，与{downstream}协同控流",
        "risk": "上游控流幅度不能过大，否则可能造成上游新溢出",
        "expected_effect": "上游削峰+目标小步释放，降低干线传导风险",
        "execution_order": ["先保护下游", "再平滑上游来车", "最后小步释放目标方向"],
    },
    {
        "plan_id": "verification_plan",
        "name": "先验核验方案",
        "scenario_template": "{direction}放行效率异常待核验；直接下游{downstream}初步有余量",
        "risk": "核验未完成前不得实施可执行配时",
        "expected_effect": "确认绿灯末端队列、出口通行与检测有效性后再决策",
        "execution_order": ["出口与检测核验", "绿灯末端队列核验", "再决定是否小步增绿"],
    },
    {
        "plan_id": "conditional_incremental_release",
        "name": "条件性小步增绿方案",
        "scenario_template": "在完成核验后，对{direction}试行小步增绿；监测{downstream}",
        "risk": "核验未通过或下游排队增长时立即回滚",
        "expected_effect": "条件满足后小幅缓解目标进口排队",
        "execution_order": ["确认核验前提", "目标有效绿小步增加", "观察周期并准备回滚"],
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
    validate_overflow_plan=None,
    build_plan_contract=None,
    pg_raw: dict[str, Any] | None = None,
    day_of_week: int | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    diagnosis = diagnosis or {}
    direction = ticket.get("direction", "东向西")
    downstream_name = (
        (diagnosis.get("downstream_diagnosis") or {}).get("primary_downstream", {}).get("inter_name")
        or (diagnosis.get("downstream_state") or {}).get("direct_downstream_inter_name")
        or "下游信控节点"
    )
    case_lessons = strategy.get("case_references") or {}
    decision = strategy.get("decision") if isinstance(strategy.get("decision"), dict) else {}
    plan_contract = {}
    if build_plan_contract is not None:
        plan_contract = build_plan_contract(strategy, ticket) or {}
    elif decision:
        # 最小契约：便于语义校验
        instr = strategy.get("strategy_instruction") or {}
        plan_contract = {
            "target_movement_key": (
                f"d{ticket['dir8_code']}_t{ticket['turn_dir_no']}"
                if ticket.get("dir8_code") is not None and ticket.get("turn_dir_no") is not None
                else None
            ),
            "target_effective_green_delta_s": instr.get("target_green_delta"),
            "cycle_delta_s": instr.get("cycle_delta", 0),
            "max_stage_change_ratio": decision.get("max_stage_change_ratio", 0.15),
        }
    allowed_plan_types = decision.get("allowed_plan_types")
    if allowed_plan_types:
        allowed_set = {str(x) for x in allowed_plan_types}
        definitions = [d for d in PLAN_DEFINITIONS if d["plan_id"] in allowed_set]
    else:
        # 无 DecisionContract 时保持历史三包，避免打断既有护栏回归
        definitions = [
            d
            for d in PLAN_DEFINITIONS
            if d["plan_id"] in {"downstream_protection", "incremental_release", "arterial_coordination"}
        ]

    plan_status = decision.get("plan_status")
    executable = decision.get("executable")
    if plan_status is None and not decision:
        plan_status = None
        executable = None

    candidates: list[dict[str, Any]] = []
    optimizer_engine: str | None = None
    for definition in definitions:
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
        if plan_id != "verification_plan" and run_single_point_optimizer is not None:
            optimized = run_single_point_optimizer(
                signal=signal,
                ticket=ticket,
                diagnosis=diagnosis,
                strategy_instruction=strategy_instruction,
                constraints=constraints,
                pg_raw=pg_raw,
                day_of_week=day_of_week,
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

        proposed_timing: dict[str, Any] | None = None
        if plan_id == "verification_plan":
            # 现状门控外，另挂一门控后拟实施借绿预览（绿差读实际计算结果，禁止用 instruction 盖写）
            trial_instr = build_strategy_instruction(strategy, "conditional_incremental_release")
            trial = adjust_phase_timing(
                signal=signal,
                strategy_instruction=trial_instr,
                ticket=ticket,
                diagnosis=diagnosis,
            )
            if trial.get("ok"):
                timing_body = dict(trial.get("timing") or {})
                proposed_timing = {
                    **timing_body,
                    "available": True,
                    "gate": "verification_passed",
                    "label": "门控通过后拟实施",
                    "requested_target_green_delta_s": int(trial_instr.get("target_green_delta") or 5),
                }
            else:
                proposed_timing = {
                    "available": False,
                    "gate": "verification_passed",
                    "label": "门控通过后拟实施",
                    "reason": trial.get("reason") or "未能生成拟实施借绿配时",
                    "target_green_delta_s": 0,
                    "donor_green_delta_s": 0,
                    "cycle_delta_s": 0,
                }
            timing_source = "baseline_no_change"
            adjusted["timing"] = _mark_verification_baseline_timing(adjusted.get("timing") or {}, signal)
            if adjusted["timing"].get("cycle_s") is not None:
                adjusted["cycle_s"] = adjusted["timing"]["cycle_s"]

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
        # 再收紧策略定量上限（防止上游 constraints 仍为信号 history/cycle+30）
        eff_constraints = _tighten_constraints(constraints, strategy)
        # 优化结果可能只把周期写在 timing 里，补齐顶栏供护栏读取
        timing_cycle = _as_dict(plan_body.get("timing")).get("cycle_s")
        if plan_body.get("cycle_s") is None and timing_cycle is not None:
            plan_body["cycle_s"] = timing_cycle
        validation_errors = list(validate_plan_guardrails(plan_body, eff_constraints) or [])
        # 硬兜底：timing/顶栏周期超过策略上限时必须拒绝（防漏检）
        cycle_for_check = plan_body.get("cycle_s")
        if cycle_for_check is None:
            cycle_for_check = _as_dict(plan_body.get("timing")).get("cycle_s")
        max_for_check = eff_constraints.get("max_cycle_s")
        try:
            if (
                cycle_for_check is not None
                and max_for_check is not None
                and float(cycle_for_check) > float(max_for_check)
            ):
                msg = f"周期 {float(cycle_for_check):.0f}s 超过约束上限 {float(max_for_check):.0f}s"
                if msg not in validation_errors:
                    validation_errors.append(msg)
        except (TypeError, ValueError):
            pass

        if plan_status is not None:
            draft_status = plan_status
        else:
            draft_status = None
        draft_executable = executable
        if executable is not None:
            draft_executable = bool(executable) and plan_id != "verification_plan"
            if plan_id in {"verification_plan", "conditional_incremental_release"} and not decision.get(
                "preconditions_satisfied"
            ):
                draft_executable = False
                draft_status = decision.get("plan_status") or "conditional"

        candidate_preview = {
            "plan_id": plan_id,
            "name": definition["name"],
            "scenario": definition["scenario_template"].format(
                downstream=downstream_name,
                direction=direction,
            ),
            "timing": adjusted["timing"],
            "cycle_s": adjusted.get("cycle_s"),
            "upstream_control": adjusted["upstream_control"],
            "executable": draft_executable,
            "plan_status": draft_status,
        }
        semantic_errors: list[str] = []
        if validate_overflow_plan is not None and decision:
            # 条件性增绿在未核验时跳过严格配时净变化（仍校验文案与 executable）
            contract = dict(plan_contract)
            if (
                plan_id == "conditional_incremental_release"
                and not decision.get("preconditions_satisfied")
            ):
                contract = {**contract, "skip_timing_check": True}
            semantic_errors = list(
                validate_overflow_plan(
                    candidate=candidate_preview,
                    baseline_signal=signal,
                    decision=decision,
                    plan_contract=contract,
                    diagnosis=diagnosis,
                    ticket=ticket,
                )
                or []
            )
            validation_errors.extend(semantic_errors)

        guardrail_pass = len(validation_errors) == 0

        candidate = {
            "plan_id": plan_id,
            "name": definition["name"],
            "status": "valid" if guardrail_pass else "rejected",
            "scenario": candidate_preview["scenario"],
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
            "semantic_errors": semantic_errors,
            "guardrail_pass": guardrail_pass,
            "execution_order": definition.get("execution_order"),
            "timing_source": timing_source,
            "optimizer_degraded": optimizer_degraded_reason is not None,
            "optimizer_degraded_reason": optimizer_degraded_reason,
            "plan_contract": plan_contract or None,
        }
        if draft_status is not None:
            candidate["plan_status"] = draft_status
        if draft_executable is not None:
            candidate["executable"] = draft_executable
        if proposed_timing is not None:
            candidate["proposed_timing"] = proposed_timing
            candidate["proposed_timing_source"] = "conditional_incremental_release"
        candidates.append(candidate)
    return candidates, optimizer_engine


def _mark_verification_baseline_timing(
    timing: dict[str, Any],
    signal: dict[str, Any],
) -> dict[str, Any]:
    """核验方案维持现状配时，禁止展示优化器周期变化。"""
    stages = timing.get("phase_stage_timing_list") or []
    if not stages:
        current_cycle = _as_dict(signal).get("current_cycle_s")
        return {
            **timing,
            "available": True,
            "current_cycle_s": current_cycle,
            "cycle_s": current_cycle,
            "cycle_delta_s": 0,
            "verification_baseline": True,
        }
    normalized: list[dict[str, Any]] = []
    for stage in stages:
        row = dict(stage)
        current = _as_dict(row.get("current_timing"))
        if current:
            row["optimized_timing"] = dict(current)
            row["green_time_s"] = current.get("green_time_s", row.get("green_time_s"))
            row["green_delta_s"] = 0
            row["stage_delta_s"] = 0
        else:
            row["green_delta_s"] = 0
            row["stage_delta_s"] = 0
        normalized.append(row)
    current_cycle = timing.get("current_cycle_s") or _sum_cycle_from_stages(normalized)
    return {
        **timing,
        "available": True,
        "phase_stage_timing_list": normalized,
        "current_cycle_s": current_cycle,
        "cycle_s": current_cycle,
        "cycle_delta_s": 0,
        "verification_baseline": True,
    }


def _sum_cycle_from_stages(stages: list[dict[str, Any]]) -> int | None:
    total = 0
    for stage in stages:
        ct = _as_dict(stage.get("current_timing"))
        if ct.get("stage_total_s") is not None:
            total += int(float(ct["stage_total_s"]))
            continue
        for key in ("green_time_s", "yellow_time_s", "all_red_time_s"):
            if stage.get(key) is not None:
                total += int(stage[key])
                break
    return total or None


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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tighten_constraints(constraints: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    """取策略 quantitative_constraints 与传入约束的更严 max_cycle_s。"""
    out = dict(constraints or {})
    strat_body = strategy.get("strategy") if isinstance(strategy.get("strategy"), dict) else strategy
    quant = _as_dict(_as_dict(strat_body).get("quantitative_constraints"))
    qmax = quant.get("max_cycle_s")
    if qmax is None:
        return out
    try:
        qmax_f = float(qmax)
    except (TypeError, ValueError):
        return out
    existing = out.get("max_cycle_s")
    if existing is None:
        out["max_cycle_s"] = qmax_f
    else:
        try:
            out["max_cycle_s"] = min(float(existing), qmax_f)
        except (TypeError, ValueError):
            out["max_cycle_s"] = qmax_f
    return out
