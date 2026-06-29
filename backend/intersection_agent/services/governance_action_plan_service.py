"""Evidence-backed governance action plan (green reallocation / non-timing measures)."""

from __future__ import annotations

from typing import Any

from intersection_agent.utils.thresholds_loader import threshold_value


def build_action_plan(
    data: dict[str, Any],
    *,
    primary: dict[str, Any] | None = None,
    problems: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Derive a structured, data-backed action plan for suggestion generation.

  Uses turn saturation, green utilization, flow_green_fit shares, and min-green
  constraints — not a single saturation×constant formula.
    """
    flow_gov = data.get("flow_timing_governance") or {}
    primary = primary or flow_gov.get("primary_diagnosis") or {}
    problems = problems or flow_gov.get("problems") or []

    timing_profile = data.get("timing_profile") or {}
    by_turn = ((data.get("granularity") or {}).get("by_turn")) or []
    flow_green = timing_profile.get("flow_green_fit") or {}
    deficit_map = {
        str(t.get("label")): t for t in (timing_profile.get("deficit_turns") or []) if t.get("label")
    }
    cycle = _float(timing_profile.get("cycle_length")) or _float(
        (data.get("signal_plan") or {}).get("cycle_length")
    ) or 120.0

    turns = _merge_turn_metrics(by_turn, flow_green)
    detected = {str(p.get("category")) for p in problems if p.get("detected")}
    primary_type = str(primary.get("type") or "")

    spillback = "spillback" in detected
    if spillback and _spillback_severe(data):
        return _spillback_plan(data, turns, cycle)

    if primary_type == "capacity_bottleneck":
        return _capacity_plan(primary, turns, cycle, flow_green)

    if primary_type == "basically_matched":
        return _maintain_plan(primary)

    # timing_optimizable or saturation/imbalance with reallocation evidence
    recipient, donor = _pick_reallocate_pair(turns, deficit_map)
    if recipient and donor:
        plan = _reallocate_plan(primary, recipient, donor, cycle, flow_green, deficit_map)
        if plan.get("transfer_seconds", 0) > 0:
            return plan

    if _should_increase_green(turns, primary_type, detected):
        return _increase_green_plan(primary, turns, cycle, data)

    return _guidance_fallback(primary, problems, turns, cycle)


def format_action_plan_for_prompt(plan: dict[str, Any]) -> str:
    """Block text injected into LLM suggestion prompt."""
    if not plan:
        return "无结构化方案"
    lines = [
        f"- 动作类型：{plan.get('action_type')}",
        f"- 要点：{plan.get('headline')}",
        f"- 数据依据：{plan.get('narrative_template')}",
    ]
    if plan.get("transfer_seconds") is not None:
        lines.append(f"- 建议挪绿：{plan.get('transfer_seconds')} 秒（保持周期不变）")
    if plan.get("donor_turn"):
        d = plan["donor_turn"]
        if d.get("green_utilization") is not None:
            lines.append(
                f"- 供绿方 {d.get('label')}：计划绿 {d.get('green_sec')}s，"
                f"利用率 {d['green_utilization']:.0%}"
            )
        else:
            lines.append(f"- 供绿方 {d.get('label')}")
    if plan.get("recipient_turn"):
        r = plan["recipient_turn"]
        lines.append(
            f"- 受绿方 {r.get('label')}：饱和度 {r.get('turn_saturation'):.2f}，"
            f"流量占比 {r.get('flow_share'):.0%}、绿信比 {r.get('green_share'):.0%}"
            if r.get("flow_share") is not None and r.get("green_share") is not None
            else f"- 受绿方 {r.get('label')}：饱和度 {r.get('turn_saturation'):.2f}"
        )
    for ev in plan.get("evidence") or []:
        lines.append(f"  · {ev}")
    lines.append("必须沿用上述秒数与转向，只可润色语言，不得改写数值或凭空增加相位。")
    return "\n".join(lines)


def _merge_turn_metrics(
    by_turn: list[dict[str, Any]],
    flow_green: dict[str, Any],
) -> list[dict[str, Any]]:
    fg_by_label = {
        str(item.get("label")): item for item in (flow_green.get("items") or []) if item.get("label")
    }
    merged: list[dict[str, Any]] = []
    for row in by_turn:
        label = str(row.get("label") or "")
        if not label:
            continue
        fg = fg_by_label.get(label, {})
        green_sec = _float(fg.get("effective_green_s") or fg.get("green_time_plan"))
        flow_vph = _float(fg.get("flow_vph") or fg.get("turn_flow_total"))
        merged.append(
            {
                "label": label,
                "turn_saturation": _float(row.get("turn_saturation")),
                "green_utilization": _float(row.get("green_utilization")),
                "green_sec": green_sec,
                "flow_vph": flow_vph,
            }
        )
    flow_shares, green_shares = _share_vectors(flow_green, merged)
    for idx, turn in enumerate(merged):
        if idx < len(flow_shares):
            turn["flow_share"] = flow_shares[idx]
        if idx < len(green_shares):
            turn["green_share"] = green_shares[idx]
    merged.sort(
        key=lambda t: (t.get("turn_saturation") is not None, t.get("turn_saturation") or 0),
        reverse=True,
    )
    return merged


def _share_vectors(
    flow_green: dict[str, Any],
    turns: list[dict[str, Any]],
) -> tuple[list[float], list[float]]:
    fs = flow_green.get("flow_shares") or []
    gs = flow_green.get("green_shares") or []
    if fs and gs and len(fs) == len(turns):
        return [float(x) for x in fs], [float(x) for x in gs]
    flows = [t.get("flow_vph") or 0 for t in turns]
    greens = [t.get("green_sec") or 0 for t in turns]
    ft, gt = sum(flows), sum(greens)
    if ft <= 0 or gt <= 0:
        return [], []
    return [round(f / ft, 4) for f in flows], [round(g / gt, 4) for g in greens]


def _pick_reallocate_pair(
    turns: list[dict[str, Any]],
    deficit_map: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    sat_high = threshold_value("saturation", "high", default=0.80)
    low_util = threshold_value("green", "low_utilization_diagnosis", default=0.60)

    recipient: dict[str, Any] | None = None
    for turn in turns:
        sat = turn.get("turn_saturation")
        if sat is not None and sat >= sat_high:
            recipient = turn
            break

    if recipient is None:
        return None, None

    donor: dict[str, Any] | None = None
    best_util = 2.0
    for turn in turns:
        if turn["label"] == recipient["label"]:
            continue
        util = turn.get("green_utilization")
        if util is None or util >= low_util:
            continue
        if not _can_donate(str(turn["label"]), deficit_map):
            continue
        if util < best_util:
            best_util = util
            donor = turn
    return recipient, donor


def _can_donate(label: str, deficit_map: dict[str, dict[str, Any]]) -> bool:
    deficit = deficit_map.get(label)
    if not deficit:
        return True
    ratio = _float(deficit.get("deficit_ratio"))
    return ratio is None or ratio <= 0


def _estimate_transfer_seconds(
    donor: dict[str, Any],
    recipient: dict[str, Any],
    *,
    cycle: float,
) -> int:
    green = donor.get("green_sec") or 0
    util = donor.get("green_utilization") or 0
    sat = recipient.get("turn_saturation") or 0
    sat_high = threshold_value("saturation", "high", default=0.80)

    spare_from_util = green * max(0.0, 0.85 - util) * 0.65 if green > 0 else 0
    need_from_sat = max(0.0, sat - sat_high) * cycle * 0.12
    cap_cycle = cycle * 0.12
    transfer = min(spare_from_util, need_from_sat, cap_cycle, 25.0)
    return max(5, int(round(transfer))) if transfer >= 5 else 0


def _reallocate_plan(
    primary: dict[str, Any],
    recipient: dict[str, Any],
    donor: dict[str, Any],
    cycle: float,
    flow_green: dict[str, Any],
    deficit_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    transfer = _estimate_transfer_seconds(donor, recipient, cycle=cycle)
    r_label, d_label = recipient["label"], donor["label"]
    r_sat = recipient.get("turn_saturation") or 0
    d_util = donor.get("green_utilization") or 0
    mismatch = str(flow_green.get("verdict") or "") in ("weak", "mismatch")

    evidence = [
        f"{r_label} 转向饱和度 {r_sat:.2f}",
        f"{d_label} 绿灯利用率 {d_util:.0%}",
    ]
    if recipient.get("flow_share") is not None and recipient.get("green_share") is not None:
        evidence.append(
            f"{r_label} 流量占比 {recipient['flow_share']:.0%}、"
            f"绿信比 {recipient['green_share']:.0%}"
        )
    if mismatch:
        evidence.append("流量-绿信比一致性偏弱")

    headline = f"保持周期 {cycle:.0f}s，从{d_label}向{r_label}挪绿约 {transfer}s"
    template = (
        f"针对{r_label}严重过饱和（{r_sat:.2f}）且{d_label}绿灯利用率仅{d_util:.0%}，"
        f"建议在周期不变前提下压缩{d_label}约 {transfer}s 有效绿灯并转给{r_label}，"
        "以纠正绿信比错配、缓解主方向排队。"
    )
    if primary.get("structure_limited"):
        template += "注意部分转向已触最小绿，挪绿需结合相位结构审慎实施。"

    return {
        "action_type": "reallocate_green",
        "headline": headline,
        "narrative_template": template,
        "transfer_seconds": transfer,
        "cycle_unchanged": True,
        "direction": "reallocate",
        "donor_turn": _turn_snapshot(donor),
        "recipient_turn": _turn_snapshot(recipient),
        "confidence": 0.82 if mismatch else 0.78,
        "evidence": evidence,
        "data_gaps": _plan_gaps(donor, recipient, deficit_map),
    }


def _increase_green_plan(
    primary: dict[str, Any],
    turns: list[dict[str, Any]],
    cycle: float,
    data: dict[str, Any],
) -> dict[str, Any]:
    sat_high = threshold_value("saturation", "high", default=0.80)
    low_util = threshold_value("green", "low_utilization_diagnosis", default=0.60)
    target = next((t for t in turns if (t.get("turn_saturation") or 0) >= sat_high), turns[0] if turns else None)
    if not target:
        return _guidance_fallback(primary, [], turns, cycle)

    util = target.get("green_utilization")
    sat = target.get("turn_saturation") or _float((data.get("traffic_flow") or {}).get("saturation_rate")) or 0
    if util is not None and util >= low_util + 0.1:
        return _guidance_fallback(primary, [], turns, cycle)

    add_sec = max(5, min(int(round((sat - sat_high) * cycle * 0.15)), 20))
    label = target["label"]
    template = (
        f"{label}饱和度 {sat:.2f} 且绿灯利用率 {util:.0%} 仍有空间，"
        f"可在周期内为{label}增加约 {add_sec}s 有效绿灯；"
        "若其他转向已高利用，优先评估是否加周期而非继续挤占。")
    return {
        "action_type": "increase_green",
        "headline": f"为{label}增加约 {add_sec}s 有效绿灯",
        "narrative_template": template,
        "transfer_seconds": add_sec,
        "cycle_unchanged": True,
        "direction": "increase",
        "recipient_turn": _turn_snapshot(target),
        "donor_turn": None,
        "confidence": 0.72,
        "evidence": [f"{label} 饱和度 {sat:.2f}", f"绿灯利用率 {util:.0%}" if util is not None else ""],
        "data_gaps": [],
    }


def _capacity_plan(
    primary: dict[str, Any],
    turns: list[dict[str, Any]],
    cycle: float,
    flow_green: dict[str, Any],
) -> dict[str, Any]:
    max_sat = max((t.get("turn_saturation") or 0 for t in turns), default=0)
    template = (
        f"各转向普遍高饱和（最高 {max_sat:.2f}），绿信比近最优，"
        "单点加绿或挪绿空间有限；建议从加大周期、干线绿波协调、车道展宽或需求调控入手。"
    )
    return {
        "action_type": "capacity_non_timing",
        "headline": "能力瓶颈，优先非配时手段",
        "narrative_template": template,
        "transfer_seconds": 0,
        "cycle_unchanged": None,
        "direction": "none",
        "donor_turn": None,
        "recipient_turn": None,
        "confidence": 0.8,
        "evidence": list(primary.get("evidence") or []),
        "data_gaps": ["turn_level_green_sec"] if not (flow_green.get("items")) else [],
    }


def _spillback_plan(
    data: dict[str, Any],
    turns: list[dict[str, Any]],
    cycle: float,
) -> dict[str, Any]:
    pe = (data.get("problem_evidence") or {}).get("metrics") or {}
    risk = _float(pe.get("spillback_risk_max"))
    template = (
        "排队接近或超过进口存储能力，溢流风险高；"
        "优先控制上游放行、出口清空与边界控流，必要时缩短周期防锁死，"
        "不宜单靠增加主方向绿灯。"
    )
    if risk is not None:
        template = f"溢流风险 {risk:.2f}；" + template
    return {
        "action_type": "spillback_control",
        "headline": "防溢流优先，控制上游放行",
        "narrative_template": template,
        "transfer_seconds": 0,
        "cycle_unchanged": None,
        "direction": "none",
        "donor_turn": None,
        "recipient_turn": None,
        "confidence": 0.85,
        "evidence": [f"溢流风险 {risk:.2f}"] if risk is not None else [],
        "data_gaps": [],
    }


def _maintain_plan(primary: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_type": "maintain",
        "headline": "维持监测",
        "narrative_template": str(primary.get("lever") or "供需与配时基本匹配，维持现有方案并持续监测。"),
        "transfer_seconds": 0,
        "cycle_unchanged": True,
        "direction": "none",
        "donor_turn": None,
        "recipient_turn": None,
        "confidence": 0.65,
        "evidence": list(primary.get("evidence") or []),
        "data_gaps": [],
    }


def _guidance_fallback(
    primary: dict[str, Any],
    problems: list[dict[str, Any]],
    turns: list[dict[str, Any]],
    cycle: float,
) -> dict[str, Any]:
    lever = str(primary.get("lever") or "").strip()
    detected = [p for p in problems if p.get("detected") and p.get("governance")]
    gov = detected[0].get("governance") if detected else lever
    return {
        "action_type": "guidance_only",
        "headline": str(primary.get("headline") or "按四维诊断方向优化"),
        "narrative_template": gov or lever or "结合运行数据优化配时结构。",
        "transfer_seconds": 0,
        "cycle_unchanged": None,
        "direction": "increase",
        "donor_turn": None,
        "recipient_turn": _turn_snapshot(turns[0]) if turns else None,
        "confidence": 0.6,
        "evidence": list(primary.get("evidence") or []),
        "data_gaps": ["insufficient_turn_pair"] if not turns else [],
    }


def _should_increase_green(
    turns: list[dict[str, Any]],
    primary_type: str,
    detected: set[str],
) -> bool:
    if primary_type == "timing_optimizable":
        return False
    return "saturation" in detected and bool(turns)


def _spillback_severe(data: dict[str, Any]) -> bool:
    pe = (data.get("problem_evidence") or {}).get("metrics") or {}
    risk = _float(pe.get("spillback_risk_max"))
    spill_high = threshold_value("spillback", "risk_high", default=0.80)
    return risk is not None and risk >= spill_high


def _turn_snapshot(turn: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": turn.get("label"),
        "turn_saturation": turn.get("turn_saturation"),
        "green_utilization": turn.get("green_utilization"),
        "green_sec": turn.get("green_sec"),
        "flow_share": turn.get("flow_share"),
        "green_share": turn.get("green_share"),
    }


def _plan_gaps(
    donor: dict[str, Any],
    recipient: dict[str, Any],
    deficit_map: dict[str, dict[str, Any]],
) -> list[str]:
    gaps: list[str] = []
    if donor.get("green_sec") is None:
        gaps.append("donor_green_sec_missing")
    if recipient.get("green_sec") is None:
        gaps.append("recipient_green_sec_missing")
    if donor["label"] in deficit_map:
        gaps.append("donor_min_green_pressure")
    return gaps


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
