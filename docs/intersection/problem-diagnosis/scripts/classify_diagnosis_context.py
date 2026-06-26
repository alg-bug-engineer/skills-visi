"""Deterministic problem_source and control_improvement_ceiling classification."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import importlib.util
import sys


def _load_config_module():
    common_dir = Path(__file__).resolve().parents[2] / "common"
    if str(common_dir) not in sys.path:
        sys.path.insert(0, str(common_dir))
    spec = importlib.util.spec_from_file_location("intersection_load_config", common_dir / "load_config.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 intersection/common/load_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_cfg = _load_config_module()


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _triggered_items(checklist_queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in checklist_queries if item.get("triggered")]


def _high_leverage_dynamic_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dynamic_codes = {
        "spillback",
        "service_imbalance",
        "empty_green",
        "green_wave_break",
    }
    return [
        issue
        for issue in issues
        if issue.get("issue_code") in dynamic_codes and issue.get("control_leverage") in {"high", "medium"}
    ]


def _apply_scene_type_priority(
    issues: list[dict[str, Any]],
    scene_type: str,
) -> list[dict[str, Any]]:
    rules = _cfg.load_scene_type_rules()
    spec = (rules.get("scene_types") or {}).get(scene_type) or {}
    diagnosis = spec.get("diagnosis") or {}
    boost = set(diagnosis.get("priority_boost") or [])
    deprioritize = set(diagnosis.get("deprioritize") or [])
    adjusted: list[dict[str, Any]] = []
    for issue in issues:
        item = dict(issue)
        code = str(item.get("issue_code") or "")
        score = _as_float(item.get("score"))
        if code in boost:
            score = min(1.0, score + 0.08)
        if code in deprioritize:
            score = max(0.0, score - 0.08)
        item["score"] = round(score, 3)
        adjusted.append(item)
    return sorted(adjusted, key=lambda row: row.get("score", 0), reverse=True)


def classify_diagnosis_context(
    profile: dict[str, Any],
    diagnosis: dict[str, Any],
    checklist_queries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return problem_source, control_improvement_ceiling, and scene_type_context."""
    items = checklist_queries or []
    issues = list(diagnosis.get("issues") or [])
    scene_type = _cfg.resolve_scene_type(profile)
    scene_rules = (_cfg.load_scene_type_rules().get("scene_types") or {}).get(scene_type) or {}
    scene_diagnosis = scene_rules.get("diagnosis") or {}

    static_triggered = [item for item in _triggered_items(items) if item.get("category") == "static"]
    dynamic_triggered = [item for item in _triggered_items(items) if item.get("category") == "dynamic"]
    cause_scores = diagnosis.get("cause_scores") or {}
    top_cause = max(cause_scores.items(), key=lambda row: row[1])[0] if cause_scores else "control"
    issue_codes = {str(issue.get("issue_code")) for issue in issues if issue.get("issue_code") != "stable"}
    tags = set(profile.get("context_tags") or [])

    problem_source = "control_parameter_mismatch"
    control_ceiling = str(scene_diagnosis.get("control_ceiling_default") or "medium")

    source_rules = _cfg.load_scene_type_rules().get("problem_source_rules") or {}
    if not _triggered_items(items) and (not issues or issue_codes == set()):
        stable = source_rules.get("stable") or {}
        problem_source = stable.get("problem_source", "stable_operation")
        control_ceiling = stable.get("control_ceiling", "none")
    elif len(static_triggered) >= 2 and not _high_leverage_dynamic_issues(issues):
        static_rule = source_rules.get("static_supply_constraint") or {}
        problem_source = static_rule.get("problem_source", "static_supply_constraint")
        control_ceiling = static_rule.get("control_ceiling", scene_diagnosis.get("static_dominant_ceiling", "low"))
    elif issue_codes.intersection({"external_disturbance", "downstream_blockage"}) or tags.intersection(
        {"construction", "incident", "illegal_parking", "temporary_parking", "on_street_parking", "driveway_interference", "bus_stop", "strong_attractor"}
    ):
        external = source_rules.get("external_disturbance") or {}
        problem_source = external.get("problem_source", "external_disturbance")
        control_ceiling = external.get("control_ceiling", "none")
    elif top_cause == "order" or issue_codes.intersection({"public_complaint", "external_disturbance"}):
        order_rule = source_rules.get("traffic_order") or {}
        problem_source = order_rule.get("problem_source", "traffic_order_interference")
        control_ceiling = order_rule.get("control_ceiling", "low")
    elif dynamic_triggered and _as_float(cause_scores.get("control")) >= 0.35:
        control_rule = source_rules.get("control_mismatch") or {}
        problem_source = control_rule.get("problem_source", "control_parameter_mismatch")
        control_ceiling = control_rule.get("control_ceiling", scene_diagnosis.get("control_ceiling_default", "high"))
    elif scene_diagnosis.get("problem_source_hint"):
        problem_source = str(scene_diagnosis["problem_source_hint"])

    signal_scores = {"high": 3, "medium": 2, "low": 1, "none": 0}
    leverage_ceiling = {3: "high", 2: "medium", 1: "low", 0: "none"}[
        max((signal_scores.get(str(issue.get("control_leverage")), 0) for issue in issues), default=0)
    ]
    ceiling_rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
    if ceiling_rank.get(leverage_ceiling, 0) < ceiling_rank.get(control_ceiling, 0):
        control_ceiling = leverage_ceiling

    priority_order = [issue["issue_code"] for issue in _apply_scene_type_priority(issues, scene_type)]
    return {
        "problem_source": problem_source,
        "control_improvement_ceiling": control_ceiling,
        "scene_type": scene_type,
        "scene_type_context": {
            "priority_boost": scene_diagnosis.get("priority_boost") or [],
            "deprioritize": scene_diagnosis.get("deprioritize") or [],
            "static_triggered_count": len(static_triggered),
            "dynamic_triggered_count": len(dynamic_triggered),
        },
        "priority_order": priority_order,
        "issues": _apply_scene_type_priority(issues, scene_type),
    }
