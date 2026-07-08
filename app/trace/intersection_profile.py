"""Build intersection metric profiles aligned with flow-trace visualization."""

from __future__ import annotations

from typing import Any

from app.metrics.traffic import (
    assess_overflow_risk,
    calculate_queue_ratio,
    calculate_saturation,
    level_of_service,
)


def build_intersection_profile(node: dict[str, Any]) -> dict[str, Any]:
    # 显式标记指标不可用时，禁止用缺省 0 伪造承接判断（BUG-004）。
    metrics_unavailable = node.get("metrics_available") is False
    queue_ratio = calculate_queue_ratio(
        node.get("queue_length_m", 0),
        node.get("storage_length_m", 0),
    )
    saturation = calculate_saturation(
        node.get("volume_vph", 0),
        node.get("capacity_vph", 0),
    )
    if metrics_unavailable:
        queue_ratio = None
        saturation = None
    movement = node.get("movement_label") or "直行"
    profile = {
        "inter_id": node.get("inter_id"),
        "inter_name": node.get("inter_name"),
        "role": node.get("role", "target"),
        "lng": node.get("lng"),
        "lat": node.get("lat"),
        "receiving_dir8": node.get("receiving_dir8"),
        "receiving_label": node.get("receiving_label"),
        "metrics_available": not metrics_unavailable,
        "metrics_reason": node.get("metrics_reason") if metrics_unavailable else None,
        "metrics": {
            "avg_delay_s": None if metrics_unavailable else node.get("avg_delay_s"),
            "saturation": saturation,
            "saturation_rate": saturation,
            "avg_queue_m": None if metrics_unavailable else node.get("queue_length_m"),
            "max_queue_m": None if metrics_unavailable else node.get("queue_length_m"),
            "queue_storage_ratio_max": queue_ratio,
            "spillback_risk_max": queue_ratio,
            "level_of_service": None if metrics_unavailable else level_of_service(saturation),
            "green_utilization": None if metrics_unavailable else node.get("green_utilization"),
            "stop_count": None if metrics_unavailable else node.get("stop_count"),
            "time_series_trend": node.get("time_series_trend"),
        },
        "by_turn": node.get("by_turn")
        or [
            {
                "label": movement,
                "turn_saturation": saturation,
                "green_utilization": node.get("green_utilization"),
                "flow_vph": node.get("volume_vph"),
                "queue_ratio": queue_ratio,
            }
        ],
        "overflow_verification": assess_overflow_risk(queue_ratio),
        "remaining_storage_m": (
            None
            if metrics_unavailable
            else max(
                0.0,
                float(node.get("storage_length_m") or 0) - float(node.get("queue_length_m") or 0),
            )
        ),
    }
    return profile
