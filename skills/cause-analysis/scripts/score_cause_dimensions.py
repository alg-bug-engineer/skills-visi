"""Deterministic six-dimension cause scoring aligned with diagnosis_checklist."""

from __future__ import annotations

from typing import Any

from app.data.intersection_load_config import threshold

DIMENSIONS = ("demand", "supply", "control", "order", "event", "coordination")

DIMENSION_LABELS = {
    "demand": "交通需求压力",
    "supply": "通行供给不足",
    "control": "信号控制不当",
    "order": "交通秩序干扰",
    "event": "事件与阻塞",
    "coordination": "协调联动不足",
}


def score_cause_dimensions(
    diagnosis: dict[str, Any],
    *,
    task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task = task or {}
    metrics = diagnosis.get("metrics") or {}
    downstream = diagnosis.get("downstream_metrics") or {}
    arterial = diagnosis.get("arterial_analysis") or {}
    bottleneck = diagnosis.get("bottleneck_analysis") or {}
    downstream_trace = diagnosis.get("downstream_trace") or {}
    pg_metrics = (task.get("metrics") or {}) if isinstance(task.get("metrics"), dict) else {}

    scores = {dim: 0.0 for dim in DIMENSIONS}
    issue_flags: list[dict[str, Any]] = []

    saturation = float(metrics.get("saturation") or pg_metrics.get("saturation") or 0)
    queue_ratio = float(metrics.get("queue_ratio") or 0)
    green_util = float(metrics.get("green_utilization") or pg_metrics.get("green_utilization") or 0)
    imbalance = float(pg_metrics.get("imbalance_index") or metrics.get("imbalance_index") or 0)
    spillback_risk = float(pg_metrics.get("spillback_risk") or 0)

    if saturation >= threshold("saturation.high"):
        scores["demand"] += 0.45
        issue_flags.append(_flag("oversaturation", "demand", saturation))
    if queue_ratio >= threshold("queue.queue_storage_ratio_high"):
        scores["demand"] += 0.35
        issue_flags.append(_flag("queue_pressure", "demand", queue_ratio))

    if bottleneck.get("bottleneck_type") == "local_release":
        scores["supply"] += 0.25
    channel_rows = (task.get("pg_raw") or {}).get("channelization") or []
    if len(channel_rows) <= 2:
        scores["supply"] += 0.15
        issue_flags.append(_flag("limited_channelization", "supply", len(channel_rows)))

    if green_util and green_util < threshold("green.low_utilization_diagnosis"):
        scores["control"] += 0.4
        issue_flags.append(_flag("empty_green", "control", green_util))
    if imbalance >= threshold("imbalance.diagnosis"):
        scores["control"] += 0.35
        issue_flags.append(_flag("service_imbalance", "control", imbalance))
    if spillback_risk >= threshold("spillback.risk_high"):
        scores["control"] += 0.25
        issue_flags.append(_flag("spillback", "control", spillback_risk))

    complaints = ((task.get("pg_raw") or {}).get("complaints") or [])
    if complaints:
        scores["order"] += 0.4
        issue_flags.append(_flag("public_complaint", "order", len(complaints)))

    if downstream_trace.get("governance", {}).get("downstream_blocked"):
        scores["event"] += 0.45
        issue_flags.append(_flag("downstream_blockage", "event", 1))
    if float(downstream.get("queue_ratio") or 0) >= threshold("queue.queue_storage_ratio_high"):
        scores["event"] += 0.35

    if arterial.get("need_upstream_metering") or diagnosis.get("downstream_diagnosis", {}).get(
        "release_answer"
    ) == "下游接不住":
        scores["coordination"] += 0.45
        issue_flags.append(_flag("arterial_coordination", "coordination", 1))
    if bottleneck.get("bottleneck_type") == "downstream_capacity":
        scores["coordination"] += 0.3

    scores = {dim: round(min(score, 1.0), 4) for dim, score in scores.items()}
    ranked = sorted(
        (
            {
                "dimension": dim,
                "label": DIMENSION_LABELS[dim],
                "score": scores[dim],
            }
            for dim in DIMENSIONS
        ),
        key=lambda item: item["score"],
        reverse=True,
    )
    primary_dimension = ranked[0]["dimension"] if ranked else "control"

    return {
        "scores": scores,
        "ranked_dimensions": ranked,
        "primary_dimension": primary_dimension,
        "issue_flags": issue_flags,
        "scoring_method": "deterministic_thresholds",
    }


def build_cause_ranking_from_scores(
    cause_scores: dict[str, Any],
    diagnosis: dict[str, Any],
) -> list[dict[str, Any]]:
    ranked = cause_scores.get("ranked_dimensions") or []
    downstream_name = (
        (diagnosis.get("downstream_diagnosis") or {}).get("primary_downstream", {}).get("inter_name")
        or "下游信控节点"
    )
    roles = ["主因", "次因", "诱因"]
    result = []
    for idx, item in enumerate(ranked[:3]):
        if item.get("score", 0) <= 0:
            continue
        label = item.get("label") or item.get("dimension")
        if idx == 0 and item.get("dimension") == "coordination":
            cause = f"{downstream_name}承接不足，需协调联动"
        elif idx == 0 and item.get("dimension") == "demand":
            cause = "目标方向持续高需求压力"
        else:
            cause = label
        result.append({"rank": idx + 1, "cause": cause, "role": roles[min(idx, 2)]})
    if not result:
        result = [
            {
                "rank": 1,
                "cause": f"{downstream_name}承接能力不足",
                "role": "主因",
            }
        ]
    return result


def _flag(code: str, dimension: str, value: Any) -> dict[str, Any]:
    return {"issue_code": code, "dimension": dimension, "value": value}
