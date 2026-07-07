"""Run production single-point optimizer (signal_optimization_engine)."""

from __future__ import annotations

import logging
from typing import Any

from app.optimization.bootstrap import engine_available, get_optimize_intersection
from app.optimization.request_builder import build_optimizer_request

logger = logging.getLogger(__name__)


def run_single_point_optimizer(
    *,
    signal: dict[str, Any],
    ticket: dict[str, Any],
    diagnosis: dict[str, Any],
    strategy_instruction: dict[str, Any],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    if not engine_available():
        return {"ok": False, "reason": "signal_optimization_engine 不可用", "engine": "unavailable"}

    request = build_optimizer_request(
        signal=signal,
        ticket=ticket,
        diagnosis=diagnosis,
        strategy_instruction=strategy_instruction,
        constraints=constraints,
    )
    try:
        optimize = get_optimize_intersection()
        plan = optimize(request)
    except Exception as exc:
        logger.exception("单点优化器执行失败")
        return {"ok": False, "reason": str(exc), "request": request}

    if plan.get("isError"):
        return {
            "ok": False,
            "reason": plan.get("error") or "优化器返回错误",
            "request": request,
            "plan": plan,
        }

    timing_list = _normalize_optimizer_stages(plan)
    meta = plan.get("meta") if isinstance(plan.get("meta"), dict) else {}
    cycle_s = int(plan.get("cycleTime") or plan.get("cycle_s") or 0)

    degraded_reason = _degradation_reason(signal, meta, timing_list, cycle_s)
    if degraded_reason:
        # 输入需求缺失/结果塌缩到最小绿：不把退化配时当优化成功，
        # 交由上游回退真实现状配时调整（禁止占位方案冒充优化结果）。
        return {
            "ok": False,
            "degraded": True,
            "engine": "signal_optimization_engine_degraded",
            "reason": degraded_reason,
            "request": request,
            "plan": plan,
        }

    return {
        "ok": True,
        "engine": "signal_optimization_engine",
        "request": request,
        "plan": plan,
        "timing": {
            "cycle_s": cycle_s,
            "phase_stage_timing_list": timing_list,
            "meta": {
                "solver": meta.get("solver"),
                "target_saturation": meta.get("target_saturation"),
                "max_phase_saturation": meta.get("max_phase_saturation"),
                "total_turn_flow_vph": meta.get("total_turn_flow_vph"),
                "direction_intensity_list": meta.get("direction_intensity_list"),
                "notes": meta.get("notes"),
            },
        },
        "cycle_s": cycle_s,
    }


def _degradation_reason(
    signal: dict[str, Any],
    meta: dict[str, Any],
    timing_list: list[dict[str, Any]],
    cycle_s: int,
) -> str | None:
    """识别退化/占位优化结果；返回原因字符串，正常时返回 None。"""
    binding = signal.get("flow_binding") if isinstance(signal, dict) else None
    if isinstance(binding, dict) and binding.get("ok") is False:
        return binding.get("reason") or "缺少真实转向流量，无法进行需求驱动配时优化"

    total_flow = meta.get("total_turn_flow_vph")
    if total_flow is not None and float(total_flow) <= 0:
        return "优化输入无真实转向流量（total_turn_flow_vph=0），结果不可信"

    saturations = [
        s.get("phase_saturation")
        for s in timing_list
        if s.get("phase_saturation") is not None
    ]
    if timing_list and not saturations:
        return "优化结果缺少逐相位饱和度，判定为退化输出"

    return None


def _normalize_optimizer_stages(plan: dict[str, Any]) -> list[dict[str, Any]]:
    stages = plan.get("phaseStageTimingList") or plan.get("data") or []
    normalized: list[dict[str, Any]] = []
    cycle = int(plan.get("cycleTime") or plan.get("cycle_s") or 1)
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        green = int(stage.get("greenTime") or stage.get("green_time_s") or 0)
        saturation = stage.get("phaseSaturation")
        if saturation is None:
            saturation = stage.get("phase_saturation")
        normalized.append(
            {
                "phase_stage_id": stage.get("phaseStageId") or stage.get("phase_stage_id"),
                "phase_stage_name": stage.get("phaseStageName") or stage.get("phase_stage_name"),
                "green_time_s": green,
                "yellow_time_s": int(stage.get("yellowTime") or stage.get("yellow_time_s") or 3),
                "all_red_time_s": int(stage.get("allRedTime") or stage.get("all_red_time_s") or 2),
                "min_green_time_s": int(stage.get("minGreenTime") or stage.get("min_green_time_s") or 0),
                "max_green_time_s": int(stage.get("maxGreenTime") or stage.get("max_green_time_s") or green + 30),
                "greenTime": green,
                "yellowTime": int(stage.get("yellowTime") or 3),
                "allRedTime": int(stage.get("allRedTime") or 2),
                "minGreenTime": int(stage.get("minGreenTime") or 0),
                "maxGreenTime": int(stage.get("maxGreenTime") or green + 30),
                "split_ratio": (
                    round(float(stage["splitRatio"]), 4)
                    if stage.get("splitRatio") is not None
                    else round(green / max(cycle, 1), 4)
                ),
                "phase_saturation": round(float(saturation), 4) if saturation is not None else None,
            }
        )
    return normalized
