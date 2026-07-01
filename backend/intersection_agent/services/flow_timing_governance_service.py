"""Flow-timing match governance for four core signal problems."""

from __future__ import annotations

from typing import Any

from intersection_agent.services.expert_rules_summary import (
    build_expert_rules_brief,
    format_expert_rules_markdown,
)
from intersection_agent.services.governance_action_plan_service import build_action_plan
from intersection_agent.services.governance_guidance import guidance_for_category
from intersection_agent.services.rule_engine import RuleEngine
from intersection_agent.utils.saturation_granularity import (
    apply_canonical_saturation_to_payload,
    canonical_saturation_summary,
    max_turn_saturation_from_rows,
)
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
        primary = _build_primary_diagnosis(data, match_verdict)
        problems = _detect_problems(
            data,
            diagnosis.matched_rules if diagnosis.diagnosed else [],
            sustained=sustained,
            primary=primary,
        )

        detected = [p for p in problems if p["detected"]]
        summary = _build_summary(primary, detected)
        expert_rules = build_expert_rules_brief({"problems": problems})

        action_plan = build_action_plan(data, primary=primary, problems=problems)
        flow_trace_supplement = _flow_trace_supplement(data, action_plan)

        return {
            "primary_diagnosis": primary,
            "flow_trace_supplement": flow_trace_supplement,
            "match_verdict": match_verdict,
            "match_narrative": match_narrative,
            "flow_green_tau": flow_green.get("spearman_tau") or timing.get("flow_green_tau"),
            "data_gaps": data_gaps,
            "problems": problems,
            "summary": summary,
            "governance_narrative": _governance_narrative(primary, detected),
            "expert_rules": expert_rules,
            "expert_rules_markdown": format_expert_rules_markdown(expert_rules),
            "sustained_checklist": sustained.get("checklist_items") or [],
            "checklist_refs": {cat: CHECKLIST_REFS.get(cat) for cat in FOCUS_CATEGORIES},
            "action_plan": action_plan,
        }


def _flow_trace_supplement(
    data: dict[str, Any], action_plan: dict[str, Any] | None
) -> str:
    """流量溯源补充建议（叠加维度，独立于主诊断类型）。

    当主方案已是上游协调时不重复；否则若存在单一上游主导来源，
    追加「也可在上游协同」的补充方向。途经率非占比，文案禁用「贡献/占比」。
    """
    if action_plan and action_plan.get("action_type") == "upstream_coordination":
        return ""
    flow_trace = data.get("flow_trace") or {}
    if not flow_trace.get("available"):
        return ""
    hints = [
        h for h in (flow_trace.get("governance_hints") or [])
        if h.get("type") == "upstream_coordination" and h.get("inter_name")
    ]
    if not hints:
        return ""
    hints.sort(key=lambda h: h.get("coverage") or 0, reverse=True)
    top = hints[0]
    cov = top.get("coverage")
    cov_text = f"约 {cov:.0f} 辆/100 " if isinstance(cov, (int, float)) else ""
    return (
        f"流量溯源补充：{top.get('problem_turn')}{cov_text}来自上一路口"
        f"{top.get('inter_name')}{top.get('feed_direction') or ''}，"
        "建议在该路口协同优化放行节奏，从源头削减进入车流。"
    )


