"""Deterministic strategy package scoring and optimizer-facing strategy_instruction."""

from __future__ import annotations

from typing import Any

PACKAGE_DEFINITIONS = {
    "downstream_protection": {
        "name": "下游保护方案",
        "target_green_delta": -2,
        "cycle_delta": 0,
        "upstream_control": False,
        "target_saturation": 0.75,
        "rollback_condition": "下游排队比持续上升时回滚至原方案",
    },
    "incremental_release": {
        "name": "小步释放方案",
        "target_green_delta": 5,
        "cycle_delta": 0,
        "upstream_control": False,
        "target_saturation": 0.82,
        "rollback_condition": "下游排队比持续上升或目标方向绿灯利用率异常下降时回滚",
    },
    "arterial_coordination": {
        "name": "干线联控方案",
        "target_green_delta": 2,
        "cycle_delta": 10,
        "upstream_control": True,
        "target_saturation": 0.78,
        "rollback_condition": "下游排队比持续上升、上游排队超过安全边界时回滚",
    },
}


def score_strategy_packages(
    cause: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, float]:
    scores = {pkg: 0.0 for pkg in PACKAGE_DEFINITIONS}
    cause_scores = (cause.get("cause_scores") or {}).get("scores") or {}
    governance = diagnosis.get("downstream_trace", {}).get("governance", {})
    arterial = diagnosis.get("arterial_analysis", {})
    bottleneck = diagnosis.get("bottleneck_analysis", {})

    if governance.get("downstream_blocked"):
        scores["downstream_protection"] += 0.5
    if float(cause_scores.get("event", 0)) >= 0.35:
        scores["downstream_protection"] += 0.25
    if float(cause_scores.get("coordination", 0)) >= 0.35:
        scores["arterial_coordination"] += 0.45
    if arterial.get("need_upstream_metering"):
        scores["arterial_coordination"] += 0.35
    if bottleneck.get("bottleneck_type") == "local_release" and not governance.get("downstream_blocked"):
        scores["incremental_release"] += 0.45
    if float(cause_scores.get("demand", 0)) >= 0.35 and not governance.get("downstream_blocked"):
        scores["incremental_release"] += 0.2

    if max(scores.values()) <= 0:
        scores["downstream_protection"] = 0.6

    return {pkg: round(min(score, 1.0), 4) for pkg, score in scores.items()}


def select_strategy_package(cause: dict[str, Any], diagnosis: dict[str, Any]) -> str:
    scores = score_strategy_packages(cause, diagnosis)
    return max(scores, key=scores.get)


def build_strategy_instruction(
    package: str,
    *,
    cause: dict[str, Any] | None = None,
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cause = cause or {}
    diagnosis = diagnosis or {}
    base = dict(PACKAGE_DEFINITIONS.get(package, PACKAGE_DEFINITIONS["downstream_protection"]))
    governance = diagnosis.get("downstream_trace", {}).get("governance", {})

    if governance.get("downstream_blocked"):
        base["target_saturation"] = min(float(base["target_saturation"]), 0.75)
    if cause.get("cause_scores", {}).get("primary_dimension") == "demand":
        base["target_saturation"] = min(float(base["target_saturation"]), 0.8)

    return {
        "package": package,
        "strategy": package,
        "name": base["name"],
        "target_green_delta": base["target_green_delta"],
        "cycle_delta": base["cycle_delta"],
        "upstream_control": base["upstream_control"],
        "target_saturation": base["target_saturation"],
        "rollback_condition": base["rollback_condition"],
        "principles": _principles_for_package(package),
        "not_recommended": _not_recommended(package, diagnosis),
        "trigger_exit_rules": {"rollback_condition": base["rollback_condition"]},
    }


def build_strategy_profile(
    cause: dict[str, Any],
    diagnosis: dict[str, Any],
    llm_strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package_scores = score_strategy_packages(cause, diagnosis)
    package = select_strategy_package(cause, diagnosis)
    instruction = build_strategy_instruction(package, cause=cause, diagnosis=diagnosis)
    llm_strategy = llm_strategy or {}

    trigger_exit = _merge_trigger_exit_rules(
        llm_strategy.get("trigger_exit_rules"),
        instruction.get("trigger_exit_rules"),
    )
    return {
        "strategy_package": package,
        "package_scores": package_scores,
        "strategy_instruction": instruction,
        "strategy": {
            "principles": llm_strategy.get("principles") or instruction["principles"],
            "not_recommended": llm_strategy.get("not_recommended") or instruction["not_recommended"],
            "recommended": llm_strategy.get("recommended") or _recommended_for_package(package),
            "hard_constraints": llm_strategy.get("hard_constraints")
            or _hard_constraints(package, diagnosis),
            "trigger_exit_rules": trigger_exit,
            "explanation": llm_strategy.get("explanation"),
            "narrative": llm_strategy.get("narrative"),
            "source": llm_strategy.get("source", "hybrid"),
        },
    }


def _principles_for_package(package: str) -> list[str]:
    common = ["防溢流优先", "可回滚", "先判断下游承接能力"]
    if package == "downstream_protection":
        return common + ["先保护下游，不宜继续强放"]
    if package == "incremental_release":
        return common + ["小步释放，保留监测窗口"]
    return common + ["上游削峰与目标路口协调", "干线传导风险控制"]


def _not_recommended(package: str, diagnosis: dict[str, Any]) -> list[str]:
    items = ["单点激进加绿"]
    if diagnosis.get("downstream_trace", {}).get("governance", {}).get("downstream_blocked"):
        items.append("继续增大目标方向放行")
    if package == "incremental_release":
        items.append("无监测条件下大幅加绿")
    return items


def _recommended_for_package(package: str) -> list[str]:
    mapping = {
        "downstream_protection": ["下游保护约束下的保守放行"],
        "incremental_release": ["下游保护约束下的小步释放"],
        "arterial_coordination": ["上游控流 + 目标小步释放 + 下游保护"],
    }
    return mapping.get(package, mapping["downstream_protection"])


def _hard_constraints(package: str, diagnosis: dict[str, Any]) -> list[str]:
    items = ["最小绿灯、黄灯全红与行人过街约束不可突破"]
    if diagnosis.get("downstream_trace", {}).get("governance", {}).get("downstream_blocked"):
        items.append("下游排队比超阈值时禁止继续增大目标方向放行")
    if package == "arterial_coordination":
        items.append("上游控流幅度不得导致上游路口新溢出")
    return items


def _merge_trigger_exit_rules(
    llm_rules: Any,
    instruction_rules: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(instruction_rules or {})
    if isinstance(llm_rules, dict):
        merged.update(llm_rules)
    elif isinstance(llm_rules, list):
        merged["rules"] = llm_rules
    return merged
