from __future__ import annotations

REQUIRED_FIELDS = {
    "object_scope",
    "scenario_tags",
    "problem_set",
    "target_priority",
    "strategy_package",
    "hard_constraints",
    "trigger_exit_rules",
    "fallback_plan",
    "explanation",
}


def validate_strategy_instruction(instruction: dict) -> list[str]:
    return sorted(REQUIRED_FIELDS - set(instruction))
