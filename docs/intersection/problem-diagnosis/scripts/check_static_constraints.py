"""Detect static supply-side constraint flags from scene profile for problem diagnosis."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent


def _load_diagnosis_static_logic():
    spec = importlib.util.spec_from_file_location("diagnosis_static_logic", _SCRIPT_DIR / "diagnosis_static_logic.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 diagnosis_static_logic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_config_module():
    common_dir = Path(__file__).resolve().parents[2] / "common"
    spec = importlib.util.spec_from_file_location("intersection_load_config", common_dir / "load_config.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 intersection/common/load_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CFG = _load_config_module()
_DSL = _load_diagnosis_static_logic()
_TH = _CFG.threshold


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _context_tokens(profile: dict[str, Any]) -> set[str]:
    tokens = {str(item) for item in _as_list(profile.get("context_tags")) if item}
    context = profile.get("context") if isinstance(profile.get("context"), dict) else {}
    for key, value in context.items():
        if isinstance(value, bool) and value:
            tokens.add(str(key))
        elif isinstance(value, str):
            tokens.add(value)
        elif isinstance(value, list):
            tokens.update(str(item) for item in value if item)
    return tokens


STRONG_ATTRACTOR_AOI_TYPES = {"学校", "医院", "商圈", "港区/园区", "查验口/收费站"}

ROAD_INTERFERENCE_DESCRIPTIONS = {
    "bus_stop": "公交站点靠近路口，停靠车辆可能占用通行空间",
    "driveway_interference": "单位/小区出入口靠近路口，进出车辆扰动明显",
    "strong_attractor": "强交通吸引点临近路口，集散需求可能挤占交叉口能力",
}


def aoi_sources_from_profile(profile: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Read scene-cognition §1.3 attraction sources from the profile."""
    context = profile.get("context") if isinstance(profile.get("context"), dict) else {}
    if "aoi_sources" in context:
        rows = [row for row in _as_list(context.get("aoi_sources")) if isinstance(row, dict)]
        return rows, "context.aoi_sources"
    report = profile.get("scenario_report") if isinstance(profile.get("scenario_report"), dict) else {}
    basic = report.get("basicScenario") if isinstance(report.get("basicScenario"), dict) else {}
    if "attractionSources" in basic:
        rows = [row for row in _as_list(basic.get("attractionSources")) if isinstance(row, dict)]
        return rows, "scenario_report.basicScenario.attractionSources"
    return [], None


