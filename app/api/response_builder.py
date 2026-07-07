"""Build frontend-safe API responses without exposing internal skill identifiers."""

from __future__ import annotations

from typing import Any

PHASE_ARTIFACT_KEYS: dict[str, str] = {
    "intent_understanding": "intent",
    "data_analysis_diagnosis": "diagnosis",
    "cause_analysis": "cause",
    "strategy_generation": "strategy",
    "plan_generation": "plan",
}


def build_public_run_response(result: dict[str, Any]) -> dict[str, Any]:
    artifacts = result.get("artifacts") or {}
    phases = {
        public_key: artifacts[skill_key]
        for skill_key, public_key in PHASE_ARTIFACT_KEYS.items()
        if skill_key in artifacts
    }

    plan_artifact = artifacts.get("plan_generation") or {}
    plan_block: dict[str, Any] | None = None
    if plan_artifact:
        plan_block = {
            "candidates": plan_artifact.get("candidates"),
            "recommended": plan_artifact.get("recommended"),
            "rollback_conditions": plan_artifact.get("rollback_conditions"),
            "signal_source": plan_artifact.get("signal_source"),
            "optimizer_engine": plan_artifact.get("optimizer_engine"),
            "all_guardrails_passed": plan_artifact.get("all_guardrails_passed"),
        }

    phase_results = [
        {
            "phase": item.get("phase"),
            "success": item.get("success"),
            "duration_ms": item.get("duration_ms"),
            "errors": item.get("errors") or [],
        }
        for item in result.get("results") or []
    ]

    return {
        "trace_id": result.get("trace_id"),
        "completed": result.get("completed"),
        "diagnosis_ticket": result.get("diagnosis_ticket"),
        "phases": phases,
        "plan": plan_block,
        "phase_results": phase_results,
    }


def build_public_skill_catalog(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "display_name": skill.get("display_name"),
            "phase": skill.get("phase"),
            "version": skill.get("version"),
            "description": skill.get("description"),
            "enabled": skill.get("enabled"),
        }
        for skill in skills
    ]
