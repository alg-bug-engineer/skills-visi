from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def _load_config_module():
    common_dir = Path(__file__).resolve().parents[2] / "common"
    spec = importlib.util.spec_from_file_location("intersection_load_config", common_dir / "load_config.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 intersection/common/load_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CFG = _load_config_module()
_TH = _CFG.threshold
_CAUSE_MAP = _CFG.load_cause_dimension_map()
_CAUSE_DIMENSIONS = _CFG.load_diagnosis_cause_dimensions()


def _load_imbalance_module():
    spec = importlib.util.spec_from_file_location(
        "diagnosis_imbalance_logic",
        Path(__file__).resolve().parent / "diagnosis_imbalance_logic.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 diagnosis_imbalance_logic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_empty_green_module():
    spec = importlib.util.spec_from_file_location(
        "diagnosis_empty_green_logic",
        Path(__file__).resolve().parent / "diagnosis_empty_green_logic.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 diagnosis_empty_green_logic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_IMBALANCE = _load_imbalance_module()
_EMPTY_GREEN = _load_empty_green_module()


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


def _first_number(*values: Any, default: float = 0.0) -> float:
    for value in values:
        if value is not None:
            return _as_float(value, default)
    return default


def _metric(
    name: str,
    value: Any,
    threshold: Any,
    source: str,
    scope: str = "intersection",
) -> dict[str, Any]:
    return {
        "metric": name,
        "value": value,
        "threshold": threshold,
        "source": source,
        "scope": scope,
    }


def _severity(score: float) -> str:
    if score >= _TH("pressure.severity_high"):
        return "high"
    if score >= _TH("pressure.severity_medium"):
        return "medium"
    return "low"


def _confidence(evidence_count: int, quality_penalty: float = 0.0) -> float:
    base = 0.55 + min(0.35, evidence_count * 0.12)
    return round(max(0.2, min(0.95, base - quality_penalty)), 2)


def _issue(
    code: str,
    name: str,
    score: float,
    evidence: list[dict[str, Any]],
    root_cause: str,
    control_leverage: str,
    non_signal_suggestion: str = "",
    confidence_penalty: float = 0.0,
    issue_detail: list[str] | None = None,
) -> dict[str, Any]:
    score = round(max(0.0, min(1.0, score)), 3)
    payload = {
        "issue_code": code,
        "code": code,
        "name": name,
        "severity": _severity(score),
        "score": score,
        "confidence": _confidence(len(evidence), confidence_penalty),
        "evidence": evidence,
        "root_cause": root_cause,
        "control_leverage": control_leverage,
        "non_signal_suggestion": non_signal_suggestion,
    }
    if issue_detail:
        payload["issue_detail"] = issue_detail
    return payload


def _collect_context_tokens(profile: dict[str, Any]) -> set[str]:
    context = profile.get("context_tags", []) or profile.get("context", {}) or {}
    tokens: set[str] = set()
    if isinstance(context, dict):
        for key, value in context.items():
            if isinstance(value, bool) and value:
                tokens.add(str(key))
            elif isinstance(value, str):
                tokens.add(value)
            elif isinstance(value, list):
                tokens.update(str(item) for item in value)
    else:
        tokens.update(str(item) for item in _as_list(context))
    for item in _as_list(profile.get("quality_tags")):
        if isinstance(item, dict):
            tokens.add(str(item.get("name", "")))
        else:
            tokens.add(str(item))
    return {token for token in tokens if token}


def _diagnosis_inputs(profile: dict[str, Any]) -> dict[str, Any]:
    state = profile.get("traffic_state", {}) or {}
    demand = profile.get("demand_profile", {}) or {}
    supply = profile.get("supply_profile", {}) or {}
    control = profile.get("control_profile", {}) or profile.get("signal", {}) or {}
    metrics = profile.get("metrics_summary", {}) or profile.get("metrics", {}) or {}
    return {
        "state": state,
        "demand": demand,
        "supply": supply,
        "control": control,
        "metrics": metrics,
        "tokens": _collect_context_tokens(profile),
    }


def score_intersection_issues(metrics: dict) -> dict[str, float]:
    return {
        "spillback": float(metrics.get("spillback_risk", 0)),
    }


def diagnose_signal_issues(profile: dict[str, Any]) -> dict[str, Any]:
    inputs = _diagnosis_inputs(profile)
    state = inputs["state"]
    demand = inputs["demand"]
    supply = inputs["supply"]
    control = inputs["control"]
    metrics = inputs["metrics"]
    tokens = inputs["tokens"]
    issues: list[dict[str, Any]] = []

    static_scan = _load_static_scan(profile)
    for flag in static_scan.get("static_flags", []):
        code = str(flag.get("code", ""))
        if code == "phase_channel_mismatch":
            issues.append(
                _issue(
                    "phase_channel_mismatch",
                    "相位相序与渠化不匹配",
                    0.78,
                    [_metric("static_flag", code, "none", "static_constraints")],
                    flag.get("description", "专用车道与相位组织不匹配。"),
                    "low",
                    "建议复核导向车道、待行区与相位保护关系，必要时提出渠化调整。",
                )
            )
        elif code in {"funnel_effect", "entrance_exit_mismatch", "road_section_mismatch"}:
            issues.append(
                _issue(
                    "lane_mismatch",
                    "进口出口或道路断面不匹配",
                    0.72,
                    [_metric("static_flag", code, "none", "static_constraints")],
                    flag.get("description", "进口道、出口道或道路断面不匹配，形成结构性瓶颈。"),
                    "low",
                    "建议评估出口道扩容、导向调整或交通组织优化。",
                )
            )
        elif code == "short_spacing_chain":
            issues.append(
                _issue(
                    "green_wave_break",
                    "短间距串联路口联动约束",
                    0.62,
                    [_metric("adjacent_inter_spacing_m", supply.get("adjacent_inter_spacing_m"), _TH("static.adjacent_spacing_m"), "supply_profile")],
                    "相邻信控路口间距过短，单点优化易引发上下游排队传导。",
                    "medium",
                    "建议按走廊协调或量出为入策略处理。",
                )
            )
        elif code == "special_poi_protection":
            issues.append(
                _issue(
                    "pedestrian_protection_gap",
                    "学校/医院等特殊吸引点慢行保护不足",
                    0.55,
                    [_metric("context_tags", sorted(tokens), "poi", "context_tags")],
                    "强吸引点存在过街、临停和集散需求，需额外慢行保护。",
                    "medium",
                    "建议增加行人专用相位、二次过街或右转控转策略。",
                )
            )
        elif code in {
            "bus_stop",
            "driveway_interference",
            "strong_attractor",
            "driveway_too_close",
        }:
            issue_code = "downstream_blockage" if code in {"driveway_interference", "driveway_too_close"} else "external_disturbance"
            issues.append(
                _issue(
                    issue_code,
                    "路段侧静态干扰影响路口运行",
                    0.64,
                    [_metric("static_flag", code, "none", "static_constraints")],
                    flag.get("description", "公交站点、出入口或强吸引点靠近路口，造成到离场扰动。"),
                    "low",
                    "建议同步核查公交停靠、出入口管控、临停秩序和强吸引点集散组织。",
                )
            )
        elif code in {"approach_capacity_deficit", "movement_capacity_deficit", "lane_group_capacity_unbalance", "tidal_detour_pressure", "outlet_capacity_mismatch"}:
            issue_code = "downstream_blockage" if code == "outlet_capacity_mismatch" else "lane_mismatch"
            issues.append(
                _issue(
                    issue_code,
                    "进口、转向或出口通行能力不匹配",
                    0.7 if code in {"movement_capacity_deficit", "outlet_capacity_mismatch"} else 0.62,
                    [_metric("static_flag", code, "none", "static_constraints")],
                    flag.get("description", "进口、转向或出口能力与需求不匹配，形成结构性瓶颈。"),
                    "low",
                    "建议评估进口车道数量、车道功能、可变车道、潮汐车道或出口道扩容。",
                )
            )
        elif code in {"no_bike_lane", "excessive_crosswalks", "bike_waiting_area_insufficient", "right_turn_lane_narrow"}:
            issues.append(
                _issue(
                    "pedestrian_protection_gap",
                    "慢行设施或右转空间不足",
                    0.58,
                    [_metric("static_flag", code, "none", "static_constraints")],
                    flag.get("description", "非机动车、行人过街或右转空间不足，慢行冲突风险升高。"),
                    "medium",
                    "建议结合行人非机动车流量、右转冲突点和清空时间复核保护策略。",
                )
            )

    lane_flow_analysis = static_scan.get("lane_flow_analysis") or {}
    lane_flow_hits = lane_flow_analysis.get("hits") or []
    if lane_flow_hits:
        first_hit = lane_flow_hits[0]
        mismatch_index = _first_number(lane_flow_analysis.get("lane_mismatch_index"))
        issues.append(
            _issue(
                "lane_mismatch",
                "渠化设计与车流量不匹配",
                max(mismatch_index, 0.62),
                [
                    _metric("lane_flow_rule", first_hit.get("rule"), "none", "lane_flow_analysis"),
                    *(
                        [_metric("lane_mismatch_index", round(mismatch_index, 3), _TH("static.lane_mismatch_index"), "lane_flow_analysis")]
                        if mismatch_index
                        else []
                    ),
                ],
                first_hit.get("message", "分进口车道功能与转向流量结构不匹配。"),
                "low",
                "建议评估导向车道、待行区、可变车道或进口道秩序治理。",
            )
        )

    spillback_risk = _first_number(state.get("spillback_risk"), metrics.get("spillback_risk"))
    queue_storage_ratio = _first_number(state.get("queue_storage_ratio"), metrics.get("queue_storage_ratio"))
    queue_m = _first_number(state.get("queue_m"), metrics.get("queue_m"))
    storage_m = _first_number(supply.get("storage_m"), metrics.get("storage_m"))
    if queue_storage_ratio == 0 and queue_m > 0 and storage_m > 0:
        queue_storage_ratio = queue_m / storage_m
    if spillback_risk >= _TH("spillback.risk_high") or queue_storage_ratio >= _TH("queue.queue_storage_ratio_high"):
        score = max(spillback_risk, min(1.0, queue_storage_ratio), 0.75)
        issues.append(
            _issue(
                "spillback",
                "排队溢出或锁死风险",
                score,
                [
                    _metric("spillback_risk", round(spillback_risk, 3), _TH("spillback.risk_high"), "traffic_state"),
                    *(
                        [_metric("queue_storage_ratio", round(queue_storage_ratio, 3), _TH("queue.queue_storage_ratio_high"), "traffic_state")]
                        if queue_storage_ratio
                        else []
                    ),
                ],
                "关键进口或下游出口清空能力不足，排队存在向上游或路口内部扩散风险。",
                "high",
                "同步排查下游阻塞、出入口干扰和路口内违法滞留。",
            )
        )

    imbalance_analysis = _IMBALANCE.evaluate_service_imbalance(profile, _TH)
    if imbalance_analysis["triggered"]:
        evidence = [
            _metric(
                "imbalance_index",
                imbalance_analysis["imbalance_index_peak"],
                _TH("imbalance.diagnosis"),
                "traffic_state",
            ),
        ]
        if imbalance_analysis["movement_saturation_gap_peak"]:
            evidence.append(
                _metric(
                    "movement_saturation_gap",
                    imbalance_analysis["movement_saturation_gap_peak"],
                    _TH("imbalance.movement_saturation_gap"),
                    "traffic_state",
                )
            )
        for window in imbalance_analysis["trigger_windows"][:4]:
            evidence.append(
                {
                    "metric": window["metric"],
                    "value": window["average"],
                    "threshold": window["threshold"],
                    "source": "traffic_state",
                    "scope": "intersection",
                    "time_window": f"{window['start']}-{window['end']}",
                    "duration_min": window["duration_min"],
                }
            )
        issues.append(
            _issue(
                "service_imbalance",
                "进口、流向或相位服务失衡",
                max(imbalance_analysis["score"], 0.55),
                evidence,
                imbalance_analysis["root_cause"],
                "high",
                issue_detail=imbalance_analysis.get("detail_lines") or [],
            )
        )

    empty_green_analysis = _EMPTY_GREEN.evaluate_empty_green(profile, _TH)
    if empty_green_analysis["triggered"]:
        evidence = []
        for window in empty_green_analysis["trigger_windows"][:6]:
            evidence.append(
                {
                    "metric": window["metric"],
                    "value": window["average"],
                    "threshold": window["threshold"],
                    "source": "traffic_state",
                    "scope": window.get("movement", "intersection"),
                    "time_window": f"{window['start']}-{window['end']}",
                    "duration_min": window["duration_min"],
                    "movement": window["movement_label"],
                }
            )
        issues.append(
            _issue(
                "empty_green",
                "绿灯损失或空放",
                max(empty_green_analysis["score"], 0.5),
                evidence,
                empty_green_analysis["root_cause"],
                "high",
                issue_detail=empty_green_analysis.get("detail_lines") or [],
            )
        )

    lane_utilization_cv = _first_number(
        state.get("lane_utilization_cv"),
        demand.get("lane_utilization_cv"),
        metrics.get("lane_utilization_cv"),
    )
    lane_mismatch_index = _first_number(
        state.get("lane_mismatch_index"),
        demand.get("lane_mismatch_index"),
        metrics.get("lane_mismatch_index"),
    )
    if lane_utilization_cv >= _TH("static.lane_utilization_cv") or lane_mismatch_index >= _TH("static.lane_mismatch_index"):
        issues.append(
            _issue(
                "lane_mismatch",
                "车道利用率低或渠化不匹配",
                max(lane_utilization_cv, lane_mismatch_index, 0.5),
                [
                    _metric("lane_utilization_cv", round(lane_utilization_cv, 3), _TH("static.lane_utilization_cv"), "demand_profile"),
                    *(
                        [_metric("lane_mismatch_index", round(lane_mismatch_index, 3), _TH("static.lane_mismatch_index"), "demand_profile")]
                        if lane_mismatch_index
                        else []
                    ),
                ],
                "车道功能、导向设置或进口渠化与流量结构不匹配。",
                "low",
                "建议评估导向车道、待行区、可变车道或进口道秩序治理。",
            )
        )

    manual_intervention_count = _first_number(
        control.get("manual_intervention_count"),
        metrics.get("manual_intervention_count"),
    )
    if manual_intervention_count >= 3 or "manual_intervention" in tokens:
        issues.append(
            _issue(
                "manual_intervention",
                "人工干预频繁",
                min(1.0, 0.45 + manual_intervention_count / 10),
                [_metric("manual_intervention_count", manual_intervention_count, 3, "control_profile")],
                "自动控制策略对异常需求或现场扰动适应不足。",
                "medium",
                "需复盘人工接管原因，补充规则触发条件和人工审核边界。",
            )
        )

    plan_count = _first_number(control.get("time_plan_count"), metrics.get("time_plan_count"))
    period_variation = _first_number(state.get("period_variation_index"), metrics.get("period_variation_index"))
    special_scene_uncovered = bool(control.get("special_scene_uncovered") or "special_scene_uncovered" in tokens)
    if (plan_count and plan_count <= _TH("plan.min_time_plans")) or period_variation >= _TH("plan.period_variation_index") or special_scene_uncovered:
        issues.append(
            _issue(
                "plan_granularity",
                "配时方案精细度不足",
                max(0.5 if plan_count and plan_count <= _TH("plan.min_time_plans") else 0, period_variation, 0.55 if special_scene_uncovered else 0),
                [
                    *([_metric("time_plan_count", plan_count, _TH("plan.min_time_plans"), "control_profile")] if plan_count else []),
                    *(
                        [_metric("period_variation_index", round(period_variation, 3), _TH("plan.period_variation_index"), "traffic_state")]
                        if period_variation
                        else []
                    ),
                    *(
                        [_metric("special_scene_uncovered", True, False, "control_profile")]
                        if special_scene_uncovered
                        else []
                    ),
                ],
                "现有时段划分或特殊场景方案不能覆盖需求波动。",
                "medium",
            )
        )

    green_wave = _first_number(state.get("green_wave_pass_rate"), metrics.get("green_wave_pass_rate"), default=1.0)
    offset_deviation = _first_number(state.get("offset_deviation_s"), metrics.get("offset_deviation_s"))
    if green_wave < _TH("green_wave_pass_rate") or offset_deviation >= _TH("offset_deviation_s"):
        issues.append(
            _issue(
                "green_wave_break",
                "上下游协调或绿波断裂",
                max(1 - green_wave, min(1.0, offset_deviation / 30), 0.5),
                [
                    _metric("green_wave_pass_rate", round(green_wave, 3), _TH("green_wave_pass_rate"), "traffic_state"),
                    *([_metric("offset_deviation_s", offset_deviation, _TH("offset_deviation_s"), "traffic_state")] if offset_deviation else []),
                ],
                "相邻路口公共周期、相位差或协调方向与实际到达不匹配。",
                "medium",
            )
        )

    external_tokens = {
        "illegal_parking",
        "temporary_parking",
        "on_street_parking",
        "driveway_interference",
        "bus_stop",
        "bus_priority",
        "strong_attractor",
        "construction",
        "incident",
    }
    if tokens.intersection(external_tokens):
        issues.append(
            _issue(
                "external_disturbance",
                "外部干扰主导",
                0.62,
                [_metric("context_tags", sorted(tokens.intersection(external_tokens)), "none", "context_tags")],
                "违停、公交停靠、出入口、施工或事故等非信控因素扰动通行。",
                "low",
                "建议同步开展秩序治理、施工协调、公交停靠或出入口管理。",
            )
        )

    complaints = _as_list((profile.get("context") or {}).get("complaints")) if isinstance(profile.get("context"), dict) else []
    special_requests = _as_list((profile.get("context") or {}).get("special_requests")) if isinstance(profile.get("context"), dict) else []
    if complaints or special_requests or {"complaint", "special_request"}.intersection(tokens):
        issues.append(
            _issue(
                "public_complaint",
                "投诉或专项保障诉求",
                0.5,
                [
                    _metric("complaints", len(complaints), 0, "context"),
                    _metric("special_requests", len(special_requests), 0, "context"),
                ],
                "公众体验或专项保障目标需要纳入控制目标权衡。",
                "medium",
                "专项保障和舆情类策略需人工审核确认。",
            )
        )

    cycle_s = _first_number(control.get("current_cycle_s"), metrics.get("current_cycle_s"))
    if cycle_s >= _TH("cycle.max_s"):
        issues.append(
            _issue(
                "cycle_timing_issue",
                "周期过长",
                min(1.0, cycle_s / 200),
                [_metric("current_cycle_s", cycle_s, _TH("cycle.max_s"), "control_profile")],
                "周期偏长可能导致支路和非协调方向排队累积。",
                "medium",
            )
        )
    elif 0 < cycle_s < _TH("cycle.min_s"):
        issues.append(
            _issue(
                "cycle_timing_issue",
                "周期过短",
                min(1.0, (_TH("cycle.min_s") - cycle_s) / 30),
                [_metric("current_cycle_s", cycle_s, _TH("cycle.min_s"), "control_profile")],
                "周期偏短可能导致关键相位绿时不足和清空失败。",
                "medium",
            )
        )

    if spillback_risk >= _TH("spillback.risk_high") and {"construction", "incident", "driveway_interference"}.intersection(tokens):
        issues.append(
            _issue(
                "downstream_blockage",
                "下游阻塞或出口干扰",
                max(spillback_risk, 0.7),
                [
                    _metric("spillback_risk", round(spillback_risk, 3), _TH("spillback.risk_high"), "traffic_state"),
                    _metric("context_tags", sorted(tokens.intersection({"construction", "incident", "driveway_interference"})), "none", "context_tags"),
                ],
                "出口道或下游路段受阻导致排队回溢。",
                "medium",
                "优先排查出口停车、施工占道和相邻路口锁死。",
            )
        )

    uncertainty: list[str] = []
    if not any(key in state or key in metrics for key in ("queue_m", "spillback_risk")):
        uncertainty.append("缺少排队或溢流指标，诊断置信度受限。")

    if not issues:
        issues.append(
            _issue(
                "stable",
                "运行基本稳定",
                0.2,
                [_metric("triggered_issue_count", 0, 0, "diagnosis")],
                "未发现达到阈值的显著信控问题。",
                "low",
            )
        )

    issues = sorted(issues, key=lambda item: item["score"], reverse=True)
    priority_order = [item["issue_code"] for item in issues]
    root_causes = [item["root_cause"] for item in issues if item["issue_code"] != "stable"]
    signal_scores = {"high": 3, "medium": 2, "low": 1, "none": 0}
    ceiling_score = max((signal_scores.get(item["control_leverage"], 0) for item in issues), default=0)
    ceiling = {3: "high", 2: "medium", 1: "low", 0: "none"}[ceiling_score]
    non_signal_dominant = any(item["control_leverage"] in {"low", "none"} for item in issues if item["issue_code"] != "stable")
    problem_source = "traffic_order_or_static_constraint" if non_signal_dominant else "control_parameter_mismatch"
    if any(item["issue_code"] == "external_disturbance" for item in issues):
        problem_source = "external_disturbance"
    if any(item["issue_code"] == "stable" for item in issues):
        problem_source = "stable_operation"

    cause_scores = _compute_cause_scores(issues, profile, static_scan)

    return {
        "issues": issues,
        "priority_order": priority_order,
        "root_causes": root_causes,
        "problem_source": problem_source,
        "control_improvement_ceiling": ceiling,
        "cause_scores": cause_scores,
        "static_constraints": static_scan,
        "uncertainty": uncertainty,
        "validation_errors": [],
    }


def _load_static_scan(profile: dict[str, Any]) -> dict[str, Any]:
    cached = profile.get("static_constraints")
    if isinstance(cached, dict) and cached.get("static_flags") is not None:
        return cached
    try:
        from pathlib import Path
        import importlib.util

        script = Path(__file__).resolve().parent / "check_static_constraints.py"
        spec = importlib.util.spec_from_file_location("check_static_constraints", script)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.check_static_constraints(profile)
    except Exception:
        pass
    return {"static_flags": [], "static_issue_codes": [], "has_structural_constraint": False}


def _compute_cause_scores(
    issues: list[dict[str, Any]],
    profile: dict[str, Any],
    static_scan: dict[str, Any],
) -> dict[str, float]:
    """Quantify main-cause contribution per checklist: supply/demand/control/order/event/data."""
    buckets = {
        "supply": 0.0,
        "demand": 0.0,
        "control": 0.0,
        "order": 0.0,
        "event": 0.0,
        "data_quality": 0.0,
    }
    for issue in issues:
        if issue.get("issue_code") == "stable":
            continue
        score = _as_float(issue.get("score"))
        dimensions = _CAUSE_DIMENSIONS.get(str(issue.get("issue_code"))) or {}
        if dimensions:
            for bucket, weight in dimensions.items():
                if bucket in buckets:
                    buckets[bucket] += score * _as_float(weight)
            continue
        bucket = _CAUSE_MAP.get(str(issue.get("issue_code")), "control")
        buckets[bucket] += score

    quality_tags = profile.get("quality_tags") or []
    if quality_tags:
        buckets["data_quality"] += min(1.0, len(quality_tags) * 0.15)

    if static_scan.get("has_structural_constraint"):
        buckets["supply"] += 0.25

    total = sum(buckets.values()) or 1.0
    return {key: round(value / total, 3) for key, value in buckets.items()}
