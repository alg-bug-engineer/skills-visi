"""溢出闭环阶段转换校验。"""

from __future__ import annotations

from typing import Any

from app.decision.overflow_mechanism import map_mechanism_to_decision
from app.domain.overflow_case_state import OverflowCaseState, update_overflow_state_after_skill
from app.runtime.skill_types import SkillContext


def validate_overflow_transition(
    *,
    context: SkillContext,
    skill_id: str,
    output: dict[str, Any],
) -> list[str]:
    """校验当前 skill 输出与已冻结的溢出状态是否一致。返回错误列表（空=通过）。"""
    errors: list[str] = []
    state = getattr(context, "overflow_state", None)
    if state is None:
        from app.domain.overflow_case_state import seed_overflow_state_from_artifacts

        state = seed_overflow_state_from_artifacts(context.artifacts)
        context.overflow_state = state

    output = output or {}

    if skill_id == "cause_analysis":
        mechanism = state.mechanism or (context.artifacts.get("data_analysis_diagnosis") or {}).get(
            "overflow_mechanism"
        )
        if isinstance(mechanism, dict) and mechanism.get("primary"):
            out_mech = output.get("overflow_mechanism") or {}
            if out_mech.get("primary") and out_mech.get("primary") != mechanism.get("primary"):
                errors.append(
                    f"成因阶段不得改写溢出机制：冻结={mechanism.get('primary')}，输出={out_mech.get('primary')}"
                )
            # LLM 主因若直接「下游接不住」但机制不是下游回堵，记冲突
            primary_cause = ((output.get("cause_analysis") or {}).get("primary_cause")) or output.get(
                "primary_cause"
            )
            if (
                isinstance(primary_cause, str)
                and ("接不住" in primary_cause or "承接不足" in primary_cause)
                and mechanism.get("primary") != "downstream_blocked"
            ):
                errors.append("成因文案不得在非下游回堵机制下输出「下游接不住/承接不足」为主因")

    if skill_id == "strategy_generation":
        mechanism = state.mechanism or {}
        primary = mechanism.get("primary")
        decision = output.get("decision") or {}
        if primary and decision:
            expected = map_mechanism_to_decision(
                primary_mechanism=str(primary),
                verification_passed=bool(
                    ((context.artifacts.get("data_analysis_diagnosis") or {}).get("verification") or {}).get(
                        "passed"
                    )
                ),
            )
            if decision.get("decision_mode") != expected.get("decision_mode"):
                errors.append(
                    f"策略决策与机制不匹配：机制={primary} 期望={expected.get('decision_mode')} "
                    f"实际={decision.get('decision_mode')}"
                )

    if skill_id == "plan_generation":
        decision = state.decision or (context.artifacts.get("strategy_generation") or {}).get("decision") or {}
        allowed = {str(x) for x in (decision.get("allowed_plan_types") or [])}
        recommended = output.get("recommended") or {}
        candidates = output.get("candidates") or []
        if allowed:
            for cand in candidates:
                pid = str(cand.get("plan_id") or "")
                if pid and pid not in allowed:
                    errors.append(f"候选方案 {pid} 不在允许类型 {sorted(allowed)} 内")
            rec_id = str(recommended.get("plan_id") or "")
            if rec_id and rec_id not in allowed:
                errors.append(f"推荐方案 {rec_id} 不在允许类型内")

        if decision.get("decision_mode") == "verify_then_adjust" and not decision.get(
            "preconditions_satisfied"
        ):
            if recommended.get("executable") is True:
                errors.append("核验未完成时推荐方案不得标记 executable=true")
            for cand in candidates:
                if cand.get("executable") is True:
                    errors.append(f"核验未完成时候选 {cand.get('plan_id')} 不得 executable=true")

        # 下游对象漂移（若方案带监测下游）
        frozen_down = (state.downstream_state or {}).get("direct_downstream_inter_id")
        for cand in candidates:
            mid = (cand.get("monitor_downstream") or {}).get("inter_id") or cand.get(
                "direct_downstream_inter_id"
            )
            if frozen_down and mid and str(mid) != str(frozen_down):
                errors.append("方案监测下游与诊断直接下游不一致")

    # 成功路径更新状态（校验用输出副本，调用方决定是否采纳）
    if not errors:
        context.overflow_state = update_overflow_state_after_skill(
            state,
            skill_id=skill_id,
            output=output,
            artifacts={**context.artifacts, skill_id: output},
        )

    return errors


def apply_overflow_transition(
    context: SkillContext,
    *,
    skill_id: str,
    result_success: bool,
    output: dict[str, Any],
) -> list[str]:
    """Executor 钩子：仅在 skill 成功时校验；返回错误（非空表示应改判失败）。"""
    if not result_success:
        return []
    # 仅当流水线已出现溢出机制/下游状态时启用
    diagnosis = context.artifacts.get("data_analysis_diagnosis") or {}
    if skill_id == "data_analysis_diagnosis":
        diagnosis = output or {}
    if not diagnosis.get("overflow_mechanism") and skill_id not in {
        "data_analysis_diagnosis",
        "intent_understanding",
    }:
        if not getattr(context, "overflow_state", None):
            return []
    return validate_overflow_transition(context=context, skill_id=skill_id, output=output)