def infer_road_segment_interference(aoi_sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Map scene-cognition §1.3 rows to road-segment interference codes."""
    codes: set[str] = set()
    hits: list[dict[str, Any]] = []
    for row in aoi_sources:
        aoi_type = str(row.get("type") or "")
        record_kind = str(row.get("recordKind") or row.get("record_kind") or "")
        access_role = row.get("accessRole") or row.get("access_role")
        if aoi_type == "公交站":
            code = "bus_stop"
        elif access_role or (record_kind == "poi" and aoi_type == "停车场"):
            code = "driveway_interference"
        elif aoi_type in STRONG_ATTRACTOR_AOI_TYPES:
            code = "strong_attractor"
        elif aoi_type == "停车场" and record_kind != "poi":
            code = "strong_attractor"
        else:
            continue
        codes.add(code)
        hits.append(
            {
                "code": code,
                "name": row.get("name"),
                "type": aoi_type,
                "distance_m": row.get("distance_m"),
                "accessRole": access_role,
            }
        )
    return {"codes": sorted(codes), "hits": hits}


def check_static_constraints(profile: dict[str, Any]) -> dict[str, Any]:
    """Scan supply profile and channelization for static issues from the checklist.

    Returns flags consumable by diagnose_signal_issues and LLM reasoning.
    """
    supply = profile.get("supply_profile", {}) or {}
    control = profile.get("control_profile", {}) or {}
    context_tags = _context_tokens(profile)
    flags: list[dict[str, Any]] = []

    static_flags = _as_list(supply.get("static_flags"))
    static_flag_set = {str(item) for item in static_flags}
    if "funnel_effect" in static_flags:
        flags.append(
            _flag(
                "funnel_effect",
                "进口直行车道数大于对应出口车道数，存在漏斗效应风险",
                "high",
                ["supply_profile.static_flags"],
            )
        )
    if "more_entrances_than_exits" in static_flags:
        flags.append(
            _flag(
                "entrance_exit_mismatch",
                "进口道数量多于出口道，可能导致内部排队堆积",
                "medium",
                ["supply_profile.static_flags"],
            )
        )
    if static_flag_set.intersection({"exit_lane_deficit", "in_out_lane_mismatch", "road_section_mismatch"}):
        flags.append(
            _flag(
                "road_section_mismatch",
                "道路断面或进出口车道数不匹配，可能形成瓶颈",
                "medium",
                ["supply_profile.static_flags"],
                evidence={"flags": sorted(static_flag_set.intersection({"exit_lane_deficit", "in_out_lane_mismatch", "road_section_mismatch"}))},
            )
        )

    channelization = _as_list(supply.get("channelization"))
    phase_analysis = _DSL.analyze_phase_channel_match(profile, _TH)
    if phase_analysis.get("hits"):
        first_hit = phase_analysis["hits"][0]
        flags.append(
            _flag(
                "phase_channel_mismatch",
                first_hit.get("message", "相位相序与渠化不匹配"),
                "high",
                ["supply_profile.channelization", "control_profile.stage_detail"],
                evidence={"hits": phase_analysis["hits"][:6], "approach_details": phase_analysis.get("approach_details", [])},
            )
        )

    funnel_analysis = _DSL.analyze_funnel_effect(profile, _TH)
    if funnel_analysis.get("hits"):
        for hit in funnel_analysis["hits"]:
            code = "funnel_effect" if hit.get("rule") == "A" else "entrance_exit_mismatch"
            if any(f.get("code") == code for f in flags):
                continue
            flags.append(
                _flag(
                    code,
                    hit.get("message", "存在进出口漏斗效应"),
                    "high" if code == "funnel_effect" else "medium",
                    ["supply_profile.channelization", "supply_profile.static_flags"],
                    evidence={"hit": hit, "pair_details": funnel_analysis.get("pair_details", [])},
                )
            )

    right_turn_narrow = _detect_narrow_right_turn_lanes(channelization)
    if right_turn_narrow or "right_turn_lane_narrow" in static_flag_set:
        flags.append(
            _flag(
                "right_turn_lane_narrow",
                "右转或混行车道有效宽度不足，易诱发机非冲突和右转通行受限",
                "medium",
                ["supply_profile.channelization", "supply_profile.static_flags"],
                evidence={"lanes": right_turn_narrow},
            )
        )

    adjacent_spacing = _as_float(supply.get("adjacent_inter_spacing_m"))
    if adjacent_spacing and adjacent_spacing < _TH("static.adjacent_spacing_m"):
        flags.append(
            _flag(
                "short_spacing_chain",
                f"与相邻信控路口间距仅约 {adjacent_spacing:.0f}m，联动与防溢流约束强",
                "medium",
                ["supply_profile.adjacent_inter_spacing_m"],
            )
        )

    driveway_spacing = _as_float(supply.get("driveway_spacing_m"))
    road_class = str(supply.get("road_class") or supply.get("road_level") or "")
    driveway_threshold = _driveway_spacing_threshold(road_class)
    if driveway_spacing and driveway_spacing < driveway_threshold:
        flags.append(
            _flag(
                "driveway_too_close",
                f"路侧出入口距交叉口约 {driveway_spacing:.0f}m，低于{road_class or '道路'}建议控制距离",
                "medium",
                ["supply_profile.driveway_spacing_m", "supply_profile.road_class"],
                evidence={"distance_m": driveway_spacing, "threshold_m": driveway_threshold, "road_class": road_class},
            )
        )

    aoi_sources, aoi_source_path = aoi_sources_from_profile(profile)
    road_interference = infer_road_segment_interference(aoi_sources)
    for code in road_interference.get("codes") or []:
        flags.append(
            _flag(
                code,
                ROAD_INTERFERENCE_DESCRIPTIONS.get(code, "路侧要素可能干扰路口运行"),
                "medium",
                [aoi_source_path or "context.aoi_sources"],
                evidence={"hits": [hit for hit in road_interference.get("hits", []) if hit.get("code") == code][:3]},
            )
        )

    approach_capacity_ratio = _as_float(supply.get("approach_capacity_ratio"))
    if approach_capacity_ratio and approach_capacity_ratio < _TH("organization.approach_capacity_ratio_low"):
        flags.append(
            _flag(
                "approach_capacity_deficit",
                f"进口通行能力与需求比约 {approach_capacity_ratio:.2f}，进口道通行能力不足",
                "medium",
                ["supply_profile.approach_capacity_ratio"],
            )
        )
    demand = profile.get("demand_profile") or {}
    metrics = profile.get("metrics_summary") or profile.get("metrics") or {}
    movement_vc = _as_float(supply.get("movement_vc_ratio") or demand.get("movement_vc_ratio"))
    if movement_vc > _TH("organization.movement_vc_ratio_high"):
        flags.append(
            _flag(
                "movement_capacity_deficit",
                f"关键转向流量/通行能力比约 {movement_vc:.2f}，对应流向能力不足",
                "high",
                ["demand_profile.movement_vc_ratio"],
            )
        )
    lane_group_unbalance = _as_float(supply.get("lane_group_capacity_unbalance") or demand.get("lane_group_capacity_unbalance"))
    if lane_group_unbalance > _TH("organization.lane_group_capacity_unbalance"):
        flags.append(
            _flag(
                "lane_group_capacity_unbalance",
                f"进口车道或转向能力不均衡系数约 {lane_group_unbalance:.2f}，存在流量溢出风险",
                "medium",
                ["demand_profile.lane_group_capacity_unbalance"],
            )
        )
    detour_time = _as_float(supply.get("detour_time_min") or metrics.get("detour_time_min"))
    if detour_time > _TH("organization.detour_time_min"):
        flags.append(
            _flag(
                "tidal_detour_pressure",
                f"平均绕行时间约 {detour_time:.0f}min，潮汐或绕行压力明显",
                "medium",
                ["metrics_summary.detour_time_min"],
            )
        )
    exit_lane_diff = _as_float(supply.get("exit_lane_merge_diff"))
    if exit_lane_diff > _TH("organization.exit_lane_merge_diff"):
        flags.append(
            _flag(
                "outlet_capacity_mismatch",
                f"同一相位汇入车道数多于出口道约 {exit_lane_diff:.0f} 条，出口通行能力不匹配",
                "high",
                ["supply_profile.exit_lane_merge_diff"],
            )
        )

    slow_flags = {
        "no_bike_lane": "缺少非机动车专用道，机非混行冲突风险升高",
        "excessive_crosswalks": "行人过街斑马线过多或过街组织复杂，清空压力升高",
        "bike_waiting_area_insufficient": "非机动车等待区不足，易侵入机动车放行空间",
    }
    for token, description in slow_flags.items():
        if token in context_tags or token in static_flag_set:
            flags.append(_flag(token, description, "medium", ["context_tags", "supply_profile.static_flags"]))

    if {"school", "hospital"}.intersection(context_tags):
        flags.append(
            _flag(
                "special_poi_protection",
                "学校/医院等强吸引点需额外慢行与清空保障",
                "medium",
                ["context_tags"],
            )
        )

    lane_flow_analysis = _DSL.analyze_lane_flow_match(profile, _TH)

    return {
        "static_flags": flags,
        "static_issue_codes": [item["code"] for item in flags],
        "has_structural_constraint": bool(flags),
        "control_improvement_hint": "low" if len(flags) >= 2 else "medium",
        "phase_channel_analysis": phase_analysis,
        "funnel_analysis": funnel_analysis,
        "lane_flow_analysis": lane_flow_analysis,
    }


def _flag(
    code: str,
    description: str,
    severity: str,
    sources: list[str],
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "description": description,
        "severity": severity,
        "sources": sources,
        "evidence": evidence or {},
    }


def _detect_narrow_right_turn_lanes(channelization: list[dict[str, Any]]) -> list[str]:
    narrow: list[str] = []
    for row in channelization:
        if not isinstance(row, dict):
            continue
        turn_move = str(row.get("turn_move") or row.get("lane_info") or "").lower()
        if not any(token in turn_move for token in ("右转", "right")):
            continue
        width = _as_float(row.get("width_m") or row.get("lane_width_m") or row.get("effective_width_m"))
        if width and width < _TH("static.right_turn_lane_width_m"):
            label = str(row.get("link_id") or row.get("dir8_label") or "right_turn_lane")
            narrow.append(f"{label}:{width:.2f}m")
    return narrow[:6]


def _driveway_spacing_threshold(road_class: str) -> float:
    text = road_class.lower()
    if "主" in road_class or "arterial" in text:
        return _TH("static.driveway_spacing_arterial_m")
    if "次" in road_class or "collector" in text:
        return _TH("static.driveway_spacing_collector_m")
    return _TH("static.driveway_spacing_branch_m")
