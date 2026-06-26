"""Run problem-diagnosis checklist item-by-item against a scene profile."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable

_SCRIPT_DIR = Path(__file__).resolve().parent


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPT_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_static = _load_module("check_static_constraints", "check_static_constraints.py")
_score = _load_module("score_intersection_issues", "score_intersection_issues.py")
_dsl = _load_module("diagnosis_static_logic", "diagnosis_static_logic.py")
_imbalance = _load_module("diagnosis_imbalance_logic", "diagnosis_imbalance_logic.py")
_empty_green = _load_module("diagnosis_empty_green_logic", "diagnosis_empty_green_logic.py")
_demand_pressure = _load_module("diagnosis_demand_pressure_logic", "diagnosis_demand_pressure_logic.py")

_as_float = _score._as_float
_as_list = _score._as_list
_first_number = _score._first_number
_collect_context_tokens = _score._collect_context_tokens
_diagnosis_inputs = _score._diagnosis_inputs


def _load_config_module():
    common_dir = Path(__file__).resolve().parents[2] / "common"
    spec = importlib.util.spec_from_file_location("intersection_load_config", common_dir / "load_config.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 intersection/common/load_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CFG = _load_config_module()
_classify = _load_module("classify_diagnosis_context", "classify_diagnosis_context.py")
CHECKLIST_SPEC: list[dict[str, Any]] = _CFG.load_diagnosis_checklist()
_THRESHOLD = _CFG.threshold

_ITEM_EVALUATORS: dict[str, Callable[..., dict[str, Any]]] = {}


def _register(item_id: str):
    def decorator(fn: Callable[..., dict[str, Any]]):
        _ITEM_EVALUATORS[item_id] = fn
        return fn

    return decorator


def _result(
    *,
    triggered: bool,
    summary: str,
    evidence: list[dict[str, Any]] | None = None,
    issue_codes: list[str] | None = None,
    has_data: bool = True,
) -> dict[str, Any]:
    if not has_data:
        status = "no_data"
    elif triggered:
        status = "triggered"
    else:
        status = "passed"
    return {
        "triggered": triggered,
        "status": status,
        "summary": summary,
        "evidence": evidence or [],
        "issue_codes": issue_codes or [],
    }


def _optional_number(*values: Any) -> float | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _format_optional_metric(value: float | None) -> str:
    return "缺少" if value is None else f"{value:.2f}"


def _enrich_evidence(
    item_id: str,
    evidence: list[dict[str, Any]],
    *,
    profile: dict[str, Any] | None = None,
    spec: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    profile_refs = (profile or {}).get("evidence_chain") or _CFG.build_profile_evidence_refs(profile or {})
    checklist_ref = (spec or {}).get("profile_checklist_ref")
    enriched: list[dict[str, Any]] = []
    for entry in evidence:
        row = dict(entry)
        row["checklist_item_id"] = item_id
        if checklist_ref:
            row["profile_checklist_ref"] = checklist_ref
        metric = row.get("metric")
        if metric:
            for ref in profile_refs:
                if ref.get("metric") == metric:
                    row["profile_evidence_ref"] = ref.get("ref_id")
                    break
        enriched.append(row)
    return enriched


@_register("phase_channel_mismatch")
def _check_phase_channel_mismatch(profile: dict[str, Any], static_scan: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    analysis = static_scan.get("phase_channel_analysis") or _dsl.analyze_phase_channel_match(profile, _THRESHOLD)
    hits = analysis.get("hits") or []
    if hits:
        rules = sorted({str(h.get("rule")) for h in hits if h.get("rule")})
        return _result(
            triggered=True,
            summary=f"相位渠化不匹配（规则 {','.join(rules)}）：{hits[0].get('message', '')}",
            evidence=[{"source": "phase_channel_analysis", "detail": hit} for hit in hits[:5]],
            issue_codes=["phase_channel_mismatch"],
        )
    flags = [f for f in static_scan.get("static_flags", []) if f.get("code") == "phase_channel_mismatch"]
    if flags:
        return _result(
            triggered=True,
            summary=flags[0].get("description", "专用车道与相位组织可能不匹配"),
            evidence=[{"source": "static_constraints", "detail": flags[0]}],
            issue_codes=["phase_channel_mismatch"],
        )
    channelization = _as_list((profile.get("supply_profile") or {}).get("channelization"))
    control = profile.get("control_profile") or {}
    if not channelization:
        return _result(triggered=False, summary="缺少渠化数据，无法判断相位匹配", has_data=False)
    if not _as_list(control.get("stage_detail")) and not _as_list(control.get("phase_sequence")):
        return _result(triggered=False, summary="缺少相位/阶段数据，无法精细判定", has_data=False)
    return _result(
        triggered=False,
        summary="未发现明确的相位相序与渠化不匹配",
        evidence=[{"source": "phase_channel_analysis_warning", "detail": warning} for warning in analysis.get("warnings", [])[:20]],
    )


@_register("lane_flow_mismatch")
def _check_lane_flow_mismatch(profile: dict[str, Any], static_scan: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    analysis = static_scan.get("lane_flow_analysis") or _dsl.analyze_lane_flow_match(profile, _THRESHOLD)
    hits = analysis.get("hits") or []
    inputs = _diagnosis_inputs(profile)
    state, demand, metrics = inputs["state"], inputs["demand"], inputs["metrics"]
    cv = _optional_number(state.get("lane_utilization_cv"), demand.get("lane_utilization_cv"), metrics.get("lane_utilization_cv"))
    mismatch = _optional_number(state.get("lane_mismatch_index"), demand.get("lane_mismatch_index"), metrics.get("lane_mismatch_index"))
    if mismatch is None:
        mismatch = _optional_number(analysis.get("lane_mismatch_index"))
    if hits:
        rules = sorted({str(h.get("rule")) for h in hits if h.get("rule")})
        first = hits[0]
        summary = f"渠化与流量不匹配（规则 {','.join(rules)}）：{first.get('message', '')}"
        evidence = [{"source": "lane_flow_analysis", "detail": hit} for hit in hits[:5]]
        if cv is not None:
            evidence.append({"metric": "lane_utilization_cv", "value": cv, "threshold": _THRESHOLD("static.lane_utilization_cv")})
        if mismatch is not None:
            evidence.append({"metric": "lane_mismatch_index", "value": mismatch, "threshold": _THRESHOLD("static.lane_mismatch_index")})
        return _result(triggered=True, summary=summary, evidence=evidence, issue_codes=["lane_mismatch"])
    data_gaps = analysis.get("data_gaps") or []
    if "lane_function_by_direction" in data_gaps:
        return _result(triggered=False, summary="缺少分进口车道功能配置，无法判断渠化与流量匹配", has_data=False)
    if not analysis.get("approach_details"):
        return _result(triggered=False, summary="缺少分进口转向流量或渠化数据", has_data=False)
    return _result(
        triggered=False,
        summary="未发现渠化与流量明显不匹配",
        evidence=[{"source": "lane_flow_analysis", "detail": detail} for detail in analysis.get("approach_details", [])[:5]],
    )


@_register("funnel_effect")
def _check_funnel_effect(profile: dict[str, Any], static_scan: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    analysis = static_scan.get("funnel_analysis") or _dsl.analyze_funnel_effect(profile, _THRESHOLD)
    hits = analysis.get("hits") or []
    if hits:
        rules = sorted({str(h.get("rule")) for h in hits if h.get("rule")})
        return _result(
            triggered=True,
            summary=f"存在漏斗效应（规则 {','.join(rules)}）：{hits[0].get('message', '')}",
            evidence=[{"source": "funnel_analysis", "detail": hit} for hit in hits[:5]],
            issue_codes=["lane_mismatch"],
        )
    flags = [f for f in static_scan.get("static_flags", []) if f.get("code") in {"funnel_effect", "entrance_exit_mismatch"}]
    if flags:
        return _result(
            triggered=True,
            summary=flags[0].get("description", "存在进出口车道不匹配"),
            evidence=[{"source": "static_constraints", "detail": flags[0]}],
            issue_codes=["lane_mismatch"],
        )
    channelization = _as_list((profile.get("supply_profile") or {}).get("channelization"))
    static_flags = _as_list((profile.get("supply_profile") or {}).get("static_flags"))
    if not channelization and not static_flags:
        return _result(triggered=False, summary="缺少进出口车道结构数据且无预扫描标记", has_data=False)
    return _result(triggered=False, summary="未发现漏斗效应")


@_register("adjacent_spacing")
def _check_adjacent_spacing(profile: dict[str, Any], static_scan: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    spacing = _as_float((profile.get("supply_profile") or {}).get("adjacent_inter_spacing_m"))
    if spacing <= 0:
        return _result(triggered=False, summary="缺少相邻路口间距", has_data=False)
    triggered = spacing < _THRESHOLD("static.adjacent_spacing_m") or any(f.get("code") == "short_spacing_chain" for f in static_scan.get("static_flags", []))
    return _result(
        triggered=triggered,
        summary=f"相邻间距约 {spacing:.0f}m" + ("，短间距串联约束强" if triggered else "，间距正常"),
        evidence=[{"metric": "adjacent_inter_spacing_m", "value": spacing, "threshold": _THRESHOLD("static.adjacent_spacing_m")}],
        issue_codes=["green_wave_break"] if triggered else [],
    )


@_register("road_segment_interference")
def _check_road_segment_interference(profile: dict[str, Any], static_scan: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    aoi_sources, source_path = _static.aoi_sources_from_profile(profile)
    if source_path is None:
        return _result(triggered=False, summary="缺少场景认知 1.3 周边交通发生源/吸引源数据", has_data=False)
    analysis = _static.infer_road_segment_interference(aoi_sources)
    codes = set(analysis.get("codes") or [])
    flags = [
        f
        for f in static_scan.get("static_flags", [])
        if f.get("code") in {"bus_stop", "driveway_interference", "strong_attractor", "driveway_too_close"}
    ]
    codes.update(str(flag.get("code")) for flag in flags if flag.get("code"))
    if not codes:
        return _result(
            triggered=False,
            summary=f"800m 范围内检索 {len(aoi_sources)} 个吸引源，未发现公交站点、出入口或强吸引点干扰",
            has_data=True,
            evidence=[{"metric": source_path, "value": len(aoi_sources), "threshold": 0}],
        )
    issue_codes = ["external_disturbance"]
    if codes.intersection({"driveway_interference", "driveway_too_close"}):
        issue_codes.append("downstream_blockage")
    hit_names = [str(hit.get("name") or hit.get("type") or hit.get("code")) for hit in analysis.get("hits", [])[:4]]
    summary = "路侧干扰：" + "、".join(hit_names or sorted(codes))
    return _result(
        triggered=True,
        summary=summary,
        evidence=[
            {"metric": source_path, "value": len(aoi_sources), "threshold": 0},
            *[{"source": "static_constraints", "detail": flag} for flag in flags],
            *[{"source": "aoi_sources", "detail": hit} for hit in analysis.get("hits", [])[:6]],
        ],
        issue_codes=issue_codes,
    )


@_register("demand_pressure_perception")
def _check_demand_pressure_perception(profile: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    analysis = _demand_pressure.analyze_demand_pressure(profile, _THRESHOLD)
    if not analysis.get("has_data"):
        return _result(triggered=False, summary="缺少路口饱和度时序（inter_evaluation）", has_data=False)
    sat_threshold = analysis["saturation_threshold"]
    duration_h_threshold = analysis["duration_h_threshold"]
    duration_h = analysis["duration_h"]
    triggered = bool(analysis.get("triggered"))
    evidence = [
        {
            "metric": "high_saturation_duration_h",
            "value": duration_h,
            "threshold": duration_h_threshold,
        },
        {
            "metric": "saturation",
            "value": sat_threshold,
            "threshold": sat_threshold,
            "source": analysis.get("source"),
        },
    ]
    window = analysis.get("summary_window")
    if window:
        evidence.append({"metric": "high_saturation_window", "value": window, "threshold": duration_h_threshold})
    summary = _demand_pressure.format_demand_pressure_summary(analysis)
    return _result(
        triggered=triggered,
        summary=summary + ("，需求压力偏高" if triggered else "，未达到需求压力阈值"),
        evidence=evidence,
        issue_codes=[] if triggered else [],
    )


@_register("attractor_demand_pressure")
def _check_attractor_demand_pressure(profile: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    inputs = _diagnosis_inputs(profile)
    metrics, tokens = inputs["metrics"], inputs["tokens"]
    context = profile.get("context") if isinstance(profile.get("context"), dict) else {}
    ratio = _first_number(
        metrics.get("attractor_arrival_capacity_ratio"),
        context.get("attractor_arrival_capacity_ratio"),
    )
    year = int(_first_number(metrics.get("attractor_year"), context.get("attractor_year"), default=1) or 1)
    threshold_key = "attractor.arrival_capacity_ratio_year3" if year >= 3 else "attractor.arrival_capacity_ratio_year2" if year == 2 else "attractor.arrival_capacity_ratio_year1"
    has_attractor = "strong_attractor" in tokens or "school" in tokens or "hospital" in tokens or bool(context.get("strong_attractor"))
    if ratio == 0 and not has_attractor:
        return _result(triggered=False, summary="缺少强吸引点或到达量/能力比证据", has_data=False)
    triggered = has_attractor and (ratio == 0 or ratio > _THRESHOLD(threshold_key))
    evidence = [{"metric": "context_tags", "value": sorted(tokens.intersection({"strong_attractor", "school", "hospital"})), "threshold": "strong_attractor"}]
    if ratio:
        evidence.append({"metric": "attractor_arrival_capacity_ratio", "value": ratio, "threshold": _THRESHOLD(threshold_key)})
    return _result(
        triggered=triggered,
        summary=f"强吸引点={'是' if has_attractor else '否'}，到达量/能力比={ratio:.2f}",
        evidence=evidence,
        issue_codes=["external_disturbance"] if triggered else [],
    )


@_register("slow_traffic_facilities")
def _check_slow_traffic_facilities(profile: dict[str, Any], static_scan: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    tokens = _collect_context_tokens(profile)
    slow_codes = {
        "no_bike_lane",
        "excessive_crosswalks",
        "bike_waiting_area_insufficient",
        "right_turn_lane_narrow",
        "special_poi_protection",
    }
    flags = [f for f in static_scan.get("static_flags", []) if f.get("code") in slow_codes]
    token_hits = sorted(tokens.intersection(slow_codes.union({"pedestrian_conflict", "bike_conflict"})))
    conflict_risk = _first_number((profile.get("traffic_state") or {}).get("conflict_risk"))
    if not flags and not token_hits and conflict_risk == 0:
        return _result(triggered=False, summary="未发现慢行设施不足或右转空间受限证据", has_data=True)
    triggered = bool(flags or token_hits) or conflict_risk >= _THRESHOLD("conflict.risk_high")
    issue_codes = ["pedestrian_protection_gap"]
    if conflict_risk >= _THRESHOLD("conflict.risk_high") or {"pedestrian_conflict", "bike_conflict"}.intersection(token_hits):
        issue_codes.append("phase_sequence_conflict")
    return _result(
        triggered=triggered,
        summary=f"慢行/右转设施风险={conflict_risk:.2f}" + (f"，标签 {', '.join(token_hits)}" if token_hits else ""),
        evidence=[
            {"metric": "conflict_risk", "value": conflict_risk, "threshold": _THRESHOLD("conflict.risk_high")},
            *[{"source": "static_constraints", "detail": flag} for flag in flags],
        ],
        issue_codes=issue_codes if triggered else [],
    )


@_register("spillback")
def _check_spillback(profile: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    inputs = _diagnosis_inputs(profile)
    state, supply, metrics = inputs["state"], inputs["supply"], inputs["metrics"]
    spillback = _first_number(state.get("spillback_risk"), metrics.get("spillback_risk"))
    queue_ratio = _first_number(state.get("queue_storage_ratio"), metrics.get("queue_storage_ratio"))
    queue_m = _first_number(state.get("queue_m"), metrics.get("queue_m"))
    storage_m = _first_number(supply.get("storage_m"), metrics.get("storage_m"))
    if queue_ratio == 0 and queue_m > 0 and storage_m > 0:
        queue_ratio = queue_m / storage_m
    if spillback == 0 and queue_ratio == 0:
        return _result(triggered=False, summary="缺少溢流/排队存储比指标", has_data=False)
    triggered = spillback >= _THRESHOLD("spillback.risk_high") or queue_ratio >= _THRESHOLD("queue.queue_storage_ratio_high")
    return _result(
        triggered=triggered,
        summary=f"溢流风险={spillback:.2f}，排队存储比={queue_ratio:.2f}" + ("，存在溢出锁死风险" if triggered else "，溢流风险可控"),
        evidence=[
            {"metric": "spillback_risk", "value": spillback, "threshold": _THRESHOLD("spillback.risk_high")},
            {"metric": "queue_storage_ratio", "value": queue_ratio, "threshold": _THRESHOLD("queue.queue_storage_ratio_high")},
        ],
        issue_codes=["spillback"] if triggered else [],
    )


@_register("downstream_blockage")
def _check_downstream_blockage(profile: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    inputs = _diagnosis_inputs(profile)
    state, tokens = inputs["state"], inputs["tokens"]
    spillback = _first_number(state.get("spillback_risk"))
    external = {"illegal_parking", "driveway_interference", "construction", "incident", "bus_stop"}
    hits = sorted(tokens.intersection(external))
    if spillback == 0 and not hits:
        return _result(triggered=False, summary="缺少溢流指标与外部干扰标签", has_data=False)
    triggered = (spillback >= _THRESHOLD("spillback.risk_high") and bool(hits)) or bool({"construction", "incident", "driveway_interference"}.intersection(tokens))
    summary = f"溢流风险={spillback:.2f}"
    if hits:
        summary += f"，外部标签 {', '.join(hits)}"
    return _result(
        triggered=triggered,
        summary=summary + ("，疑似下游阻塞/出口干扰" if triggered else "，未发现明显下游阻塞"),
        issue_codes=["downstream_blockage"] if triggered else [],
    )


@_register("service_imbalance")
def _check_service_imbalance(profile: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    analysis = _imbalance.evaluate_service_imbalance(profile, _THRESHOLD)
    if not analysis["has_data"]:
        return _result(triggered=False, summary=analysis["summary"], has_data=False)
    return _result(
        triggered=analysis["triggered"],
        summary=analysis["summary"],
        evidence=analysis["evidence"],
        issue_codes=["service_imbalance"] if analysis["triggered"] else [],
    )


@_register("empty_green")
def _check_empty_green(profile: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    analysis = _empty_green.evaluate_empty_green(profile, _THRESHOLD)
    if not analysis["has_data"]:
        return _result(triggered=False, summary=analysis["summary"], has_data=False)
    return _result(
        triggered=analysis["triggered"],
        summary=analysis["summary"],
        evidence=analysis["evidence"],
        issue_codes=["empty_green"] if analysis["triggered"] else [],
    )


@_register("cycle_timing")
def _check_cycle_timing(profile: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    inputs = _diagnosis_inputs(profile)
    cycle = _first_number(inputs["control"].get("current_cycle_s"), inputs["metrics"].get("current_cycle_s"))
    if cycle <= 0:
        return _result(triggered=False, summary="缺少当前周期数据", has_data=False)
    triggered = cycle >= _THRESHOLD("cycle.max_s") or cycle < _THRESHOLD("cycle.min_s")
    label = "过长" if cycle >= _THRESHOLD("cycle.max_s") else "过短" if cycle < _THRESHOLD("cycle.min_s") else "正常"
    return _result(
        triggered=triggered,
        summary=f"当前周期 {cycle:.0f}s，{label}",
        issue_codes=["cycle_timing_issue"] if triggered else [],
    )


@_register("plan_granularity")
def _check_plan_granularity(profile: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    inputs = _diagnosis_inputs(profile)
    control, state, metrics, tokens = inputs["control"], inputs["state"], inputs["metrics"], inputs["tokens"]
    plan_count = _first_number(control.get("time_plan_count"), metrics.get("time_plan_count"))
    period_var = _first_number(state.get("period_variation_index"), metrics.get("period_variation_index"))
    special_uncovered = bool(control.get("special_scene_uncovered") or "special_scene_uncovered" in tokens)
    if plan_count == 0 and period_var == 0 and not special_uncovered:
        return _result(triggered=False, summary="缺少时段方案/波动指标", has_data=False)
    triggered = (plan_count and plan_count <= _THRESHOLD("plan.min_time_plans")) or period_var >= _THRESHOLD("plan.period_variation_index") or special_uncovered
    return _result(
        triggered=triggered,
        summary=f"时段方案 {int(plan_count) if plan_count else '-'} 套" + ("，精细度不足" if triggered else "，覆盖尚可"),
        issue_codes=["plan_granularity"] if triggered else [],
    )


@_register("special_demand")
def _check_special_demand(profile: dict[str, Any], static_scan: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    tokens = _collect_context_tokens(profile)
    poi_tokens = {"school", "hospital", "port", "freight", "bus_priority", "emergency", "construction"}
    hits = sorted(tokens.intersection(poi_tokens))
    static_poi = any(f.get("code") == "special_poi_protection" for f in static_scan.get("static_flags", []))
    if not hits and not static_poi:
        return _result(triggered=False, summary="未发现学校/医院/公交/施工等特殊需求标签", has_data=True)
    triggered = bool(hits) or static_poi
    return _result(
        triggered=triggered,
        summary="特殊需求：" + (", ".join(hits) if hits else "学校/医院 POI"),
        issue_codes=["pedestrian_protection_gap", "external_disturbance"] if triggered else [],
    )


@_register("public_complaint")
def _check_public_complaint(profile: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    context = profile.get("context") if isinstance(profile.get("context"), dict) else {}
    complaints = _as_list(context.get("complaints"))
    surveys = _as_list(context.get("field_survey"))
    tokens = _collect_context_tokens(profile)
    if not complaints and not surveys and "complaint" not in tokens:
        return _result(triggered=False, summary="无投诉或调研记录", has_data=True)
    triggered = bool(complaints or surveys or "complaint" in tokens)
    return _result(
        triggered=triggered,
        summary=f"投诉 {len(complaints)} 条，调研 {len(surveys)} 条",
        issue_codes=["public_complaint"] if triggered else [],
    )


@_register("cause_scores")
def _check_cause_scores(profile: dict[str, Any], diagnosis: dict[str, Any] | None = None, **_kwargs: Any) -> dict[str, Any]:
    scores = (diagnosis or {}).get("cause_scores") or {}
    if not scores:
        return _result(triggered=False, summary="成因评分尚未计算", has_data=False)
    top = max(scores.items(), key=lambda item: item[1])
    summary = "；".join(f"{k}={v:.0%}" for k, v in sorted(scores.items(), key=lambda x: -x[1]))
    return _result(
        triggered=top[1] >= 0.25,
        summary=f"主因 {top[0]}（{top[1]:.0%}）· {summary}",
        evidence=[{"cause_scores": scores}],
        issue_codes=[],
        has_data=True,
    )


def _evaluate_item(
    spec: dict[str, Any],
    profile: dict[str, Any],
    static_scan: dict[str, Any],
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evaluator = _ITEM_EVALUATORS.get(spec["item_id"])
    if evaluator is None:
        return _result(triggered=False, summary="未实现检查项", has_data=False)
    try:
        outcome = evaluator(profile=profile, static_scan=static_scan, diagnosis=diagnosis)
    except Exception as exc:
        return {
            "triggered": False,
            "status": "error",
            "summary": str(exc),
            "evidence": [],
            "issue_codes": [],
            "error": str(exc),
        }
    if outcome.get("evidence") is not None:
        outcome["evidence"] = _enrich_evidence(
            spec["item_id"],
            outcome.get("evidence") or [],
            profile=profile,
            spec=spec,
        )
    return outcome


def _checklist_item_from_spec(
    spec: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    return {
        "item_id": spec["item_id"],
        "category": spec["category"],
        "label": spec["label"],
        "profile_field": spec.get("profile_field", ""),
        "issue_codes": outcome.get("issue_codes") or spec.get("issue_codes") or [],
        "status": outcome.get("status", "passed"),
        "triggered": bool(outcome.get("triggered")),
        "summary": outcome.get("summary", ""),
        "evidence": outcome.get("evidence") or [],
        "error": outcome.get("error"),
    }


def get_diagnosis_checklist_spec() -> list[dict[str, Any]]:
    """Return checklist manifest for frontend progress UI."""
    return [
        {
            "item_id": spec["item_id"],
            "category": spec["category"],
            "label": spec["label"],
        }
        for spec in CHECKLIST_SPEC
    ]


def run_diagnosis_checklist(profile: dict[str, Any]) -> dict[str, Any]:
    """Run all checklist items and assemble full diagnosis output."""
    result: dict[str, Any] | None = None
    for event in iter_diagnosis_checklist(profile):
        if event["type"] == "complete":
            result = event
    if result is None:
        return {"ok": False, "checklist_queries": [], "errors": ["诊断检查单未完成"]}
    return result


def iter_diagnosis_checklist(profile: dict[str, Any]):
    """Yield checklist item progress events, then final diagnosis payload."""
    if not profile:
        yield {"type": "error", "message": "缺少场景画像 profile"}
        return

    static_scan = _static.check_static_constraints(profile)
    profile_with_static = {**profile, "static_constraints": static_scan}
    checklist_queries: list[dict[str, Any]] = []
    total = len(CHECKLIST_SPEC)
    diagnosis: dict[str, Any] | None = None

    for index, spec in enumerate(CHECKLIST_SPEC[:-1], start=1):
        if spec["item_id"] == "cause_scores":
            continue
        outcome = _evaluate_item(spec, profile_with_static, static_scan)
        item = _checklist_item_from_spec(spec, outcome)
        checklist_queries.append(item)
        yield {
            "type": "checklist_item",
            "index": index,
            "total": total,
            "item": item,
        }

    diagnosis = _score.diagnose_signal_issues(profile_with_static)
    validation_errors = []
    try:
        validate_module = _load_module("validate_diagnosis_output", "validate_diagnosis_output.py")
        validation_errors = validate_module.validate_diagnosis_output(diagnosis)
    except Exception:
        pass
    diagnosis["validation_errors"] = validation_errors

    context = _classify.classify_diagnosis_context(profile_with_static, diagnosis, checklist_queries)
    diagnosis["problem_source"] = context["problem_source"]
    diagnosis["control_improvement_ceiling"] = context["control_improvement_ceiling"]
    diagnosis["scene_type"] = context["scene_type"]
    diagnosis["scene_type_context"] = context["scene_type_context"]
    diagnosis["issues"] = context["issues"]
    diagnosis["priority_order"] = context["priority_order"]
    diagnosis["evidence_chain"] = _CFG.build_profile_evidence_refs(profile_with_static)

    summary_spec = CHECKLIST_SPEC[-1]
    summary_outcome = _evaluate_item(summary_spec, profile_with_static, static_scan, diagnosis=diagnosis)
    summary_item = _checklist_item_from_spec(summary_spec, summary_outcome)
    checklist_queries.append(summary_item)
    yield {
        "type": "checklist_item",
        "index": total,
        "total": total,
        "item": summary_item,
    }

    yield {
        "type": "complete",
        "ok": True,
        "static_constraints": static_scan,
        "diagnosis": diagnosis,
        "checklist_queries": checklist_queries,
    }
