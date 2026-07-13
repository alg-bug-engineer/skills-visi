"""Traffic metric calculations adapted from references/intersection/scene-cognition."""

from __future__ import annotations

from typing import Any


THRESHOLDS = {
    "queue_ratio_warning": 0.8,
    "queue_ratio_spillback": 1.0,
    "saturation_high": 0.8,
    "saturation_oversaturation": 0.9,
    "green_utilization_low": 0.6,
    "green_utilization_high": 0.85,
    # 与 assess_downstream_capacity 默认 sat_threshold=0.85 对齐，避免 0.80 误判接不住（BUG-007）
    "downstream_saturation_high": 0.85,
}


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_queue_ratio(queue_length_m: float, storage_length_m: float) -> float | None:
    storage = to_float(storage_length_m)
    if storage <= 0:
        return None
    return round(to_float(queue_length_m) / storage, 4)


def calculate_saturation(volume: float, capacity: float) -> float:
    capacity = to_float(capacity)
    if capacity <= 0:
        return 0.0
    return round(to_float(volume) / capacity, 4)


def level_of_service(saturation: float) -> str:
    s = to_float(saturation)
    if s <= 0.60:
        return "A"
    if s <= 0.70:
        return "B"
    if s <= 0.80:
        return "C"
    if s <= 0.90:
        return "D"
    if s <= 1.00:
        return "E"
    return "F"


def assess_overflow_risk(queue_ratio: float | None) -> dict[str, Any]:
    if queue_ratio is None:
        return {
            "verified": False,
            "risk_level": "unknown",
            "message": "缺少排队长度或进口道蓄车长度，无法验证溢出",
        }
    ratio = to_float(queue_ratio)
    if ratio >= THRESHOLDS["queue_ratio_spillback"]:
        return {
            "verified": True,
            "risk_level": "high",
            "message": "排队已突破进口道空间边界，存在明确溢出风险",
        }
    if ratio >= THRESHOLDS["queue_ratio_warning"]:
        return {
            "verified": True,
            "risk_level": "warning",
            "message": "排队接近进口道空间边界，进入溢出预警状态",
        }
    return {
        "verified": True,
        "risk_level": "low",
        "message": "排队尚在进口道可容纳范围内，溢出风险较低",
    }


def classify_release_bottleneck(
    *,
    target_saturation: float,
    target_green_utilization: float,
    downstream_queue_ratio: float | None,
    downstream_saturation: float,
) -> dict[str, Any]:
    """区分本路口放不出去 vs 下游接不住。"""
    high_demand = (
        to_float(target_saturation) >= THRESHOLDS["saturation_high"]
        and to_float(target_green_utilization) >= THRESHOLDS["green_utilization_high"]
    )
    downstream_blocked = (
        (downstream_queue_ratio is not None and downstream_queue_ratio >= THRESHOLDS["queue_ratio_warning"])
        or to_float(downstream_saturation) >= THRESHOLDS["downstream_saturation_high"]
    )

    if high_demand and downstream_blocked:
        return {
            "bottleneck_type": "downstream_capacity",
            "label": "下游承接不足",
            "can_simple_add_green": False,
            "reason": "目标方向需求高且下游承接空间不足，不宜简单加绿",
        }
    if high_demand and not downstream_blocked:
        return {
            "bottleneck_type": "local_release",
            "label": "本路口放行不足",
            "can_simple_add_green": True,
            "reason": "目标方向需求高但下游仍有承接空间，可考虑适度增加有效绿",
        }
    if not high_demand and to_float(target_green_utilization) < THRESHOLDS["green_utilization_low"]:
        return {
            "bottleneck_type": "downstream_or_channelization",
            "label": "绿灯给了也用不上",
            "can_simple_add_green": False,
            "reason": "排队高但绿灯利用率低，可能存在下游阻塞、出口不畅或检测异常",
        }
    return {
        "bottleneck_type": "mixed",
        "label": "复合瓶颈",
        "can_simple_add_green": False,
        "reason": "需结合上下游拓扑与连续时序进一步判断",
    }
