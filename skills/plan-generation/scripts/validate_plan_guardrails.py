from __future__ import annotations

from typing import Any


def validate_plan_guardrails(plan: dict[str, Any], constraints: dict[str, Any] | None = None) -> list[str]:
    """Validate intersection plan-generation guardrails."""
    constraints = constraints or {}
    errors: list[str] = []
    timing = _as_dict(plan.get("timing"))
    cycle = _to_float(
        plan.get("cycle_s")
        or plan.get("cycleTime")
        or timing.get("cycle_s")
    )
    max_cycle = _to_float(constraints.get("max_cycle_s"))
    # 产品硬约束不可被引擎 history max 旁路（需求 34 E7/G6）
    if cycle is not None and max_cycle is None:
        errors.append("缺少周期上限约束 max_cycle_s，无法完成护栏校验")
    elif cycle is not None and max_cycle is not None and cycle > max_cycle:
        errors.append(f"周期 {cycle:.0f}s 超过约束上限 {max_cycle:.0f}s")
    if not str(plan.get("rollback_condition") or "").strip():
        errors.append("缺少回滚条件")

    stages = _stage_list(plan)
    if stages:
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            green = _to_float(stage.get("greenTime") or stage.get("green_time_s"))
            min_green = _to_float(stage.get("minGreenTime") or stage.get("min_green_time_s"))
            max_green = _to_float(stage.get("maxGreenTime") or stage.get("max_green_time_s"))
            name = stage.get("phaseStageName") or stage.get("phase_stage_name") or stage.get("phaseStageId") or "未知阶段"
            if green is not None and min_green is not None and green + 1e-6 < min_green:
                errors.append(f"{name} 绿灯 {green:.0f}s 小于最小绿 {min_green:.0f}s")
            if green is not None and max_green is not None and green - 1e-6 > max_green:
                errors.append(f"{name} 绿灯 {green:.0f}s 超过最大绿 {max_green:.0f}s")
    elif plan.get("parameters", {}).get("optimization_engine"):
        errors.append("优化引擎未返回可用单路口方案")
    elif plan.get("plan_id") and not stages:
        errors.append("缺少相位阶段配时列表")

    pedestrian = _as_dict(plan.get("pedestrian_constraints"))
    if pedestrian and pedestrian.get("satisfied") is False:
        for item in pedestrian.get("violations") or []:
            errors.append(f"行人过街约束不满足: {item}")

    return errors


def _stage_list(plan: dict[str, Any]) -> list[dict[str, Any]]:
    timing = _as_dict(plan.get("timing"))
    if timing.get("phase_stage_timing_list"):
        return list(timing["phase_stage_timing_list"])
    optimizer_plan = _optimizer_plan(plan)
    return list(
        optimizer_plan.get("phaseStageTimingList") or optimizer_plan.get("data") or []
    )


def _optimizer_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("planType") == "single_point":
        return plan
    engine = _as_dict(_as_dict(plan.get("parameters")).get("optimization_engine"))
    candidate = engine.get("plan")
    return candidate if isinstance(candidate, dict) else {}


def _optimizer_meta(plan: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(_optimizer_plan(plan).get("meta"))


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
