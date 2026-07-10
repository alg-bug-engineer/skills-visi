"""精简成因分析 LLM 输入：仅权威数值 + 评分，禁止灌入完整 diagnosis 原文。"""

from __future__ import annotations

from typing import Any


def _top_movements(metrics: dict[str, Any], limit: int = 4) -> list[dict[str, Any]]:
    rows = metrics.get("by_movement") or []
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "movement": row.get("movement"),
                "saturation": row.get("saturation"),
                "green_utilization": row.get("green_utilization"),
                "level": row.get("level"),
            }
        )
    out.sort(key=lambda x: float(x.get("saturation") or 0), reverse=True)
    return out[:limit]


def build_llm_cause_context(
    diagnosis: dict[str, Any],
    cause_scores: dict[str, Any],
    ticket: dict[str, Any],
    similar_cases: list[dict[str, Any]],
    user_experience_refs: list[dict[str, Any]],
    evidence_summary: dict[str, Any],
) -> dict[str, Any]:
    metrics = diagnosis.get("metrics") or {}
    downstream_diag = diagnosis.get("downstream_diagnosis") or {}
    bottleneck = diagnosis.get("bottleneck_analysis") or {}

    return {
        "ticket": {
            "inter_id": ticket.get("inter_id"),
            "intersection_name": ticket.get("intersection_name"),
            "direction": ticket.get("direction"),
            "movement": ticket.get("movement"),
            "time_range": ticket.get("time_range"),
            "period": ticket.get("period"),
            "problem_type": ticket.get("problem_type"),
        },
        "metrics_authoritative": {
            "queue_ratio": metrics.get("queue_ratio"),
            "saturation": metrics.get("saturation") if metrics.get("saturation") is not None else metrics.get("saturation_rate"),
            "green_utilization": metrics.get("green_utilization"),
            "los": metrics.get("los"),
            "queue_length_m": metrics.get("queue_length_m"),
            "storage_length_m": metrics.get("storage_length_m"),
            "imbalance_index": metrics.get("imbalance_index"),
            "top_movements": _top_movements(metrics),
        },
        "overflow_verification": {
            "verified": (diagnosis.get("overflow_verification") or {}).get("verified"),
            "risk_level": (diagnosis.get("overflow_verification") or {}).get("risk_level"),
            "message": (diagnosis.get("overflow_verification") or {}).get("message"),
        },
        "downstream_diagnosis": {
            "scenario": downstream_diag.get("scenario"),
            "release_answer": downstream_diag.get("release_answer"),
            "narrative": downstream_diag.get("narrative"),
        },
        "bottleneck_type": bottleneck.get("bottleneck_type"),
        "evidence_summary": evidence_summary,
        "cause_scores": cause_scores,
        "similar_cases_brief": [
            {
                "title": c.get("title") or c.get("case_title"),
                "similarity": c.get("similarity"),
                "measure": c.get("measure") or c.get("key_measure"),
            }
            for c in (similar_cases or [])[:2]
            if isinstance(c, dict)
        ],
        "user_experience_brief": [
            {
                "summary": r.get("summary") or r.get("content"),
                "intersection_name": r.get("intersection_name"),
            }
            for r in (user_experience_refs or [])[:2]
            if isinstance(r, dict)
        ],
        "metric_format_rules": {
            "saturation": "decimal 0-1+ (e.g. 0.87), NOT percent",
            "green_utilization": "decimal 0-1+ (e.g. 0.57), NOT percent",
            "queue_ratio": "decimal ratio vs storage length",
        },
    }
