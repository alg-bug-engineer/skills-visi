from __future__ import annotations

from typing import Any


def select_strategy_package(cause: dict[str, Any], diagnosis: dict[str, Any]) -> str:
    if cause.get("arterial_coordination_needed") or diagnosis.get("arterial_analysis", {}).get(
        "need_upstream_metering"
    ):
        return "arterial_coordination"
    governance = diagnosis.get("downstream_trace", {}).get("governance", {})
    if governance.get("downstream_blocked"):
        return "downstream_protection"
    bottleneck = diagnosis.get("bottleneck_analysis", {})
    if bottleneck.get("bottleneck_type") == "local_release":
        return "incremental_release"
    return "downstream_protection"


def extract_case_lessons(cause: dict[str, Any]) -> dict[str, Any]:
    cases = cause.get("similar_cases", [])
    return {
        "failure_lesson": "单点加绿后下游排队继续增长" if cases else None,
        "success_lesson": "上游控流+目标小步释放+下游保护后外溢风险下降" if cases else None,
        "matched_count": len(cases),
    }
