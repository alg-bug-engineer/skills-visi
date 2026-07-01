"""治理建议生成：上游溯源与用户经验等上下文拼装。"""

from __future__ import annotations

from typing import Any

from intersection_agent.models.domain import SuggestionReference
from intersection_agent.services.governance_action_plan_service import build_action_plan


def derive_suggestion_references(
    case_matches: list[dict[str, Any]] | None,
    reused_experience: list[str] | None,
    *,
    inter_id: str | None,
    cap: int = 6,
) -> list[SuggestionReference]:
    """由同类专家案例 + 本路口复用经验确定性派生建议的可溯源依据。

    - 专家场景 → industry 依据（跳转案例库·行业案例）。
    - 本路口存在复用经验 → intersection 依据（跳转案例库·路口案例）。
    去重（按 id），上限 cap。
    """
    refs: list[SuggestionReference] = []
    seen: set[str] = set()

    for sc in case_matches or []:
        scenario_id = str(sc.get("scenario_id") or "").strip()
        if not scenario_id:
            continue
        ref_id = f"industry:{scenario_id}"
        if ref_id in seen:
            continue
        summary = str(sc.get("description") or "").strip()
        if not summary:
            problems = sc.get("problems") or []
            summary = "、".join(
                str(p.get("problem", "")) for p in problems[:2] if p.get("problem")
            )
        refs.append(
            SuggestionReference(
                type="industry",
                id=ref_id,
                title=str(sc.get("scenario_name") or scenario_id),
                summary=summary[:120],
                scenario_id=scenario_id,
            )
        )
        seen.add(ref_id)

    if reused_experience and inter_id:
        ref_id = f"intersection:{inter_id}"
        if ref_id not in seen:
            refs.append(
                SuggestionReference(
                    type="intersection",
                    id=ref_id,
                    title=str(inter_id),
                    summary=str(reused_experience[0])[:120],
                )
            )
            seen.add(ref_id)

    return refs[:cap]


def _fmt_turn_split(split: list[dict[str, Any]] | None) -> str:
    if not split:
        return "无转向拆分"
    parts: list[str] = []
    for s in split:
        turn = s.get("turn") or "—"
        if s.get("data_gap"):
            parts.append(f"{turn}（数仓无记录，待核查）")
            continue
        pct = s.get("share_pct")
        parts.append(f"{turn}{pct}%" if pct is not None else turn)
    return "、".join(parts)


def synthesize_flow_trace_from_upstream(upstream_trace: dict[str, Any]) -> dict[str, Any]:
    """将上游治理溯源结果转为 flow_trace 风格 hints，供 action_plan 消费。"""
    hints: list[dict[str, Any]] = []
    for tree in upstream_trace.get("trees") or []:
        approach = str(tree.get("approach") or "")

        def walk(node: dict[str, Any]) -> None:
            split = node.get("turn_split") or []
            dom = split[0] if split and not split[0].get("data_gap") else None
            name = node.get("inter_name") or node.get("inter_id")
            if node.get("decision") == "治理落点" and name:
                hints.append(
                    {
                        "type": "upstream_coordination",
                        "problem_turn": approach,
                        "inter_id": node.get("inter_id"),
                        "inter_name": name,
                        "feed_direction": dom.get("turn", "") if dom else "",
                        "coverage": dom.get("share_pct") if dom else None,
                        "turn_split": _fmt_turn_split(split),
                    }
                )
            for child in node.get("children") or []:
                walk(child)

        root = tree.get("root") or {}
        walk(root)
    if not hints:
        return {"available": False}
    return {"available": True, "governance_hints": hints}


