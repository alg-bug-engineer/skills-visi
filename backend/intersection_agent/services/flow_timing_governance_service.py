"""Flow-timing match governance for four core signal problems."""

from __future__ import annotations

from typing import Any

from intersection_agent.services.expert_rules_summary import (
    build_expert_rules_brief,
    format_expert_rules_markdown,
)
from intersection_agent.services.rule_engine import RuleEngine
from intersection_agent.utils.thresholds_loader import threshold_value

FOCUS_CATEGORIES = ("saturation", "imbalance", "empty_green", "spillback")

_CATEGORY_LABELS = {
    "saturation": "饱和度",
    "imbalance": "失衡",
    "empty_green": "绿灯空放",
    "spillback": "溢出",
}

CHECKLIST_REFS = {
    "saturation": "inter_evaluation",
    "imbalance": "service_imbalance",
    "empty_green": "empty_green",
    "spillback": "spillback",
}


class FlowTimingGovernanceService:
    """Diagnose saturation/imbalance/empty-green/spillback with flow-timing fit."""

    def __init__(self, rules: RuleEngine | None = None) -> None:
        self._rules = rules or RuleEngine()

    def build(self, data: dict[str, Any]) -> dict[str, Any]:
        """Build structured governance report from diagnosis payload."""
        timing = data.get("timing") or {}
        timing_profile = data.get("timing_profile") or {}
        sustained = data.get("sustained_metrics") or {}
        flow_green = timing_profile.get("flow_green_fit") or {}
        match_verdict = str(flow_green.get("verdict") or timing.get("flow_green_verdict") or "insufficient")
        match_narrative = str(
            flow_green.get("narrative") or _match_narrative_from_verdict(match_verdict)
        )
        data_gaps = _collect_data_gaps(data)

        diagnosis = self._rules.diagnose_focused(list(FOCUS_CATEGORIES), data)
        problems = _detect_problems(
            data,
            diagnosis.matched_rules if diagnosis.diagnosed else [],
            sustained=sustained,
        )

        detected = [p for p in problems if p["detected"]]
        summary = _build_summary(match_verdict, detected)
        expert_rules = build_expert_rules_brief({"problems": problems})

        return {
            "match_verdict": match_verdict,
            "match_narrative": match_narrative,
            "flow_green_tau": flow_green.get("spearman_tau") or timing.get("flow_green_tau"),
            "data_gaps": data_gaps,
            "problems": problems,
            "summary": summary,
            "governance_narrative": _governance_narrative(match_verdict, detected),
            "expert_rules": expert_rules,
            "expert_rules_markdown": format_expert_rules_markdown(expert_rules),
            "sustained_checklist": sustained.get("checklist_items") or [],
            "checklist_refs": {cat: CHECKLIST_REFS.get(cat) for cat in FOCUS_CATEGORIES},
        }


def _match_narrative_from_verdict(verdict: str) -> str:
    mapping = {
        "strong": "各转向流量占比与有效绿灯占比高度一致，配时结构基本匹配需求",
        "weak": "流量与绿信比存在一定偏差，部分转向配时与需求匹配偏弱",
        "mismatch": "高流量转向的有效绿灯占比偏低，存在明显的流量-配时失配",
        "insufficient": "转向流量或配时样本不足，暂无法评价流量-绿信比一致性",
    }
    return mapping.get(verdict, mapping["insufficient"])


