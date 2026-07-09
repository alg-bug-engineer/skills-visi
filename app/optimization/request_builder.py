"""Build optimizer requests from PG signal or fixture signal plans."""

from __future__ import annotations

from typing import Any

from app.data.schedule_period_resolver import resolve_timing_period
from app.trace.topology import DIRECTION_MOVEMENT, resolve_dir8_turn


def build_optimizer_request(
    *,
    signal: dict[str, Any],
    ticket: dict[str, Any],
    diagnosis: dict[str, Any],
    strategy_instruction: dict[str, Any],
    constraints: dict[str, Any],
    pg_raw: dict[str, Any] | None = None,
    timing_period: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inter_id = str(signal.get("inter_id") or ticket.get("inter_id") or "UNKNOWN")
    phase_plan = _build_phase_plan(signal, inter_id)
    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    dir8, turn = resolve_dir8_turn(direction, movement)

    bottleneck = diagnosis.get("bottleneck_analysis", {})
    downstream_blocked = (diagnosis.get("downstream_trace") or {}).get("governance", {}).get(
        "downstream_blocked", False
    )
    target_saturation = 0.82
    if downstream_blocked or bottleneck.get("bottleneck_type") == "downstream_capacity":
        target_saturation = 0.78

    strategy = dict(strategy_instruction)
    strategy.setdefault("target_saturation", target_saturation)
    if strategy_instruction.get("package") == "downstream_protection":
        strategy["target_saturation"] = min(target_saturation, 0.75)

    merged_constraints = {
        "max_cycle_s": constraints.get("max_cycle_s") or signal.get("max_cycle_s") or 150,
        "default_cycle_s": signal.get("current_cycle_s") or 120,
        "saturation_flow_vph": 1400.0,
        "green_loss_s": 2,
        **{k: v for k, v in constraints.items() if v is not None},
    }

    resolved = timing_period or signal.get("timing_period")
    if not isinstance(resolved, dict) or not resolved.get("target_periods"):
        schedule_rows = (pg_raw or {}).get("schedule_cfg") or []
        day_of_week = (pg_raw or {}).get("context_day_of_week")
        resolved = resolve_timing_period(ticket, schedule_rows, day_of_week=day_of_week)
    target_periods = list(resolved.get("target_periods") or [])
    if not target_periods:
        fallback = str(ticket.get("time_range") or "").strip()
        if fallback:
            target_periods = [fallback]

    return {
        "interId": inter_id,
        "planNo": signal.get("plan_no"),
        "dir8No": dir8,
        "turnDirNo": turn,
        "obj_intensity": strategy.get("target_saturation", target_saturation),
        "phasePlanOfTimeList": [phase_plan],
        "constraints": merged_constraints,
        "strategy_instruction": strategy,
        "target_periods": target_periods,
        "meta": {
            "target_periods": target_periods,
            "period_plan_no": resolved.get("period_plan_no"),
            "period_label": resolved.get("period_label"),
            "period_match_method": resolved.get("match_method"),
        },
    }


def _build_phase_plan(signal: dict[str, Any], inter_id: str) -> dict[str, Any]:
    if signal.get("phasePlanOfTimeList"):
        return dict(signal["phasePlanOfTimeList"][0])

    stages = signal.get("phase_stage_timing_list") or []
    stage_detail = signal.get("stage_detail") or []
    if stage_detail and not stages:
        stages = [
            {
                "phase_stage_id": row.get("stage_no"),
                "phase_stage_name": row.get("release_movements") or f"阶段{row.get('stage_no')}",
                "greenTime": row.get("green_sec"),
                "yellowTime": row.get("yellow_sec") or 3,
                "allRedTime": row.get("all_red_sec") or 2,
                "minGreenTime": row.get("min_green_sec"),
                "maxGreenTime": row.get("max_green_sec"),
                "movement_key": row.get("release_movements"),
            }
            for row in stage_detail
        ]

    phase_stages = []
    for stage in stages:
        green = _int_or_none(stage.get("greenTime"), stage.get("green_time_s"))
        yellow = _int_or_none(stage.get("yellowTime"), stage.get("yellow_time_s")) or 3
        all_red = _int_or_none(stage.get("allRedTime"), stage.get("all_red_time_s")) or 2
        min_green = _int_or_none(stage.get("minGreenTime"), stage.get("min_green_time_s"))
        max_green = _int_or_none(stage.get("maxGreenTime"), stage.get("max_green_time_s"))

        phase_stage = {
            "phaseStageId": str(stage.get("phase_stage_id") or stage.get("phaseStageId") or ""),
            "phaseStageName": str(stage.get("phase_stage_name") or stage.get("phaseStageName") or ""),
            "phaseDirInfoDTOList": _resolve_stage_dir_infos(stage),
            "greenTime": green or 0,
            "yellowTime": yellow,
            "allRedTime": all_red,
            # currentTiming / greenBounds 让优化引擎按真实现状绿与真实最小绿定界，
            # 否则引擎回落默认机动车最小绿 14s（见 signal_optimization_engine
            # single_intersection._stage_min_green_s / _stage_history_green_s）。
            "currentTiming": {
                "greenSec": green,
                "yellowSec": yellow,
                "allRedSec": all_red,
                "stageTotalSec": (green + yellow + all_red) if green is not None else None,
            },
        }
        green_bounds: dict[str, Any] = {}
        if min_green is not None:
            green_bounds["minGreenS"] = min_green
            phase_stage["minGreenTime"] = min_green
            phase_stage["min_green_s"] = min_green
        if max_green is not None:
            green_bounds["maxGreenS"] = max_green
            phase_stage["maxGreenTime"] = max_green
            phase_stage["max_green_s"] = max_green
        if green_bounds:
            phase_stage["greenBounds"] = green_bounds
        if stage.get("source_stage_atoms"):
            phase_stage["sourceStageAtoms"] = stage["source_stage_atoms"]
        if stage.get("flow_combo"):
            phase_stage["flow_combo"] = stage["flow_combo"]
        if stage.get("ped_dir_list"):
            phase_stage["pedDirList"] = stage["ped_dir_list"]
        phase_stages.append(phase_stage)

    return {
        "interId": inter_id,
        "phasePlanId": str(signal.get("plan_no") or signal.get("plan_id") or "PLAN-1"),
        "phasePlanName": str(signal.get("plan_name") or "现状方案"),
        "phaseStageInfoList": phase_stages,
    }


def _resolve_stage_dir_infos(stage: dict[str, Any]) -> list[dict[str, Any]]:
    """优先使用后端已绑定的真实逐转向流量，缺失时按释放转向标注降级。

    不再使用固定占位流量（原 500）。绑定不到真实流量的转向以 turnFlowTotal=0
    传入（引擎据此走虚拟流量→最小绿，而非编造需求）。
    """
    bound = stage.get("phaseDirInfoDTOList")
    if isinstance(bound, list) and bound:
        infos: list[dict[str, Any]] = []
        for item in bound:
            if not isinstance(item, dict):
                continue
            dir8 = item.get("dir8No")
            turn = item.get("turnDirNo")
            if dir8 is None or turn is None:
                continue  # 无法定位方向的转向不下发，避免错配
            vph = item.get("turnFlowTotal")
            entry: dict[str, Any] = {
                "dir8No": int(dir8),
                "turnDirNo": int(turn),
                "turnFlowTotal": float(vph) if vph is not None else 0.0,
            }
            for key in (
                "movementKey",
                "movement_key",
                "label",
                "saturation",
                "flow_available",
                "source",
                "historyVirtualFlowVph",
            ):
                if key in item:
                    entry[key] = item[key]
            lane = item.get("laneCount")
            if lane is not None:
                entry["laneCount"] = int(lane)
            infos.append(entry)
        if infos:
            return infos

    # 降级：无绑定流量（如 fixture 现状配时），按阶段释放转向给单条方向，
    # 不带流量（引擎走虚拟流量→最小绿），显式区别于真实需求。
    movement_key = str(stage.get("movement_key") or stage.get("phase_stage_name") or "")
    dir8, turn = _movement_to_dir8_turn(movement_key)
    entry = {"dir8No": dir8, "turnDirNo": turn}
    flow = stage.get("turnFlowTotal") or stage.get("flow_vph")
    if flow is not None:
        entry["turnFlowTotal"] = float(flow)
    lane = stage.get("laneCount")
    if lane:
        entry["laneCount"] = int(lane)
    return [entry]


def _int_or_none(*values: Any) -> int | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _movement_to_dir8_turn(movement_key: str) -> tuple[int, int]:
    for label, pair in DIRECTION_MOVEMENT.items():
        if label in movement_key or movement_key in label:
            return pair
    if "东" in movement_key and "直" in movement_key:
        return 2, 2
    if "西" in movement_key and "直" in movement_key:
        return 6, 2
    if "南" in movement_key and "直" in movement_key:
        return 4, 2
    if "北" in movement_key and "直" in movement_key:
        return 0, 2
    return 2, 2