def format_upstream_trace_for_prompt(data: dict[str, Any]) -> str:
    """上游溯源分镜摘要，供 LLM 写入治理建议。"""
    trace = data.get("upstream_trace") or {}
    trees = trace.get("trees") or []
    points = trace.get("governance_points") or []
    if not trees and not points:
        return "无上游溯源结果。"

    lines: list[str] = []
    for tree in trees:
        approach = tree.get("approach") or "—"
        target = tree.get("target") or {}
        lines.append(
            f"- {approach}：自「{target.get('name') or target.get('inter_id')}」向上游追溯"
        )

        def walk(node: dict[str, Any], depth: int = 1) -> None:
            name = node.get("inter_name") or node.get("inter_id")
            if not name:
                return
            sat = node.get("approach_profiles")
            sat_txt = "待核查数仓"
            if node.get("saturation") is not None and float(node["saturation"]) > 0.01:
                sat_txt = f"饱和{float(node['saturation']):.2f}"
            split_txt = _fmt_turn_split(node.get("turn_split"))
            decision = node.get("decision") or "继续上溯"
            indent = "  " * depth
            lines.append(
                f"{indent}· 上游{name}：{sat_txt}；汇入车流 {split_txt}；判定「{decision}」"
            )
            for child in node.get("children") or []:
                walk(child, depth + 1)

        walk(tree.get("root") or {}, 1)

    if points:
        lines.append("- 治理落点：")
        for p in points[:4]:
            lines.append(
                f"  · {p.get('approach')} → {p.get('inter_name')}（hop {p.get('hop')}）"
            )
    return "\n".join(lines)


def format_user_experience_for_prompt(
    data: dict[str, Any], user_suggestion: str | None
) -> str:
    """用户口述约束、量化边界与复用经验。"""
    parts: list[str] = []
    if user_suggestion and user_suggestion.strip():
        parts.append(f"- 用户约束/经验：{user_suggestion.strip()}")
    qc = data.get("quantitative_constraints") or {}
    if qc.get("narrative"):
        parts.append(f"- 量化边界：{qc['narrative']}")
    reused = data.get("reused_experience") or []
    if reused:
        parts.append(f"- 本次复用经验：{'；'.join(str(x) for x in reused)}")
    nlu = data.get("meta", {}).get("nlu") or {}
    directions = nlu.get("directions") or data.get("nlu_directions")
    if directions:
        parts.append(f"- 关注方向：{directions}")
    if not parts:
        return "用户未补充额外约束。"
    return "\n".join(parts)


def _upstream_action_sentence(data: dict[str, Any]) -> str:
    """从溯源落点提炼一句可执行建议。"""
    trace = data.get("upstream_trace") or {}
    points = trace.get("governance_points") or []
    if points:
        names = [str(p.get("inter_name") or p.get("inter_id")) for p in points[:2]]
        names = [n for n in names if n]
        if names:
            joined = "、".join(names)
            return (
                f"溯源显示车流主要来自上游{joined}，"
                "建议在该治理落点协同优化放行节奏或截流，从源头削减进入本路口车流。"
            )
    flow_gov = data.get("flow_timing_governance") or {}
    supplement = str(flow_gov.get("flow_trace_supplement") or "").strip()
    if supplement:
        return supplement.replace("上游溯源：", "")
    hints = (data.get("flow_trace") or {}).get("governance_hints") or []
    if hints:
        h = hints[0]
        name = h.get("inter_name")
        if name:
            turn = h.get("feed_direction") or ""
            return (
                f"其中主要车流来自上游{name}{turn}，"
                f"建议优先在{name}协同信控，避免仅在本路口加绿。"
            )
    trees = trace.get("trees") or []
    if trees and not points:
        return "上游路口普遍过饱和，单点信控优化空间有限，需协调控流或扩容手段。"
    return ""


