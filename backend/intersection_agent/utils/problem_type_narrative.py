"""Problem-type aware narrative and metric hints (shared by evidence + runtime panel)."""

from __future__ import annotations

from typing import Any

PROBLEM_TYPE_PRIORITY = ("conflict", "spillback", "empty_green", "congestion")


def resolve_primary_problem_type(problem_types: list[str] | None) -> str:
    if not problem_types:
        return "congestion"
    for pt in PROBLEM_TYPE_PRIORITY:
        if pt in problem_types:
            return pt
    return "congestion"


def _arm_dir_label(arm: dict[str, Any]) -> str:
    return str(arm.get("dir4_label") or arm.get("dir8_label") or "")[:1]


def infer_mixed_turn_approaches(cognition: dict[str, Any] | None) -> list[str]:
    """进口同时存在左转与直行车道 → 混行线索。"""
    mixed: list[str] = []
    if not cognition:
        return mixed
    for arm in cognition.get("arms") or []:
        if str(arm.get("link_role") or "") not in ("", "entrance"):
            if arm.get("link_role") not in (None, "entrance"):
                continue
        turns: set[str] = set()
        lane_info = str(arm.get("lane_info") or "")
        if "混合" in lane_info or "混行" in lane_info:
            dir_l = _arm_dir_label(arm)
            if dir_l:
                mixed.append(f"{dir_l}进口")
            continue
        for lane in arm.get("lanes") or []:
            move = str(lane.get("turn_move") or lane.get("turn_type") or "")
            if "左" in move:
                turns.add("左")
            if "直" in move:
                turns.add("直")
        if "左" in turns and "直" in turns:
            dir_l = _arm_dir_label(arm)
            if dir_l:
                mixed.append(f"{dir_l}进口")
    return mixed


def user_mentions(user_context: str, *tokens: str) -> bool:
    text = user_context or ""
    return any(t in text for t in tokens)


