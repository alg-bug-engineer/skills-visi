from __future__ import annotations

from typing import Any


def compare_kpis(before: dict, after: dict) -> dict[str, float]:
    return {key: round(float(after.get(key, 0)) - float(before.get(key, 0)), 4) for key in set(before) | set(after)}


def evaluate_signal_plan(plan: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    objectives = task.get("objectives", {}) or {}
    metrics = task.get("metrics", {}) or {}
    delay = float(metrics.get("avg_delay_s", 60))
    wave = float(metrics.get("green_wave_pass_rate", 0.5))
    delay_reduction = 10.0 if "绿波" in plan.get("strategy", "") else 8.0 if delay >= 60 else 3.0
    wave_uplift = 7.0 if plan.get("offset_policy") == "recalculate_corridor_offsets" else 2.0
    meets = delay_reduction >= float(objectives.get("delay_reduction_pct", 5)) and wave_uplift >= float(
        objectives.get("green_wave_uplift_pct", 0)
    )
    return {
        "estimated_kpis": {
            "delay_reduction_pct": delay_reduction,
            "green_wave_uplift_pct": wave_uplift,
            "expected_delay_s": round(delay * (1 - delay_reduction / 100), 1),
            "expected_green_wave_pass_rate": round(min(0.95, wave + wave_uplift / 100), 3),
        },
        "meets_target": meets,
        "confidence_score": 0.82 if meets else 0.62,
        "learning_notes": ["记录策略-指标响应关系", "保留人工确认与回滚条件", "将执行效果回灌策略库"],
        "iteration_recommendation": None
        if meets
        else "回流到问题诊断与控制策略环节，提升目标优先级并收紧触发/退出规则。",
    }
