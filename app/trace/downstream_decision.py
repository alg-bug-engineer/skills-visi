"""下游承接状态唯一真源：blocked | slack | unknown。"""

from __future__ import annotations

from typing import Any

from app.metrics.traffic import THRESHOLDS


def decide_downstream_state(
    *,
    saturation: float | None,
    queue_ratio: float | None,
    spillback_threshold: float | None = None,
    sat_threshold: float | None = None,
    remaining_storage_m: float | None = None,
    direct_downstream_inter_id: str | None = None,
    direct_downstream_inter_name: str | None = None,
    missing_metrics: list[str] | None = None,
) -> dict[str, Any]:
    """输出下游单一决策对象，供诊断/机制/策略/方案/前端统一消费。"""
    spillback_threshold = spillback_threshold or THRESHOLDS["queue_ratio_warning"]
    sat_threshold = sat_threshold or THRESHOLDS["downstream_saturation_high"]
    missing = list(missing_metrics or [])
    if saturation is None and "saturation" not in missing:
        missing.append("saturation")
    if queue_ratio is None and "queue_ratio" not in missing:
        missing.append("queue_ratio")

    # 排队与饱和度双缺：指标不足，禁止伪装「有余量」或「承接受限」
    if queue_ratio is None and saturation is None:
        return {
            "decision": "unknown",
            "blocked": False,
            "unknown": True,
            "can_release": None,
            "confidence": 0.2,
            "reasons": ["downstream_queue_and_saturation_unavailable"],
            "release_guard": "downstream_metrics_unknown",
            "queue_ratio": None,
            "saturation": None,
            "remaining_storage_m": remaining_storage_m,
            "direct_downstream_inter_id": direct_downstream_inter_id,
            "direct_downstream_inter_name": direct_downstream_inter_name,
            "missing_metrics": missing,
        }

    blocked = False
    reasons: list[str] = []
    if queue_ratio is not None and queue_ratio >= spillback_threshold:
        blocked = True
        reasons.append(f"queue_ratio={queue_ratio:.2f}>={spillback_threshold}")
    if saturation is not None and saturation >= sat_threshold:
        blocked = True
        reasons.append(f"saturation={saturation:.2f}>={sat_threshold}")

    if blocked:
        decision = "blocked"
        confidence = 0.85 if saturation is not None and queue_ratio is not None else 0.7
        if not reasons:
            reasons = ["下游承接空间不足"]
    else:
        decision = "slack"
        confidence = 0.8
        if saturation is None or "green_utilization" in missing:
            confidence = 0.72
            reasons.append("下游排队较短")
            if remaining_storage_m is not None and remaining_storage_m > 50:
                reasons.append("下游剩余蓄车空间较大")
            reasons.append("部分关键指标缺失，承接余量结论为初步判断")
        else:
            reasons.append("下游排队与饱和度均未达阻塞阈值")

    return {
        "decision": decision,
        "blocked": blocked,
        "unknown": False,
        "can_release": not blocked,
        "confidence": confidence,
        "reasons": reasons,
        "release_guard": "downstream_blocked" if blocked else "downstream_has_slack",
        "queue_ratio": queue_ratio,
        "saturation": saturation,
        "remaining_storage_m": remaining_storage_m,
        "direct_downstream_inter_id": direct_downstream_inter_id,
        "direct_downstream_inter_name": direct_downstream_inter_name,
        "missing_metrics": missing,
    }