def build_conflict_story_beats(
    evidence: dict[str, Any],
    *,
    user_context: str = "",
    data_payload: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    beats: list[dict[str, str]] = []
    cognition = (data_payload or {}).get("cognition") or {}
    timing = evidence.get("timing_profile") or (data_payload or {}).get("timing_profile") or {}
    channel = (data_payload or {}).get("channelization") or {}

    mixed = infer_mixed_turn_approaches(cognition)
    if mixed or user_mentions(user_context, "混行", "左转和直行", "左转与直行"):
        dirs = "、".join(mixed) if mixed else "关注进口"
        beats.append(
            {
                "phase": "conflict_channel",
                "title": "渠化匹配",
                "text": f"{dirs}存在左转与直行混行，车道功能与放行结构需对齐",
            }
        )
    elif channel.get("has_mixed_left"):
        beats.append(
            {
                "phase": "conflict_channel",
                "title": "渠化匹配",
                "text": "进口存在混合左转车道，与专用相位结构可能不匹配",
            }
        )

    fit = timing.get("flow_green_fit") or {}
    phase_text = str(fit.get("narrative") or "").strip()
    if user_mentions(user_context, "相位", "放行", "相序") or fit.get("verdict") == "mismatch":
        beats.append(
            {
                "phase": "conflict_phase",
                "title": "相位相序",
                "text": phase_text or "相位放行与流量结构不够顺畅，存在相序优化空间",
            }
        )
    elif timing.get("narrative") and any(k in str(timing["narrative"]) for k in ("相序", "冲突", "相位")):
        beats.append(
            {
                "phase": "conflict_phase",
                "title": "相位相序",
                "text": str(timing["narrative"])[:80],
            }
        )

    if user_mentions(user_context, "机非", "非机动车", "行人"):
        beats.append(
            {
                "phase": "conflict_nonmotor",
                "title": "机非冲突",
                "text": "机非冲突风险突出，需复核慢行保护与机动车放行时序",
            }
        )

    for rule in (data_payload or {}).get("matched_rules") or evidence.get("matched_rules") or []:
        if rule.get("focus_category") == "channelization" or "conflict" in str(rule.get("id") or ""):
            conclusion = str(rule.get("conclusion") or rule.get("name") or "").strip()
            if conclusion:
                beats.append(
                    {
                        "phase": "conflict_rule",
                        "title": "冲突类型",
                        "text": conclusion[:80],
                    }
                )
            break

    if not beats and user_mentions(user_context, "冲突"):
        beats.append(
            {
                "phase": "conflict_rule",
                "title": "冲突风险",
                "text": "用户描述的转向/相位冲突与渠化结构需进一步核验",
            }
        )
    return beats


def build_empty_green_story_beats(
    evidence: dict[str, Any],
    *,
    user_context: str = "",
    nlu_directions: list[str] | None = None,
) -> list[dict[str, str]]:
    beats: list[dict[str, str]] = []
    metrics = evidence.get("metrics") or {}
    eval_green = metrics.get("green_utilization")
    empty_rate = metrics.get("empty_green_rate")

    if eval_green is not None:
        beats.append(
            {
                "phase": "empty_green_util",
                "title": "绿灯利用",
                "text": f"路口绿灯利用率 {float(eval_green):.2f}，存在绿灯时间未有效服务车流",
            }
        )
    if empty_rate is not None:
        beats.append(
            {
                "phase": "empty_green_rate",
                "title": "空放率",
                "text": f"空放率约 {float(empty_rate):.2f}，部分相位绿灯放空明显",
            }
        )

    low_turns: list[str] = []
    for turn in evidence.get("by_turn") or []:
        gu = turn.get("green_utilization")
        label = str(turn.get("label") or "")
        if gu is not None and float(gu) < 0.55 and label:
            low_turns.append(f"{label}({float(gu):.2f})")
    if low_turns:
        beats.append(
            {
                "phase": "empty_green_turn",
                "title": "低利用转向",
                "text": f"低绿灯利用：{'、'.join(low_turns[:3])}",
            }
        )

    timing = evidence.get("timing_profile") or {}
    fit = timing.get("flow_green_fit") or {}
    if fit.get("verdict") == "mismatch" or fit.get("narrative"):
        beats.append(
            {
                "phase": "empty_green_split",
                "title": "绿信比",
                "text": str(fit.get("narrative") or "流量与绿信比匹配偏弱，存在可压缩空放相位"),
            }
        )

    if user_mentions(user_context, "没车", "无车", "空放", "放空") or user_mentions(
        user_context, "绿灯经常"
    ):
        spare_dir = next((d for d in (nlu_directions or []) if "西" in d), "西进口")
        busy_dir = next((d for d in (nlu_directions or []) if "东" in d), "东进口")
        beats.append(
            {
                "phase": "empty_green_contrast",
                "title": "空放对比",
                "text": f"{spare_dir}绿灯常无车放行，而{busy_dir}排队较长，绿信比分配不均",
            }
        )

    return beats


def build_spillback_story_beats(evidence: dict[str, Any]) -> list[dict[str, str]]:
    beats: list[dict[str, str]] = []
    metrics = evidence.get("metrics") or {}
    if metrics.get("max_queue_m") is not None:
        beats.append(
            {
                "phase": "spillback_queue",
                "title": "排队长度",
                "text": f"最大排队约 {float(metrics['max_queue_m']):.0f} m，接近或超过进口存储能力",
            }
        )
    if metrics.get("spillback_risk_max") is not None:
        risk = float(metrics["spillback_risk_max"])
        beats.append(
            {
                "phase": "spillback_risk",
                "title": "溢流风险",
                "text": f"溢流风险 {risk:.2f}，存在排队外溢隐患",
            }
        )
    if metrics.get("queue_storage_ratio_max") is not None:
        ratio = float(metrics["queue_storage_ratio_max"])
        beats.append(
            {
                "phase": "spillback_storage",
                "title": "排队存储比",
                "text": f"排队存储比 {ratio:.2f}，进口储车空间利用率偏高",
            }
        )
    return beats


def build_congestion_story_beats(evidence: dict[str, Any]) -> list[dict[str, str]]:
    """默认拥堵类验证叙事（常发/周期/饱和）。"""
    beats: list[dict[str, str]] = []
    chronic = evidence.get("chronic") or {}
    if chronic.get("verdict") and str(chronic["verdict"]).strip():
        beats.append({"phase": "chronic", "title": "常发性", "text": str(chronic["verdict"])})
    dow = evidence.get("dow_pattern") or {}
    if dow.get("verdict") and str(dow["verdict"]).strip():
        beats.append({"phase": "dow", "title": "周期性", "text": str(dow["verdict"])})

    metrics = evidence.get("metrics") or {}
    metric_bits: list[str] = []
    if metrics.get("saturation_rate") is not None:
        metric_bits.append(f"饱和度 {float(metrics['saturation_rate']):.2f}")
    if metrics.get("delay_index") is not None:
        metric_bits.append(f"延误指数 {float(metrics['delay_index']):.2f}")
    if metrics.get("level_of_service_label"):
        metric_bits.append(f"服务水平 {metrics['level_of_service_label']}")
    if metric_bits:
        beats.append(
            {
                "phase": "metrics",
                "title": "运行状态",
                "text": "，".join(metric_bits),
            }
        )
    return beats


def build_problem_diagnosis_story(
    evidence: dict[str, Any],
    *,
    problem_types: list[str] | None = None,
    user_context: str = "",
    data_payload: dict[str, Any] | None = None,
    nlu_directions: list[str] | None = None,
) -> list[dict[str, str]]:
    """Assemble verification beats prioritized by problem type."""
    primary = resolve_primary_problem_type(problem_types)
    beats: list[dict[str, str]] = []

    if primary == "conflict":
        beats.extend(
            build_conflict_story_beats(
                evidence, user_context=user_context, data_payload=data_payload
            )
        )
    elif primary == "spillback":
        beats.extend(build_spillback_story_beats(evidence))
    elif primary == "empty_green":
        beats.extend(
            build_empty_green_story_beats(
                evidence, user_context=user_context, nlu_directions=nlu_directions
            )
        )
    else:
        beats.extend(build_congestion_story_beats(evidence))

    timing = evidence.get("timing_profile") or {}
    if primary == "empty_green" and timing.get("narrative"):
        if not any(b.get("phase") == "empty_green_split" for b in beats):
            beats.append(
                {"phase": "timing", "title": "配时画像", "text": str(timing["narrative"])}
            )
    elif primary == "congestion" and timing.get("narrative"):
        beats.append({"phase": "timing", "title": "配时画像", "text": str(timing["narrative"])})

    # 多类型叠加：拥堵类补充常发（空放/冲突主问题时不抢主位）
    if primary != "congestion" and problem_types and "congestion" in problem_types:
        chronic = evidence.get("chronic") or {}
        if chronic.get("is_chronic") and chronic.get("congested_days") is not None:
            window = chronic.get("window_days") or 7
            days = chronic["congested_days"]
            beats.append(
                {
                    "phase": "chronic_secondary",
                    "title": "常发背景",
                    "text": f"近 {window} 天有 {days} 天同时段运行压力偏高（背景参考）",
                }
            )

    return beats