def compose_suggestion_narrative(
    data: dict[str, Any],
    *,
    user_suggestion: str | None = None,
    quantitative_constraints: dict[str, Any] | None = None,
) -> str:
    """由 action_plan、溯源与用户约束拼装治理建议正文（不重复诊断 headline）。"""
    flow_gov = data.get("flow_timing_governance") or {}
    action_plan = flow_gov.get("action_plan") or {}
    primary = flow_gov.get("primary_diagnosis") or {}
    meta = data.get("meta") or {}
    tp = meta.get("time_period") or {}
    time_label = str(tp.get("label") or "").strip()
    intersection = str(meta.get("intersection") or "").strip()

    sentences: list[str] = []

    opener = ""
    if intersection and time_label:
        opener = f"针对{intersection}{time_label}，"
    elif intersection:
        opener = f"针对{intersection}，"

    template = str(action_plan.get("narrative_template") or "").strip()
    plan_type = str(action_plan.get("action_type") or "")
    if template:
        body = template if not opener or template.startswith(opener.rstrip("，")) else f"{opener}{template}"
        sentences.append(body.rstrip("。") + "。")
    else:
        transfer = action_plan.get("transfer_seconds")
        donor = (action_plan.get("donor_turn") or {}).get("label")
        recipient = (action_plan.get("recipient_turn") or {}).get("label")
        if plan_type == "reallocate_green" and donor and recipient and transfer:
            sentences.append(
                f"{opener}建议保持周期不变，从{donor}向{recipient}挪绿约 {transfer}s，"
                "纠正绿信比错配、缓解主方向排队。"
            )
        elif plan_type == "upstream_coordination":
            up_name = action_plan.get("upstream_inter_name") or "上游来源路口"
            sentences.append(
                f"{opener}本路口已过饱和、单点加绿空间有限；"
                f"建议优先在上游{up_name}协同优化放行节奏，从源头削减进入车流。"
            )
        elif action_plan.get("headline"):
            sentences.append(f"{opener}{action_plan['headline']}。".lstrip())
        else:
            lever = str(primary.get("lever") or "").strip()
            if lever and len(lever) >= 12:
                sentences.append(f"{opener}{lever.rstrip('。')}。")

    upstream = _upstream_action_sentence(data)
    if upstream and upstream not in "".join(sentences):
        sentences.append(upstream.rstrip("。") + "。")

    qc = quantitative_constraints or data.get("quantitative_constraints") or {}
    qc_text = str(qc.get("narrative") or "").strip()
    if qc_text:
        sentences.append(f"须严守量化边界：{qc_text.rstrip('。')}。")
    elif user_suggestion and user_suggestion.strip():
        sentences.append(f"须兼顾用户约束：{user_suggestion.strip().rstrip('。')}。")

    case_experience = data.get("case_experience")
    if isinstance(case_experience, list) and case_experience:
        first = case_experience[0]
        if isinstance(first, dict) and first.get("measure"):
            sentences.append(f"同类场景参考：{first['measure']}。")

    return "".join(sentences)


def is_healthy_monitoring_case(flow_timing_governance: dict[str, Any] | None) -> bool:
    """供需与配时基本匹配、无需治理动作时，走监测反馈终态。"""
    primary = (flow_timing_governance or {}).get("primary_diagnosis") or {}
    return str(primary.get("type") or "") == "basically_matched"


