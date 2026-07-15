"""确定性治理方案包（对外展示口径）。

对外只输出三类可落地方案，禁止「分析亮点 / 道路等级画像」等演示性文案：
- signal_control  信控方案：哪个相位加/减多少秒
- organization    交通组织优化：渠化、导向、借道等
- management      交通管理建议：勤务、违停、机非秩序等
"""

from __future__ import annotations

import re
from typing import Any


SCHEME_KEYS = ("signal_control", "organization", "management")


def build_action_package(
    *,
    diagnosis: dict[str, Any] | None,
    strategy: dict[str, Any] | None,
    ticket: dict[str, Any] | None = None,
    proposed_timing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnosis = diagnosis or {}
    strategy = strategy or {}
    ticket = ticket or {}

    decision = strategy.get("decision") if isinstance(strategy.get("decision"), dict) else {}
    decision_mode = str(decision.get("decision_mode") or "")
    mechanism = (
        (diagnosis.get("overflow_mechanism") or {}).get("primary")
        or (strategy.get("overflow_mechanism") or {}).get("primary")
        or ""
    )
    road = _road_profile(diagnosis)
    target = _target_labels(ticket, strategy)
    downstream = _downstream_name(diagnosis)

    signal_control = _signal_control_scheme(
        decision_mode, mechanism, target, downstream, proposed_timing
    )
    organization = _organization_scheme(road, target, downstream, mechanism)
    management = _management_scheme(road, target, downstream, mechanism)

    package = {
        "available": True,
        "road_profile": road,  # 内部字段，前端不直接展示
        "decision_mode": decision_mode or None,
        "mechanism": mechanism or None,
        "schemes": {
            "signal_control": signal_control,
            "organization": organization,
            "management": management,
        },
        # 兼容旧字段名，避免前端短暂空窗；不再含 insight
        "layers": {
            "proposed_timing": [x for x in signal_control if x.get("kind") == "timing"],
            "organization": organization,
            "management": management,
        },
        "headline": _headline(signal_control),
        "execution_order": _scheme_lines(signal_control)[:4],
    }
    return package


def enrich_signal_control_from_timing(
    action_package: dict[str, Any],
    proposed_timing: dict[str, Any] | None,
) -> dict[str, Any]:
    """用真实相位绿差覆盖/补齐信控方案文案。"""
    if not isinstance(action_package, dict) or not proposed_timing:
        return action_package
    phase_lines = _phase_delta_items(proposed_timing)
    if not phase_lines:
        return action_package
    schemes = dict(action_package.get("schemes") or {})
    # 保留门控说明，用相位加减替换笼统「有效绿+5s」
    kept = [
        row
        for row in (schemes.get("signal_control") or [])
        if row.get("kind") in {"gate", "monitor"}
    ]
    schemes["signal_control"] = [*phase_lines, *kept]
    action_package = {**action_package, "schemes": schemes}
    action_package["headline"] = _headline(schemes["signal_control"])
    action_package["execution_order"] = _scheme_lines(schemes["signal_control"])[:4]
    layers = dict(action_package.get("layers") or {})
    layers["proposed_timing"] = [x for x in schemes["signal_control"] if x.get("kind") == "timing"]
    action_package["layers"] = layers
    return action_package


def merge_action_texts_into_recommended(
    recommended: list[str],
    action_package: dict[str, Any],
) -> list[str]:
    """策略 recommended 只收三类方案短句，不收分析口吻。"""
    out: list[str] = []
    schemes = action_package.get("schemes") or {}
    for key in SCHEME_KEYS:
        for item in schemes.get(key) or []:
            text = _action_text(item, compact=True)
            if text and text not in out:
                out.append(text)
    for text in recommended or []:
        # 过滤演示性 / 分析性残留
        if _is_demo_copy(str(text)):
            continue
        if text and text not in out:
            out.append(text)
    return out[:10]


def _is_demo_copy(text: str) -> bool:
    needles = (
        "分析亮点",
        "道路等级画像",
        "道路等级视角",
        "本例价值",
        "演示",
        "拆成",
        "三叉诊断",
        "眼前一亮",
    )
    return any(n in text for n in needles)


def _action_text(item: Any, *, compact: bool = False) -> str:
    if isinstance(item, dict):
        action = str(item.get("action") or "").strip()
        if compact:
            return action
        where = str(item.get("where") or item.get("target") or "").strip()
        detail = str(item.get("detail") or "").strip()
        parts = [p for p in (action, f"位置：{where}" if where else "", detail) if p]
        return "；".join(parts)
    return str(item or "").strip()


def _scheme_lines(items: list[dict[str, Any]]) -> list[str]:
    return [t for t in (_action_text(i, compact=True) for i in items) if t]


def _headline(signal_control: list[dict[str, Any]]) -> str:
    timing = [x for x in signal_control if x.get("kind") == "timing"]
    if timing:
        return "；".join(_action_text(x, compact=True) for x in timing[:3])
    return "给出可执行信控相位调整"


def _target_labels(ticket: dict[str, Any], strategy: dict[str, Any]) -> dict[str, str]:
    target = (strategy.get("strategy") or {}).get("target_intersection") or {}
    direction = ticket.get("direction") or target.get("direction") or ""
    movement = ticket.get("movement") or target.get("movement") or ""
    name = ticket.get("intersection_name") or target.get("inter_name") or "目标路口"
    return {
        "inter_name": str(name),
        "movement": f"{direction}{movement}".strip() or "目标流向",
        "direction": str(direction),
        "turn": str(movement),
    }


def _downstream_name(diagnosis: dict[str, Any]) -> str:
    ds = diagnosis.get("downstream_state") or {}
    if ds.get("direct_downstream_inter_name"):
        return str(ds["direct_downstream_inter_name"])
    primary = (diagnosis.get("downstream_diagnosis") or {}).get("primary_downstream") or {}
    return str(primary.get("inter_name") or "直接下游")


def _road_profile(diagnosis: dict[str, Any]) -> dict[str, Any]:
    labels: list[str] = []
    issues = (diagnosis.get("scenario_report") or {}).get("issues") or diagnosis.get("checklist_issues") or []
    if isinstance(issues, list):
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            summary = str(issue.get("summary") or "")
            if "道路等级" in summary or issue.get("item_id") == "adjacent_spacing":
                labels.extend(_extract_road_labels(summary))
    for key in ("topology", "scope", "intersection_profile"):
        blob = diagnosis.get(key)
        if isinstance(blob, dict):
            for item in blob.get("road_levels") or []:
                if isinstance(item, dict) and item.get("label"):
                    labels.append(str(item["label"]))
            combo = blob.get("road_grade_combination")
            if combo:
                labels.extend(_extract_road_labels(str(combo)))

    labels = list(dict.fromkeys(labels))
    groups = {_label_to_group(x) for x in labels}
    groups.discard("")
    primary_group = "次干路"
    if "快速路/高速" in groups or "主干路" in groups:
        primary_group = "主干路" if "主干路" in groups else "快速路/高速"
    if groups <= {"支路"} or (
        "支路" in groups and "主干路" not in groups and "快速路/高速" not in groups and "次干路" not in groups
    ):
        primary_group = "支路"
    if "次干路" in groups and primary_group not in {"主干路", "快速路/高速"}:
        primary_group = "次干路"

    small_road = primary_group == "支路" or any(
        "小路" in x or "支路" in x or "普通道路" in x for x in labels
    )
    arterial = primary_group in {"主干路", "快速路/高速"}
    return {
        "labels": labels,
        "groups": sorted(groups),
        "primary_group": primary_group,
        "is_small_road_context": small_road,
        "is_arterial_context": arterial,
        "mix_summary": "／".join(labels) if labels else "未分级",
    }


def _extract_road_labels(text: str) -> list[str]:
    return re.findall(
        r"城市(?:快速路|主干道|次干道|普通道路)|高速公路|国道|省道|县道|乡道|小路|主干路|次干路|支路",
        text,
    )


def _label_to_group(label: str) -> str:
    if any(k in label for k in ("快速", "高速")):
        return "快速路/高速"
    if any(k in label for k in ("主干", "国道")):
        return "主干路"
    if any(k in label for k in ("次干", "省道")):
        return "次干路"
    if any(k in label for k in ("支路", "普通", "小路", "乡道", "县道", "县乡")):
        return "支路"
    return ""


def _phase_delta_items(proposed_timing: dict[str, Any]) -> list[dict[str, Any]]:
    stages = proposed_timing.get("phase_stage_timing_list") or []
    items: list[dict[str, Any]] = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        raw = stage.get("green_delta_s")
        if raw is None:
            cur = (stage.get("current_timing") or {}).get("green_time_s")
            opt = (stage.get("optimized_timing") or {}).get("green_time_s")
            if cur is not None and opt is not None:
                try:
                    raw = float(opt) - float(cur)
                except (TypeError, ValueError):
                    raw = None
        try:
            delta = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            continue
        if abs(delta) < 0.5:
            continue
        stage_id = stage.get("phase_stage_id") or stage.get("phaseStageId") or ""
        name = stage.get("phase_stage_name") or stage.get("phaseStageName") or f"阶段{stage_id}"
        sign = f"+{int(delta)}s" if delta > 0 else f"{int(delta)}s"
        items.append(
            {
                "kind": "timing",
                "action": f"阶段{stage_id}（{name}）绿灯 {sign}",
                "where": str(name),
                "phase_stage_id": str(stage_id),
                "phase_stage_name": str(name),
                "green_delta_s": int(delta),
                "executable_now": True,
            }
        )
    cycle_delta = proposed_timing.get("cycle_delta_s")
    if cycle_delta is None and proposed_timing.get("cycle_s") is not None:
        cur_c = proposed_timing.get("current_cycle_s")
        if cur_c is not None:
            try:
                cycle_delta = float(proposed_timing["cycle_s"]) - float(cur_c)
            except (TypeError, ValueError):
                cycle_delta = 0
    try:
        cd = int(float(cycle_delta or 0))
    except (TypeError, ValueError):
        cd = 0
    if items:
        items.append(
            {
                "kind": "timing",
                "action": f"信号周期 {'±0s' if cd == 0 else (f'+{cd}s' if cd > 0 else f'{cd}s')}",
                "where": "整周期",
                "cycle_delta_s": cd,
            }
        )
    return items


def _signal_control_scheme(
    decision_mode: str,
    mechanism: str,
    target: dict[str, str],
    downstream: str,
    proposed_timing: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    phase_items = _phase_delta_items(proposed_timing or {})
    movement = target["movement"]
    if phase_items:
        rows = list(phase_items)
    elif decision_mode in {"verify_then_adjust", "verification_required"}:
        rows = [
            {
                "kind": "timing",
                "action": f"目标相位（{movement}）绿灯 +5s",
                "where": target["inter_name"],
                "green_delta_s": 5,
                "gate": "verification_passed",
                "executable_now": False,
            },
            {
                "kind": "timing",
                "action": "非目标最长相位绿灯 -5s（相位内借绿）",
                "where": target["inter_name"],
                "green_delta_s": -5,
                "gate": "verification_passed",
                "executable_now": False,
            },
            {
                "kind": "timing",
                "action": "信号周期 ±0s",
                "where": target["inter_name"],
                "cycle_delta_s": 0,
            },
        ]
    elif decision_mode in {"incremental_release", "incremental_release_trial"}:
        rows = [
            {
                "kind": "timing",
                "action": f"目标相位（{movement}）绿灯 +5s",
                "where": target["inter_name"],
                "green_delta_s": 5,
                "executable_now": True,
            },
            {
                "kind": "timing",
                "action": "非目标最长相位绿灯 -5s（相位内借绿）",
                "where": target["inter_name"],
                "green_delta_s": -5,
                "executable_now": True,
            },
            {"kind": "timing", "action": "信号周期 ±0s", "cycle_delta_s": 0},
        ]
    elif decision_mode == "downstream_protection":
        rows = [
            {
                "kind": "timing",
                "action": f"目标相位（{movement}）绿灯 −2s",
                "where": target["inter_name"],
                "green_delta_s": -2,
                "executable_now": True,
            },
            {"kind": "timing", "action": "信号周期 ±0s", "cycle_delta_s": 0},
        ]
    elif decision_mode == "upstream_coordination":
        rows = [
            {
                "kind": "timing",
                "action": f"目标相位（{movement}）绿灯 +2s",
                "green_delta_s": 2,
                "executable_now": True,
            },
            {"kind": "timing", "action": "信号周期 +10s", "cycle_delta_s": 10},
        ]
    else:
        rows = []

    if decision_mode in {"verify_then_adjust", "verification_required"}:
        rows.append(
            {
                "kind": "gate",
                "action": "下发前完成：出口畅通核验、检测有效、绿灯末端队列记录",
                "where": target["inter_name"],
            }
        )
        rows.append(
            {
                "kind": "monitor",
                "action": f"试验 5 周期；{downstream}排队比>0.9 立即回滚原方案",
                "where": downstream,
            }
        )
    elif decision_mode in {"incremental_release", "incremental_release_trial"}:
        rows.append(
            {
                "kind": "monitor",
                "action": f"下发后试运行 5 个周期；{downstream}排队比>0.9 或目标排队未改善时自动回滚",
                "where": downstream,
            }
        )
    return rows


def _organization_scheme(
    road: dict[str, Any],
    target: dict[str, str],
    downstream: str,
    mechanism: str,
) -> list[dict[str, Any]]:
    """交通组织优化：可执行措施，不含分析口号。"""
    inter = target["inter_name"]
    movement = target["movement"]
    rows: list[dict[str, Any]] = []
    if road.get("is_small_road_context") or mechanism == "discharge_anomaly":
        rows.append(
            {
                "kind": "organization",
                "action": f"核查并优化{movement}进口车道功能（直/左/直右）与高峰流量匹配",
                "where": inter,
            }
        )
        rows.append(
            {
                "kind": "organization",
                "action": "高峰时段评估可变导向车道或临时借道组织，减少绿灯放空",
                "where": inter,
            }
        )
    if road.get("is_arterial_context"):
        rows.append(
            {
                "kind": "organization",
                "action": f"核对{inter}至{downstream}走廊车队到达与相位差是否错峰",
                "where": f"{inter}—{downstream}",
            }
        )
    if not rows:
        rows.append(
            {
                "kind": "organization",
                "action": f"核查{movement}出口渠化与下游进口衔接，消除出口瓶颈",
                "where": f"{inter} → {downstream}",
            }
        )
    return rows


def _management_scheme(
    road: dict[str, Any],
    target: dict[str, str],
    downstream: str,
    mechanism: str,
) -> list[dict[str, Any]]:
    """交通管理建议：勤务与秩序类可执行动作。"""
    inter = target["inter_name"]
    movement = target["movement"]
    rows = [
        {
            "kind": "management",
            "action": f"晚高峰对{movement}出口及{downstream}进口开展视频巡检，清除违停占道",
            "where": f"{inter}出口 / {downstream}",
        },
        {
            "kind": "management",
            "action": "加强机非隔离与借道冲突劝导，保障绿灯有效放行",
            "where": inter,
        },
    ]
    if road.get("is_small_road_context"):
        rows.append(
            {
                "kind": "management",
                "action": "小路进口增设临时导流与行人过街管控，缩短干扰放行时段",
                "where": inter,
            }
        )
    if mechanism == "discharge_anomaly":
        rows.append(
            {
                "kind": "management",
                "action": "同步核对检测器工作状态，异常立即报修，避免误导配时加绿",
                "where": inter,
            }
        )
    return rows
