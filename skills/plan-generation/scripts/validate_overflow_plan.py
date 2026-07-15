"""溢出方案语义护栏（后置校验，拒绝不符合契约的候选）。"""

from __future__ import annotations

from typing import Any

from app.decision.effective_green import (
    compute_target_effective_green_delta,
    max_stage_change_ratio,
    movement_key_from_ticket,
)


def validate_overflow_plan(
    *,
    candidate: dict[str, Any],
    baseline_signal: dict[str, Any],
    decision: dict[str, Any] | None,
    plan_contract: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None,
    ticket: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    decision = decision or {}
    plan_contract = plan_contract or {}
    diagnosis = diagnosis or {}
    ticket = ticket or {}
    candidate = candidate or {}

    plan_id = str(candidate.get("plan_id") or "")
    allowed = decision.get("allowed_plan_types") or []
    if allowed and plan_id and plan_id not in {str(x) for x in allowed}:
        errors.append(f"方案 {plan_id} 不在当前决策允许类型 {allowed} 内")

    downstream = diagnosis.get("downstream_state") or {}
    scenario = str(candidate.get("scenario") or "")
    name = str(candidate.get("name") or "")
    text = scenario + name
    if downstream.get("decision") == "slack" and ("接不住" in text or "承接不足" in text):
        errors.append("下游状态为 slack，方案文案不得使用「接不住/承接不足」")

    if decision.get("decision_mode") == "verify_then_adjust" and not decision.get(
        "preconditions_satisfied"
    ):
        if candidate.get("executable") is True:
            errors.append("核验未完成时方案不得标记为可执行（executable=true）")
        if candidate.get("plan_status") == "trial_ready" and plan_id != "verification_plan":
            errors.append("核验未完成时 plan_status 不得为 trial_ready")

    if plan_id == "arterial_coordination" or decision.get("decision_mode") == "upstream_coordination":
        upstream = candidate.get("upstream_control") or {}
        if upstream.get("enabled") and not (upstream.get("control_points") or []):
            errors.append("干线联控启用时必须包含真实上游控制点")

    if plan_contract.get("skip_timing_check") or plan_id == "verification_plan":
        return errors

    movement_key = plan_contract.get("target_movement_key") or movement_key_from_ticket(ticket)
    before_stages = list(
        (baseline_signal or {}).get("phase_stage_timing_list")
        or (baseline_signal or {}).get("phaseStageTimingList")
        or []
    )
    timing = candidate.get("timing") if isinstance(candidate.get("timing"), dict) else {}
    after_stages = list(
        timing.get("phase_stage_timing_list")
        or timing.get("phaseStageTimingList")
        or candidate.get("phase_stage_timing_list")
        or []
    )

    if not movement_key or not before_stages or not after_stages:
        return errors

    target_delta = plan_contract.get("target_effective_green_delta_s")
    if target_delta is not None and plan_id in {
        "incremental_release",
        "conditional_incremental_release",
    }:
        delta_info = compute_target_effective_green_delta(
            before_stages=before_stages,
            after_stages=after_stages,
            movement_key=str(movement_key),
        )
        actual = delta_info["delta_s"]
        expected = float(target_delta)
        if expected > 0 and actual < 0:
            errors.append(
                f"目标有效绿净减少：契约要求增加，实际 {actual:+.1f}s（movement={movement_key}）"
            )
        elif expected > 0 and actual < expected - 1.0:
            errors.append(
                f"目标有效绿净变化不足：契约 +{expected:.0f}s，实际 {actual:+.1f}s（movement={movement_key}）"
            )
        elif expected < 0 and actual > expected + 1.0:
            errors.append(
                f"目标有效绿净变化偏离契约：期望 {expected:+.0f}s，实际 {actual:+.1f}s"
            )

    cycle_delta = plan_contract.get("cycle_delta_s")
    if cycle_delta is not None:
        before_cycle = _cycle_s(baseline_signal)
        after_cycle = _cycle_s(timing) or _cycle_s(candidate)
        if before_cycle is not None and after_cycle is not None:
            actual_cycle_delta = after_cycle - before_cycle
            if abs(actual_cycle_delta - float(cycle_delta)) > 1.0:
                errors.append(
                    f"周期变化偏离契约：期望 {float(cycle_delta):+.0f}s，实际 {actual_cycle_delta:+.0f}s"
                )

    max_ratio = plan_contract.get("max_stage_change_ratio")
    if max_ratio is not None and before_stages and after_stages:
        worst = max_stage_change_ratio(before_stages, after_stages)
        if worst > float(max_ratio) + 1e-6:
            errors.append(
                f"单阶段调整比例过大：最大 {worst:.2%}，允许 {float(max_ratio):.0%}"
            )

    return errors


def build_plan_contract_from_strategy(
    strategy: dict[str, Any],
    ticket: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从 DecisionContract / strategy_instruction 编译方案契约。"""
    decision = strategy.get("decision") if isinstance(strategy.get("decision"), dict) else {}
    instruction = strategy.get("strategy_instruction") or {}
    strategy_body = strategy.get("strategy") if isinstance(strategy.get("strategy"), dict) else {}
    movement_key = (
        decision.get("target_movement_key")
        or strategy_body.get("target_movement_key")
        or movement_key_from_ticket(ticket)
    )
    target_delta = instruction.get("target_green_delta")
    if target_delta is None:
        target_delta = strategy_body.get("target_green_delta")
    cycle_delta = instruction.get("cycle_delta")
    if cycle_delta is None:
        cycle_delta = strategy_body.get("cycle_delta", 0)
    return {
        "target_movement_key": movement_key,
        "target_effective_green_delta_s": target_delta,
        "cycle_delta_s": cycle_delta if cycle_delta is not None else 0,
        "max_stage_change_ratio": decision.get("max_stage_change_ratio", 0.15),
        "direct_downstream_inter_id": decision.get("direct_downstream_inter_id"),
        "preconditions_satisfied": decision.get("preconditions_satisfied"),
        "upstream_control_required": bool(instruction.get("upstream_control")),
    }


def _cycle_s(obj: dict[str, Any] | None) -> float | None:
    if not isinstance(obj, dict):
        return None
    for key in ("cycle_s", "current_cycle_s", "cycle"):
        if obj.get(key) is not None:
            try:
                return float(obj[key])
            except (TypeError, ValueError):
                continue
    return None