def _build_primary_diagnosis(data: dict[str, Any], match_verdict: str) -> dict[str, Any]:
    """Primary narrative axis: is this a timing-fixable mis-allocation or a capacity ceiling.

    供需匹配度为主轴——把"饱和度高不高"重构为"绿灯该不该挪、往哪挪、还是单点配时已无解"。
    所有判定量均已在 payload 中，无新增取数。
    """
    tf = data.get("traffic_flow") or {}
    timing_profile = data.get("timing_profile") or {}
    timing = data.get("timing") or {}
    # max_x：与左侧面板 / 运行数据同口径——仅使用 granularity 汇总，不用 traffic_flow 全局峰值
    by_turn = ((data.get("granularity") or {}).get("by_turn")) or []
    gran = data.get("granularity") or {}
    sat_summary = canonical_saturation_summary(
        by_turn=by_turn,
        by_lane=gran.get("by_lane"),
        inter_saturation_max=_float((data.get("evaluation") or {}).get("saturation_max")),
        inter_saturation_avg=_float((data.get("evaluation") or {}).get("saturation_avg")),
    )
    max_x = sat_summary.get("turn_saturation_max")
    if max_x is None:
        max_x = max_turn_saturation_from_rows(by_turn)
    if max_x is None:
        max_x = _float(tf.get("saturation_rate"))
    if max_x is None:
        max_x = _float(tf.get("lane_saturation_max"))
    spread = sat_summary.get("turn_saturation_spread")
    if spread is None:
        spread = _float(tf.get("turn_saturation_spread"))

    flow_green = timing_profile.get("flow_green_fit") or {}
    flow_green_verdict = str(flow_green.get("verdict") or timing.get("flow_green_verdict") or "")

    sat_high = threshold_value("saturation", "high", default=0.80)
    sat_over = threshold_value("saturation", "oversaturation", default=0.90)
    spread_balanced = threshold_value(
        "imbalance", "spread_balanced",
        default=threshold_value("imbalance", "diagnosis", default=0.30),
    )

    deficit_ratio_max = _float(timing_profile.get("green_deficit_ratio_max")) or _float(
        timing.get("green_deficit_ratio_max")
    )
    deficit_turns = timing_profile.get("deficit_turns") or []
    structure_limited = bool(
        deficit_ratio_max is not None and deficit_ratio_max > 0 and deficit_turns
    )

    low_util = threshold_value("green", "low_utilization_diagnosis", default=0.60)

    over_turn = _best_over_turn(by_turn, sat_high)
    spare_turn = _best_spare_turn(
        by_turn, exclude=over_turn.get("label") if over_turn else None, low_util=low_util
    )
    deficit_turn_label = deficit_turns[0].get("label") if deficit_turns else None

    # —— 四选一主诊断 ——
    if max_x is not None and max_x >= sat_high and spread is not None and spread >= spread_balanced:
        dtype = "timing_optimizable"
        severity = "high" if max_x >= sat_over else "medium"
        if over_turn and spare_turn:
            o_label, o_sat, o_util = (
                over_turn["label"], over_turn["turn_saturation"], over_turn["green_utilization"]
            )
            s_label, s_util = spare_turn["label"], spare_turn["green_utilization"]
            util_part = f"、绿灯利用{o_util:.2f}" if o_util is not None else ""
            headline = (
                f"{o_label}已过饱和（饱和{o_sat:.2f}{util_part}），"
                f"而{s_label}绿灯利用率{s_util:.2f}仍有富余"
                "——属于绿灯分配不均，配时可改善"
            )
            lever = f"建议把{s_label}的部分绿灯时间让给{o_label}，优先调整绿信比分配"
        else:
            headline = (
                f"部分转向已过饱和（最高 {max_x:.2f}），另一些转向绿灯仍有富余"
                "——属于绿灯分配不均，配时可改善"
            )
            lever = "建议把绿灯富余转向的时间让给过饱和转向，优先调整绿信比分配"
    elif max_x is not None and max_x >= sat_over and (spread is None or spread < spread_balanced):
        dtype = "capacity_bottleneck"
        severity = "high"
        headline = f"各转向饱和度接近且普遍偏高（最高 {max_x:.2f}），该路口已接近通行能力上限"
        lever = (
            "绿信比分配已接近最优，单点配时优化空间有限；"
            "建议从加大周期、绿波协调、车道渠化展宽、需求调控等方向入手"
        )
    else:
        dtype = "basically_matched"
        severity = "none"
        headline = "供需与配时基本匹配，未见明显绿灯错配"
        lever = "维持现有配时方案，持续监测高峰表现"

    if structure_limited and dtype != "basically_matched":
        if deficit_turn_label:
            headline += f"；其中{deficit_turn_label}绿灯已触最小绿，压缩空间有限"
        else:
            headline += "；其中关键转向绿灯已触最小绿，压缩空间有限"

    evidence = _evidence_lines(
        [
            _line(max_x is not None, f"最高转向饱和度 {max_x:.2f}" if max_x is not None else ""),
            _line(spread is not None, f"转向饱和度极差 {spread:.2f}" if spread is not None else ""),
            _line(
                dtype == "timing_optimizable" and spare_turn is not None,
                (
                    f"{spare_turn['label']}绿灯利用率 {spare_turn['green_utilization']:.2f}"
                    f"（低于富余阈值 {low_util:.2f}），可向"
                    f"{over_turn['label']}（饱和 {over_turn['turn_saturation']:.2f}）挪绿"
                    if spare_turn and over_turn
                    else ""
                ),
            ),
            _line(
                flow_green_verdict in ("weak", "mismatch"),
                "流量-绿信比一致性偏弱，印证绿灯错配"
                if flow_green_verdict in ("weak", "mismatch")
                else "",
            ),
            _line(
                structure_limited and bool(deficit_turn_label),
                f"{deficit_turn_label}绿灯已触最小绿（亏空 {deficit_ratio_max:.0%}）"
                if structure_limited and deficit_turn_label and deficit_ratio_max is not None
                else "",
            ),
        ]
    )

    return {
        "type": dtype,
        "headline": headline,
        "lever": lever,
        "severity": severity,
        "evidence": evidence,
        "structure_limited": structure_limited,
        "turn_balance": _turn_balance_payload(over_turn, spare_turn, low_util),
    }