def _collect_data_gaps(data: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    if data.get("meta", {}).get("missing_dws_coverage"):
        gaps.append("dws_coverage_missing")
    lanes = (data.get("granularity") or {}).get("by_lane") or []
    if lanes and all(lane.get("lane_capacity") is None for lane in lanes):
        gaps.append("lane_capacity_missing")
    if not lanes:
        gaps.append("lane_granularity_missing")
    pe_metrics = (data.get("problem_evidence") or {}).get("metrics") or {}
    if pe_metrics.get("spillback_risk_max") is None:
        gaps.append("spillback_proxy_missing")
    return gaps


def _detect_problems(
    data: dict[str, Any],
    matched_rules: list[dict[str, Any]],
    *,
    sustained: dict[str, Any],
) -> list[dict[str, Any]]:
    tf = data.get("traffic_flow") or {}
    ev = data.get("evaluation") or {}
    pe_metrics = (data.get("problem_evidence") or {}).get("metrics") or {}
    timing = data.get("timing") or {}
    sustained_dims = sustained.get("dimensions") or {}

    sat_high = threshold_value("saturation", "high", default=0.80)
    sat_over = threshold_value("saturation", "oversaturation", default=0.90)
    imb_diag = threshold_value("imbalance", "diagnosis", default=0.30)
    empty_rate = threshold_value("green", "empty_green_rate", default=0.20)
    low_util = threshold_value("green", "low_utilization_diagnosis", default=0.60)
    spill_high = threshold_value("spillback", "risk_high", default=0.80)
    queue_ratio_high = threshold_value("queue", "queue_storage_ratio_high", default=0.80)
    gap_high = threshold_value("imbalance", "movement_saturation_gap", default=0.60)

    saturation_rate = _float(tf.get("saturation_rate"))
    imbalance_index = _float(ev.get("imbalance_index"))
    empty_green = _float(ev.get("empty_green_rate"))
    green_util = _float(ev.get("green_utilization"))
    spillback_risk = _float(pe_metrics.get("spillback_risk_max"))
    queue_ratio = _float(pe_metrics.get("queue_storage_ratio_max"))
    max_queue = _float(pe_metrics.get("max_queue_m"))
    lane_sat_max = _float(tf.get("lane_saturation_max"))

    rules_by_category: dict[str, list[dict[str, Any]]] = {c: [] for c in FOCUS_CATEGORIES}
    for rule in matched_rules:
        cat = rule.get("focus_category")
        if cat in rules_by_category:
            rules_by_category[cat].append(rule)

    problems: list[dict[str, Any]] = []

    sat_value = saturation_rate if saturation_rate is not None else lane_sat_max
    sat_detected = sat_value is not None and sat_value >= sat_high
    sat_severity = "high" if sat_value is not None and sat_value >= sat_over else "medium"
    problems.append(
        _problem_entry(
            category="saturation",
            detected=sat_detected,
            severity=sat_severity if sat_detected else "none",
            evidence=_evidence_lines(
                [
                    _line(
                        saturation_rate is not None,
                        f"路口饱和度 {saturation_rate:.2f}" if saturation_rate is not None else "",
                    ),
                    _line(
                        lane_sat_max is not None,
                        f"车道最高饱和度 {lane_sat_max:.0%}" if lane_sat_max is not None else "",
                    ),
                ]
            ),
            governance=_rule_governance(rules_by_category["saturation"])
            or (
                "关键方向过饱和，建议增加有效绿灯时长"
                if sat_detected
                else "饱和度处于可控范围，维持现有配时并持续监测"
            ),
            matched_rule_ids=[r["id"] for r in rules_by_category["saturation"]],
            checklist_ref=CHECKLIST_REFS["saturation"],
        )
    )

    turn_spread = _float(tf.get("turn_saturation_spread"))
    flow_green_verdict = str(timing.get("flow_green_verdict") or "")
    imb_sustained = bool(sustained_dims.get("imbalance_sustained"))
    imb_detected = (
        imb_sustained
        or (imbalance_index is not None and imbalance_index >= imb_diag)
        or (turn_spread is not None and turn_spread >= gap_high)
        or flow_green_verdict in ("weak", "mismatch")
    )
    imb_evidence = [
        _line(
            imbalance_index is not None,
            f"失衡系数 {imbalance_index:.2f}" if imbalance_index is not None else "",
        ),
        _line(
            turn_spread is not None,
            f"转向饱和度极差 {turn_spread:.2f}" if turn_spread is not None else "",
        ),
        _line(
            flow_green_verdict in ("weak", "mismatch"),
            f"流量-绿信比评价 {flow_green_verdict}",
        ),
        _line(imb_sustained, "连续15分钟服务失衡（检查单）"),
    ]
    problems.append(
        _problem_entry(
            category="imbalance",
            detected=imb_detected,
            severity="high"
            if imb_sustained or (imbalance_index is not None and imbalance_index >= imb_diag + 0.1)
            else "medium",
            evidence=_evidence_lines(imb_evidence),
            governance=_rule_governance(rules_by_category["imbalance"])
            or (
                "进口/转向服务失衡，建议重分配绿信比，向高流量转向倾斜"
                if imb_detected
                else "各进口服务相对均衡"
            ),
            matched_rule_ids=[r["id"] for r in rules_by_category["imbalance"]],
            checklist_ref=CHECKLIST_REFS["imbalance"],
        )
    )

    empty_sustained = bool(sustained_dims.get("empty_green_sustained"))
    empty_detected = empty_sustained or (
        (empty_green is not None and empty_green >= empty_rate)
        or (green_util is not None and green_util < low_util)
    )
    problems.append(
        _problem_entry(
            category="empty_green",
            detected=empty_detected,
            severity="medium" if empty_detected else "none",
            evidence=_evidence_lines(
                [
                    _line(
                        empty_green is not None,
                        f"空放率 {empty_green:.0%}" if empty_green is not None else "",
                    ),
                    _line(
                        green_util is not None,
                        f"绿灯利用率 {green_util:.0%}" if green_util is not None else "",
                    ),
                    _line(empty_sustained, "连续15分钟低利用（检查单）"),
                ]
            ),
            governance=_rule_governance(rules_by_category["empty_green"])
            or (
                "存在绿灯空放，建议压缩低利用相位绿灯并转给拥堵方向"
                if empty_detected
                else "绿灯利用率正常，无明显空放"
            ),
            matched_rule_ids=[r["id"] for r in rules_by_category["empty_green"]],
            checklist_ref=CHECKLIST_REFS["empty_green"],
        )
    )

    long_queue = threshold_value("queue", "long_queue_m", default=100)
    spill_detected = (
        (spillback_risk is not None and spillback_risk >= queue_ratio_high)
        or (queue_ratio is not None and queue_ratio >= queue_ratio_high)
        or (max_queue is not None and max_queue >= long_queue)
    )
    spill_severity = (
        "high"
        if spillback_risk is not None and spillback_risk >= spill_high
        else "medium"
    )
    problems.append(
        _problem_entry(
            category="spillback",
            detected=spill_detected,
            severity=spill_severity if spill_detected else "none",
            evidence=_evidence_lines(
                [
                    _line(
                        spillback_risk is not None,
                        f"溢流风险 {spillback_risk:.2f}" if spillback_risk is not None else "",
                    ),
                    _line(
                        queue_ratio is not None,
                        f"排队存储比 {queue_ratio:.2f}" if queue_ratio is not None else "",
                    ),
                    _line(
                        max_queue is not None,
                        f"最长排队 {max_queue:.0f}m" if max_queue is not None else "",
                    ),
                ]
            ),
            governance=_rule_governance(rules_by_category["spillback"])
            or (
                "排队接近或超过存储能力，建议控制上游放行、避免外溢"
                if spill_detected
                else "未发现明显溢出风险"
            ),
            matched_rule_ids=[r["id"] for r in rules_by_category["spillback"]],
            checklist_ref=CHECKLIST_REFS["spillback"],
        )
    )

    return problems


def _problem_entry(
    *,
    category: str,
    detected: bool,
    severity: str,
    evidence: list[str],
    governance: str,
    matched_rule_ids: list[str],
    checklist_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "label": _CATEGORY_LABELS.get(category, category),
        "detected": detected,
        "severity": severity if detected else "none",
        "evidence": evidence,
        "governance": governance,
        "matched_rule_ids": matched_rule_ids,
        "checklist_ref": checklist_ref,
    }


def _evidence_lines(items: list[tuple[bool, str]]) -> list[str]:
    return [text for ok, text in items if ok and text]


def _line(ok: bool, text: str) -> tuple[bool, str]:
    return (ok, text)


def _rule_governance(rules: list[dict[str, Any]]) -> str | None:
    if not rules:
        return None
    parts = [str(r.get("conclusion") or "").strip() for r in rules[:2]]
    return "；".join(p for p in parts if p) or None


def _build_summary(match_verdict: str, detected: list[dict[str, Any]]) -> str:
    if not detected:
        if match_verdict == "strong":
            return "流量与配时匹配良好，四类核心问题均未达告警阈值"
        return "未发现四类核心问题的明显异常，建议结合现场观测复核"

    labels = [p["label"] for p in detected]
    match_part = {
        "mismatch": "流量-配时失配",
        "weak": "流量-配时匹配偏弱",
        "strong": "流量-配时基本匹配",
    }.get(match_verdict, "流量-配时待进一步核实")

    return f"{match_part}，主要问题：{'、'.join(labels)}"


def _governance_narrative(match_verdict: str, detected: list[dict[str, Any]]) -> str:
    if not detected:
        return "当前指标下四类问题均未触发，可维持配时并持续监测高峰表现。"

    lines = []
    if match_verdict in ("weak", "mismatch"):
        lines.append("从流量-配时匹配看，信号配时结构与实际需求存在偏差，治理应优先调整绿信比分配。")
    for problem in detected:
        lines.append(f"【{problem['label']}】{problem['governance']}")
    return " ".join(lines)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
