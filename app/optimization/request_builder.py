"""Build optimizer requests from PG signal or fixture signal plans."""

from __future__ import annotations

from typing import Any

from app.trace.topology import DIRECTION_MOVEMENT, resolve_dir8_turn


def build_optimizer_request(
    *,
    signal: dict[str, Any],
    ticket: dict[str, Any],
    diagnosis: dict[str, Any],
    strategy_instruction: dict[str, Any],
    constraints: dict[str, Any],
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

    return {
        "interId": inter_id,
        "dir8No": dir8,
        "turnDirNo": turn,
        "phasePlanOfTimeList": [phase_plan],
        "constraints": merged_constraints,
        "strategy_instruction": strategy,
        "target_periods": [ticket.get("time_range")] if ticket.get("time_range") else [],
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
        movement_key = str(stage.get("movement_key") or stage.get("phase_stage_name") or "")
        dir8, turn = _movement_to_dir8_turn(movement_key)
        flow = int(stage.get("turnFlowTotal") or stage.get("flow_vph") or 500)
        phase_stages.append(
            {
                "phaseStageId": str(stage.get("phase_stage_id") or stage.get("phaseStageId") or ""),
                "phaseStageName": str(stage.get("phase_stage_name") or stage.get("phaseStageName") or ""),
                "phaseDirInfoDTOList": [
                    {
                        "dir8No": dir8,
                        "turnDirNo": turn,
                        "turnFlowTotal": flow,
                        "laneCount": int(stage.get("laneCount") or 2),
                    }
                ],
                "greenTime": int(stage.get("greenTime") or stage.get("green_time_s") or 0),
                "yellowTime": int(stage.get("yellowTime") or stage.get("yellow_time_s") or 3),
                "allRedTime": int(stage.get("allRedTime") or stage.get("all_red_time_s") or 2),
                "minGreenTime": int(stage.get("minGreenTime") or stage.get("min_green_time_s") or 15),
                "maxGreenTime": int(stage.get("maxGreenTime") or stage.get("max_green_time_s") or 60),
            }
        )

    return {
        "interId": inter_id,
        "phasePlanId": str(signal.get("plan_no") or signal.get("plan_id") or "PLAN-1"),
        "phasePlanName": str(signal.get("plan_name") or "现状方案"),
        "phaseStageInfoList": phase_stages,
    }


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