def _turn_balance_payload(
    over_turn: dict[str, Any] | None,
    spare_turn: dict[str, Any] | None,
    low_util: float,
) -> dict[str, Any]:
    """过饱和方 vs 绿灯富余方，供前端展示可核对指标。"""
    payload: dict[str, Any] = {"spare_util_threshold": low_util}
    if over_turn:
        payload["over"] = over_turn
    if spare_turn:
        payload["spare"] = spare_turn
    return payload


def _turn_row_metrics(turn: dict[str, Any]) -> dict[str, Any] | None:
    label = turn.get("label")
    if not label:
        return None
    return {
        "label": str(label),
        "turn_saturation": _float(turn.get("turn_saturation")),
        "green_utilization": _float(turn.get("green_utilization")),
    }


def _best_over_turn(by_turn: list[dict[str, Any]], sat_high: float) -> dict[str, Any] | None:
    """最饱和且达高饱和阈值的转向（含饱和度、绿灯利用率）。"""
    best: dict[str, Any] | None = None
    best_sat = -1.0
    for turn in by_turn:
        metrics = _turn_row_metrics(turn)
        if not metrics:
            continue
        sat = metrics.get("turn_saturation")
        if sat is None or sat <= best_sat:
            continue
        best_sat = sat
        best = metrics
    if best is not None and best_sat >= sat_high:
        return best
    return None


def _best_spare_turn(
    by_turn: list[dict[str, Any]],
    *,
    exclude: str | None = None,
    low_util: float,
) -> dict[str, Any] | None:
    """绿灯富余方：利用率低于阈值且最低的转向（须有可展示的利用率）。"""
    best: dict[str, Any] | None = None
    best_util = 2.0
    for turn in by_turn:
        metrics = _turn_row_metrics(turn)
        if not metrics:
            continue
        if exclude and metrics["label"] == exclude:
            continue
        util = metrics.get("green_utilization")
        if util is None or util >= low_util:
            continue
        if util < best_util:
            best_util = util
            best = metrics
    return best


def _over_saturated_turn(by_turn: list[dict[str, Any]], sat_high: float) -> str | None:
    """兼容旧调用：返回过饱和转向 label。"""
    row = _best_over_turn(by_turn, sat_high)
    return row["label"] if row else None


def _spare_green_turn(
    by_turn: list[dict[str, Any]], *, exclude: str | None = None
) -> str | None:
    """兼容旧调用：返回富余转向 label（带阈值）。"""
    low_util = threshold_value("green", "low_utilization_diagnosis", default=0.60)
    row = _best_spare_turn(by_turn, exclude=exclude, low_util=low_util)
    return row["label"] if row else None


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
    primary: dict[str, Any] | None = None,
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

    guidance_data = data
    if primary is not None:
        guidance_data = {
            **data,
            "flow_timing_governance": {
                **(data.get("flow_timing_governance") or {}),
                "primary_diagnosis": primary,
            },
        }

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
            governance=guidance_for_category("saturation", guidance_data)
            or _rule_governance(rules_by_category["saturation"]),
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
            governance=guidance_for_category("imbalance", guidance_data)
            or _rule_governance(rules_by_category["imbalance"]),
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
                        f"绿灯利用率 {green_util:.2f}" if green_util is not None else "",
                    ),
                    _line(empty_sustained, "连续15分钟低利用（检查单）"),
                ]
            ),
            governance=guidance_for_category("empty_green", guidance_data)
            or _rule_governance(rules_by_category["empty_green"]),
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
            governance=guidance_for_category("spillback", guidance_data)
            or _rule_governance(rules_by_category["spillback"]),
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


def _build_summary(primary: dict[str, Any], detected: list[dict[str, Any]]) -> str:
    headline = str(primary.get("headline") or "").strip()
    if not detected:
        return headline
    labels = [p["label"] for p in detected]
    return f"{headline}；同步扫描命中：{'、'.join(labels)}"


def _governance_narrative(primary: dict[str, Any], detected: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    headline = str(primary.get("headline") or "").strip()
    lever = str(primary.get("lever") or "").strip()
    if headline:
        lines.append(headline + "。")
    if lever:
        lines.append(lever + "。")
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
