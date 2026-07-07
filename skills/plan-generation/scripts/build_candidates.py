from __future__ import annotations

from typing import Any


def build_plan_candidates(
    strategy: dict[str, Any],
    ticket: dict[str, Any],
    diagnosis: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    diagnosis = diagnosis or {}
    direction = ticket.get("direction", "东向西")
    downstream_name = (
        (diagnosis.get("downstream_diagnosis") or {}).get("primary_downstream", {}).get(
            "inter_name"
        )
        or "下游信控节点"
    )
    need_upstream = diagnosis.get("arterial_analysis", {}).get("need_upstream_metering", False)
    return [
        {
            "plan_id": "downstream_protection",
            "name": "下游保护方案",
            "scenario": f"{downstream_name}承接不足，目标路口不宜继续强放",
            "actions": {
                "cycle_sec": 120,
                f"{direction}直行绿灯_sec": 28,
                "upstream_control": False,
                "phase_offset_sec": 0,
            },
            "risk": "目标进口排队缓解速度较慢，需配合上游控流",
        },
        {
            "plan_id": "incremental_release",
            "name": "目标路口小步释放方案",
            "scenario": "下游仍有部分承接空间，目标方向排队较高",
            "actions": {
                "cycle_sec": 120,
                f"{direction}直行绿灯_sec": 35,
                "green_delta_sec": 5,
                "upstream_control": False,
            },
            "risk": "下游排队继续增长需立即回滚",
        },
        {
            "plan_id": "arterial_coordination",
            "name": "干线联控方案",
            "scenario": (
                f"{downstream_name}接不住，上游持续来车，目标路口接近溢出"
                if need_upstream
                else "下游接不住，需干线协调削峰"
            ),
            "actions": {
                "cycle_sec": 130,
                f"{direction}直行绿灯_sec": 32,
                "upstream_control": True,
                "upstream_green_ratio_delta": -0.08,
                "phase_offset_sec": 15,
                "downstream_protection": True,
            },
            "risk": "上游控流幅度不能过大，否则可能造成上游新溢出",
            "execution_order": [
                "先保护下游",
                "再平滑上游来车",
                "最后小步释放目标方向",
            ],
        },
    ]
