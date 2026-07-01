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
from intersection_agent.utils.problem_type_narrative import resolve_primary_problem_type
from intersection_agent.utils.saturation_granularity import canonical_saturation_summary
from intersection_agent.utils.traffic_labels import DIR8_LABELS
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
        return _orient_path_endpoints(best_path, up_lon, up_lat, float(clon), float(clat))
    return [[up_lon, up_lat], [float(clon), float(clat)]]


def _orient_path_endpoints(
    path: list[list[float]],
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
) -> list[list[float]]:
    """确保折线从上游路口 (start) 指向目标路口 (end)。"""
    if len(path) < 2:
        return path
    d0s = (path[0][0] - start_lon) ** 2 + (path[0][1] - start_lat) ** 2
    d0e = (path[0][0] - end_lon) ** 2 + (path[0][1] - end_lat) ** 2
    if d0e < d0s:
        return list(reversed(path))
    return path


_APPROACH_TO_DIR8 = {f"{label}进口": code for code, label in DIR8_LABELS.items()}


def _upstream_edge_path(
    cognition: dict[str, Any] | None,
    *,
    approach: str,
    from_lon: float | None,
    from_lat: float | None,
    to_lon: float | None,
    to_lat: float | None,
    target_edge: bool,
) -> list[list[float]]:
    if (
        from_lon is None
        or from_lat is None
        or to_lon is None
        or to_lat is None
    ):
        return []
    if target_edge:
        dir8 = _APPROACH_TO_DIR8.get(approach)
        if dir8 is not None:
            return _road_path_for_entry(
                cognition,
                dir8,
                {"lon": to_lon, "lat": to_lat},
                from_lon,
                from_lat,
            )
    return _orient_path_endpoints(
        [[from_lon, from_lat], [to_lon, to_lat]],
        from_lon,
        from_lat,
        to_lon,
        to_lat,
    )


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

    dir_lines = _approach_metric_lines(
        cognition,
        focus_groups=focus_groups,
        protected_groups=protected_groups,
        nlu=nlu,
    )
    if not dir_lines:
        dir_lines = _direction_metric_lines(
            cognition.get("direction_groups") or [],
            focus_groups=focus_groups,
            protected_groups=protected_groups,
        )
    if dir_lines:
        steps.append(
            {
                "phase": "direction",
                "title": "进口道饱和度",
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
                f"绿灯利用率 {green_util:.2f}。"
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
    """路口结构口播：仅主轴道路（东西向 / 南北向），不含进口数、车道数等概览。"""
    del cognition, inter_name
    return build_axis_roads_speakable(axis_roads, inter_name="")


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

_APPROACH_DIR_ORDER = ("东", "南", "西", "北")


def _approach_saturation_by_dir(cognition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map 东/南/西/北 → per-arm saturation metric."""
    from intersection_agent.utils.turn_metrics import max_turn_saturation_by_dir

    metrics_by_turn = cognition.get("metrics_by_turn") or []
    turn_by_dir = max_turn_saturation_by_dir(metrics_by_turn)
    if turn_by_dir:
        return {
            dir_key: {
                "saturation": sat,
                "level": _severity(sat),
            }
            for dir_key, sat in turn_by_dir.items()
        }

    metrics_by_arm = cognition.get("metrics_by_arm") or []
    arms = cognition.get("arms") or []
    metrics_map = {m["link_id"]: m for m in metrics_by_arm}
    dir_metrics = {
        _normalize_dir(str(m.get("dir4_label") or "")): m
        for m in metrics_by_arm
        if m.get("saturation") is not None
    }
    result: dict[str, dict[str, Any]] = {}
    for arm in arms:
        dir_key = _normalize_dir(str(arm.get("dir4_label") or ""))
        if not dir_key:
            continue
        m = metrics_map.get(arm["link_id"]) or dir_metrics.get(dir_key)
        if not m or m.get("saturation") is None:
            continue
        sat = float(m["saturation"])
        if sat <= 0:
            continue
        prev = result.get(dir_key)
        if prev is None or sat > float(prev.get("saturation") or 0):
            result[dir_key] = m
    for dir_key, m in dir_metrics.items():
        if dir_key not in result and m.get("saturation") is not None:
            sat = float(m["saturation"])
            if sat > 0:
                result[dir_key] = m
    if not result:
        for group in cognition.get("direction_groups") or []:
            sat_raw = group.get("saturation_max")
            if sat_raw is None:
                sat_raw = group.get("saturation_avg")
            if sat_raw is None or float(sat_raw) <= 0:
                continue
            sat = float(sat_raw)
            level = str(group.get("level") or "")
            for arm_label in group.get("arm_labels") or []:
                dir_key = _normalize_dir(str(arm_label))
                if dir_key and dir_key not in result:
                    result[dir_key] = {"saturation": sat, "level": level}
    return result


def _approach_dir_prefix(
    dir_key: str,
    *,
    focus_groups: list[str] | None = None,
    protected_groups: list[str] | None = None,
    nlu: NluResult | None = None,
) -> str:
    focus_set = set(focus_groups or [])
    protect_set = set(protected_groups or [])
    group = DIR4_TO_GROUP.get(dir_key, "")
    if group in focus_set:
        return "【关注】"
    if group in protect_set:
        return "【保护】"
    if nlu and nlu.directions:
        explicit = {_normalize_dir(str(d)) for d in nlu.directions if d}
        if dir_key in explicit:
            return "【关注】"
    return ""


def _approach_metric_lines(
    cognition: dict[str, Any],
    *,
    focus_groups: list[str] | None = None,
    protected_groups: list[str] | None = None,
    nlu: NluResult | None = None,
) -> list[str]:
    """东西南北进口道各自的饱和度（非东西/南北向聚合）。"""
    by_dir = _approach_saturation_by_dir(cognition)
    lines: list[str] = []
    for dir_key in _APPROACH_DIR_ORDER:
        m = by_dir.get(dir_key)
        if not m:
            continue
        sat = float(m["saturation"])
        level_cn = {"high": "拥堵", "medium": "偏高", "low": "畅通"}.get(
            str(m.get("level") or ""), ""
        )
        prefix = _approach_dir_prefix(
            dir_key,
            focus_groups=focus_groups,
            protected_groups=protected_groups,
            nlu=nlu,
        )
        lines.append(f"· {prefix}{dir_key}进口 饱和度 {sat:.2f} {level_cn}")
    return lines


def _hud_metrics_by_approach(cognition: dict[str, Any]) -> list[dict[str, Any]]:
    """HUD 指标：四进口道各自饱和度。"""
    by_dir = _approach_saturation_by_dir(cognition)
    metrics: list[dict[str, Any]] = []
    for dir_key in _APPROACH_DIR_ORDER:
        m = by_dir.get(dir_key)
        if not m:
            continue
        sat = float(m["saturation"])
        metrics.append(
            {
                "label": f"{dir_key}进口",
                "value": f"{sat:.2f}",
                "severity": _severity(sat),
            }
        )
    return metrics


def _primary_problem_type(nlu: NluResult | None) -> str:
    pts = list(nlu.problem_types) if nlu and nlu.problem_types else None
    return resolve_primary_problem_type(pts)


def _hud_title_for_primary(primary: str, default: str) -> str:
    titles = {
        "empty_green": "绿灯利用",
        "spillback": "排队与溢流",
        "conflict": "渠化/相位",
    }
    return titles.get(primary, default)


def _profile_summary_hud(
    primary: str,
    data: dict[str, Any],
    cognition: dict[str, Any],
) -> list[dict[str, Any]]:
    """Problem-type primary metrics for map HUD (align with runtime panel)."""
    del cognition
    eval_metrics = data.get("evaluation") or {}
    pe_metrics = (data.get("problem_evidence") or {}).get("metrics") or {}
    if primary == "empty_green":
        items: list[dict[str, Any]] = []
        gu = eval_metrics.get("green_utilization")
        if gu is not None:
            items.append(
                {
                    "label": "绿灯利用率",
                    "value": f"{float(gu):.2f}",
                    "severity": "low" if float(gu) < 0.55 else "medium",
                }
            )
        er = eval_metrics.get("empty_green_rate")
        if er is not None:
            items.append(
                {
                    "label": "空放率",
                    "value": f"{float(er):.2f}",
                    "severity": "medium",
                }
            )
        return items
    if primary == "spillback":
        items = []
        mq = pe_metrics.get("max_queue_m")
        if mq is not None:
            items.append(
                {
                    "label": "最大排队",
                    "value": f"{float(mq):.0f} m",
                    "severity": "high",
                }
            )
        sr = pe_metrics.get("spillback_risk_max")
        if sr is not None:
            items.append(
                {
                    "label": "溢流风险",
                    "value": f"{float(sr):.2f}",
                    "severity": "high",
                }
            )
        return items
    if primary == "conflict":
        return [
            {
                "label": "诊断焦点",
                "value": "渠化/相位冲突",
                "severity": "medium",
            }
        ]
    return []


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
    gran = data.get("granularity") or {}
    sat_summary = canonical_saturation_summary(
        by_turn=gran.get("by_turn"),
        by_lane=gran.get("by_lane"),
        inter_saturation_max=float(eval_metrics["saturation_max"])
        if eval_metrics.get("saturation_max") is not None
        else None,
        inter_saturation_avg=float(eval_metrics["saturation_avg"])
        if eval_metrics.get("saturation_avg") is not None
        else None,
    )
    saturation = sat_summary.get("saturation_rate") or flow.get("saturation_rate")
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
        primary = _primary_problem_type(nlu)
        profile_hud = _profile_summary_hud(primary, data, cognition)
        time_label = ""
        if nlu and nlu.time_period:
            time_label = nlu.time_period.label or ""

        if primary == "empty_green" and profile_hud:
            base.update(
                {
                    "zoom": 17.6,
                    "pulse_link_ids": [],
                    "hud": {
                        "title": _hud_title_for_primary(primary, time_label or "运行数据"),
                        "icon": "🟢",
                        "metrics": profile_hud,
                    },
                    "markers": [],
                }
            )
            return base

        if primary == "spillback" and profile_hud:
            base.update(
                {
                    "zoom": 17.6,
                    "pulse_link_ids": [],
                    "hud": {
                        "title": _hud_title_for_primary(primary, time_label or "运行数据"),
                        "icon": "📏",
                        "metrics": profile_hud,
                    },
                    "markers": [],
                }
            )
            return base

        if primary == "conflict" and profile_hud:
            base.update(
                {
                    "zoom": 17.6,
                    "pulse_link_ids": [],
                    "hud": {
                        "title": _hud_title_for_primary(primary, time_label or "运行数据"),
                        "icon": "⚡",
                        "metrics": profile_hud,
                    },
                    "markers": [],
                }
            )
            return base

        delay_text = f"{float(delay):.2f}" if delay is not None else "—"
        # 流量阶段地图仅呈现延误（饱和度由左侧面板 update_metrics 承担，分向饱和度留到 direction 阶段）
        delay_marker = {
            "id": "delay-chip",
            "lon": center_lon,
            "lat": center_lat,
            "kind": "chip",
            "variant": "delay",
            "title": "延误指数",
            "value": delay_text,
            "severity": _severity(delay),
        }
        hud_metrics: list[dict[str, Any]] = []
        if delay is not None:
            hud_metrics.append(
                {
                    "label": "延误指数",
                    "value": delay_text,
                    "severity": _severity(delay),
                }
            )
        base.update(
            {
                "zoom": 17.6,
                "pulse_link_ids": [],
                "hud": {
                    "title": time_label or "运行数据",
                    "icon": "📊",
                    "metrics": hud_metrics,
                }
                if hud_metrics
                else None,
                "markers": [delay_marker] if delay is not None else [],
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
            metrics_by_arm = cognition.get("metrics_by_arm") or []
            if _approach_saturation_by_dir(cognition):
                markers = _markers_for_traffic_phase(
                    links,
                    center_lon,
                    center_lat,
                    metrics_by_arm,
                    groups,
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
        approach_hud = _hud_metrics_by_approach(cognition)
        primary = _primary_problem_type(nlu)
        profile_hud = _profile_summary_hud(primary, data, cognition)
        if profile_hud and primary != "congestion":
            approach_hud = profile_hud
        if not approach_hud and worst_sat is not None:
            approach_hud = [
                {
                    "label": worst.get("group", "关键方向") if worst else "方向",
                    "value": f"{worst_sat:.2f}",
                    "severity": _severity(worst_sat),
                }
            ]
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
                    "title": _hud_title_for_primary(primary, "进口道饱和度"),
                    "icon": "🧭",
                    "metrics": approach_hud,
                },
            }
        )
        return base

    if phase == "saturation":
        primary = _primary_problem_type(nlu)
        profile_hud = _profile_summary_hud(primary, data, cognition)
        sat_highlight = focus_dirs if focus_dirs else worst_dirs
        metrics_by_arm = cognition.get("metrics_by_arm") or []
        sat_markers = _markers_for_traffic_phase(
            links,
            center_lon,
            center_lat,
            metrics_by_arm,
            groups,
        )
        approach_hud = _hud_metrics_by_approach(cognition)
        sat_val = float(saturation) if saturation is not None else None
        if profile_hud and primary != "congestion":
            approach_hud = profile_hud
        if not sat_markers and sat_val is not None and primary == "congestion":
            sat_markers = [
                {
                    "id": "saturation-center",
                    "lon": center_lon,
                    "lat": center_lat,
                    "kind": "alert",
                    "title": "过饱和" if sat_val >= 0.85 else "偏高",
                    "value": _fmt_sat(sat_val),
                    "severity": _severity(sat_val),
                }
            ]
        if not approach_hud and sat_val is not None and primary == "congestion":
            approach_hud = [
                {
                    "label": "路口饱和度",
                    "value": _fmt_sat(sat_val),
                    "severity": _severity(sat_val),
                }
            ]
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
                "markers": sat_markers if primary == "congestion" else [],
                "hud": {
                    "title": _hud_title_for_primary(primary, "进口道饱和度"),
                    "icon": "⚠️" if primary == "congestion" else "📊",
                    "metrics": approach_hud,
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
                            "value": f"{util_val:.2f}" if util_val is not None else "—",
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
                            "value": f"{util_val:.2f}" if util_val is not None else "—",
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


def _node_saturation(node: dict[str, Any]) -> float | None:
    """节点四向进口最大饱和度（用于标注与运镜叙事）。"""
    profiles = node.get("approach_profiles") or []
    sats = [
        p.get("turn_saturation_max")
        for p in profiles
        if p.get("turn_saturation_max") is not None
    ]
    if not sats:
        return None
    mx = max(float(s) for s in sats)
    if mx <= 0.01:
        return None
    return mx


def _saturation_label_text(sat: float | None) -> str:
    if sat is None:
        return "待核查数仓"
    if float(sat) <= 0.01:
        return "待核查数仓"
    return f"饱和{float(sat):.2f}"


def _turn_split_text(turn_split: list[dict[str, Any]] | None) -> str:
    """转向拆分文案，如「东直行76.2%、北右转16.1%」。"""
    if not turn_split:
        return ""
    parts: list[str] = []
    for s in turn_split:
        label = s.get("feed_direction") or s.get("turn")
        if not label:
            continue
        if s.get("data_gap"):
            parts.append(f"{label}待核查")
            continue
        if s.get("share_pct") is not None:
            parts.append(f"{label}{s.get('share_pct')}%")
    return "、".join(parts)


_UPSTREAM_CORRIDOR_ZOOM = 17
_UPSTREAM_PULLBACK_ZOOM = 17


def _merge_upstream_frames(frames: list[dict[str, Any]], frame_idx: int) -> dict[str, Any]:
    """多进口道同一逻辑相位合并为一帧（并行呈现）。"""
    if len(frames) == 1:
        out = dict(frames[0])
        out["idx"] = frame_idx
        return out
    base = dict(frames[0])
    reveal: list[str] = []
    seen: set[str] = set()
    for f in frames:
        for rid in f.get("reveal") or []:
            if rid not in seen:
                seen.add(rid)
                reveal.append(rid)
    base.update(
        {
            "idx": frame_idx,
            "tree": "*",
            "reveal": reveal,
            "parallel": True,
            "show_labels": any(f.get("show_labels") for f in frames),
            "fit": any(f.get("fit") for f in frames),
            "narration": "",
        }
    )
    return base


def _build_single_tree_phases(
    tree: dict[str, Any],
    cognition: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """单进口道溯源树 → 侧卡数据 + 分相位帧（pullback/target/hops/fit）。"""
    tid = tree["tree_id"]
    approach = tree.get("approach") or ""
    root = tree["root"]
    target = tree.get("target") or {}
    target_id = target.get("inter_id")
    target_lon = target.get("lon")
    target_lat = target.get("lat")
    node_coords: dict[str, tuple[float | None, float | None]] = {
        str(target_id): (target_lon, target_lat),
    }

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    path_nodes: list[dict[str, Any]] = []

    nodes.append(
        {
            "id": target_id,
            "inter_id": target_id,
            "name": target.get("name"),
            "lon": target.get("lon"),
            "lat": target.get("lat"),
            "role": "target",
            "approach": approach,
            "saturation": None,
            "turn_split": [],
            "approach_profiles": [],
            "decision": None,
        }
    )

    def _walk(node: dict[str, Any], parent_id: str | None) -> None:
        nid = node.get("inter_id")
        view = {
            "id": nid,
            "inter_id": nid,
            "name": node.get("inter_name"),
            "lon": node.get("lng"),
            "lat": node.get("lat"),
            "role": "governance" if node.get("decision") == "治理落点" else "upstream",
            "hop": node.get("hop"),
            "feeding_dir8": node.get("feeding_dir8"),
            "saturation": _node_saturation(node),
            "turn_split": node.get("turn_split") or [],
            "approach_profiles": node.get("approach_profiles") or [],
            "decision": node.get("decision"),
            "governable": node.get("governable"),
        }
        nodes.append(view)
        path_nodes.append(view)
        node_coords[str(nid)] = (view.get("lon"), view.get("lat"))
        if parent_id is not None:
            hop_path = node.get("hop_path") or []
            path_source = node.get("path_source") or (
                "link_geom" if len(hop_path) >= 2 else "none"
            )
            edges.append(
                {
                    "id": f"edge:{tid}:{parent_id}-{nid}",
                    "from": parent_id,
                    "to": nid,
                    "path": hop_path,
                    "path_source": path_source,
                    "flow_pct": node.get("coverage"),
                    "dominant_turn": node.get("feeding_dir8"),
                }
            )
        for child in node.get("children") or []:
            _walk(child, nid)

    _walk(root, target_id)
    out_tree = {"tree_id": tid, "approach": approach, "nodes": nodes, "edges": edges}

    pullback = {
        "tree": tid,
        "frame_type": "pullback",
        "focus": target_id,
        "center": [target.get("lon"), target.get("lat")],
        "zoom": _UPSTREAM_PULLBACK_ZOOM,
        "fit": False,
        "reveal": [target_id] if target_id else [],
        "show_labels": False,
        "narration": f"抬升视角，从{approach}沿干线向上游追溯来车。",
    }
    target_frame = {
        "tree": tid,
        "frame_type": "target",
        "focus": target_id,
        "center": [target.get("lon"), target.get("lat")],
        "zoom": _UPSTREAM_CORRIDOR_ZOOM,
        "fit": False,
        "reveal": [target_id] if target_id else [],
        "show_labels": False,
        "narration": f"{approach}过饱和，沿干线向上游追溯来车。",
    }

    hops: list[dict[str, Any]] = []
    gov_count = 0
    for view in path_nodes:
        nid = view["id"]
        parent_edge = next((e["id"] for e in edges if e["to"] == nid), None)
        spread_frame = None
        if parent_edge:
            spread_frame = {
                "tree": tid,
                "frame_type": "spread",
                "focus": parent_edge,
                "center": [view.get("lon"), view.get("lat")],
                "zoom": _UPSTREAM_CORRIDOR_ZOOM,
                "fit": False,
                "reveal": [parent_edge],
                "show_labels": False,
                "animate_edge": parent_edge,
                "narration": f"沿{approach}干线向上游蔓延…",
            }
        sat = view.get("saturation")
        sat_txt = _saturation_label_text(sat if isinstance(sat, (int, float)) else None)
        split_txt = _turn_split_text(view.get("turn_split"))
        split_seg = f"，汇入车流 {split_txt}" if split_txt else ""
        if view.get("decision") == "治理落点":
            gov_count += 1
            tail = "（有信控空间，可作治理落点）"
        elif view.get("decision") == "二跳截止":
            if view.get("governable") is False:
                tail = "（上游亦过饱和，单点信控优化空间有限）"
            else:
                tail = "（已达溯源上限）"
        elif view.get("governable") is False:
            tail = "（上游亦过饱和，信控优化空间有限，继续上溯）"
        else:
            tail = "（仍偏饱和，继续上溯）"
        name = view.get("name") or nid
        node_frame = {
            "tree": tid,
            "frame_type": "node",
            "focus": nid,
            "center": [view.get("lon"), view.get("lat")],
            "zoom": _UPSTREAM_CORRIDOR_ZOOM,
            "fit": False,
            "reveal": [nid] + ([parent_edge] if parent_edge else []),
            "show_labels": True,
            "narration": f"上游{name}：{sat_txt}{split_seg}{tail}",
        }
        hops.append({"spread": spread_frame, "node": node_frame})

    all_ids = [n["id"] for n in nodes if n.get("id")] + [e["id"] for e in edges]
    if gov_count:
        summary = (
            f"{approach}共溯 {len(path_nodes)} 个上游路口，"
            f"定位 {gov_count} 个治理落点。"
        )
    else:
        summary = (
            f"{approach}共溯 {len(path_nodes)} 个上游路口，"
            "上游普遍过饱和，单点信控优化空间有限。"
        )
    fit_frame = {
        "tree": tid,
        "frame_type": "fit",
        "focus": [n["id"] for n in path_nodes],
        "center": None,
        "zoom": _UPSTREAM_PULLBACK_ZOOM,
        "fit": True,
        "reveal": all_ids,
        "show_labels": True,
        "narration": summary,
    }

    phases = {"pullback": pullback, "target": target_frame, "hops": hops, "fit": fit_frame}
    return out_tree, phases


def _flatten_tree_phases(phases: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [phases["pullback"], phases["target"]]
    for hop in phases["hops"]:
        if hop.get("spread"):
            out.append(hop["spread"])
        out.append(hop["node"])
    out.append(phases["fit"])
    return out


def build_upstream_storyboard(
    trees: list[dict[str, Any]], cognition: dict[str, Any] | None = None
) -> dict[str, Any]:
    """进口道溯源分镜：单进口串行；多进口按相位并行（同一跳 spread/node 同时揭示）。

    每帧 {idx, tree, focus, center:[lng,lat], zoom, fit, reveal:[overlay_id], narration}：
    - center/zoom 驱动前端平滑运镜（panTo / setZoomAndCenter），用户全程不操作。
    - fit=True 时前端 setFitView 收束全景。
    - reveal 仅含「该帧新增」覆盖物 id（节点 inter_id 或 `edge:*` 边 id），前端按帧累计并集。
    - 节点带 saturation 与 turn_split，前端落浮动文本标注（路口名+饱和度+转向拆分）。
    - 多树时 tree=\"*\" 且 parallel=True，前端不按树变暗。
    """
    if not trees:
        return {"trees": [], "frames": [], "parallel": False}

    out_trees: list[dict[str, Any]] = []
    all_phases: list[dict[str, Any]] = []
    for tree in trees:
        out_tree, phases = _build_single_tree_phases(tree, cognition)
        out_trees.append(out_tree)
        all_phases.append(phases)

    parallel = len(trees) > 1
    if not parallel:
        flat = _flatten_tree_phases(all_phases[0])
        return {
            "trees": out_trees,
            "frames": [{**f, "idx": i} for i, f in enumerate(flat)],
            "parallel": False,
        }

    merged: list[dict[str, Any]] = []
    idx = 0
    merged.append(_merge_upstream_frames([p["pullback"] for p in all_phases], idx))
    idx += 1
    merged.append(_merge_upstream_frames([p["target"] for p in all_phases], idx))
    idx += 1

    max_hops = max(len(p["hops"]) for p in all_phases)
    for hi in range(max_hops):
        spreads = [
            p["hops"][hi]["spread"]
            for p in all_phases
            if hi < len(p["hops"]) and p["hops"][hi].get("spread")
        ]
        if spreads:
            merged.append(_merge_upstream_frames(spreads, idx))
            idx += 1
        nodes = [p["hops"][hi]["node"] for p in all_phases if hi < len(p["hops"])]
        if nodes:
            merged.append(_merge_upstream_frames(nodes, idx))
            idx += 1

    merged.append(_merge_upstream_frames([p["fit"] for p in all_phases], idx))
    return {"trees": out_trees, "frames": merged, "parallel": True}
