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
    signal: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package_scores = score_strategy_packages(cause, diagnosis)
    package = select_strategy_package(cause, diagnosis)
    instruction = build_strategy_instruction(package, cause=cause, diagnosis=diagnosis)
    llm_strategy = llm_strategy or {}

    trigger_exit = _merge_trigger_exit_rules(
        llm_strategy.get("trigger_exit_rules"),
        instruction.get("trigger_exit_rules"),
    )
    quantitative = _quantitative_constraints(signal, constraints)
    # 红线：LLM 定性项（或包定性项）在前，量化护栏在后；量化项恒补齐，
    # 避免「纯定性描述与红线关联不大」（需求 20·R5）。
    hard_constraints = (
        _as_str_list(llm_strategy.get("hard_constraints"))
        or _hard_constraints(package, diagnosis)
    ) + quantitative["constraints"]
    return {
        "strategy_package": package,
        "package_scores": package_scores,
        "strategy_instruction": instruction,
        "strategy": {
            "principles": _as_str_list(llm_strategy.get("principles")) or instruction["principles"],
            "not_recommended": _as_str_list(llm_strategy.get("not_recommended"))
            or instruction["not_recommended"],
            "recommended": _as_str_list(llm_strategy.get("recommended"))
            or _recommended_for_package(package),
            "hard_constraints": hard_constraints,
            "quantitative_constraints": quantitative["detail"],
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


def _as_str_list(value: Any) -> list[str]:
    """把 LLM 可能返回的字符串/None/列表统一归一为 list[str]。

    LLM 偶发把本应为数组的字段（如 hard_constraints/principles）返回成单个
    字符串，直接与内置列表相加会抛 TypeError（需求 20·R5 红线拼接）。
    """
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _to_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if num > 0 else None


def _fmt_s(value: float) -> str:
    return f"{int(value)}s" if float(value).is_integer() else f"{value:g}s"


def _quantitative_constraints(
    signal: dict[str, Any] | None,
    constraints: dict[str, Any] | None,
) -> dict[str, Any]:
    """从真实现状配时/约束派生量化红线（最小绿/最大绿/最大周期）。

    数据缺失时不编造，仅记录 ``missing`` 供上层降级（rule 14/16）。
    """
    signal = signal or {}
    constraints = constraints or {}
    stages = signal.get("phase_stage_timing_list") or []
    min_greens: list[float] = []
    max_greens: list[float] = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        mg = _to_number(stage.get("min_green_time_s") or stage.get("minGreenTime"))
        if mg is not None:
            min_greens.append(mg)
        xg = _to_number(stage.get("max_green_time_s") or stage.get("maxGreenTime"))
        if xg is not None:
            max_greens.append(xg)

    max_cycle = _to_number(constraints.get("max_cycle_s") or signal.get("max_cycle_s"))
    current_cycle = _to_number(signal.get("current_cycle_s") or signal.get("cycle_s"))

    detail: dict[str, Any] = {
        "min_green_s": round(min(min_greens), 1) if min_greens else None,
        "max_green_s": round(max(max_greens), 1) if max_greens else None,
        "max_cycle_s": max_cycle,
        "current_cycle_s": current_cycle,
        "source": "pg_signal_plan" if stages else "unavailable",
        "missing": [],
    }
    items: list[str] = []
    if min_greens:
        items.append(f"各相位最小绿不得低于 {_fmt_s(min(min_greens))}（含黄灯全红、行人过街清空）")
    else:
        detail["missing"].append("min_green_s")
    if max_greens:
        items.append(f"单相位绿灯不得超过 {_fmt_s(max(max_greens))}（最大绿上限）")
    else:
        detail["missing"].append("max_green_s")
    if max_cycle is not None:
        items.append(f"信号周期不得超过 {_fmt_s(max_cycle)}（最大周期约束）")
    else:
        detail["missing"].append("max_cycle_s")
    if not items:
        detail["missing"].append("all")
    return {"constraints": items, "detail": detail}


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
