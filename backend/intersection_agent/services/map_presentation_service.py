"""Build map presentation actions for SSE streaming to frontend."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from intersection_agent.models.domain import DiagnosisResult, NluResult, SuggestionResult
from intersection_agent.utils.direction_groups import (
    primary_groups_from_nlu,
    protected_groups_for_vertical_constraint,
)
from intersection_agent.utils.turn_metrics import normalize_turn_metrics


def build_understanding_card(
    nlu: NluResult,
    *,
    resolved_name: str | None = None,
    resolution_source: str | None = None,
) -> dict[str, Any]:
    """Structured NLU summary for step-1 map overlay."""
    tp = nlu.time_period
    time_text = ""
    if tp:
        time_text = f"{tp.label}（{tp.start}–{tp.end}）"
    directions = nlu.directions or []
    dir_text = "、".join(directions) if directions else "待从数据推断"
    return {
        "phase": "understanding",
        "title": "理解您的问题",
        "fields": [
            {
                "key": "intersection",
                "label": "路口",
                "value": resolved_name or nlu.intersection or "—",
            },
            {"key": "time_period", "label": "时段", "value": time_text or "—"},
            {"key": "problem_type", "label": "问题", "value": "拥堵诊断"},
            {"key": "directions", "label": "方向", "value": dir_text},
        ],
        "resolution_source": resolution_source,
        "text": (
            f"路口：{resolved_name or nlu.intersection}\n"
            f"时段：{time_text}\n"
            f"关注方向：{dir_text}"
        ),
    }


def build_flow_sources_action(
    flow_trace: dict[str, Any],
    cognition: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """流量溯源地图动作：按进口道沿路折线展示上一跳来源（禁止中心飞线）。"""
    if not flow_trace or not flow_trace.get("available"):
        return None
    inter = (cognition or {}).get("intersection") or {}
    center_lon, center_lat = inter.get("lon"), inter.get("lat")
    center = {"lon": center_lon, "lat": center_lat}

    entries = flow_trace.get("entry_traces") or []
    if not entries:
        return None

    traces: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("upstream_lng") is None or entry.get("upstream_lat") is None:
            continue
        path = _road_path_for_entry(
            cognition,
            int(entry.get("dir8_code") or 0),
            center,
            float(entry["upstream_lng"]),
            float(entry["upstream_lat"]),
        )
        dom = entry.get("dominant_movement") or {}
        traces.append(
            {
                "entry": entry.get("entry"),
                "dir8_code": entry.get("dir8_code"),
                "upstream_inter_id": entry.get("upstream_inter_id"),
                "name": entry.get("upstream_inter_name") or "上一路口",
                "narrative": entry.get("narrative"),
                "lon": entry.get("upstream_lng"),
                "lat": entry.get("upstream_lat"),
                "dominant_turn": dom.get("turn"),
                "vehicles_of_100": dom.get("vehicles_of_100"),
                "movements": entry.get("upstream_movements") or [],
                "path": path,
                "dominant": True,
            }
        )
    if not traces:
        return None

    summary = "；".join(t["narrative"] for t in traces[:3] if t.get("narrative"))
    return {
        "phase": "flow_trace",
        "title": "流量溯源",
        "source_center": center,
        "entry_traces": traces,
        "text": summary,
    }


_DIR8_KEYWORDS = {
    0: "北", 1: "东北", 2: "东", 3: "东南",
    4: "南", 5: "西南", 6: "西", 7: "西北",
}


def _road_path_for_entry(
    cognition: dict[str, Any] | None,
    dir8_code: int,
    center: dict[str, Any],
    up_lon: float,
    up_lat: float,
) -> list[list[float]]:
    """优先沿进口道 link 折线，否则退回上游点→中心折线（仍非多路口飞线）。"""
    clon, clat = center.get("lon"), center.get("lat")
    if clon is None or clat is None:
        return []
    links = (cognition or {}).get("links") or []
    kw = _DIR8_KEYWORDS.get(dir8_code, "")
    best_path: list[list[float]] | None = None
    best_len = 0
    for link in links:
        label = str(link.get("dir8_label") or link.get("dir4_label") or "")
        if kw and kw not in label:
            continue
        raw = link.get("path") or []
        if len(raw) < 2:
            continue
        path = [[float(p[0]), float(p[1])] for p in raw if len(p) >= 2]
        if len(path) > best_len:
            best_len = len(path)
            best_path = path
    if best_path:
        return best_path
    return [[up_lon, up_lat], [float(clon), float(clat)]]


def pick_narration_step(steps: list[dict[str, Any]], phase: str) -> dict[str, Any] | None:
    """Return a single narration step by phase."""
    for step in steps:
        if step.get("phase") == phase:
            return step
    return None


def build_narration_steps(
    *,
    cognition: dict[str, Any],
    data: dict[str, Any],
    diagnosis: DiagnosisResult | None = None,
    suggestion: SuggestionResult | None = None,
    nlu: NluResult | None = None,
) -> list[dict[str, Any]]:
    """Ordered narration cards for map overlay during analysis."""
    inter = cognition.get("intersection", {})
    eval_metrics = data.get("evaluation", {})
    flow = data.get("traffic_flow", {})
    signal = data.get("signal_plan", {})
    time_label = ""
    if nlu and nlu.time_period:
        time_label = nlu.time_period.label or f"{nlu.time_period.start}-{nlu.time_period.end}"

    focus_groups, protected_groups = _focus_and_protected_groups(nlu)

    steps: list[dict[str, Any]] = [
        {
            "phase": "locate",
            "title": "定位路口",
            "text": f"已锁定「{inter.get('name', '')}」，共 {inter.get('arm_count', 0)} 个进口、"
            f"{inter.get('total_lanes', 0)} 条车道。",
        },
    ]

    arms = cognition.get("arms") or []
    if arms:
        steps.append(
            {
                "phase": "channelization",
                "title": "路口渠化",
                "text": _channelization_summary(inter, arms),
            }
        )

    saturation = flow.get("saturation_rate")
    delay = eval_metrics.get("delay_index")
    imbalance = eval_metrics.get("imbalance_index")
    green_util = eval_metrics.get("green_utilization")

    steps.append(
        {
            "phase": "traffic",
            "title": "当前流量",
            "text": (
                f"{time_label or '当前时段'}延误指数 {delay:.2f}。"
                if delay is not None
                else "正在汇总路口运行流量…"
            ),
            "metrics": {"delay_index": delay},
        }
    )

    dir_lines = _direction_metric_lines(
        cognition.get("direction_groups") or [],
        focus_groups=focus_groups,
        protected_groups=protected_groups,
    )
    if dir_lines:
        steps.append(
            {
                "phase": "direction",
                "title": "分向饱和度",
                "text": "\n".join(dir_lines),
                "highlight_groups": [g["group"] for g in cognition.get("direction_groups", [])],
            }
        )

    timing_profile = data.get("timing_profile") or {}
    timing_text = _timing_step_text(timing_profile)
    if timing_text:
        steps.append(
            {
                "phase": "timing",
                "title": "配时适配性",
                "text": timing_text,
            }
        )

    steps.append(
        {
            "phase": "imbalance",
            "title": "失衡系数",
            "text": (
                f"失衡系数 {imbalance:.2f}，"
                f"{'各进口差异明显' if imbalance and imbalance >= 0.3 else '各向相对均衡'}；"
                f"绿灯利用率 {green_util:.0%}。"
                if imbalance is not None and green_util is not None
                else "正在计算进口失衡…"
            ),
            "metrics": {"imbalance_index": imbalance, "green_utilization": green_util},
        }
    )

    if diagnosis and diagnosis.diagnosed and diagnosis.matched_rules:
        rule = diagnosis.matched_rules[0]
        extra = ""
        if len(diagnosis.matched_rules) > 1:
            names = "、".join(str(r.get("name") or r.get("id")) for r in diagnosis.matched_rules[1:4])
            extra = f"\n同时命中：{names}"
        steps.append(
            {
                "phase": "rule",
                "title": "规则命中",
                "text": _diagnosis_only_text(
                    str(rule.get("conclusion") or ""),
                    fallback=rule.get("name", "拥堵诊断规则命中"),
                )
                + extra,
                "rule_id": rule.get("id"),
                "matched_count": len(diagnosis.matched_rules),
            }
        )

    if suggestion:
        dir_cn = "增加" if suggestion.direction == "increase" else "减少"
        steps.append(
            {
                "phase": "conclusion",
                "title": "治理建议",
                "text": (
                    f"证据链：饱和度 {saturation:.2f} + 失衡 {imbalance:.2f} + "
                    f"绿信比 {signal.get('green_ratio', 0):.0%} → "
                    f"建议{dir_cn}绿灯 {abs(suggestion.delta_seconds)} 秒。"
                    f"\n{suggestion.narrative}"
                ),
                "suggestion": suggestion.model_dump(),
            }
        )

    return [enrich_narration_step(s) for s in steps]


_PHASE_FOCUS_STEP: dict[str, int] = {
    "locate": 1,
    "links": 2,
    "channelization": 2,
    "traffic": 3,
    "direction": 3,
    "granularity": 3,
    "timing": 3,
    "corridor": 3,
    "external": 3,
    "saturation": 3,
    "imbalance": 3,
    "rule": 5,
    "conclusion": 6,
}


def _clamp_summary(text: str, max_len: int = 40) -> str:
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if not compact:
        return ""
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip() + "…"


def _summary_for_narration_step(step: dict[str, Any]) -> str:
    """One-line business summary for leadership-facing UI (≤40 chars)."""
    phase = str(step.get("phase") or "")
    text = str(step.get("text") or "")
    first_line = text.split("\n", 1)[0].strip()
    first_line = first_line.replace("【关注】", "关注").replace("【保护】", "保护")

    if phase == "locate":
        match = re.search(r"已锁定[「\"](.+?)[」\"]", first_line)
        if match:
            return _clamp_summary(f"已锁定{match.group(1)}。")
    if phase in ("links", "channelization"):
        axis = step.get("axis_roads") or {}
        if axis:
            parts = [f"{group}为{road}" for group, road in axis.items()]
            return _clamp_summary("，".join(parts) + "。")
    if phase == "traffic":
        return _clamp_summary(first_line.split("，")[0] + "。" if "，" in first_line else first_line)
    if phase in ("direction", "saturation", "imbalance"):
        return _clamp_summary(first_line.split("；")[0] if "；" in first_line else first_line)
    if phase == "rule":
        return _clamp_summary(first_line)
    if phase == "conclusion":
        narrative = str((step.get("suggestion") or {}).get("narrative") or "")
        if narrative:
            return _clamp_summary(narrative)
        for line in text.split("\n"):
            if line.strip() and not line.strip().startswith("证据链"):
                return _clamp_summary(line.strip())
    if phase in ("granularity", "timing", "corridor", "external"):
        return _clamp_summary(first_line)

    title = str(step.get("title") or "")
    return _clamp_summary(first_line or title)


def enrich_narration_step(step: dict[str, Any]) -> dict[str, Any]:
    """Attach step_summary and focus_step_index for frontend presentation."""
    phase = str(step.get("phase") or "")
    out = dict(step)
    summary = _summary_for_narration_step(step)
    if summary:
        out["step_summary"] = summary
    out["focus_step_index"] = _PHASE_FOCUS_STEP.get(phase, 3)
    return out


def _clean_road_name(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    if ":" in text:
        text = text.split(":")[0].strip()
    return text


def _dir_to_group(dir_label: str) -> str | None:
    key = _normalize_dir(str(dir_label or ""))
    for group, dirs in GROUP_TO_DIRS.items():
        if key in dirs:
            return group
    return None


def axis_roads_summary(cognition: dict[str, Any]) -> dict[str, str]:
    """Aggregate dominant road_name per axis group (东西向 / 南北向)."""
    group_names: dict[str, list[str]] = {"东西向": [], "南北向": []}
    links = cognition.get("links") or []
    for link in links:
        role = str(link.get("link_role") or "")
        if role not in ("entrance", "进口"):
            continue
        group = _dir_to_group(str(link.get("dir4_label") or link.get("dir8_label") or ""))
        if not group or group not in group_names:
            continue
        name = _clean_road_name(str(link.get("road_name") or ""))
        if name:
            group_names[group].append(name)

    if not any(group_names.values()):
        for arm in cognition.get("arms") or []:
            group = _dir_to_group(str(arm.get("dir4_label") or arm.get("dir8_label") or ""))
            if not group or group not in group_names:
                continue
            name = _clean_road_name(str(arm.get("road_name") or ""))
            if name:
                group_names[group].append(name)

    result: dict[str, str] = {}
    for group, names in group_names.items():
        if not names:
            continue
        result[group] = Counter(names).most_common(1)[0][0]
    return result


def build_axis_roads_speakable(
    axis_roads: dict[str, str],
    inter_name: str = "",
) -> str:
    segments: list[str] = []
    if inter_name:
        segments.append(str(inter_name))
    axis_parts: list[str] = []
    for group in ("东西向", "南北向"):
        road = axis_roads.get(group)
        if road:
            axis_parts.append(f"{group}为{road}")
    if axis_parts:
        segments.append("，".join(axis_parts))
    if not segments:
        return ""
    return "，".join(segments) + "。"


def build_links_speakable(
    cognition: dict[str, Any],
    axis_roads: dict[str, str],
    inter_name: str = "",
) -> str:
    """完整的路口结构播报：路口名 + 主轴道路 + 进口/车道概览。

    仅播主轴道路会让语音在面板还显示进口/车道信息时显得「被截断」，
    这里把结构概览一并纳入，保证口播与面板结构一致。
    """
    segments: list[str] = []
    if inter_name:
        segments.append(str(inter_name))
    axis_parts = [
        f"{group}为{axis_roads[group]}"
        for group in ("东西向", "南北向")
        if axis_roads.get(group)
    ]
    if axis_parts:
        segments.append("，".join(axis_parts))

    inter = cognition.get("intersection") or {}
    links = cognition.get("links") or []
    entrances = [
        link
        for link in links
        if str(link.get("link_role") or "") in ("entrance", "进口")
    ]
    arm_count = (
        len(entrances)
        or len(cognition.get("arms") or [])
        or inter.get("arm_count")
    )
    total_lanes = inter.get("total_lanes")
    overview: list[str] = []
    if arm_count:
        overview.append(f"共{arm_count}个进口方向")
    if total_lanes:
        overview.append(f"总计{total_lanes}条车道")
    if overview:
        segments.append("，".join(overview))

    if not segments:
        return ""
    return "，".join(segments) + "。"


def build_links_narration_payload(cognition: dict[str, Any]) -> dict[str, Any]:
    """Narration card for links phase with axis road names and TTS speakable."""
    inter = cognition.get("intersection") or {}
    axis = axis_roads_summary(cognition)
    speakable = build_links_speakable(cognition, axis, str(inter.get("name") or ""))
    body = links_summary(cognition)
    if axis:
        header = "，".join(f"{group}为{road}" for group, road in axis.items())
        text = f"{header}。\n{body}"
    else:
        text = body
    payload = {
        "phase": "links",
        "title": "关联路段",
        "text": text,
        "axis_roads": axis,
        "speakable": speakable or None,
    }
    if axis:
        parts = [f"{group}为{road}" for group, road in axis.items()]
        payload["step_summary"] = _clamp_summary("，".join(parts) + "。")
    payload["focus_step_index"] = _PHASE_FOCUS_STEP["links"]
    return enrich_narration_step(payload)


def _focus_and_protected_groups(nlu: NluResult | None) -> tuple[list[str], list[str]]:
    if not nlu or not nlu.directions:
        return [], []
    focus = primary_groups_from_nlu(nlu.directions)
    protect = protected_groups_for_vertical_constraint(focus)
    return focus, protect


def _build_direction_roles(
    groups: list[dict[str, Any]],
    focus_groups: list[str],
    protected_groups: list[str],
) -> list[dict[str, Any]]:
    focus_set = set(focus_groups)
    protect_set = set(protected_groups)
    roles: list[dict[str, Any]] = []
    for group in groups:
        name = str(group.get("group") or "")
        if name in focus_set:
            role = "focus"
        elif name in protect_set:
            role = "protect"
        else:
            role = "neutral"
        sat = group.get("saturation_max")
        if sat is None:
            sat = group.get("saturation_avg")
        roles.append({"group": name, "role": role, "saturation": sat})
    return roles


def _timing_step_text(timing_profile: dict[str, Any]) -> str:
    """配时适配性步骤仅播报周期与时段数量，不下适配/不匹配结论。"""
    cycle = timing_profile.get("cycle_length")
    period_count = timing_profile.get("period_count")
    if cycle is None and not period_count:
        return ""
    cycle_text = f"{float(cycle):.0f}s" if cycle is not None else "—"
    period_text = str(period_count) if period_count is not None else "—"
    return f"当前方案周期约 {cycle_text}。"


def _direction_metric_lines(
    groups: list[dict[str, Any]],
    *,
    focus_groups: list[str] | None = None,
    protected_groups: list[str] | None = None,
) -> list[str]:
    focus_set = set(focus_groups or [])
    protect_set = set(protected_groups or [])
    lines: list[str] = []
    for g in groups:
        sat = g.get("saturation_max")
        if sat is None:
            sat = g.get("saturation_avg")
        level = g.get("level", "")
        level_cn = {"high": "拥堵", "medium": "偏高", "low": "畅通"}.get(level, "")
        arms = "、".join(g.get("arm_labels") or [])
        group_name = str(g.get("group") or "")
        if group_name in focus_set:
            prefix = "【关注】"
        elif group_name in protect_set:
            prefix = "【保护】"
        else:
            prefix = ""
        if sat is not None and float(sat) > 0:
            lines.append(
                f"· {prefix}{group_name}（{arms}）饱和度 {float(sat):.2f} {level_cn}"
            )
    return lines


def links_summary(cognition: dict[str, Any]) -> str:
    """Human-readable summary of intersection links for narration."""
    inter = cognition.get("intersection") or {}
    links = cognition.get("links") or []
    if not links:
        arms = cognition.get("arms") or []
        return _channelization_summary(inter, arms)
    lines = [
        f"已加载 {len(links)} 条关联路段（进口高亮、出口次级显示）：",
    ]
    for link in links[:8]:
        role = str(link.get("link_role") or "—")
        if role in ("entrance", "进口"):
            role_cn = "进口"
        elif role in ("exit", "出口"):
            role_cn = "出口"
        else:
            role_cn = role
        dir_l = link.get("dir4_label") or link.get("dir8_label") or "—"
        lanes = link.get("lane_num") or "—"
        name = link.get("road_name") or str(link.get("link_id", ""))[:12]
        lines.append(f"· {dir_l}{role_cn} {name}（{lanes} 车道）")
    if len(links) > 8:
        lines.append(f"… 另有 {len(links) - 8} 条路段")
    return "\n".join(lines)


def _channelization_summary(inter: dict[str, Any], arms: list[dict[str, Any]]) -> str:
    parts = []
    for arm in arms[:6]:
        label = arm.get("dir4_label") or arm.get("dir8_label") or "?"
        lanes = arm.get("lane_num") or len(arm.get("lanes") or [])
        turn = arm.get("turn_move") or arm.get("lane_info") or ""
        parts.append(f"{label}进口 {lanes} 车道（{turn}）")
    head = f"{inter.get('name', '')} · 总车道 {inter.get('total_lanes', 0)}"
    return head + "\n" + "；".join(parts)


GROUP_TO_DIRS: dict[str, list[str]] = {
    "东西向": ["东", "西"],
    "南北向": ["南", "北"],
    "东南向": ["东南"],
    "西南向": ["西南"],
    "东北向": ["东北"],
    "西北向": ["西北"],
}

DIR4_TO_GROUP: dict[str, str] = {
    d: group for group, dirs in GROUP_TO_DIRS.items() for d in dirs
}


def _worst_direction_group(
    groups: list[dict[str, Any]],
    nlu: NluResult | None = None,
) -> dict[str, Any] | None:
    if not groups:
        return None
    if nlu and nlu.directions:
        preferred = {str(d).strip() for d in nlu.directions if d}
        for group in groups:
            if group.get("group") in preferred:
                return group
    return max(
        groups,
        key=lambda g: float(g.get("saturation_max") or g.get("saturation_avg") or 0),
    )


def _normalize_dir(label: str) -> str:
    text = str(label or "").replace("进口", "").replace("出口", "").strip()
    for key in ("东北", "东南", "西北", "西南", "东", "西", "南", "北"):
        if key in text:
            return key
    return text


def _diagnosis_only_text(text: str, *, fallback: str) -> str:
    """Remove governance-action clauses from pre-confirmation diagnosis narration."""
    action_terms = (
        "建议",
        "治理",
        "措施",
        "增加",
        "减少",
        "延长",
        "缩短",
        "优化",
        "调整",
        "改善",
    )
    parts = [part.strip() for part in re.split(r"[，,。；;]", text) if part.strip()]
    kept = [part for part in parts if not any(term in part for term in action_terms)]
    if kept:
        return "，".join(kept)
    return fallback


def _link_anchor(
    link: dict[str, Any],
    center_lon: float,
    center_lat: float,
) -> list[float]:
    """Anchor on entrance link segment near stop line (not pushed to outer bbox)."""
    path = link.get("path") or []
    if not path:
        return [center_lon, center_lat]

    best_idx = 0
    best_d = float("inf")
    for i, pt in enumerate(path):
        if len(pt) < 2:
            continue
        lon, lat = float(pt[0]), float(pt[1])
        d = (lon - center_lon) ** 2 + (lat - center_lat) ** 2
        if d < best_d:
            best_d = d
            best_idx = i

    anchor = [float(path[best_idx][0]), float(path[best_idx][1])]

    def _dist2(a: list[float], b: list[float]) -> float:
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2

    center = [center_lon, center_lat]
    if best_idx + 1 < len(path):
        nxt = [float(path[best_idx + 1][0]), float(path[best_idx + 1][1])]
        if _dist2(nxt, center) > _dist2(anchor, center):
            return [(anchor[0] + nxt[0]) / 2, (anchor[1] + nxt[1]) / 2]
    if best_idx > 0:
        prev = [float(path[best_idx - 1][0]), float(path[best_idx - 1][1])]
        if _dist2(prev, center) > _dist2(anchor, center):
            return [(anchor[0] + prev[0]) / 2, (anchor[1] + prev[1]) / 2]
    return anchor


def _resolve_metrics_by_turn(
    cognition: dict[str, Any],
    data: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Turn-level saturation rows from cognition or data.granularity."""
    turns = cognition.get("metrics_by_turn") or []
    if turns:
        return turns
    by_turn = ((data or {}).get("granularity") or {}).get("by_turn") or []
    return normalize_turn_metrics(by_turn)


