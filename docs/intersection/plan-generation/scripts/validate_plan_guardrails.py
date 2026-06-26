from __future__ import annotations


def validate_plan_guardrails(plan: dict, constraints: dict) -> list[str]:
    errors = []
    max_cycle = int(constraints.get("max_cycle_s", 150))
    if int(plan.get("cycle_s", 0)) > max_cycle:
        errors.append("cycle_exceeds_max")
    if not plan.get("rollback_condition"):
        errors.append("missing_rollback_condition")
    return errors
