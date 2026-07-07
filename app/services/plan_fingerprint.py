"""Build retrieval fingerprints for plan feedback records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def build_topology_hash(topology: dict[str, Any] | None) -> str:
    if not topology:
        return ""
    upstream = sorted(
        node.get("inter_id") or node.get("name") or str(node)
        for node in (topology.get("upstream_nodes") or [])
    )
    downstream = sorted(
        node.get("inter_id") or node.get("name") or str(node)
        for node in (topology.get("downstream_nodes") or [])
    )
    payload = {
        "target_inter_id": topology.get("target_inter_id"),
        "upstream": upstream,
        "downstream": downstream,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def build_metrics_summary(diagnosis: dict[str, Any] | None) -> dict[str, Any]:
    if not diagnosis:
        return {}
    metrics = diagnosis.get("metrics") or {}
    overflow = diagnosis.get("overflow_verification") or {}
    return {
        "queue_ratio_max": overflow.get("queue_ratio") or metrics.get("queue_ratio"),
        "saturation_max": metrics.get("saturation"),
        "primary_direction": metrics.get("direction") or diagnosis.get("primary_direction"),
        "risk_level": overflow.get("risk_level"),
    }


def build_feedback_tags(
    *,
    diagnosis_ticket: dict[str, Any] | None,
    cause_analysis: dict[str, Any] | None,
    strategy_generation: dict[str, Any] | None,
) -> dict[str, Any]:
    cause = (cause_analysis or {}).get("cause_analysis") or cause_analysis or {}
    strategy = (strategy_generation or {}).get("strategy") or strategy_generation or {}
    ticket = diagnosis_ticket or {}
    return {
        "primary_cause": cause.get("primary_cause") or "",
        "strategy_applied": (
            strategy.get("recommended", [""])[0]
            if isinstance(strategy.get("recommended"), list) and strategy.get("recommended")
            else strategy.get("explanation", "")
        ),
        "spatial_structure": ", ".join(ticket.get("diagnosis_scope") or [])[:120],
        "problem_type": ticket.get("problem_type"),
    }


def fingerprint_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    score = 0.0
    if left.get("problem_type") and left.get("problem_type") == right.get("problem_type"):
        score += 2.0
    if left.get("topology_hash") and left.get("topology_hash") == right.get("topology_hash"):
        score += 3.0
    left_metrics = left.get("metrics_summary") or {}
    right_metrics = right.get("metrics_summary") or {}
    if left_metrics.get("primary_direction") == right_metrics.get("primary_direction"):
        score += 1.0
    if left_metrics.get("risk_level") and left_metrics.get("risk_level") == right_metrics.get("risk_level"):
        score += 0.5
    return score
