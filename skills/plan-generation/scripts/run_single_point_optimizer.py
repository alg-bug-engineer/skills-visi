"""Run production single-point optimizer (signal_optimization_engine)."""

from __future__ import annotations

import logging
from typing import Any

from app.optimization.bootstrap import engine_available, get_optimize_intersection
from app.optimization.request_builder import build_optimizer_request
from app.trace.topology import DIR8_ENTRY

logger = logging.getLogger(__name__)

# 优化引擎 turnDirNo 口径：0=掉头,1=左转,2=直行,3=右转（见 turn_flow_binding）。
_ENGINE_TURN_LABEL = {0: "掉头", 1: "左转", 2: "直行", 3: "右转", 4: "掉头"}


def _movement_cn_label(dir8: Any, turn: Any, existing: Any = None) -> str | None:
    """人可读中文转向标签；已有非机器码标签优先，否则由 dir8/turn 生成。

    避免前端在缺 label 时回落到 ``d2_t2`` 机器码（需求 20·R1）。
    """
    if isinstance(existing, str) and existing.strip() and not _is_machine_key(existing):
        return existing
    try:
        entry = DIR8_ENTRY.get(int(dir8), "")
        turn_cn = _ENGINE_TURN_LABEL.get(int(turn), "")
    except (TypeError, ValueError):
        entry, turn_cn = "", ""
    label = f"{entry}{turn_cn}" if entry and turn_cn else (entry or turn_cn)
    if label:
        return label
    return existing if isinstance(existing, str) and existing.strip() else None


def _is_machine_key(value: str) -> bool:
    text = value.strip()
    return text.startswith("d") and "_t" in text


