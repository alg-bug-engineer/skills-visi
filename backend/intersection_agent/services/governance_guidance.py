"""Context-aware governance guidance from editable skill rules."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from intersection_agent.utils.thresholds_loader import threshold_value

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_RULES_PATH = (
    _REPO_ROOT
    / "docs"
    / "intersection"
    / "flow-timing-governance"
    / "references"
    / "governance_rules.yaml"
)


@lru_cache(maxsize=1)
def _load_rules() -> dict[str, Any]:
    if not _RULES_PATH.is_file():
        return {}
    with open(_RULES_PATH, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def build_governance_context(data: dict[str, Any]) -> dict[str, Any]:
    """Derive boolean flags and metrics for governance rule matching."""
    tf = data.get("traffic_flow") or {}
    ev = data.get("evaluation") or {}
    timing = data.get("timing") or {}
    timing_profile = data.get("timing_profile") or {}
    pe_metrics = (data.get("problem_evidence") or {}).get("metrics") or {}
    flow_gov = data.get("flow_timing_governance") or {}
    primary = flow_gov.get("primary_diagnosis") or {}
    by_turn = ((data.get("granularity") or {}).get("by_turn")) or []

    sat_high = threshold_value("saturation", "high", default=0.80)
    sat_over = threshold_value("saturation", "oversaturation", default=0.90)
    low_util = threshold_value("green", "low_utilization_diagnosis", default=0.60)
    empty_rate = threshold_value("green", "empty_green_rate", default=0.20)
    imb_diag = threshold_value("imbalance", "diagnosis", default=0.30)
    gap_high = threshold_value("imbalance", "movement_saturation_gap", default=0.60)
    spill_high = threshold_value("spillback", "risk_high", default=0.80)
    queue_ratio_high = threshold_value("queue", "queue_storage_ratio_high", default=0.80)

    max_sat = _float(tf.get("turn_saturation_max")) or _float(tf.get("saturation_rate"))
    spread = _float(tf.get("turn_saturation_spread"))
    green_util = _float(ev.get("green_utilization"))
    empty_green = _float(ev.get("empty_green_rate"))
    imbalance_index = _float(ev.get("imbalance_index"))
    spillback_risk = _float(pe_metrics.get("spillback_risk_max"))
    queue_ratio = _float(pe_metrics.get("queue_storage_ratio_max"))
    flow_green_verdict = str(
        (timing_profile.get("flow_green_fit") or {}).get("verdict")
        or timing.get("flow_green_verdict")
        or ""
    )

    oversaturated = max_sat is not None and max_sat >= sat_high
    empty_detected = (
        (empty_green is not None and empty_green >= empty_rate)
        or (green_util is not None and green_util < low_util)
        or _turn_has_low_util(by_turn, low_util)
    )
    imbalance_detected = (
        (imbalance_index is not None and imbalance_index >= imb_diag)
        or (spread is not None and spread >= gap_high)
        or flow_green_verdict in ("weak", "mismatch")
    )
    spill_detected = (
        (spillback_risk is not None and spillback_risk >= queue_ratio_high)
        or (queue_ratio is not None and queue_ratio >= queue_ratio_high)
    )

    return {
        "max_saturation": max_sat,
        "spread": spread,
        "green_utilization": green_util,
        "oversaturated": oversaturated,
        "oversaturation": max_sat is not None and max_sat >= sat_over,
        "empty_green_detected": empty_detected,
        "imbalance_detected": imbalance_detected,
        "spillback_detected": spill_detected,
        "spillback_high": spillback_risk is not None and spillback_risk >= spill_high,
        "spread_above": spread,
        "green_utilization_below": green_util,
        "flow_green_mismatch": flow_green_verdict in ("weak", "mismatch"),
        "primary_type": str(primary.get("type") or ""),
        "structure_limited": bool(primary.get("structure_limited")),
    }


def guidance_for_category(category: str, data: dict[str, Any]) -> str:
    """Return best-matching governance guidance for one focus category."""
    rules_doc = _load_rules()
    category_rules = (rules_doc.get("categories") or {}).get(category) or []
    if not category_rules:
        return _fallback_guidance(category, data)

    ctx = build_governance_context(data)
    sorted_rules = sorted(category_rules, key=lambda r: int(r.get("priority", 99)))

    for rule in sorted_rules:
        when = rule.get("when") or {}
        if _conditions_match(when, ctx):
            return str(rule.get("guidance") or "").strip()

    return _fallback_guidance(category, data)


def format_category_guidance_block(data: dict[str, Any]) -> str:
    """Multi-line block for LLM suggestion prompt."""
    flow_gov = data.get("flow_timing_governance") or {}
    problems = flow_gov.get("problems") or []
    lines: list[str] = []
    for problem in problems:
        if not problem.get("detected"):
            continue
        label = problem.get("label") or problem.get("category")
        text = problem.get("governance") or guidance_for_category(
            str(problem.get("category") or ""), data
        )
        if text:
            lines.append(f"- 【{label}】{text}")
    primary = flow_gov.get("primary_diagnosis") or {}
    if primary.get("headline"):
        lines.insert(0, f"- 【主诊断】{primary['headline']}")
    if primary.get("lever"):
        lines.insert(1, f"- 【信控落点】{primary['lever']}")
    return "\n".join(lines) if lines else "暂无显著四维异常"


def _conditions_match(when: dict[str, Any], ctx: dict[str, Any]) -> bool:
    if not when:
        return True
    for key, expected in when.items():
        actual = ctx.get(key)
        if key.endswith("_above") or key.endswith("_below"):
            metric_key = key.replace("_above", "").replace("_below", "")
            value = ctx.get(metric_key) if metric_key in ctx else actual
            if value is None:
                return False
            threshold = float(expected)
            if key.endswith("_above") and not (float(value) >= threshold):
                return False
            if key.endswith("_below") and not (float(value) < threshold):
                return False
            continue
        if key == "primary_type":
            if str(actual) != str(expected):
                return False
            continue
        if bool(actual) != bool(expected):
            return False
    return True


def _turn_has_low_util(by_turn: list[dict[str, Any]], low_util: float) -> bool:
    for turn in by_turn:
        util = _float(turn.get("green_utilization"))
        if util is not None and util < low_util:
            return True
    return False


def _fallback_guidance(category: str, data: dict[str, Any]) -> str:
    defaults = {
        "saturation": "关键方向过饱和，建议结合绿灯利用率与空放情况评估是否加绿或再分配绿信比",
        "imbalance": "进口/转向服务失衡，建议重分配绿信比，向高流量转向倾斜",
        "empty_green": "存在绿灯空放，建议压缩低利用相位绿灯并转给拥堵方向",
        "spillback": "排队接近或超过存储能力，建议控制上游放行、避免外溢",
    }
    return defaults.get(category, "")


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
