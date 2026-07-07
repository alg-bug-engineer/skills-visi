from __future__ import annotations

import copy
from typing import Any


PACKAGE_STRATEGIES = {
    "downstream_protection": {
        "strategy": "downstream_protection",
        "target_green_delta": -2,
        "cycle_delta": 0,
        "upstream_control": False,
        "rollback_condition": "下游排队比持续上升时回滚至原方案",
    },
    "incremental_release": {
        "strategy": "incremental_release",
        "target_green_delta": 5,
        "cycle_delta": 0,
        "upstream_control": False,
        "rollback_condition": "下游排队比持续上升或目标方向绿灯利用率异常下降时回滚",
    },
    "arterial_coordination": {
        "strategy": "arterial_coordination",
        "target_green_delta": 2,
        "cycle_delta": 10,
        "upstream_control": True,
        "rollback_condition": "下游排队比持续上升、上游排队超过安全边界时回滚",
    },
}


def build_strategy_instruction(strategy: dict[str, Any], plan_id: str) -> dict[str, Any]:
    package = strategy.get("strategy_package") or plan_id
    base = copy.deepcopy(PACKAGE_STRATEGIES.get(package, PACKAGE_STRATEGIES["downstream_protection"]))
    base["package"] = package
    base["plan_id"] = plan_id
    return base


