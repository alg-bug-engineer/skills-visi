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
            "recommended_plan_id": plan_artifact.get("recommended_plan_id")
            or (plan_artifact.get("recommended") or {}).get("plan_id"),
            "recommendation": plan_artifact.get("recommendation"),
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
        "pipeline_complete": result.get("pipeline_complete", False),
        "diagnosis_ticket": result.get("diagnosis_ticket"),
        "phases": phases,
        "plan": plan_block,
        "phase_results": phase_results,
    }


def build_public_snapshot(
    *,
    trace_id: str,
    artifacts: dict[str, Any],
    results: list[dict[str, Any]],
    task: dict[str, Any] | None = None,
    completed: bool | None = None,
    pipeline_complete: bool = False,
) -> dict[str, Any]:
    """基于"截至当前"的 artifacts/results 构建公开快照（流式逐 phase 复用）。

    与 build_public_run_response 同构；phases/plan 随 artifacts 增长而逐步补齐。
    """
    intent_artifact = (artifacts or {}).get("intent_understanding") or {}
    diagnosis_ticket = intent_artifact.get("diagnosis_ticket")
    if not diagnosis_ticket and task:
        diagnosis_ticket = task.get("diagnosis_ticket")

    result = {
        "trace_id": trace_id,
        "completed": completed,
        "pipeline_complete": pipeline_complete,
        "diagnosis_ticket": diagnosis_ticket,
        "artifacts": artifacts or {},
        "results": results or [],
    }
    return build_public_run_response(result)


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
