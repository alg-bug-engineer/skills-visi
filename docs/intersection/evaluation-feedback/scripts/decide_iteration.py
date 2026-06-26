from __future__ import annotations


def decide_iteration(meets_target: bool, risk_worsened: bool = False) -> str | None:
    if meets_target and not risk_worsened:
        return None
    if risk_worsened:
        return "plan_generation"
    return "control_strategy"