def _dir_from_turn_label(label: str) -> str:
    m = re.match(r"([东南西北]+)", str(label or "").strip())
    return m.group(1) if m else ""


def _markers_for_turn_saturation(
    links: list[dict[str, Any]],
    center_lon: float,
    center_lat: float,
    metrics_by_turn: list[dict[str, Any]],
    *,
    title_prefix_by_dir: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """One marker per turn movement; dirs without turn data are omitted."""
    prefixes = title_prefix_by_dir or {}
    turns_by_dir: dict[str, list[dict[str, Any]]] = {}
    for turn in metrics_by_turn:
        dir_key = _normalize_dir(
            str(turn.get("dir4_label") or _dir_from_turn_label(str(turn.get("label") or "")))
        )
        if not dir_key:
            continue
        turns_by_dir.setdefault(dir_key, []).append(turn)

    markers: list[dict[str, Any]] = []
    seen_dirs: set[str] = set()
    for link in links:
        if str(link.get("link_role") or "") not in ("entrance", "进口"):
            continue
        dir_key = _normalize_dir(str(link.get("dir4_label") or link.get("dir8_label") or ""))
        if not dir_key or dir_key in seen_dirs:
            continue
        seen_dirs.add(dir_key)
        lon, lat = _link_anchor(link, center_lon, center_lat)
        turns = turns_by_dir.get(dir_key, [])
        prefix = prefixes.get(dir_key, "")
        if turns:
            for turn in turns:
                label = str(turn.get("label") or "")
                sat_raw = turn.get("turn_saturation")
                if sat_raw is None:
                    continue
                sat_f = float(sat_raw)
                title = f"{prefix}{label}" if prefix else label
                markers.append(
                    {
                        "id": f"turn-{dir_key}-{turn.get('turn_dir_no', label)}",
                        "lon": lon,
                        "lat": lat,
                        "dir": dir_key,
                        "link_id": link.get("link_id"),
                        "kind": "metric",
                        "variant": "turn",
                        "title": title,
                        "subtitle": "转向饱和度",
                        "value": _fmt_sat(sat_f),
                        "severity": _severity(sat_f),
                        "turn_dir_no": turn.get("turn_dir_no"),
                    }
                )
    return markers


def _title_prefix_by_dir_from_groups(
    groups: list[dict[str, Any]],
    *,
    focus_groups: list[str] | None = None,
    protected_groups: list[str] | None = None,
) -> dict[str, str]:
    """Map compass dir → marker title prefix (关注/保护) from direction groups."""
    focus_set = set(focus_groups or [])
    protect_set = set(protected_groups or [])
    prefixes: dict[str, str] = {}
    for group in groups:
        group_name = str(group.get("group") or "")
        if not group_name:
            continue
        if group_name in focus_set:
            prefix = f"关注·"
        elif group_name in protect_set:
            prefix = f"保护·"
        else:
            continue
        dirs = GROUP_TO_DIRS.get(group_name) or [
            _normalize_dir(str(a)) for a in (group.get("arm_labels") or [])
        ]
        for d in dirs:
            norm = _normalize_dir(d)
            if norm:
                prefixes[norm] = prefix
    return prefixes


def _saturation_for_dir(
    dir_key: str,
    metrics_by_arm: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> float | None:
    """Per-arm saturation first, then direction-group aggregate for missing arms."""
    for metric in metrics_by_arm:
        if _normalize_dir(str(metric.get("dir4_label") or "")) != dir_key:
            continue
        sat = metric.get("saturation")
        if sat is not None and float(sat) > 0:
            return float(sat)
    group_name = DIR4_TO_GROUP.get(dir_key)
    if not group_name:
        return None
    for group in groups:
        if str(group.get("group") or "") != group_name:
            continue
        sat_raw = group.get("saturation_max")
        if sat_raw is None:
            sat_raw = group.get("saturation_avg")
        if sat_raw is not None and float(sat_raw) > 0:
            return float(sat_raw)
    return None


def _markers_for_traffic_phase(
    links: list[dict[str, Any]],
    center_lon: float,
    center_lat: float,
    metrics_by_arm: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """One saturation marker per entrance arm; missing data shows as —."""
    markers: list[dict[str, Any]] = []
    seen_dirs: set[str] = set()
    for link in links:
        if str(link.get("link_role") or "") not in ("entrance", "进口"):
            continue
        dir_key = _normalize_dir(str(link.get("dir4_label") or link.get("dir8_label") or ""))
        if not dir_key or dir_key in seen_dirs:
            continue
        seen_dirs.add(dir_key)
        sat = _saturation_for_dir(dir_key, metrics_by_arm, groups)
        lon, lat = _link_anchor(link, center_lon, center_lat)
        markers.append(
            {
                "id": f"traffic-{link.get('link_id')}-{dir_key}",
                "lon": lon,
                "lat": lat,
                "dir": dir_key,
                "link_id": link.get("link_id"),
                "kind": "metric",
                "variant": "saturation",
                "title": f"{dir_key}进口",
                "subtitle": "饱和度" if sat is not None else "无数据",
                "value": f"{sat:.2f}" if sat is not None else "—",
                "severity": _severity(sat),
            }
        )
    return markers


def _fmt_sat(value: float | None) -> str:
    """饱和度展示为小数（如 0.92、1.50），不用百分号。"""
    return f"{value:.2f}" if value is not None else "—"


def _severity(sat: float | None) -> str:
    if sat is None:
        return "unknown"
    if sat >= 0.85:
        return "high"
    if sat >= 0.65:
        return "medium"
    return "low"


def _markers_for_direction_groups(
    groups: list[dict[str, Any]],
    links: list[dict[str, Any]],
    center_lon: float,
    center_lat: float,
    *,
    focus_groups: list[str] | None = None,
    protected_groups: list[str] | None = None,
) -> list[dict[str, Any]]:
    """为每个分向组生成渠化/地图标注，与理解过程分向饱和度列表一致。"""
    focus_set = set(focus_groups or [])
    protect_set = set(protected_groups or [])
    markers: list[dict[str, Any]] = []
    seen_dirs: set[str] = set()

    for group in groups:
        group_name = str(group.get("group") or "")
        if not group_name:
            continue
        sat_raw = group.get("saturation_max")
        if sat_raw is None:
            sat_raw = group.get("saturation_avg")
        sat_f = float(sat_raw) if sat_raw is not None else None
        dirs = GROUP_TO_DIRS.get(group_name)
        if not dirs:
            dirs = [_normalize_dir(str(a)) for a in (group.get("arm_labels") or [])]
        if group_name in focus_set:
            title = f"关注·{group_name}"
        elif group_name in protect_set:
            title = f"保护·{group_name}"
        else:
            title = group_name
        for dir_key in dirs:
            norm = _normalize_dir(dir_key)
            if not norm or norm in seen_dirs:
                continue
            seen_dirs.add(norm)
            for link in links:
                link_dir = _normalize_dir(str(link.get("dir4_label") or link.get("dir8_label") or ""))
                if link_dir != norm:
                    continue
                role = str(link.get("link_role") or "")
                if role not in ("entrance", "进口"):
                    continue
                lon, lat = _link_anchor(link, center_lon, center_lat)
                markers.append(
                    {
                        "id": f"dir-group-{group_name}-{norm}",
                        "lon": lon,
                        "lat": lat,
                        "dir": norm,
                        "link_id": link.get("link_id"),
                        "kind": "metric",
                        "variant": "direction",
                        "title": title,
                        "value": f"{sat_f:.2f}" if sat_f is not None else "—",
                        "severity": _severity(sat_f),
                    }
                )
                break
    return markers


def _markers_for_dirs(
    links: list[dict[str, Any]],
    center_lon: float,
    center_lat: float,
    dirs: list[str],
    *,
    label_prefix: str = "",
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for d in dirs:
        dir_key = _normalize_dir(d)
        for link in links:
            link_dir = _normalize_dir(str(link.get("dir4_label") or link.get("dir8_label") or ""))
            if link_dir != dir_key:
                continue
            role = str(link.get("link_role") or "")
            if role not in ("entrance", "进口"):
                continue
            lon, lat = _link_anchor(link, center_lon, center_lat)
            markers.append(
                {
                    "id": f"{link.get('link_id')}-{dir_key}",
                    "lon": lon,
                    "lat": lat,
                    "dir": dir_key,
                    "link_id": link.get("link_id"),
                    "title": f"{label_prefix}{dir_key}进口",
                    "subtitle": link.get("road_name") or "",
                }
            )
            break
    return markers


def build_map_scene(
    phase: str,
    *,
    cognition: dict[str, Any],
    data: dict[str, Any] | None = None,
    diagnosis: DiagnosisResult | None = None,
    suggestion: SuggestionResult | None = None,
    nlu: NluResult | None = None,
) -> dict[str, Any]:
    """Structured map scene for frontend bubbles, emphasis, and camera."""
    data = data or {}
    inter = cognition.get("intersection") or {}
    center_lon = float(inter.get("lon") or 0)
    center_lat = float(inter.get("lat") or 0)
    links = cognition.get("links") or []
    groups = cognition.get("direction_groups") or []
    eval_metrics = data.get("evaluation") or {}
    flow = data.get("traffic_flow") or {}

    saturation = flow.get("saturation_rate")
    delay = eval_metrics.get("delay_index")
    imbalance = eval_metrics.get("imbalance_index")
    green_util = eval_metrics.get("green_utilization")
    worst = _worst_direction_group(groups, nlu)
    worst_dirs = GROUP_TO_DIRS.get(str(worst.get("group") if worst else ""), [])
    if not worst_dirs and worst:
        worst_dirs = [_normalize_dir(x) for x in (worst.get("arm_labels") or [])]

    focus_groups, protected_groups = _focus_and_protected_groups(nlu)
    focus_dirs: list[str] = []
    for group in focus_groups:
        focus_dirs.extend(GROUP_TO_DIRS.get(group, []))
    protect_dirs: list[str] = []
    for group in protected_groups:
        protect_dirs.extend(GROUP_TO_DIRS.get(group, []))

    base: dict[str, Any] = {
        "action": "map_scene",
        "phase": phase,
        "center": [center_lon, center_lat],
        "zoom": 17.8,
        "highlight_dirs": [],
        "pulse_link_ids": [],
        "dim_other_links": False,
        "markers": [],
        "hud": None,
        "focus": None,
        "focus_groups": focus_groups,
        "protected_groups": protected_groups,
        "direction_roles": _build_direction_roles(groups, focus_groups, protected_groups),
    }

    if phase == "traffic":
        sat_text = f"{float(saturation):.2f}" if saturation is not None else "—"
        delay_text = f"{float(delay):.2f}" if delay is not None else "—"
        time_label = ""
        if nlu and nlu.time_period:
            time_label = nlu.time_period.label or ""
        arm_metrics = cognition.get("metrics_by_arm") or []
        metrics_by_turn = _resolve_metrics_by_turn(cognition, data)
        if metrics_by_turn:
            entrance_markers = _markers_for_turn_saturation(
                links, center_lon, center_lat, metrics_by_turn
            )
        else:
            entrance_markers = _markers_for_traffic_phase(
                links, center_lon, center_lat, arm_metrics, groups
            )
        if not entrance_markers and saturation is not None:
            entrance_markers = _markers_for_dirs(links, center_lon, center_lat, worst_dirs)
            for m in entrance_markers:
                m["kind"] = "metric"
                m["variant"] = "saturation"
                m["value"] = sat_text
                m["subtitle"] = "路口整体"
                m["severity"] = _severity(saturation)
        delay_marker = {
            "id": "delay-chip",
            "lon": center_lon,
            "lat": center_lat,
            "kind": "chip",
            "variant": "delay",
            "title": "延误指数",
            "value": delay_text,
            "severity": _severity(saturation),
        }
        base.update(
            {
                "zoom": 17.6,
                "pulse_link_ids": [str(m["link_id"]) for m in entrance_markers if m.get("link_id")],
                "hud": {
                    "title": time_label or "运行数据",
                    "icon": "📊",
                    "metrics": [
                        {"label": "饱和度", "value": sat_text, "severity": _severity(saturation)},
                    ],
                },
                "markers": entrance_markers + ([delay_marker] if delay is not None else []),
            }
        )
        return base

    if phase == "direction":
        highlight_dirs = focus_dirs if focus_dirs else (worst_dirs or [])
        role_group = focus_groups[0] if focus_groups else (str(worst.get("group") or "") if worst else "")
        worst_sat_raw = None
        for group in groups:
            if str(group.get("group") or "") == role_group:
                worst_sat_raw = group.get("saturation_max") or group.get("saturation_avg")
                break
        if worst_sat_raw is None and worst:
            worst_sat_raw = worst.get("saturation_max") or worst.get("saturation_avg")
        worst_sat = float(worst_sat_raw) if worst_sat_raw is not None else None
        if worst_sat is None and saturation is not None:
            worst_sat = float(saturation)
        metrics_by_turn = _resolve_metrics_by_turn(cognition, data)
        if metrics_by_turn:
            prefix_by_dir = _title_prefix_by_dir_from_groups(
                groups,
                focus_groups=focus_groups,
                protected_groups=protected_groups,
            )
            markers = _markers_for_turn_saturation(
                links,
                center_lon,
                center_lat,
                metrics_by_turn,
                title_prefix_by_dir=prefix_by_dir,
            )
        else:
            markers = _markers_for_direction_groups(
                groups,
                links,
                center_lon,
                center_lat,
                focus_groups=focus_groups,
                protected_groups=protected_groups,
            )
        focus = next(
            (m for m in markers if role_group and role_group in str(m.get("title") or "")),
            markers[0] if markers else None,
        )
        base.update(
            {
                "zoom": 18.2,
                "highlight_dirs": highlight_dirs,
                "protected_link_dirs": protect_dirs,
                "pulse_link_ids": [
                    str(lk.get("link_id"))
                    for lk in links
                    if _normalize_dir(str(lk.get("dir4_label") or "")) in highlight_dirs
                ],
                "dim_other_links": True,
                "markers": markers,
                "focus": focus,
                "hud": {
                    "title": "分向饱和度",
                    "icon": "🧭",
                    "metrics": [
                        {
                            "label": worst.get("group", "关键方向") if worst else "方向",
                            "value": f"{worst_sat:.2f}" if worst_sat is not None else "—",
                            "severity": _severity(worst_sat),
                        }
                    ],
                },
            }
        )
        return base

    if phase == "saturation":
        sat_val = float(saturation) if saturation is not None else None
        sat_highlight = focus_dirs if focus_dirs else worst_dirs
        base.update(
            {
                "zoom": 17.9,
                "highlight_dirs": sat_highlight,
                "protected_link_dirs": protect_dirs,
                "pulse_link_ids": [
                    str(lk.get("link_id"))
                    for lk in links
                    if _normalize_dir(str(lk.get("dir4_label") or "")) in sat_highlight
                ],
                "dim_other_links": True,
                "markers": [
                    {
                        "id": "saturation-center",
                        "lon": center_lon,
                        "lat": center_lat,
                        "kind": "alert",
                        "title": "过饱和" if sat_val and sat_val >= 0.85 else "偏高",
                        "value": _fmt_sat(sat_val),
                        "severity": _severity(sat_val),
                    }
                ],
                "hud": {
                    "title": "饱和度判断",
                    "icon": "⚠️",
                    "metrics": [
                        {
                            "label": "路口饱和度",
                            "value": _fmt_sat(sat_val),
                            "severity": _severity(sat_val),
                        }
                    ],
                },
            }
        )
        return base

    if phase == "imbalance":
        imb_val = float(imbalance) if imbalance is not None else None
        util_val = float(green_util) if green_util is not None else None
        markers = _markers_for_dirs(
            links, center_lon, center_lat, worst_dirs, label_prefix="失衡·"
        )
        for m in markers:
            m["kind"] = "imbalance"
            m["variant"] = "imbalance"
            m["value"] = f"{imb_val:.2f}" if imb_val is not None else "—"
            m["severity"] = "high" if imb_val and imb_val >= 0.3 else "medium"
        base.update(
            {
                "zoom": 18.0,
                "highlight_dirs": worst_dirs,
                "dim_other_links": True,
                "markers": markers,
                "hud": {
                    "title": "失衡分析",
                    "icon": "⚖️",
                    "metrics": [
                        {
                            "label": "失衡系数",
                            "value": f"{imb_val:.2f}" if imb_val is not None else "—",
                            "severity": "high" if imb_val and imb_val >= 0.3 else "low",
                        },
                        {
                            "label": "绿灯利用率",
                            "value": f"{util_val:.0%}" if util_val is not None else "—",
                            "severity": "medium",
                        },
                    ],
                },
            }
        )
        return base

    if phase == "rule":
        rule = (diagnosis.matched_rules[0] if diagnosis and diagnosis.matched_rules else {}) or {}
        focus = _markers_for_dirs(links, center_lon, center_lat, worst_dirs)
        sat_val = float(saturation) if saturation is not None else None
        imb_val = float(imbalance) if imbalance is not None else None
        util_val = float(green_util) if green_util is not None else None
        evidence_markers: list[dict[str, Any]] = []
        if focus and sat_val is not None:
            evidence_markers.append(
                {
                    "id": "evidence-saturation",
                    "lon": focus[0]["lon"],
                    "lat": focus[0]["lat"],
                    "kind": "evidence",
                    "title": "饱和度证据",
                    "value": _fmt_sat(sat_val),
                    "subtitle": worst.get("group") if worst else "",
                    "severity": _severity(sat_val),
                    "dir": focus[0].get("dir"),
                }
            )
        if focus and len(focus) > 1 and imb_val is not None:
            evidence_markers.append(
                {
                    "id": "evidence-imbalance",
                    "lon": focus[1]["lon"],
                    "lat": focus[1]["lat"],
                    "kind": "evidence",
                    "title": "失衡证据",
                    "value": f"{imb_val:.2f}",
                    "subtitle": "进口差异",
                    "severity": "high" if imb_val >= 0.3 else "medium",
                    "dir": focus[1].get("dir"),
                }
            )
        base.update(
            {
                "zoom": 18.1,
                "highlight_dirs": worst_dirs,
                "pulse_link_ids": [
                    str(lk.get("link_id"))
                    for lk in links
                    if _normalize_dir(str(lk.get("dir4_label") or "")) in worst_dirs
                ],
                "dim_other_links": True,
                "focus": focus[0] if focus else None,
                "markers": evidence_markers
                + [
                    {
                        "id": "rule-hit",
                        "lon": (focus[0]["lon"] if focus else center_lon),
                        "lat": (focus[0]["lat"] if focus else center_lat),
                        "kind": "rule",
                        "title": "规则命中",
                        "subtitle": rule.get("name") or rule.get("conclusion") or "",
                        "severity": "high",
                        "dir": focus[0].get("dir") if focus else None,
                    }
                ],
                "hud": {
                    "title": "证据链 · 规则诊断",
                    "icon": "🎯",
                    "metrics": [
                        {
                            "label": "饱和度",
                            "value": _fmt_sat(sat_val),
                            "severity": _severity(sat_val),
                        },
                        {
                            "label": "失衡系数",
                            "value": f"{imb_val:.2f}" if imb_val is not None else "—",
                            "severity": "high" if imb_val and imb_val >= 0.3 else "low",
                        },
                        {
                            "label": "绿灯利用率",
                            "value": f"{util_val:.0%}" if util_val is not None else "—",
                            "severity": "medium",
                        },
                        {
                            "label": "规则结论",
                            "value": (rule.get("conclusion") or rule.get("name") or "命中")[:16],
                            "severity": "high",
                        },
                    ],
                },
            }
        )
        return base

    if phase == "conclusion" and suggestion:
        delta = abs(int(suggestion.delta_seconds or 0))
        dir_cn = "增加" if suggestion.direction == "increase" else "减少"
        focus_markers = _markers_for_dirs(links, center_lon, center_lat, worst_dirs)
        anchor = focus_markers[0] if focus_markers else {"lon": center_lon, "lat": center_lat}
        sat_val = float(saturation) if saturation is not None else None
        imb_val = float(imbalance) if imbalance is not None else None
        util_val = float(green_util) if green_util is not None else None
        rule = (diagnosis.matched_rules[0] if diagnosis and diagnosis.matched_rules else {}) or {}
        evidence_markers: list[dict[str, Any]] = []
        if sat_val is not None and focus_markers:
            evidence_markers.append(
                {
                    "id": "evidence-saturation",
                    "lon": focus_markers[0]["lon"],
                    "lat": focus_markers[0]["lat"],
                    "kind": "evidence",
                    "title": "饱和度",
                    "value": _fmt_sat(sat_val),
                    "subtitle": "证据 ①",
                    "severity": _severity(sat_val),
                    "dir": focus_markers[0].get("dir"),
                }
            )
        if imb_val is not None:
            imb_anchor = focus_markers[1] if len(focus_markers) > 1 else anchor
            evidence_markers.append(
                {
                    "id": "evidence-imbalance",
                    "lon": imb_anchor["lon"],
                    "lat": imb_anchor["lat"],
                    "kind": "evidence",
                    "title": "失衡系数",
                    "value": f"{imb_val:.2f}",
                    "subtitle": "证据 ②",
                    "severity": "high" if imb_val >= 0.3 else "medium",
                    "dir": imb_anchor.get("dir"),
                }
            )
        if util_val is not None and len(focus_markers) > 2:
            evidence_markers.append(
                {
                    "id": "evidence-green",
                    "lon": focus_markers[2]["lon"],
                    "lat": focus_markers[2]["lat"],
                    "kind": "evidence",
                    "title": "绿信比",
                    "value": f"{util_val:.0%}",
                    "subtitle": "证据 ③",
                    "severity": "medium",
                    "dir": focus_markers[2].get("dir"),
                }
            )
        suggestion_value = (
            f"+{delta}s" if suggestion.direction == "increase" else f"-{delta}s"
        )
        base.update(
            {
                "zoom": 18.3,
                "highlight_dirs": worst_dirs,
                "pulse_link_ids": [
                    str(lk.get("link_id"))
                    for lk in links
                    if _normalize_dir(str(lk.get("dir4_label") or "")) in worst_dirs
                ],
                "dim_other_links": True,
                "focus": anchor,
                "markers": evidence_markers
                + [
                    {
                        "id": "suggestion",
                        "lon": anchor.get("lon", center_lon),
                        "lat": anchor.get("lat", center_lat),
                        "kind": "suggestion",
                        "title": f"{dir_cn}绿灯",
                        "value": suggestion_value,
                        "subtitle": worst.get("group") if worst else "治理建议",
                        "severity": "high",
                        "dir": anchor.get("dir"),
                    }
                ],
                "hud": {
                    "title": "治理建议 · 证据链",
                    "icon": "💡",
                    "metrics": [
                        {
                            "label": "证据链",
                            "value": (
                                f"饱和{_fmt_sat(sat_val)} + 失衡{imb_val:.2f}"
                                if sat_val is not None and imb_val is not None
                                else "见地图标注"
                            ),
                            "severity": _severity(sat_val),
                        },
                        {
                            "label": "规则",
                            "value": (rule.get("name") or rule.get("id") or "—")[:14],
                            "severity": "medium",
                        },
                        {
                            "label": "信号调整",
                            "value": f"{dir_cn} {delta} 秒",
                            "severity": "high",
                        },
                        {
                            "label": "绿信比",
                            "value": f"{util_val:.0%}" if util_val is not None else "—",
                            "severity": "medium",
                        },
                    ],
                },
            }
        )
        return base

    if phase == "granularity":
        gran = data.get("granularity") or {}
        turn_rows = gran.get("by_turn") or []
        top = turn_rows[0] if turn_rows else {}
        label = str(top.get("label") or "")
        highlight_dirs: list[str] = []
        for key in ("东", "西", "南", "北"):
            if key in label and key not in highlight_dirs:
                highlight_dirs.append(key)
        turn_char = next((ch for ch in ("左", "直", "右", "调") if ch in label), None)
        highlight_turn = None
        if highlight_dirs and turn_char:
            highlight_turn = {
                "dir": highlight_dirs[0],
                "turn": turn_char,
                "label": label,
                "saturation": top.get("turn_saturation"),
            }
        sat_val = float(top.get("turn_saturation") or 0) if top else None
        markers = _markers_for_dirs(links, center_lon, center_lat, highlight_dirs or worst_dirs)
        for m in markers:
            m["kind"] = "metric"
            m["variant"] = "turn"
            m["title"] = label[:8] if label else "转向"
            m["value"] = _fmt_sat(sat_val)
            m["severity"] = _severity(sat_val)
        base.update(
            {
                "zoom": 18.1,
                "highlight_dirs": highlight_dirs or worst_dirs,
                "highlight_turn": highlight_turn,
                "dim_other_links": bool(highlight_dirs),
                "markers": markers,
                "hud": {
                    "title": "多粒度画像",
                    "icon": "🔬",
                    "metrics": [
                        {
                            "label": label[:10] if label else "关键转向",
                            "value": _fmt_sat(sat_val),
                            "severity": _severity(sat_val),
                        }
                    ],
                },
            }
        )
        return base

    if phase == "timing":
        timing = data.get("timing_profile") or {}
        cycle = timing.get("cycle_length")
        period_count = timing.get("period_count")
        base.update(
            {
                "zoom": 17.9,
                "highlight_dirs": [],
                "dim_other_links": False,
                "markers": [],
                "hud": {
                    "title": "配时画像",
                    "icon": "⏱",
                    "metrics": [
                        {
                            "label": "周期",
                            "value": f"{float(cycle):.0f}s" if cycle is not None else "—",
                            "severity": "medium",
                        },
                    ],
                },
            }
        )
        return base

    if phase == "corridor":
        corridor = data.get("corridor_context") or {}
        nodes = corridor.get("corridor_nodes") or []
        coord_markers: list[dict[str, Any]] = []
        for node in nodes:
            lon = node.get("lon")
            lat = node.get("lat")
            if lon is None or lat is None:
                continue
            coord_markers.append(
                {
                    "id": f"corridor-{node.get('inter_id')}",
                    "lon": float(lon),
                    "lat": float(lat),
                    "kind": "corridor",
                    "variant": "current" if node.get("is_current") else "peer",
                    "title": str(node.get("inter_name") or "")[:12],
                    "value": f"#{node.get('seq')}",
                    "subtitle": "当前" if node.get("is_current") else "协调节点",
                    "severity": "high" if node.get("is_current") else "medium",
                }
            )
        pos = corridor.get("inter_position")
        total = corridor.get("corridor_inter_count")
        base.update(
            {
                "zoom": 16.8 if len(coord_markers) > 1 else 17.6,
                "markers": coord_markers,
                "hud": {
                    "title": "干线协调",
                    "icon": "🌊",
                    "metrics": [
                        {
                            "label": "协调周期",
                            "value": (
                                f"{float(corridor.get('coord_cycle_sec')):.0f}s"
                                if corridor.get("coord_cycle_sec")
                                else "—"
                            ),
                            "severity": "low",
                        },
                    ],
                },
            }
        )
        return base

    return base


def _collect_governance_points(node: dict[str, Any]) -> list[dict[str, Any]]:
    """深度优先收集树内所有 decision == 治理落点 的节点。"""
    points: list[dict[str, Any]] = []
    if node.get("decision") == "治理落点":
        points.append(node)
    for child in node.get("children") or []:
        points.extend(_collect_governance_points(child))
    return points


def _approach_profile_summary(profiles: list[dict[str, Any]]) -> str:
    """挑出最饱和进口道的简述，用于 narration。"""
    if not profiles:
        return ""
    worst = max(profiles, key=lambda p: p.get("turn_saturation_max") or 0.0)
    sat = worst.get("turn_saturation_max")
    gu = worst.get("green_util_min")
    parts = []
    if sat is not None:
        parts.append(f"饱和{float(sat):.2f}")
    if gu is not None:
        parts.append(f"绿用{float(gu):.2f}")
    return "、".join(parts)


def build_upstream_storyboard(
    trees: list[dict[str, Any]], cognition: dict[str, Any] | None = None
) -> dict[str, Any]:
    """逐树串讲 + 帧重建底座：对每棵溯源树生成有序帧序列。

    每帧 reveal 仅含"该帧新增"的覆盖物 id（前端按帧号累计并集得到可见集）。
    帧顺序保持输入树顺序——即逐树串讲。
    """
    out_trees: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    idx = 0

    for tree in trees:
        tid = tree["tree_id"]
        approach = tree.get("approach") or ""
        root = tree["root"]
        target = tree.get("target") or {}
        root_id = root.get("inter_id")
        root_name = root.get("inter_name") or root_id

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        target_id = target.get("inter_id")
        nodes.append(
            {
                "id": target_id,
                "inter_id": target_id,
                "name": target.get("name"),
                "lon": target.get("lon"),
                "lat": target.get("lat"),
                "role": "target",
                "approach": approach,
                "approach_profiles": [],
                "decision": None,
            }
        )

        def _walk(node: dict[str, Any], parent_id: str | None) -> None:
            nid = node.get("inter_id")
            nodes.append(
                {
                    "id": nid,
                    "inter_id": nid,
                    "name": node.get("inter_name"),
                    "lon": node.get("lng"),
                    "lat": node.get("lat"),
                    "role": "governance" if node.get("decision") == "治理落点" else "upstream",
                    "hop": node.get("hop"),
                    "approach_profiles": node.get("approach_profiles") or [],
                    "decision": node.get("decision"),
                    "feeding_dir8": node.get("feeding_dir8"),
                }
            )
            if parent_id is not None:
                edges.append(
                    {
                        "id": f"edge:{tid}:{parent_id}-{nid}",
                        "from": parent_id,
                        "to": nid,
                        "path": [],
                        "flow_pct": node.get("coverage"),
                        "dominant_turn": node.get("feeding_dir8"),
                    }
                )
            for child in node.get("children") or []:
                _walk(child, nid)

        _walk(root, target_id)
        out_trees.append({"tree_id": tid, "approach": approach, "nodes": nodes, "edges": edges})

        # —— 帧序列 ——
        edge_root = f"edge:{tid}:{target_id}-{root_id}"
        ring_root = f"ring:{root_id}"

        frames.append(
            {
                "idx": idx,
                "tree": tid,
                "kind": "thesis",
                "focus": "target",
                "reveal": [],
                "camera": "intersection",
                "narration": f"{approach}本地无可调空间，向上游溯源。",
            }
        )
        idx += 1
        frames.append(
            {
                "idx": idx,
                "tree": tid,
                "kind": "zoom_out",
                "focus": "target",
                "reveal": [],
                "camera": "corridor",
                "narration": "缩放到道路级，追上一跳来车。",
            }
        )
        idx += 1
        frames.append(
            {
                "idx": idx,
                "tree": tid,
                "kind": "hop1",
                "focus": root_id,
                "reveal": [edge_root],
                "camera": "corridor",
                "narration": f"主要来自上游{root_name}。",
            }
        )
        idx += 1
        root_summary = _approach_profile_summary(root.get("approach_profiles") or [])
        if root.get("decision") == "治理落点":
            inspect_narration = f"{root_name}有信控空间（{root_summary}），可作治理落点。"
        else:
            inspect_narration = f"{root_name}四向全饱和，继续上溯。"
        frames.append(
            {
                "idx": idx,
                "tree": tid,
                "kind": "inspect",
                "focus": root_id,
                "reveal": [ring_root],
                "narration": inspect_narration,
            }
        )
        idx += 1

        children = root.get("children") or []
        if children:
            reveal2: list[str] = []
            for child in children:
                cid = child.get("inter_id")
                reveal2.append(f"edge:{tid}:{root_id}-{cid}")
                reveal2.append(f"ring:{cid}")
            frames.append(
                {
                    "idx": idx,
                    "tree": tid,
                    "kind": "hop2",
                    "focus": root_id,
                    "reveal": reveal2,
                    "narration": "对其余进口道继续向上一跳溯源。",
                }
            )
            idx += 1

        gov_points = _collect_governance_points(root)
        badges = [f"badge:{g.get('inter_id')}★" for g in gov_points]
        gov_names = "、".join(str(g.get("inter_name") or g.get("inter_id")) for g in gov_points)
        if gov_points:
            resolve_narration = f"共定位 {len(gov_points)} 个治理落点：{gov_names}，可借调绿信比。"
        else:
            resolve_narration = "本树未定位到可信控治理落点。"
        frames.append(
            {
                "idx": idx,
                "tree": tid,
                "kind": "resolve",
                "focus": [g.get("inter_id") for g in gov_points],
                "reveal": badges,
                "camera": f"fit_tree_{tid}",
                "narration": resolve_narration,
            }
        )
        idx += 1

    return {"trees": out_trees, "frames": frames}
