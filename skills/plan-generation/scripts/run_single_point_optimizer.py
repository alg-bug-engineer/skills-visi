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
    return {
        "ok": True,
        "engine": "signal_optimization_engine",
        "request": request,
        "plan": plan,
        "timing": {
            "cycle_s": int(plan.get("cycleTime") or plan.get("cycle_s") or 0),
            "phase_stage_timing_list": timing_list,
        },
        "cycle_s": int(plan.get("cycleTime") or plan.get("cycle_s") or 0),
    }


def _normalize_optimizer_stages(plan: dict[str, Any]) -> list[dict[str, Any]]:
    stages = plan.get("phaseStageTimingList") or plan.get("data") or []
    normalized: list[dict[str, Any]] = []
    cycle = int(plan.get("cycleTime") or plan.get("cycle_s") or 1)
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        green = int(stage.get("greenTime") or stage.get("green_time_s") or 0)
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
                "split_ratio": round(green / max(cycle, 1), 4),
            }
        )
    return normalized
