from __future__ import annotations

from typing import Any


def generate_timing_plan(
    strategy_instruction: dict[str, Any],
    task: dict[str, Any],
    signal: dict[str, Any],
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build PlanDraft shell before deterministic phase adjustment."""
    diagnosis = diagnosis or {}
    context = _as_dict(task.get("context"))
    constraints = _as_dict(task.get("constraints"))
    cycle_s = _first_int(
        signal.get("current_cycle_s"),
        constraints.get("default_cycle_s"),
        120,
    )
    return {
        "plan_id": f"intersection-plan-{signal.get('inter_id') or 'UNKNOWN'}",
        "strategy": str(strategy_instruction.get("strategy") or strategy_instruction.get("package")),
        "cycle_s": cycle_s,
        "rollback_condition": _rollback_condition(strategy_instruction),
        "parameters": {
            "target_periods": _extract_target_periods(strategy_instruction, diagnosis, context),
            "signal_inter_id": signal.get("inter_id"),
        },
        "validation_errors": [],
    }


def _extract_target_periods(
    strategy_instruction: dict[str, Any],
    diagnosis: dict[str, Any],
    context: dict[str, Any],
) -> list[str]:
    ticket_period = context.get("time_range") or context.get("target_periods")
    if isinstance(ticket_period, str) and ticket_period:
        return [ticket_period]
    if isinstance(ticket_period, list) and ticket_period:
        return [str(item) for item in ticket_period if item]
    for value in (
        strategy_instruction.get("target_periods"),
        strategy_instruction.get("applicable_periods"),
    ):
        if isinstance(value, list) and value:
            return [str(item) for item in value if item is not None]
    target = diagnosis.get("target") or {}
    if target.get("time_range"):
        return [str(target["time_range"])]
    return []


def _rollback_condition(strategy_instruction: dict[str, Any]) -> str:
    for value in (
        strategy_instruction.get("rollback_condition"),
        _as_dict(strategy_instruction.get("trigger_exit_rules")).get("rollback_condition"),
    ):
        if value:
            return str(value)
    return "连续两个统计周期关键指标恶化时回滚至原方案"


def _first_int(*values: Any) -> int:
    for value in values:
        parsed = _to_float(value)
        if parsed is not None:
            return int(round(parsed))
    return 0


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