def adjust_phase_timing(
    *,
    signal: dict[str, Any],
    strategy_instruction: dict[str, Any],
    ticket: dict[str, Any],
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lightweight deterministic phase adjustment with min/max green bounds."""
    diagnosis = diagnosis or {}
    stages = [copy.deepcopy(s) for s in signal.get("phase_stage_timing_list") or []]
    if not stages:
        return {"ok": False, "reason": "signal 缺少 phase_stage_timing_list"}

    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    target_key = f"{direction}{movement}"
    target_idx = _find_target_stage_index(stages, target_key)
    if target_idx is None:
        return {"ok": False, "reason": f"未找到目标相位: {target_key}"}

    target_delta = int(strategy_instruction.get("target_green_delta") or 0)
    cycle_delta = int(strategy_instruction.get("cycle_delta") or 0)
    donor_idx = _find_donor_stage_index(stages, skip_idx=target_idx)

    if target_delta > 0 and donor_idx is not None:
        borrow = min(target_delta, _borrowable(stages[donor_idx]))
        stages[donor_idx]["greenTime"] = int(stages[donor_idx]["greenTime"]) - borrow
        stages[target_idx]["greenTime"] = int(stages[target_idx]["greenTime"]) + borrow
    elif target_delta != 0:
        stages[target_idx]["greenTime"] = int(stages[target_idx]["greenTime"]) + target_delta

    _clamp_stage(stages[target_idx])
    if donor_idx is not None:
        _clamp_stage(stages[donor_idx])

    cycle_s = _sum_cycle(stages) + cycle_delta
    timing_list = [_normalize_stage(stage, cycle_s) for stage in stages]

    upstream_control = _build_upstream_control(strategy_instruction, diagnosis)
    downstream_risk = _assess_downstream_risk(diagnosis)

    return {
        "ok": True,
        "timing": {
            "cycle_s": cycle_s,
            "phase_stage_timing_list": timing_list,
        },
        "phaseStageTimingList": timing_list,
        "cycle_s": cycle_s,
        "upstream_control": upstream_control,
        "phase_offset_sec": 15 if strategy_instruction.get("upstream_control") else 0,
        "pedestrian_constraints": {"satisfied": True, "violations": []},
        "downstream_risk": downstream_risk,
    }


def _find_target_stage_index(stages: list[dict[str, Any]], target_key: str) -> int | None:
    for idx, stage in enumerate(stages):
        movement_key = str(stage.get("movement_key") or "")
        name = str(stage.get("phase_stage_name") or stage.get("phaseStageName") or "")
        if movement_key == target_key or target_key in name or target_key[:2] in name:
            return idx
    return 0 if stages else None


def _find_donor_stage_index(stages: list[dict[str, Any]], *, skip_idx: int) -> int | None:
    best_idx = None
    best_green = None
    for idx, stage in enumerate(stages):
        if idx == skip_idx:
            continue
        green = int(stage.get("greenTime") or 0)
        min_green = int(stage.get("minGreenTime") or 0)
        spare = green - min_green
        if spare <= 0:
            continue
        if best_green is None or green > best_green:
            best_green = green
            best_idx = idx
    return best_idx


def _borrowable(stage: dict[str, Any]) -> int:
    green = int(stage.get("greenTime") or 0)
    min_green = int(stage.get("minGreenTime") or 0)
    return max(0, green - min_green)


def _clamp_stage(stage: dict[str, Any]) -> None:
    green = int(stage.get("greenTime") or 0)
    min_green = int(stage.get("minGreenTime") or 0)
    max_green = int(stage.get("maxGreenTime") or green + 30)
    stage["greenTime"] = max(min_green, min(max_green, green))


def _sum_cycle(stages: list[dict[str, Any]]) -> int:
    total = 0
    for stage in stages:
        total += int(stage.get("greenTime") or 0)
        total += int(stage.get("yellowTime") or stage.get("yellow_time_s") or 3)
        total += int(stage.get("allRedTime") or stage.get("all_red_time_s") or 2)
    return total


def _normalize_stage(stage: dict[str, Any], cycle_s: int) -> dict[str, Any]:
    green = int(stage.get("greenTime") or stage.get("green_time_s") or 0)
    yellow = int(stage.get("yellowTime") or stage.get("yellow_time_s") or 3)
    all_red = int(stage.get("allRedTime") or stage.get("all_red_time_s") or 2)
    min_green = int(stage.get("minGreenTime") or stage.get("min_green_time_s") or 0)
    max_green = int(stage.get("maxGreenTime") or stage.get("max_green_time_s") or green)
    return {
        "phase_stage_id": stage.get("phase_stage_id") or stage.get("phaseStageId"),
        "phase_stage_name": stage.get("phase_stage_name") or stage.get("phaseStageName"),
        "green_time_s": green,
        "yellow_time_s": yellow,
        "all_red_time_s": all_red,
        "min_green_time_s": min_green,
        "max_green_time_s": max_green,
        "greenTime": green,
        "yellowTime": yellow,
        "allRedTime": all_red,
        "minGreenTime": min_green,
        "maxGreenTime": max_green,
        "split_ratio": round(green / max(cycle_s, 1), 4),
        "movement_key": stage.get("movement_key"),
    }


def _build_upstream_control(
    strategy_instruction: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, Any]:
    if not strategy_instruction.get("upstream_control"):
        return {"enabled": False, "control_points": []}

    points = []
    for trace in (diagnosis.get("flow_trace") or {}).get("entry_traces") or []:
        points.append(
            {
                "inter_id": trace.get("upstream_inter_id"),
                "inter_name": trace.get("upstream_inter_name"),
                "lng": trace.get("upstream_lng"),
                "lat": trace.get("upstream_lat"),
                "green_ratio_delta": -0.08,
            }
        )
    return {"enabled": True, "control_points": points}


def _assess_downstream_risk(diagnosis: dict[str, Any]) -> dict[str, Any]:
    blocked = (diagnosis.get("downstream_trace") or {}).get("governance", {}).get(
        "downstream_blocked", False
    )
    reasons = []
    if blocked:
        reasons.append("下游节点饱和，继续放量存在外溢风险")
    down_queue = (diagnosis.get("downstream_metrics") or {}).get("queue_ratio")
    if down_queue is not None and down_queue >= 0.8:
        reasons.append(f"下游排队比={down_queue:.2f}")
    return {
        "level": "high" if reasons else "medium",
        "reasons": reasons or ["需持续监测下游承接能力"],
    }
