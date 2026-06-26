from __future__ import annotations

from typing import Any


def calculate_phase_splits(cycle_s: int, critical_green_ratio: float) -> dict[str, int]:
    critical = round(cycle_s * critical_green_ratio)
    return {"critical_phase_s": critical, "other_phases_total_s": max(0, cycle_s - critical)}


def _ratio(value: float, base: float) -> float:
    return round(value / base, 4) if base else 0.0


def generate_timing_plan(
    strategy_instruction: dict[str, Any],
    task: dict[str, Any],
    profile: dict[str, Any] | None = None,
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    constraints = task.get("constraints", {}) or {}
    metrics = task.get("metrics", {}) or {}
    profile = profile or {}
    diagnosis = diagnosis or {}
    base_cycle = int(constraints.get("current_cycle_s", 90))
    max_cycle = int(constraints.get("max_cycle_s", 150))
    traffic_state = profile.get("traffic_state", {}) if isinstance(profile.get("traffic_state"), dict) else {}
    saturation = float(traffic_state.get("saturation", _ratio(float(metrics.get("volume", 0)), float(metrics.get("capacity", 1) or 1))))
    if "spillback" in diagnosis.get("priority_order", []):
        max_cycle = max(max_cycle, 160)
    cycle = min(max_cycle, max(70, round(base_cycle * (1 + max(0, saturation - 0.85) * 0.35))))
    strategy_package = strategy_instruction.get("strategy_package", {}) or {}
    strategy = strategy_instruction.get("strategy") or strategy_package.get("name", "常态监测与微调")
    return {
        "plan_id": f"draft-{task.get('task_id', 'task')}",
        "strategy": strategy,
        "cycle_s": cycle,
        "critical_green_ratio": 0.48 if "绿波" in strategy else 0.54 if saturation >= 0.9 else 0.45,
        "offset_policy": "recalculate_corridor_offsets" if "绿波" in strategy else "keep_or_local_adjust",
        "release_mode": "human_confirmed",
        "rollback_condition": strategy_instruction.get("trigger_exit_rules", {}).get(
            "trigger",
            "平均延误或排队连续 2 个评价窗口恶化超过 10%",
        ),
        "parameters": {
            "strategy_actions": strategy_package.get("actions", strategy_instruction.get("actions", [])),
            "hard_constraints": strategy_instruction.get("hard_constraints", []),
            "fallback_plan": strategy_instruction.get("fallback_plan", {}),
        },
    }