def run_single_point_optimizer(
    *,
    signal: dict[str, Any],
    ticket: dict[str, Any],
    diagnosis: dict[str, Any],
    strategy_instruction: dict[str, Any],
    constraints: dict[str, Any],
    pg_raw: dict[str, Any] | None = None,
    day_of_week: int | None = None,
) -> dict[str, Any]:
    if not engine_available():
        return {"ok": False, "reason": "signal_optimization_engine 不可用", "engine": "unavailable"}

    from app.data.schedule_period_resolver import prepare_signal_for_ticket

    signal_for_opt, timing_period = prepare_signal_for_ticket(
        signal,
        ticket,
        pg_raw,
        day_of_week=day_of_week,
    )

    request = build_optimizer_request(
        signal=signal_for_opt,
        ticket=ticket,
        diagnosis=diagnosis,
        strategy_instruction=strategy_instruction,
        constraints=constraints,
        pg_raw=pg_raw,
        timing_period=timing_period,
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

    timing = _build_timing_evidence(
        signal=signal,
        request=request,
        cycle_s=cycle_s,
        timing_list=timing_list,
        meta=meta,
    )
    # 与 timing 展示口径对齐：阶段加总修正后的周期必须回写顶栏，供护栏校验
    try:
        aligned_cycle = int(timing.get("cycle_s") or cycle_s)
    except (TypeError, ValueError):
        aligned_cycle = cycle_s

    return {
        "ok": True,
        "engine": "signal_optimization_engine",
        "request": request,
        "plan": plan,
        "timing": timing,
        "cycle_s": aligned_cycle,
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


def _sum_if_numbers(*values: Any) -> float | None:
    nums = [_number_or_none(v) for v in values]
    if any(n is None for n in nums):
        return None
    return float(sum(nums))  # type: ignore[arg-type]


def _sum_stage_totals(stages: list[dict[str, Any]], timing_key: str) -> float | None:
    total = 0.0
    count = 0
    for stage in stages:
        block = stage.get(timing_key) if isinstance(stage.get(timing_key), dict) else {}
        stage_total = _number_or_none(block.get("stage_total_s"))
        if stage_total is None:
            stage_total = _sum_if_numbers(
                block.get("green_time_s"),
                block.get("yellow_time_s"),
                block.get("all_red_time_s"),
            )
        if stage_total is None:
            continue
        total += float(stage_total)
        count += 1
    return total if count else None


def _build_timing_evidence(
    *,
    signal: dict[str, Any],
    request: dict[str, Any],
    cycle_s: int,
    timing_list: list[dict[str, Any]],
    meta: dict[str, Any],
) -> dict[str, Any]:
    current_cycle = _number_or_none(signal.get("current_cycle_s"))
    request_stages = ((request.get("phasePlanOfTimeList") or [{}])[0].get("phaseStageInfoList") or [])
    request_by_id = {
        str(s.get("phaseStageId") or s.get("phase_stage_id")): s
        for s in request_stages
        if isinstance(s, dict)
    }
    request_by_index = [s for s in request_stages if isinstance(s, dict)]

    missing_fields: list[str] = []
    stages: list[dict[str, Any]] = []
    for idx, optimized in enumerate(timing_list):
        stage_id = str(optimized.get("phase_stage_id") or "")
        source = request_by_id.get(stage_id) or (request_by_index[idx] if idx < len(request_by_index) else {})
        current = source.get("currentTiming") if isinstance(source.get("currentTiming"), dict) else {}
        movements = source.get("phaseDirInfoDTOList") if isinstance(source.get("phaseDirInfoDTOList"), list) else []
        if not current:
            missing_fields.append(f"phase_stage_timing_list[{stage_id or idx + 1}].current_timing")
        if not movements:
            missing_fields.append(f"phase_stage_timing_list[{stage_id or idx + 1}].movements")

        current_green = _number_or_none(current.get("greenSec"))
        current_yellow = _number_or_none(current.get("yellowSec"))
        current_all_red = _number_or_none(current.get("allRedSec"))
        current_total = _number_or_none(current.get("stageTotalSec"))
        if current_total is None:
            current_total = _sum_if_numbers(current_green, current_yellow, current_all_red)

        optimized_green = _number_or_none(optimized.get("green_time_s"))
        optimized_yellow = _number_or_none(optimized.get("yellow_time_s"))
        optimized_all_red = _number_or_none(optimized.get("all_red_time_s"))
        optimized_total = _sum_if_numbers(optimized_green, optimized_yellow, optimized_all_red)

        stages.append(
            {
                **optimized,
                "current_timing": {
                    "green_time_s": current_green,
                    "yellow_time_s": current_yellow,
                    "all_red_time_s": current_all_red,
                    "stage_total_s": current_total,
                },
                "optimized_timing": {
                    "green_time_s": optimized_green,
                    "yellow_time_s": optimized_yellow,
                    "all_red_time_s": optimized_all_red,
                    "stage_total_s": optimized_total,
                },
                "green_delta_s": _diff_if_numbers(optimized_green, current_green),
                "stage_delta_s": _diff_if_numbers(optimized_total, current_total),
                "movements": [_normalize_movement_evidence(item) for item in movements if isinstance(item, dict)],
                **_stage_visualization_fields(source),
            }
        )

    if current_cycle is None:
        missing_fields.append("timing.current_cycle_s")
    if not meta.get("direction_intensity_list"):
        missing_fields.append("timing.meta.direction_intensity_list")

    # PG signal.current_cycle_s 常与阶段绿+黄+全红之和脱节；展示口径以阶段加总为准，避免「60→123 +63」与全阶段减绿冲突。
    current_from_stages = _sum_stage_totals(stages, "current_timing")
    optimized_from_stages = _sum_stage_totals(stages, "optimized_timing")
    if current_from_stages is not None:
        if current_cycle is None or abs(float(current_cycle) - current_from_stages) > 2:
            current_cycle = (
                int(current_from_stages)
                if float(current_from_stages).is_integer()
                else round(current_from_stages, 1)
            )
    if optimized_from_stages is not None:
        opt_cycle = (
            int(optimized_from_stages)
            if float(optimized_from_stages).is_integer()
            else round(optimized_from_stages, 1)
        )
        if cycle_s is None or abs(float(cycle_s) - float(optimized_from_stages)) > 2:
            cycle_s = opt_cycle

    return {
        "available": not missing_fields,
        "reason": None if not missing_fields else "方案证据字段不完整，无法生产级展示",
        "missing_fields": missing_fields,
        "current_cycle_s": current_cycle,
        "cycle_s": cycle_s,
        "cycle_delta_s": _diff_if_numbers(cycle_s, current_cycle),
        "phase_stage_timing_list": stages,
        "meta": _build_optimization_meta(meta, request.get("meta")),
    }


def _build_optimization_meta(
    meta: dict[str, Any],
    period_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    direction_list = meta.get("direction_intensity_list")
    if not isinstance(direction_list, list):
        direction_list = []
    normalized_direction: list[dict[str, Any]] = []
    for item in direction_list:
        if not isinstance(item, dict):
            continue
        enriched = {
            key: value
            for key, value in item.items()
            if key != "historyVirtualFlowVph"
        }
        enriched["label"] = _movement_cn_label(
            item.get("dir8No"), item.get("turnDirNo"), item.get("label")
        )
        normalized_direction.append(enriched)
    direction_list = normalized_direction
    result: dict[str, Any] = {
        "solver": meta.get("solver"),
        "target_saturation": meta.get("target_saturation"),
        "max_phase_saturation": meta.get("max_phase_saturation"),
        "total_turn_flow_vph": meta.get("total_turn_flow_vph"),
        "direction_intensity_list": direction_list,
        "notes": meta.get("notes") if isinstance(meta.get("notes"), list) else [],
        "data_quality": {
            "current_timing_source": "pg_signal_plan",
            "movement_source": "pg_turn_flow+pg_turn_saturation",
        },
    }
    if isinstance(period_meta, dict):
        for key in (
            "target_periods",
            "period_plan_no",
            "period_label",
            "period_match_method",
        ):
            if period_meta.get(key) is not None:
                result[key] = period_meta[key]
    return result


def _stage_visualization_fields(source: dict[str, Any]) -> dict[str, Any]:
    """保留阶段图绘制所需的 flow_combo / sourceStageAtoms（对齐参考项目）。"""
    if not isinstance(source, dict):
        return {}
    out: dict[str, Any] = {}
    atoms = source.get("source_stage_atoms") or source.get("sourceStageAtoms")
    if isinstance(atoms, list) and atoms:
        out["source_stage_atoms"] = atoms
    combo = source.get("flow_combo") or source.get("flowCombo")
    if isinstance(combo, list) and combo:
        out["flow_combo"] = combo
    ped_dirs = source.get("ped_dir_list") or source.get("pedDirList")
    if isinstance(ped_dirs, list) and ped_dirs:
        out["ped_dir_list"] = ped_dirs
    display_name = source.get("phase_stage_name") or source.get("phaseStageName")
    if display_name:
        out["phase_stage_name"] = str(display_name)
    return out


def _normalize_movement_evidence(item: dict[str, Any]) -> dict[str, Any]:
    movement_key = item.get("movement_key") or item.get("movementKey")
    if not movement_key and item.get("dir8No") is not None and item.get("turnDirNo") is not None:
        movement_key = f"d{item.get('dir8No')}_t{item.get('turnDirNo')}"
    label = _movement_cn_label(item.get("dir8No"), item.get("turnDirNo"), item.get("label"))
    return {
        "movement_key": movement_key,
        "movementKey": movement_key,
        "label": label,
        "dir8No": item.get("dir8No"),
        "turnDirNo": item.get("turnDirNo"),
        "turnFlowTotal": item.get("turnFlowTotal"),
        "laneCount": item.get("laneCount"),
        "saturation": item.get("saturation"),
        "flow_available": item.get("flow_available"),
        "source": item.get("source"),
    }


def _number_or_none(value: Any) -> int | float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _diff_if_numbers(left: int | float | None, right: int | float | None) -> int | float | None:
    if left is None or right is None:
        return None
    return left - right
