"""Build frontend-safe API responses without exposing internal skill identifiers."""

from __future__ import annotations

from typing import Any

from app.trace.axis_roads import build_axis_roads
from app.trace.act_map_enrichment import (
    enrich_intent_spatial_scene as enrich_intent_spatial_scene_contract,
    enrich_map_scenes,
)

PHASE_ARTIFACT_KEYS: dict[str, str] = {
    "intent_understanding": "intent",
    "data_analysis_diagnosis": "diagnosis",
    "cause_analysis": "cause",
    "strategy_generation": "strategy",
    "plan_generation": "plan",
}


def _enrich_intent_spatial_scene(
    phases: dict[str, Any], root_ticket: dict[str, Any] | None = None
) -> None:
    intent = phases.get("intent")
    if not isinstance(intent, dict):
        return
    scene = intent.get("spatial_scene")
    if not isinstance(scene, dict):
        return
    diagnosis = phases.get("diagnosis") if isinstance(phases.get("diagnosis"), dict) else {}
    map_scenes = diagnosis.get("map_scenes") if isinstance(diagnosis.get("map_scenes"), dict) else {}
    ch = map_scenes.get("channelization_map") if isinstance(map_scenes.get("channelization_map"), dict) else {}
    links = ch.get("links") if isinstance(ch.get("links"), list) else []
    inter_name = (scene.get("target") or {}).get("inter_name") or intent.get("diagnosis_ticket", {}).get(
        "intersection_name"
    )
    axis = build_axis_roads(intersection_name=inter_name, link_rows=links)
    if axis.get("available"):
        scene["axis_roads"] = axis
    topology = diagnosis.get("topology") if isinstance(diagnosis.get("topology"), dict) else {}
    ticket = intent.get("diagnosis_ticket") if isinstance(intent.get("diagnosis_ticket"), dict) else (root_ticket or {})
    raw_source = str(diagnosis.get("data_source") or "postgresql")
    source = "postgresql" if raw_source in {"pg", "postgres", "postgresql"} else raw_source
    enrich_intent_spatial_scene_contract(
        intent=intent,
        ticket=ticket,
        topology=topology,
        source=source,
    )
    intent["spatial_scene"] = intent.get("spatial_scene") or scene
    phases["intent"] = intent


def build_public_run_response(result: dict[str, Any]) -> dict[str, Any]:
    artifacts = result.get("artifacts") or {}
    phases = {
        public_key: artifacts[skill_key]
        for skill_key, public_key in PHASE_ARTIFACT_KEYS.items()
        if skill_key in artifacts
    }
    _enrich_intent_spatial_scene(
        phases,
        result.get("diagnosis_ticket") if isinstance(result.get("diagnosis_ticket"), dict) else {},
    )

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
            "trial_loop": plan_artifact.get("trial_loop"),
            "plan_status": plan_artifact.get("plan_status")
            or (plan_artifact.get("recommended") or {}).get("plan_status"),
            "executable": plan_artifact.get("executable")
            if plan_artifact.get("executable") is not None
            else (plan_artifact.get("recommended") or {}).get("executable"),
            "signal_source": plan_artifact.get("signal_source"),
            "optimizer_engine": plan_artifact.get("optimizer_engine"),
            "all_guardrails_passed": plan_artifact.get("all_guardrails_passed"),
        }

    enrich_map_scenes(
        ticket=result.get("diagnosis_ticket") if isinstance(result.get("diagnosis_ticket"), dict) else {},
        phases=phases,
        plan_block=plan_block,
    )

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
        "healthy": result.get("healthy"),
        "completion_status": result.get("completion_status"),
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
    healthy: bool | None = None,
    completion_status: str | None = None,
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
        "healthy": healthy,
        "completion_status": completion_status,
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