def compose_monitoring_feedback_narrative(data: dict[str, Any]) -> str:
    """无显著信控问题时，生成数据解释型监测反馈（非治理动作）。"""
    meta = data.get("meta") or {}
    tp = meta.get("time_period") or {}
    time_label = str(tp.get("label") or "").strip()
    intersection = str(meta.get("intersection") or "").strip()
    tf = data.get("traffic_flow") or {}
    ev = data.get("evaluation") or {}
    sp = data.get("signal_plan") or {}
    flow_gov = data.get("flow_timing_governance") or {}
    primary = flow_gov.get("primary_diagnosis") or {}

    if intersection and time_label:
        opener = f"针对{intersection}{time_label}，"
    elif intersection:
        opener = f"针对{intersection}，"
    else:
        opener = ""

    metric_parts: list[str] = []
    sat = tf.get("saturation_rate")
    if sat is not None:
        metric_parts.append(f"综合饱和度 {float(sat):.2f}")
    los = ev.get("level_of_service_label") or ev.get("level_of_service")
    if los:
        metric_parts.append(f"服务水平 {los}")
    imb = ev.get("imbalance_index")
    if imb is not None:
        metric_parts.append(f"方向失衡 {float(imb):.2f}")
    cycle = sp.get("cycle_length")
    if cycle is not None:
        metric_parts.append(f"信号周期 {int(float(cycle))}s")
    green_util = ev.get("green_utilization")
    if green_util is not None:
        metric_parts.append(f"绿灯利用率 {float(green_util):.2f}")

    turns = sorted(
        (data.get("granularity") or {}).get("by_turn") or [],
        key=lambda row: float(row.get("turn_saturation") or 0),
        reverse=True,
    )[:3]
    turn_lines: list[str] = []
    for row in turns:
        label = row.get("label")
        turn_sat = row.get("turn_saturation")
        turn_util = row.get("green_utilization")
        if not label or turn_sat is None:
            continue
        segment = f"{label}饱和度 {float(turn_sat):.2f}"
        if turn_util is not None:
            segment += f"、绿灯利用 {float(turn_util):.2f}"
        turn_lines.append(segment)

    sentences: list[str] = []
    if metric_parts:
        sentences.append(f"{opener}当前运行指标整体平稳：{'，'.join(metric_parts)}。")
    elif opener:
        sentences.append(f"{opener}当前运行指标未见明显异常。")

    lever = str(primary.get("lever") or "").strip()
    headline = str(primary.get("headline") or "").strip()
    joined = "".join(sentences)
    if lever and lever not in joined:
        sentences.append(f"{lever.rstrip('。')}。")
    elif headline and headline not in joined:
        sentences.append(f"{headline.rstrip('。')}。")

    if turn_lines:
        sentences.append(f"主要转向：{'；'.join(turn_lines)}。")

    for ev_line in (primary.get("evidence") or [])[:3]:
        line = str(ev_line).strip()
        if line and line not in "".join(sentences):
            sentences.append(f"{line.rstrip('。')}。")

    sentences.append("本次结论已记录，将持续关注该路口高峰运行表现；暂无需调整信控方案。")
    return "".join(sentences)


def narrative_echoes_diagnosis(narrative: str, data: dict[str, Any]) -> bool:
    """LLM 输出是否只是在复述四维诊断 headline。"""
    text = (narrative or "").strip()
    if not text:
        return True
    primary = (data.get("flow_timing_governance") or {}).get("primary_diagnosis") or {}
    headline = str(primary.get("headline") or "").strip()
    if headline and headline in text:
        return True
    lever = str(primary.get("lever") or "").strip()
    if lever and len(text) < len(lever) + 40 and lever in text:
        return True
    return False


def prepare_suggestion_data(data: dict[str, Any]) -> dict[str, Any]:
    """在生成治理建议前合并上游溯源并刷新 action_plan。"""
    payload = dict(data)
    upstream = payload.get("upstream_trace") or {}
    flow_trace = dict(payload.get("flow_trace") or {})
    if upstream.get("trees") and not flow_trace.get("governance_hints"):
        merged = synthesize_flow_trace_from_upstream(upstream)
        if merged.get("available"):
            flow_trace = {**flow_trace, **merged}
            payload["flow_trace"] = flow_trace

    flow_gov = dict(payload.get("flow_timing_governance") or {})
    primary = flow_gov.get("primary_diagnosis")
    problems = flow_gov.get("problems")
    plan = build_action_plan(payload, primary=primary, problems=problems)
    flow_gov["action_plan"] = plan
    if upstream.get("trees") and plan.get("action_type") == "upstream_coordination":
        supplement = (
            f"上游溯源：建议优先在{plan.get('upstream_inter_name')}协同信控，"
            f"削减进入本路口车流。"
        )
        flow_gov["flow_trace_supplement"] = supplement
    payload["flow_timing_governance"] = flow_gov
    return payload
