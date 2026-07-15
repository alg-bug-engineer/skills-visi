"""Expert release judgment for downstream signal nodes (剧本第四幕)."""

from __future__ import annotations

from typing import Any

from app.metrics.traffic import THRESHOLDS


def build_downstream_diagnosis(
    *,
    target_profile: dict[str, Any],
    downstream_trace: dict[str, Any],
    bottleneck: dict[str, Any],
    downstream_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """区分「本路口放不出去」与「下游接不住」，输出剧本第四幕判断依据。"""
    target_metrics = target_profile.get("metrics") or {}
    target_queue = target_metrics.get("queue_storage_ratio_max")
    target_sat = target_metrics.get("saturation_rate")
    target_green = target_metrics.get("green_utilization")

    downstream_nodes = downstream_trace.get("adjacent_intersections") or []
    primary = downstream_nodes[0] if downstream_nodes else {}
    down_metrics = primary.get("metrics") or {}
    down_queue = down_metrics.get("queue_storage_ratio_max")
    down_sat = down_metrics.get("saturation_rate")
    down_capacity = primary.get("capacity") or {}

    high_demand = (
        (target_sat or 0) >= THRESHOLDS["saturation_high"]
        and (target_green or 0) >= THRESHOLDS["green_utilization_high"]
    )
    high_queue = (target_queue or 0) >= THRESHOLDS["queue_ratio_warning"]
    low_green_util = (target_green or 1) < THRESHOLDS["green_utilization_low"]
    down_unknown = bool(down_capacity.get("unknown")) or (
        down_queue is None and down_sat is None and "blocked" not in down_capacity
    )
    # 有 capacity 时以 blocked 为准，避免与 assess_downstream_capacity 双口径（BUG-007）
    if down_unknown:
        downstream_blocked = False
    elif "blocked" in down_capacity:
        downstream_blocked = bool(down_capacity.get("blocked"))
    else:
        downstream_blocked = (down_queue or 0) >= THRESHOLDS["queue_ratio_warning"] or (
            down_sat or 0
        ) >= THRESHOLDS["downstream_saturation_high"]

    criteria = {
        "target_queue_high": high_queue,
        "target_saturation_high": (target_sat or 0) >= THRESHOLDS["saturation_high"],
        "target_green_utilization_high": (target_green or 0) >= THRESHOLDS["green_utilization_high"],
        "downstream_queue_high": (down_queue or 0) >= THRESHOLDS["queue_ratio_warning"],
        "downstream_near_saturation": (down_sat or 0) >= THRESHOLDS["downstream_saturation_high"],
        "downstream_metrics_unknown": down_unknown,
        "add_green_spillback_risk": downstream_blocked and high_demand,
    }

    ds_decision = (downstream_state or {}).get("decision")
    if ds_decision == "slack":
        criteria["downstream_queue_high"] = False
        criteria["downstream_near_saturation"] = False
        criteria["add_green_spillback_risk"] = False
        downstream_blocked = False

    if down_unknown:
        scenario = "downstream_metrics_unknown"
        narrative = (
            "直接下游缺少真实排队/饱和度样本，无法判定承接能力；"
            "按典型 Case 门槛不得据此进入点/线治理闭环。"
        )
        release_answer = "下游指标不足"
    elif high_demand and downstream_blocked:
        scenario = "high_demand_downstream_blocked"
        narrative = (
            "目标方向排队高、饱和度高、绿灯利用率高，同时下游排队比也高，"
            "问题不是单纯信号供给不足，而是「本路口高需求 + 下游承接不足」共同作用。"
        )
        release_answer = "下游接不住"
    elif high_queue and low_green_util:
        scenario = "queue_high_green_underused"
        narrative = (
            "目标方向排队高但绿灯利用率不高，需优先核验出口通行、检测有效性与绿灯末端队列，"
            "不宜在未完成先验前简单加绿。"
        )
        release_answer = "放行效率异常，待核验" if ds_decision == "slack" else "绿灯给了也用不上"
    elif not high_demand and downstream_blocked:
        scenario = "downstream_primary"
        narrative = (
            "目标方向放行能力尚可，但下游信控节点持续高饱和，主因更可能是下游承接不足。"
        )
        release_answer = "下游接不住"
    elif high_demand and not downstream_blocked:
        scenario = "local_release_primary"
        narrative = (
            "目标方向需求高且绿灯利用率高，下游仍有承接空间，可考虑适度增加有效绿。"
        )
        release_answer = "本路口放不出去"
    else:
        scenario = "mixed"
        narrative = bottleneck.get("reason") or "需结合连续时序与干线拓扑进一步判断。"
        release_answer = bottleneck.get("label", "复合瓶颈")

    down_name = primary.get("inter_name") or "下游信控节点"
    return {
        "available": bool(downstream_nodes),
        "scenario": scenario,
        "release_answer": release_answer,
        "can_simple_add_green": False if down_unknown else bottleneck.get("can_simple_add_green", False),
        "primary_downstream": {
            "inter_id": primary.get("inter_id"),
            "inter_name": down_name,
            "metrics": down_metrics,
            "by_turn": primary.get("by_turn", []),
            "remaining_storage_m": primary.get("remaining_storage_m"),
            "capacity": down_capacity,
        },
        "judgment_criteria": criteria,
        "narrative": narrative,
        "expert_question": "加绿以后，车有没有地方去？",
    }
