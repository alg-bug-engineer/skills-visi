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


def _load_metrics_logic_module():
    scripts_dir = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "intersection_traffic_metrics_logic",
        scripts_dir / "traffic_metrics_logic.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 scene-cognition/scripts/traffic_metrics_logic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CFG = _load_config_module()
_TH = _CFG.threshold
_TML = _load_metrics_logic_module()

DEFAULT_PERIOD_WINDOWS = {
    "早高峰": ("07:00", "09:00"),
    "白平峰": ("10:00", "16:00"),
    "晚高峰": ("17:00", "19:00"),
}
PERIOD_ROW_ORDER = ("早高峰", "晚高峰", "白平峰")

DIRECTION_ORDER = {"东进口": 0, "南进口": 1, "西进口": 2, "北进口": 3}
TURN_ORDER = {"左转": 0, "直行": 1, "右转": 2, "掉头": 3}
DIR8_APPROACH_LABELS = {
    0: "北",
    1: "东北",
    2: "东",
    3: "东南",
    4: "南",
    5: "西南",
    6: "西",
    7: "西北",
}
FLOW_TRACE_TURN_LABELS = {1: "左转", 2: "直行", 3: "右转", 4: "掉头"}
PERIOD_TYPE_LABELS = {
    "MORNING_PEAK": "早高峰",
    "EVENING_PEAK": "晚高峰",
    "OFF_PEAK": "白平峰",
}

CN_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "important_transfer_node": "重要转换节点",
    "important_transfer": "重要转换节点",
    "transfer_node": "转换节点",
    "arterial_node": "主干路衔接节点",
    "funnel_effect": "进出口承接不匹配",
    "more_entrances_than_exits": "进口方向多于出口方向",
    "school": "学校影响",
    "hospital": "医院影响",
    "commercial": "商圈影响",
    "transit": "公交/轨道接驳影响",
    "port": "物流货运影响",
    "parking": "停车场影响",
    "checkpoint": "查验口/收费站影响",
    "emergency": "应急事件影响",
    "construction": "施工影响",
}


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


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value not in (None, {}, [])}


def _keep_schema(data: dict[str, Any]) -> dict[str, Any]:
    """Keep required report keys even when the value is empty."""
    return {key: value for key, value in data.items() if value is not None}


def _cn_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return CN_LABELS.get(text, text)


def _pressure_label(value: Any) -> str:
    label = _cn_label(value)
    return label if label in {"高", "中", "低"} else label


def _road_function_label(value: Any) -> str:
    text = _cn_label(value)
    return text or "一般交通节点"


def _poi_labels(values: Any) -> list[str]:
    return [_cn_label(item) for item in _as_list(values) if _cn_label(item)]


def _movement_sort_key(row: dict[str, Any]) -> tuple[int, str, int, str]:
    direction = str(row.get("进口道") or row.get("进口方向") or "")
    turn = str(row.get("转向") or "")
    return (DIRECTION_ORDER.get(direction, 99), direction, TURN_ORDER.get(turn, 99), turn)


def _period_sort_key(value: Any) -> int:
    text = str(value or "")
    return {name: index for index, name in enumerate(PERIOD_ROW_ORDER)}.get(text, 99)


def _tag(name: str, value: Any, confidence: float = 1.0, source: str = "scene_cognition") -> dict[str, Any]:
    return {"name": name, "value": value, "confidence": confidence, "source": source}


def _evidence(
    metric: str,
    value: Any,
    source: str,
    *,
    checklist_item_id: str | None = None,
    scope: str = "intersection",
) -> dict[str, Any]:
    fact_id = f"profile.{checklist_item_id}.{metric}" if checklist_item_id else f"profile.{metric}"
    return {
        "metric": metric,
        "value": value,
        "source": source,
        "scope": scope,
        "checklist_item_id": checklist_item_id,
        "fact_id": fact_id,
    }


def calculate_saturation(volume: float, capacity: float) -> float:
    return _TML.calculate_saturation(volume, capacity)


def _severity(score: float) -> str:
    if score >= _TH("pressure.severity_high"):
        return "high"
    if score >= _TH("pressure.severity_medium"):
        return "medium"
    return "low"


def _scene_type(level: str, context: dict[str, Any]) -> str:
    profile_stub = {"scope": {"level": level}, "context": context, "context_tags": _context_tags(context)}
    return _CFG.resolve_scene_type(profile_stub)


def _context_tags(context: dict[str, Any]) -> list[str]:
    tags: set[str] = set()
    for key in ("time_period", "weather"):
        if context.get(key):
            tags.add(str(context[key]))
    for key in ("poi", "events", "complaints", "special_requests"):
        for item in _as_list(context.get(key)):
            tags.add(str(item))
    if context.get("emergency"):
        tags.add("emergency")
    if context.get("construction"):
        tags.add("construction")
    if context.get("school"):
        tags.add("school")
    if context.get("hospital"):
        tags.add("hospital")
    return sorted(tag for tag in tags if tag)


def _movement_saturation(metrics: dict[str, Any]) -> dict[str, float]:
    volumes = metrics.get("movement_volume") or {}
    capacities = metrics.get("movement_capacity") or metrics.get("capacity_by_movement") or {}
    if not isinstance(volumes, dict) or not isinstance(capacities, dict):
        return {}
    result: dict[str, float] = {}
    for movement, volume in volumes.items():
        capacity = _as_float(capacities.get(movement))
        if capacity > 0:
            result[str(movement)] = min(1.5, calculate_saturation(_as_float(volume), capacity))
    return result


def _build_supply_profile(task: dict[str, Any]) -> dict[str, Any]:
    scope = task.get("scope", {}) or {}
    metrics = task.get("metrics", {}) or {}
    signal = task.get("signal", {}) or {}
    constraints = task.get("constraints", {}) or {}
    capacity = _as_float(metrics.get("capacity"))
    storage_m = _as_float(metrics.get("storage_m") or constraints.get("storage_m"))
    cross_roads = _as_list(scope.get("cross_roads"))
    road_grades = [
        item.get("grade") for item in cross_roads if isinstance(item, dict) and item.get("grade")
    ]
    return _compact(
        {
            "intersection_id": scope.get("intersection_id"),
            "name": scope.get("name"),
            "location": scope.get("location"),
            "signal_controller_id": scope.get("signal_controller_id") or signal.get("controller_id"),
            "inter_type": scope.get("inter_type"),
            "cross_type": scope.get("cross_type"),
            "intersection_shape": scope.get("intersection_shape"),
            "leg_count": scope.get("leg_count"),
            "cross_roads": cross_roads,
            "road_grades": road_grades or scope.get("road_grades"),
            "road_levels": scope.get("road_levels"),
            "road_grade_combination": scope.get("road_grade_combination"),
            "intersection_importance": scope.get("intersection_importance"),
            "approaches": scope.get("approaches") or scope.get("entrances"),
            "exits": scope.get("exits"),
            "lanes": scope.get("lanes"),
            "channelization": scope.get("channelization"),
            "capacity": capacity,
            "movement_capacity": metrics.get("movement_capacity") or metrics.get("capacity_by_movement"),
            "storage_m": storage_m,
            "adjacent_inter_spacing_m": scope.get("adjacent_inter_spacing_m"),
            "adjacent_inter_spacing_detail": scope.get("adjacent_inter_spacing_detail"),
            "intersection_area_m2": scope.get("intersection_area_m2"),
            "static_flags": scope.get("static_flags"),
            "funnel_details": scope.get("funnel_details"),
            "controller_capabilities": signal.get("controller_capabilities") or constraints.get("controller_capabilities"),
        }
    )


def _build_demand_profile(task: dict[str, Any]) -> dict[str, Any]:
    metrics = task.get("metrics", {}) or {}
    context = task.get("context", {}) or {}
    return _compact(
        {
            "volume": _as_float(metrics.get("volume")),
            "movement_volume": metrics.get("movement_volume"),
            "lane_volume": metrics.get("lane_volume"),
            "approach_volume": metrics.get("approach_volume"),
            "phase_volume": metrics.get("phase_volume"),
            "turning_ratio": metrics.get("turning_ratio"),
            "arrival_pattern": metrics.get("arrival_pattern") or context.get("arrival_pattern"),
            "peak_hour_factor": metrics.get("peak_hour_factor"),
            "pedestrian_volume": metrics.get("pedestrian_volume"),
            "bike_volume": metrics.get("bike_volume"),
            "lane_utilization_cv": metrics.get("lane_utilization_cv"),
            "lane_mismatch_index": metrics.get("lane_mismatch_index"),
            "imbalance_index": metrics.get("imbalance_index"),
            "time_period": context.get("time_period"),
            "od_share": metrics.get("od_share"),
            "main_paths": metrics.get("main_paths"),
            "special_vehicle_share": metrics.get("special_vehicle_share"),
        }
    )


def _build_control_profile(task: dict[str, Any]) -> dict[str, Any]:
    signal = task.get("signal", {}) or {}
    constraints = task.get("constraints", {}) or {}
    metrics = task.get("metrics", {}) or {}
    return _compact(
        {
            "plan_no": signal.get("plan_no"),
            "plan_name": signal.get("plan_name"),
            "current_cycle_s": signal.get("current_cycle_s") or metrics.get("current_cycle_s"),
            "phase_sequence": signal.get("phase_sequence"),
            "phase_splits": signal.get("phase_splits"),
            "stage_detail": signal.get("stage_detail"),
            "coordination_mode": signal.get("coordination_mode"),
            "offset_s": signal.get("offset_s"),
            "time_plan_count": signal.get("time_plan_count") or metrics.get("time_plan_count"),
            "manual_intervention_count": signal.get("manual_intervention_count")
            or metrics.get("manual_intervention_count"),
            "special_scene_uncovered": signal.get("special_scene_uncovered"),
            "min_green_s": signal.get("min_green_s") or constraints.get("min_green_s"),
            "min_green_detail": signal.get("min_green_detail"),
            "max_cycle_s": constraints.get("max_cycle_s"),
            "yellow_s": constraints.get("yellow_s"),
            "all_red_s": constraints.get("all_red_s"),
            "ped_clearance_s": constraints.get("ped_clearance_s"),
            "release_mode": constraints.get("release_mode"),
        }
    )


def _build_traffic_state(task: dict[str, Any], supply_profile: dict[str, Any]) -> dict[str, Any]:
    metrics = task.get("metrics", {}) or {}
    volume = _as_float(metrics.get("volume"))
    capacity = _as_float(metrics.get("capacity") or supply_profile.get("capacity"))
    saturation = _as_float(metrics.get("saturation"))
    if saturation == 0 and capacity > 0:
        saturation = calculate_saturation(volume, capacity)
    queue_m = _as_float(metrics.get("queue_m"))
    storage_m = _as_float(metrics.get("storage_m") or supply_profile.get("storage_m"))
    queue_storage_ratio = _as_float(metrics.get("queue_storage_ratio"))
    if queue_storage_ratio == 0 and queue_m > 0 and storage_m > 0:
        queue_storage_ratio = calculate_saturation(queue_m, storage_m)
    los = metrics.get("los")
    if not los and saturation > 0:
        los = _TML.level_of_service(saturation)
    state = {
        "saturation": min(1.5, saturation),
        "movement_saturation": _movement_saturation(metrics),
        "avg_delay_s": _as_float(metrics.get("avg_delay_s")),
        "queue_m": queue_m,
        "queue_storage_ratio": min(1.5, queue_storage_ratio),
        "stop_count": _as_float(metrics.get("stop_count")),
        "empty_green_rate": _as_float(metrics.get("empty_green_rate")),
        "green_utilization": _as_float(metrics.get("green_utilization") or metrics.get("green_utilization_rate"), 1.0),
        "green_wave_pass_rate": _as_float(metrics.get("green_wave_pass_rate"), 1.0),
        "spillback_risk": _as_float(metrics.get("spillback_risk")),
        "imbalance_index": _as_float(metrics.get("imbalance_index")),
        "los": los,
        "conflict_risk": _as_float(metrics.get("conflict_risk")),
        "uncleared_cycles": _as_float(metrics.get("uncleared_cycles")),
        "phase_saturation_gap": _as_float(metrics.get("movement_saturation_gap") or metrics.get("phase_saturation_gap")),
        "lane_utilization_cv": _as_float(metrics.get("lane_utilization_cv")),
        "lane_mismatch_index": _as_float(metrics.get("lane_mismatch_index")),
        "period_variation_index": _as_float(metrics.get("period_variation_index")),
        "offset_deviation_s": _as_float(metrics.get("offset_deviation_s")),
        "start_loss_s": _as_float(metrics.get("start_loss_s")),
    }
    return _compact(state)


def _quality_tags(task: dict[str, Any], traffic_state: dict[str, Any], control_profile: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    metrics = task.get("metrics", {}) or {}
    context = task.get("context", {}) or {}
    signal = task.get("signal", {}) or {}
    checklist_summary = context.get("checklist_summary") or {}
    missing_items = set(_as_list(checklist_summary.get("missing_items")))
    tags: list[dict[str, Any]] = []
    errors: list[str] = []

    required_metrics = {"volume", "capacity", "avg_delay_s"}
    for field in sorted(required_metrics - set(metrics)):
        tags.append(_tag("missing_required_metric", field, 1.0, "input_validation"))
        errors.append(f"missing metrics.{field}")
    if not (task.get("scope") or {}).get("level"):
        tags.append(_tag("missing_scope_level", True, 1.0, "input_validation"))
        errors.append("missing scope.level")
    if "turn_perf" in missing_items:
        tags.append(_tag("missing_turn_perf_data", "turn_perf", 0.9, "checklist"))
        errors.append("缺少 turn_perf 运行明细：该路口暂未检索到排队、延误、停车次数数据，相关指标将显示为缺失或仅用其他数据估算")

    capacity = _as_float(metrics.get("capacity"))
    volume = _as_float(metrics.get("volume"))
    if capacity <= 0 and volume > 0:
        tags.append(_tag("invalid_capacity", capacity, 1.0, "metrics"))
        errors.append("metrics.capacity must be positive when volume exists")

    data_quality = context.get("data_quality") or {}
    detector_online_rate = _as_float(data_quality.get("detector_online_rate"), 1.0)
    if detector_online_rate < _TH("data_quality.detector_online_rate"):
        tags.append(_tag("detector_online_rate_low", detector_online_rate, _TH("data_quality.detector_online_rate"), "context.data_quality"))
    data_latency_s = _as_float(data_quality.get("latency_s"))
    if data_latency_s > _TH("data_quality.latency_s"):
        tags.append(_tag("data_latency_high", data_latency_s, 0.9, "context.data_quality"))

    if not signal and not control_profile:
        tags.append(_tag("missing_signal_profile", True, 0.85, "signal"))
        errors.append("missing signal/control_profile")
    elif not control_profile.get("current_cycle_s"):
        tags.append(_tag("missing_current_cycle_s", True, 0.8, "signal"))

    saturation = _as_float(traffic_state.get("saturation"))
    avg_delay = _as_float(traffic_state.get("avg_delay_s"))
    queue_m = _as_float(traffic_state.get("queue_m"))
    if saturation < _TH("saturation.low_saturation_conflict") and (avg_delay >= 80 or queue_m >= 200):
        tags.append(_tag("metric_conflict_low_saturation_high_delay_queue", True, 0.75, "metrics"))
        errors.append("metric conflict: low saturation with high delay or queue")

    empty_green = _as_float(traffic_state.get("empty_green_rate"))
    utilization = _as_float(traffic_state.get("green_utilization"), 1.0)
    if empty_green >= _TH("green.empty_green_rate") and utilization >= _TH("green.utilization_conflict_high"):
        tags.append(_tag("metric_conflict_empty_green_high_utilization", True, 0.75, "metrics"))

    return tags, errors


def _pressure_level(traffic_state: dict[str, Any]) -> str:
    saturation = _as_float(traffic_state.get("saturation"))
    avg_delay = _as_float(traffic_state.get("avg_delay_s"))
    queue_storage_ratio = _as_float(traffic_state.get("queue_storage_ratio"))
    queue_m = _as_float(traffic_state.get("queue_m"))
    spillback = _as_float(traffic_state.get("spillback_risk"))
    conflict = _as_float(traffic_state.get("conflict_risk"))
    pressure_score = max(
        saturation - _TH("saturation.pressure_baseline"),
        avg_delay / _TH("delay.delay_pressure"),
        queue_storage_ratio,
        queue_m / _TH("queue.queue_m_pressure"),
        spillback,
        conflict,
    )
    return _severity(pressure_score)


def _supply_demand_state(supply_profile: dict[str, Any], demand_profile: dict[str, Any], traffic_state: dict[str, Any]) -> dict[str, Any]:
    saturation = _as_float(traffic_state.get("saturation"))
    if saturation >= _TH("saturation.oversaturation"):
        status = "oversaturated"
    elif saturation >= _TH("saturation.high"):
        status = "near_saturated"
    elif saturation > 0:
        status = "stable"
    else:
        status = "unknown"
    return {
        "status": status,
        "volume": demand_profile.get("volume", 0),
        "capacity": supply_profile.get("capacity", 0),
        "saturation": saturation,
    }


def _congestion_stage(traffic_state: dict[str, Any], context: dict[str, Any]) -> str:
    saturation = _as_float(traffic_state.get("saturation"))
    queue_ratio = _as_float(traffic_state.get("queue_storage_ratio"))
    spillback = _as_float(traffic_state.get("spillback_risk"))
    if spillback >= _TH("spillback.risk_high") or queue_ratio >= _TH("queue.queue_storage_ratio_diffusion"):
        return "扩散期"
    if saturation >= _TH("saturation.high") or queue_ratio >= _TH("queue.queue_storage_ratio_high"):
        return "萌芽期"
    if saturation > 0 and saturation < 0.5:
        return "消散期"
    return "稳定"


def _congestion_spatial_form(traffic_state: dict[str, Any], scope: dict[str, Any]) -> str:
    spillback = _as_float(traffic_state.get("spillback_risk"))
    level = str(scope.get("level", "intersection"))
    if level == "corridor" or spillback >= _TH("spillback.risk_high"):
        return "线状"
    if _as_float(traffic_state.get("imbalance_index")) >= _TH("imbalance.high"):
        return "面状"
    return "点状"


def _build_congestion_profile(
    task: dict[str, Any],
    traffic_state: dict[str, Any],
    demand_profile: dict[str, Any],
) -> dict[str, Any]:
    context = task.get("context", {}) or {}
    scope = task.get("scope", {}) or {}
    stage = _congestion_stage(traffic_state, context)
    spatial = _congestion_spatial_form(traffic_state, scope)
    severity = "high" if _as_float(traffic_state.get("saturation")) >= _TH("saturation.oversaturation") else (
        "medium" if _as_float(traffic_state.get("saturation")) >= _TH("saturation.high") else "low"
    )
    return _compact(
        {
            "time_period": context.get("time_period") or demand_profile.get("time_period"),
            "time_window": context.get("time_window"),
            "day_of_week": context.get("day_of_week"),
            "step_index": context.get("step_index"),
            "severity": severity,
            "stage": stage,
            "spatial_form": spatial,
            "max_queue_m": traffic_state.get("queue_m"),
            "avg_delay_s": traffic_state.get("avg_delay_s"),
            "stop_count": traffic_state.get("stop_count"),
            "spillback_risk": traffic_state.get("spillback_risk"),
            "los": task.get("metrics", {}).get("los"),
        }
    )


def _dir4_label(value: Any) -> str:
    text = str(value or "").strip()
    for suffix in ("进口", "出口"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    for direction in ("东", "西", "南", "北"):
        if text.startswith(direction) or direction in text[:3]:
            return direction
    return ""


def _import_dir(value: Any) -> str | None:
    direction = _dir4_label(value)
    return f"{direction}进口" if direction in {"东", "西", "南", "北"} else None


def _import_dir_from_dir8(value: Any) -> str:
    try:
        label = DIR8_APPROACH_LABELS.get(int(_as_float(value)), "")
    except (TypeError, ValueError):
        label = ""
    return f"{label}进口" if label else ""


def _flow_trace_turn_label(value: Any) -> str:
    try:
        return FLOW_TRACE_TURN_LABELS.get(int(_as_float(value)), str(value or ""))
    except (TypeError, ValueError):
        return str(value or "")


def _format_flow_trace_item(row: dict[str, Any]) -> str:
    inter = str(row.get("cor_inter_name") or row.get("cor_inter_id") or "").strip()
    direction = _import_dir_from_dir8(row.get("cor_f_dir8_no"))
    turn = _flow_trace_turn_label(row.get("cor_turn_dir_no"))
    ratio = _optional_float(row.get("flow_share_ratio"))
    movement = f"{direction}{turn}" if direction and turn else (direction or turn)
    if not inter:
        return ""
    if ratio is None:
        return f"{inter} {movement}".strip()
    return f"{inter} {movement} {ratio:.2f}%".strip()


def _flow_trace_placeholder_rows(turn_flows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    rows: list[dict[str, Any]] = []
    for row in turn_flows or []:
        direction = str(row.get("进口道") or "")
        turn = str(row.get("转向") or "")
        if not direction or not turn:
            continue
        for period in PERIOD_ROW_ORDER:
            key = (direction, turn, period)
            if key in seen:
                continue
            seen.add(key)
            entry: dict[str, Any] = {
                "进口道": direction,
                "转向": turn,
                "时段": period,
                "流量来源": [],
                "流量去向": [],
            }
            for index in range(1, 4):
                entry[f"流量来源TOP{index}"] = ""
                entry[f"流量去向TOP{index}"] = ""
            rows.append(entry)
    return rows


def _flow_trace_rows(
    rows: list[dict[str, Any]] | None,
    turn_flows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not rows:
        return _flow_trace_placeholder_rows(turn_flows)

    buckets: dict[tuple[int, int, str], dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        period = PERIOD_TYPE_LABELS.get(str(row.get("period_type") or "").upper(), "")
        if not period:
            continue
        try:
            key = (int(_as_float(row.get("f_dir8_no"))), int(_as_float(row.get("turn_dir_no"))), period)
        except (TypeError, ValueError):
            continue
        trace = str(row.get("trace_type") or "").upper()
        if trace not in {"UPSTREAM", "DOWNSTREAM"}:
            continue
        bucket = buckets.setdefault(key, {"UPSTREAM": [], "DOWNSTREAM": []})
        bucket[trace].append(row)

    result: list[dict[str, Any]] = []
    for (dir8_no, turn_dir_no, period), traces in sorted(
        buckets.items(),
        key=lambda item: (
            item[0][0],
            TURN_ORDER.get(_flow_trace_turn_label(item[0][1]), 99),
            _period_sort_key(item[0][2]),
        ),
    ):
        direction = _import_dir_from_dir8(dir8_no)
        turn = _flow_trace_turn_label(turn_dir_no)
        if not direction or not turn:
            continue
        sources = sorted(
            traces["UPSTREAM"],
            key=lambda item: _as_float(item.get("flow_share_ratio")),
            reverse=True,
        )[:3]
        destinations = sorted(
            traces["DOWNSTREAM"],
            key=lambda item: _as_float(item.get("flow_share_ratio")),
            reverse=True,
        )[:3]
        entry: dict[str, Any] = {
            "进口道": direction,
            "转向": turn,
            "时段": period,
            "流量来源": [_format_flow_trace_item(item) for item in sources if _format_flow_trace_item(item)],
            "流量去向": [_format_flow_trace_item(item) for item in destinations if _format_flow_trace_item(item)],
        }
        for index in range(1, 4):
            entry[f"流量来源TOP{index}"] = _format_flow_trace_item(sources[index - 1]) if len(sources) >= index else ""
            entry[f"流量去向TOP{index}"] = (
                _format_flow_trace_item(destinations[index - 1]) if len(destinations) >= index else ""
            )
        result.append(entry)
    if result:
        return result
    return _flow_trace_placeholder_rows(turn_flows)


def _shape_label(value: Any) -> str:
    mapping = {
        "cross": "十字",
        "t": "T型",
        "y": "Y型",
        "multi_leg": "五叉",
        "roundabout": "环岛",
        "irregular": "畸形",
        "x": "畸形",
        "pedestrian_crossing": "畸形",
    }
    text = str(value or "")
    return mapping.get(text, text if text in {"十字", "T型", "Y型", "五叉", "环岛", "畸形"} else "")


def _movement_parts(key: Any, supply_profile: dict[str, Any]) -> tuple[str | None, str]:
    text = str(key or "")
    turn = "直行"
    for candidate in ("左转", "直行", "右转"):
        if candidate in text:
            turn = candidate
            break
    link_token = text.split("_", 1)[0]
    for row in _as_list(supply_profile.get("channelization")):
        if not isinstance(row, dict):
            continue
        link_id = str(row.get("link_id") or "")
        if link_token and (link_id == link_token or link_id.endswith(link_token)):
            direction = _import_dir(row.get("dir4_label") or row.get("dir8_label"))
            if direction:
                return direction, turn
    direction = _import_dir(text)
    return direction, turn


def _turn_label_from_row(row: dict[str, Any]) -> str:
    turn_dir_no = row.get("turn_dir_no")
    if turn_dir_no is not None:
        labels = {1: "左转", 2: "直行", 3: "右转"}
        label = labels.get(int(_as_float(turn_dir_no)))
        if label:
            return label
    explicit = str(row.get("turn_dir_label") or "").strip()
    if explicit:
        for candidate in ("左转", "直行", "右转"):
            if candidate in explicit:
                return candidate
    _, turn = _movement_parts(row.get("link_id") or row.get("f_dir_8"), {})
    return turn


def _movement_parts_from_row(row: dict[str, Any], supply_profile: dict[str, Any]) -> tuple[str | None, str]:
    direction, _ = _movement_parts(row.get("link_id") or row.get("f_dir_8"), supply_profile)
    if not direction:
        direction = _import_dir(row.get("dir4_label") or row.get("dir8_label") or row.get("f_dir_8_label"))
    turn = _turn_label_from_row(row)
    if row.get("turn_dir_no") is None and row.get("lane_id"):
        lane = _lane_lookup(supply_profile).get(str(row.get("lane_id"))) or {}
        lane_turn = _turn_move_label(lane.get("turn_move") or lane.get("lane_func_code") or lane.get("lane_info"))
        if lane_turn:
            turn = lane_turn
    return direction, turn


def _period_name(task: dict[str, Any], congestion_profile: dict[str, Any]) -> str | None:
    context = task.get("context") or {}
    step_index = context.get("step_index")
    if step_index is not None:
        period = _period_from_minutes(int(_as_float(step_index)) * 5)
        if period:
            return period

    text = " ".join(
        str(value or "")
        for value in (
            context.get("time_period"),
            context.get("time_window"),
            context.get("time_hhmm"),
            congestion_profile.get("time_period"),
            congestion_profile.get("time_window"),
        )
    )
    period = _period_from_text_time(text)
    if period:
        return period
    if any(token in text for token in ("晚", "pm", "evening")):
        return "晚高峰"
    if any(token in text for token in ("平峰", "off_peak", "平")):
        return "白平峰"
    if any(token in text for token in ("早", "am", "morning", "高峰", "peak")):
        return "早高峰"
    return None


def _hhmm_to_minutes(value: str) -> int | None:
    parts = value.strip().split(":")
    if not parts or not parts[0].isdigit():
        return None
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def _period_from_minutes(minutes: int) -> str | None:
    for period, (start, end) in DEFAULT_PERIOD_WINDOWS.items():
        start_minutes = _hhmm_to_minutes(start)
        end_minutes = _hhmm_to_minutes(end)
        if start_minutes is not None and end_minutes is not None and start_minutes <= minutes < end_minutes:
            return period
    return None


def _period_from_text_time(text: str) -> str | None:
    import re

    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    minutes = _hhmm_to_minutes(match.group(0))
    return _period_from_minutes(minutes) if minutes is not None else None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _period_values(value: Any = None, period: str | None = None) -> dict[str, float | None]:
    """Fill only the period backed by source data; unknown periods stay empty for UI '-' display."""
    result: dict[str, float | None] = {name: None for name in PERIOD_ROW_ORDER}
    number = _optional_float(value)
    if period in result and number is not None:
        result[period] = round(number, 4)
    return result


def _period_value(value: Any, current_period: str, source_period: str | None) -> float | None:
    if source_period != current_period:
        return None
    number = _optional_float(value)
    return round(number, 4) if number is not None else None


def _period_from_step_value(value: Any) -> str | None:
    step = _optional_float(value)
    if step is None:
        return None
    return _period_from_minutes(int(step) * 5)


def _aggregate(values: list[float], mode: str) -> float | None:
    if not values:
        return None
    if mode == "sum":
        return round(sum(values), 4)
    if mode == "max":
        return round(max(values), 4)
    return round(sum(values) / len(values), 4)


_FIVE_MIN_VOLUME_FIELDS = frozenset({"avg_lane_flow_5min", "volume_5min", "lane_flow_5min"})


def _as_hourly_pcu_h(value: Any, *, field: str = "") -> float | None:
    """Normalize flow/capacity metrics to hourly pcu/h for capacityAndSupply reporting."""
    number = _optional_float(value)
    if number is None:
        return None
    if field in _FIVE_MIN_VOLUME_FIELDS:
        return round(number * 12, 2)
    return round(number, 2)


def _hourly_period_dict(values: dict[str, Any], *, field: str = "") -> dict[str, float | None]:
    return {period: _as_hourly_pcu_h(values.get(period), field=field) for period in PERIOD_ROW_ORDER}


def _hourly_movement_period_rows(rows: list[dict[str, Any]], *, field: str = "") -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        for period in PERIOD_ROW_ORDER:
            if period in updated:
                updated[period] = _as_hourly_pcu_h(updated.get(period), field=field)
        result.append(updated)
    return result


def _hourly_saturation_flow_rates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        for key in ("饱和流率", "平均饱和流率"):
            if key in updated:
                updated[key] = _as_hourly_pcu_h(updated.get(key), field="saturation_flow")
        result.append(updated)
    return result


def _period_metric_values(rows: Any, field: str, mode: str = "avg") -> dict[str, float | None]:
    buckets: dict[str, list[float]] = {name: [] for name in PERIOD_ROW_ORDER}
    for row in _as_list(rows):
        if not isinstance(row, dict):
            continue
        period = _period_from_step_value(row.get("step_index"))
        value = _optional_float(row.get(field))
        if period in buckets and value is not None:
            buckets[period].append(value)
    return {period: _aggregate(values, mode) for period, values in buckets.items()}


def _los_rank(value: Any) -> int:
    text = str(value or "").strip().upper()[:1]
    return {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}.get(text, 0)


def _period_los_values(rows: Any, fallback_los: Any = None, fallback_period: str | None = None) -> dict[str, str | None]:
    buckets: dict[str, list[str]] = {name: [] for name in PERIOD_ROW_ORDER}
    for row in _as_list(rows):
        if not isinstance(row, dict):
            continue
        period = _period_from_step_value(row.get("step_index"))
        los = str(row.get("level_of_service") or row.get("los") or "").strip().upper()[:1]
        if period in buckets and los:
            buckets[period].append(los)
    result = {
        period: max(values, key=_los_rank) if values else None
        for period, values in buckets.items()
    }
    los = str(fallback_los or "").strip().upper()[:1]
    if fallback_period in result and los and result[fallback_period] is None:
        result[fallback_period] = los
    return result


def _merge_period_values(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    return {
        period: primary.get(period) if primary.get(period) is not None else fallback.get(period)
        for period in PERIOD_ROW_ORDER
    }


def _movement_period_table(
    rows: Any,
    supply_profile: dict[str, Any],
    field: str,
    mode: str = "avg",
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, list[float]]] = {}
    for row in _as_list(rows):
        if not isinstance(row, dict):
            continue
        period = _period_from_step_value(row.get("step_index"))
        value = _optional_float(row.get(field))
        if period is None or value is None:
            continue
        direction, turn = _movement_parts_from_row(row, supply_profile)
        if not direction:
            continue
        period_buckets = buckets.setdefault((direction, turn), {name: [] for name in PERIOD_ROW_ORDER})
        period_buckets[period].append(value)

    result: list[dict[str, Any]] = []
    turn_order = {"左转": 0, "直行": 1, "右转": 2}
    for (direction, turn), period_buckets in sorted(
        buckets.items(),
        key=lambda item: (item[0][0], turn_order.get(item[0][1], 9)),
    ):
        result.append(
            {
                "进口道": direction,
                "转向": turn,
                **{period: _aggregate(values, mode) for period, values in period_buckets.items()},
            }
        )
    return result


def _total_by_period(movement_rows: list[dict[str, Any]]) -> dict[str, float | None]:
    totals: dict[str, float] = {name: 0.0 for name in PERIOD_ROW_ORDER}
    seen: dict[str, bool] = {name: False for name in PERIOD_ROW_ORDER}
    for row in movement_rows:
        for period in PERIOD_ROW_ORDER:
            value = _optional_float(row.get(period))
            if value is not None:
                totals[period] += value
                seen[period] = True
    return {period: round(totals[period], 4) if seen[period] else None for period in PERIOD_ROW_ORDER}


def _ratio_by_period(numerator: dict[str, Any], denominator: dict[str, Any]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for period in PERIOD_ROW_ORDER:
        num = _optional_float(numerator.get(period))
        den = _optional_float(denominator.get(period))
        result[period] = round(num / den, 4) if num is not None and den and den > 0 else None
    return result


def _sum_lanes(rows: Any) -> tuple[int, dict[str, int]]:
    by_dir = {"东": 0, "西": 0, "南": 0, "北": 0}
    seen: set[str] = set()
    total = 0
    for row in _as_list(rows):
        if not isinstance(row, dict):
            continue
        marker = str(row.get("link_id") or row)
        if marker in seen:
            continue
        seen.add(marker)
        count = int(_as_float(row.get("lane_num") or row.get("c_lane_num")))
        total += count
        direction = _dir4_label(row.get("dir4_label") or row.get("dir8_label"))
        if direction in by_dir:
            by_dir[direction] += count
    return total, by_dir


def _turn_tokens(value: Any) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    tokens = [token.strip() for token in text.replace(",", "|").split("|") if token.strip()] or [text]
    mapping = {
        "11": {"直行"},
        "12": {"左转"},
        "13": {"右转"},
        "21": {"左转", "直行"},
        "22": {"直行", "右转"},
        "23": {"左转", "右转"},
        "32": {"左转", "直行"},
    }
    turns: set[str] = set()
    for token in tokens:
        if token in mapping:
            turns.update(mapping[token])
            continue
        if "左" in token:
            turns.add("左转")
        if "直" in token:
            turns.add("直行")
        if "右" in token:
            turns.add("右转")
    return turns


def _mixed_turn_directions(supply_profile: dict[str, Any]) -> set[str]:
    mixed: set[str] = set()
    for row in _as_list(supply_profile.get("lanes") or supply_profile.get("channelization")):
        if not isinstance(row, dict):
            continue
        role = str(row.get("link_role") or "").lower()
        if role and role != "entrance":
            continue
        direction = _import_dir(row.get("dir4_label") or row.get("dir8_label"))
        if not direction:
            direction, _ = _movement_parts(row.get("link_id"), supply_profile)
        if not direction:
            continue
        turns = _turn_tokens(row.get("turn_move") or row.get("lane_info") or row.get("lane_func_code"))
        if len(turns) > 1:
            mixed.add(direction)
    return mixed


def _movement_table(values: Any, supply_profile: dict[str, Any], period: str | None, value_name: str) -> list[dict[str, Any]]:
    if not isinstance(values, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key, value in values.items():
        direction, turn = _movement_parts(key, supply_profile)
        if not direction:
            continue
        row = {"进口道": direction, "转向": turn, **_period_values(value, period)}
        if value_name:
            row[value_name] = round(_as_float(value), 4)
        rows.append(row)
    return rows


def _turn_proportions(demand_profile: dict[str, Any], supply_profile: dict[str, Any], period: str | None) -> list[dict[str, Any]]:
    volumes = demand_profile.get("movement_volume")
    if not isinstance(volumes, dict):
        return []
    period_name = period or PERIOD_ROW_ORDER[0]
    buckets: dict[tuple[str, str], dict[str, float]] = {}
    for key, value in volumes.items():
        direction, turn = _movement_parts(key, supply_profile)
        if not direction or turn not in TURN_ORDER:
            continue
        buckets.setdefault((direction, period_name), {"左转": 0.0, "直行": 0.0, "右转": 0.0})
        buckets[(direction, period_name)][turn] += _as_float(value)
    rows: list[dict[str, Any]] = []
    for (direction, row_period), turns in sorted(
        buckets.items(),
        key=lambda item: (DIRECTION_ORDER.get(item[0][0], 99), item[0][0], _period_sort_key(item[0][1])),
    ):
        total = sum(turns.values())
        if total <= 0:
            continue
        left = round(turns["左转"] / total * 100, 2)
        through = round(turns["直行"] / total * 100, 2)
        right = round(turns["右转"] / total * 100, 2)
        rows.append(
            {
                "进口道": direction,
                "时段": row_period,
                "左转": left,
                "直行": through,
                "右转": right,
                "左转占比": left,
                "直行占比": through,
                "右转占比": right,
            }
        )
    return rows


def _turn_flow_proportions(turn_flows: list[dict[str, Any]], supply_profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one row per import direction and period, with left/through/right shares."""
    buckets: dict[tuple[str, str], dict[str, float]] = {}
    for row in turn_flows:
        direction = str(row.get("进口道") or "")
        turn = str(row.get("转向") or "")
        if not direction or turn not in TURN_ORDER:
            continue
        for period in PERIOD_ROW_ORDER:
            value = _optional_float(row.get(period))
            if value is None:
                continue
            period_bucket = buckets.setdefault((direction, period), {"左转": 0.0, "直行": 0.0, "右转": 0.0})
            period_bucket[turn] += value

    rows: list[dict[str, Any]] = []
    for (direction, period), turns in sorted(
        buckets.items(),
        key=lambda item: (DIRECTION_ORDER.get(item[0][0], 99), item[0][0], _period_sort_key(item[0][1])),
    ):
        total = sum(turns.values())
        if total <= 0:
            continue
        left = round(turns["左转"] / total * 100, 2)
        through = round(turns["直行"] / total * 100, 2)
        right = round(turns["右转"] / total * 100, 2)
        rows.append(
            {
                "进口道": direction,
                "时段": period,
                "左转": left,
                "直行": through,
                "右转": right,
                "左转占比": left,
                "直行占比": through,
                "右转占比": right,
            }
        )
    return rows


def _movement_rows_from_lanes(supply_profile: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    rows: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for lane in _as_list(supply_profile.get("lanes") or supply_profile.get("channelization")):
        if not isinstance(lane, dict):
            continue
        role = str(lane.get("link_role") or "").lower()
        if role and role != "entrance":
            continue
        direction = _import_dir(lane.get("dir4_label") or lane.get("dir8_label"))
        if not direction:
            direction, _ = _movement_parts(lane.get("link_id"), supply_profile)
        if not direction:
            continue
        turns = _turn_tokens(lane.get("turn_move") or lane.get("lane_func_code") or lane.get("lane_info")) or {"直行"}
        lane_id = str(lane.get("lane_id") or lane.get("link_id") or "")
        for turn in turns:
            key = (direction, turn, lane_id or None)
            if key not in seen:
                seen.add(key)
                rows.append(key)
    return rows


def _complete_movement_rows(rows: list[dict[str, Any]], supply_profile: dict[str, Any]) -> list[dict[str, Any]]:
    existing = {(str(row.get("进口道") or ""), str(row.get("转向") or "")) for row in rows}
    completed = list(rows)
    for direction, turn, _lane_id in _movement_rows_from_lanes(supply_profile):
        if (direction, turn) in existing:
            continue
        completed.append({"进口道": direction, "转向": turn, **{period: None for period in PERIOD_ROW_ORDER}})
        existing.add((direction, turn))
    return sorted(completed, key=_movement_sort_key)


def _demand_status(saturation: float) -> str:
    if saturation >= _TH("saturation.oversaturation"):
        return "过饱和"
    if saturation >= _TH("saturation.high"):
        return "饱和"
    return "非饱和"


def _turn_move_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    tokens = [token.strip() for token in text.replace(",", "|").split("|") if token.strip()]
    mapping = {
        "11": "直行",
        "12": "左转",
        "13": "右转",
        "21": "左转",
        "22": "左转",
        "23": "右转",
        "32": "左转",
    }
    labels: list[str] = []
    for token in tokens or [text]:
        if token in mapping:
            labels.append(mapping[token])
        elif any(word in token for word in ("左", "直", "右")):
            if "左" in token:
                labels.append("左转")
            if "直" in token:
                labels.append("直行")
            if "右" in token:
                labels.append("右转")
    return "+".join(dict.fromkeys(labels)) or text


def _lane_lookup(supply_profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in _as_list(supply_profile.get("lanes")):
        if not isinstance(row, dict):
            continue
        lane_id = str(row.get("lane_id") or "")
        if not lane_id:
            continue
        lookup[lane_id] = row
    return lookup


def _weekday_label(value: Any) -> str:
    labels = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
    number = int(_as_float(value)) if value is not None else 0
    return labels.get(number, str(value or ""))


def _saturation_flow_rates(rows: Any, supply_profile: dict[str, Any]) -> list[dict[str, Any]]:
    lanes = _lane_lookup(supply_profile)
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _as_list(rows):
        if not isinstance(row, dict):
            continue
        lane_id = str(row.get("lane_id") or "")
        if not lane_id:
            continue
        saturation_flow = _optional_float(row.get("saturation_flow"))
        if saturation_flow is None:
            continue
        lane = lanes.get(lane_id) or {}
        direction = _import_dir(lane.get("dir4_label") or lane.get("dir8_label")) or ""
        turn_move = _turn_move_label(lane.get("turn_move") or lane.get("lane_func_code") or lane.get("lane_info")) or "未知"
        bucket = buckets.setdefault(
            (direction, turn_move),
            {
                "direction": direction,
                "turn_move": turn_move,
                "lane_ids": set(),
                "lane_nos": [],
                "flows": [],
                "headways": [],
                "periods": [],
                "dayofweek": row.get("dayofweek"),
            },
        )
        bucket["lane_ids"].add(lane_id)
        lane_no = row.get("lane_no") or lane.get("lane_no")
        if lane_no is not None:
            bucket["lane_nos"].append(str(lane_no))
        bucket["flows"].append(saturation_flow)
        headway = _optional_float(row.get("saturation_headway"))
        if headway is not None:
            bucket["headways"].append(headway)
        if row.get("period"):
            bucket["periods"].append(str(row.get("period")))

    result: list[dict[str, Any]] = []
    for bucket in buckets.values():
        flows = bucket["flows"]
        headways = bucket["headways"]
        periods = list(dict.fromkeys(bucket["periods"]))
        condition_parts = [_weekday_label(bucket.get("dayofweek"))]
        if periods:
            condition_parts.append("日内多时段均值")
        avg_headway = round(sum(headways) / len(headways), 3) if headways else None
        avg_flow = round(sum(flows) / len(flows), 1)
        direction = bucket.get("direction") or "未知进口"
        turn = bucket.get("turn_move") or "未知"
        result.append(
            {
                "进口道": direction,
                "转向": turn,
                "进口转向": f"{direction}{turn}",
                "车道数": len(bucket["lane_ids"]) or None,
                "车道号": "、".join(dict.fromkeys(bucket["lane_nos"])),
                "车道功能": turn,
                "平均饱和车头时距": avg_headway,
                "平均饱和流率": avg_flow,
                "饱和车头时距": avg_headway,
                "饱和流率": avg_flow,
                "测定条件": "；".join(part for part in condition_parts if part),
            }
        )
    return sorted(result, key=_movement_sort_key)


def _lane_capacity_period_table(rows: Any, supply_profile: dict[str, Any]) -> list[dict[str, Any]]:
    lanes = _lane_lookup(supply_profile)
    buckets: dict[tuple[str, str], dict[str, dict[str, list[float]]]] = {}
    for row in _as_list(rows):
        if not isinstance(row, dict):
            continue
        period = _period_from_step_value(row.get("step_index"))
        value = _optional_float(row.get("lane_capacity"))
        if period is None or value is None:
            continue
        lane = lanes.get(str(row.get("lane_id") or "")) or {}
        direction = _import_dir(lane.get("dir4_label") or lane.get("dir8_label"))
        if not direction:
            direction, _ = _movement_parts(row.get("link_id"), supply_profile)
        if not direction:
            continue
        turns = _turn_tokens(lane.get("turn_move") or lane.get("lane_func_code") or lane.get("lane_info")) or {"直行"}
        split_value = value / len(turns)
        for turn in turns:
            lane_key = str(row.get("lane_id") or row.get("link_id") or f"{direction}:{turn}")
            period_lanes = buckets.setdefault(
                (direction, turn),
                {name: {} for name in PERIOD_ROW_ORDER},
            )[period]
            period_lanes.setdefault(lane_key, []).append(split_value)

    for direction, turn, _lane_id in _movement_rows_from_lanes(supply_profile):
        if turn == "右转":
            bucket = buckets.setdefault((direction, turn), {name: {} for name in PERIOD_ROW_ORDER})
            for period in PERIOD_ROW_ORDER:
                if not bucket[period]:
                    bucket[period]["__default_right_turn__"] = [1200.0]

    result: list[dict[str, Any]] = []
    for (direction, turn), period_lane_buckets in buckets.items():
        result.append(
            {
                "进口道": direction,
                "转向": turn,
                **{
                    period: _aggregate(
                        [
                            sum(values) / len(values)
                            for values in lane_buckets.values()
                            if values
                        ],
                        "sum",
                    )
                    for period, lane_buckets in period_lane_buckets.items()
                },
            }
        )
    return sorted(result, key=_movement_sort_key)


def _movement_status_rows(
    saturations: list[dict[str, Any]],
    queues: list[dict[str, Any]],
    delays: list[dict[str, Any]],
    stops: list[dict[str, Any]],
    green_utilization: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lookup: dict[tuple[str, str, str], dict[str, Any]] = {}

    def ensure(direction: str, turn: str, period: str) -> dict[str, Any]:
        return lookup.setdefault((direction, turn, period), {"进口道": direction, "转向": turn, "时段": period})

    sources = [
        (saturations, "饱和度"),
        (queues, "最大排队长度"),
        (delays, "平均延误"),
        (stops, "平均停车次数"),
        (green_utilization, "绿灯利用率"),
    ]
    for rows, field in sources:
        for row in rows:
            direction = str(row.get("进口道") or "")
            turn = str(row.get("转向") or "")
            if not direction or not turn:
                continue
            for period in PERIOD_ROW_ORDER:
                value = _optional_float(row.get(period))
                if value is not None:
                    ensure(direction, turn, period)[field] = value
    return sorted(
        lookup.values(),
        key=lambda row: (*_movement_sort_key(row), _period_sort_key(row.get("时段"))),
    )


def _operational_data_availability(raw: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not _as_list(raw.get("turn_perf")):
        rows.append(
            {
                "指标": "排队长度/延误/停车次数",
                "说明": "未检索到 turn_perf 时序数据；4.1 仅展示饱和度、绿灯利用率等可用指标。",
            }
        )
    return rows


def _queue_peak_rows(raw_turn_perf: Any, supply_profile: dict[str, Any], storage_ratio_values: dict[str, Any]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in _as_list(raw_turn_perf):
        if not isinstance(row, dict):
            continue
        period = _period_from_step_value(row.get("step_index"))
        queue = _optional_float(row.get("queue_len_max") or row.get("queue_len_avg"))
        if period is None or queue is None:
            continue
        direction, turn = _movement_parts_from_row(row, supply_profile)
        current = buckets.get(period)
        if current is None or queue > _as_float(current.get("最大排队")):
            buckets[period] = {
                "时段": period,
                "进口方向": direction or "",
                "转向": turn,
                "最大排队": queue,
                "存储比": storage_ratio_values.get(period),
                "描述": f"{period}最大排队约 {queue:.0f}m，对应{direction or '未知进口'}{turn}",
            }
    return [buckets[period] for period in PERIOD_ROW_ORDER if period in buckets]


def _normalize_time(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    if not text or ":" not in text:
        return default
    hour_text, minute_text = text.split(":", 1)
    hour = int(_as_float(hour_text))
    minute = int(_as_float(minute_text))
    if hour == 24 and minute == 0:
        return "24:00"
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return default
    return f"{hour:02d}:{minute:02d}"


def _time_minutes(value: str) -> int:
    normalized = _normalize_time(value, default="00:00")
    if normalized == "24:00":
        return 24 * 60
    hour, minute = normalized.split(":", 1)
    return int(hour) * 60 + int(minute)


def _ctrl_mode_label(value: Any) -> str:
    text = str(value or "").strip()
    mapping = {
        "21": "定周期",
        "31": "协调定周期",
        "timing": "定周期",
        "coord_timing": "协调定周期",
    }
    return mapping.get(text.lower(), mapping.get(text, text))


def _stage_total(row: dict[str, Any]) -> float | None:
    explicit = _optional_float(row.get("stage_total_sec"))
    if explicit is not None:
        return explicit
    green = _optional_float(row.get("green_sec"))
    yellow = _optional_float(row.get("yellow_sec"))
    all_red = _optional_float(row.get("all_red_sec"))
    values = [value for value in (green, yellow, all_red) if value is not None]
    return round(sum(values), 4) if values else None


def _cycle_consistency(cycle: float | None, phase_rows: list[dict[str, Any]]) -> dict[str, Any]:
    stage_total = sum(
        _as_float(row.get("阶段总时长"))
        for row in phase_rows
        if row.get("阶段总时长") is not None
    )
    if cycle is None or cycle <= 0 or stage_total <= 0:
        return {"stageTotalSec": round(stage_total, 4) if stage_total else None, "status": "unknown"}
    diff = round(stage_total - cycle, 4)
    return {
        "stageTotalSec": round(stage_total, 4),
        "cycleSec": cycle,
        "diffSec": diff,
        "status": "matched" if abs(diff) <= 1 else "mismatch",
    }


def _stage_label(row: dict[str, Any]) -> str:
    stage = row.get("stage_no")
    return f"阶段{stage}" if stage is not None else str(row.get("phase") or "未知阶段")


def _phase_sequence_rows(control: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cycle = _as_float(control.get("current_cycle_s"))
    for row in _as_list(control.get("stage_detail")):
        if not isinstance(row, dict):
            continue
        green = _optional_float(row.get("green_sec"))
        stage_total = _stage_total(row)
        rows.append(
            {
                "方案编号": row.get("plan_no"),
                "方案名称": row.get("plan_name"),
                "阶段": _stage_label(row),
                "相序": row.get("stage_seq_no"),
                "放行车流": row.get("release_movements") or "空阶段",
                "绿灯时长": green,
                "黄灯时长": _optional_float(row.get("yellow_sec")),
                "全红时长": _optional_float(row.get("all_red_sec")),
                "阶段总时长": stage_total,
                "最小绿": _optional_float(row.get("min_green_sec")),
                "最大绿": _optional_float(row.get("max_green_sec")),
                "绿信比": round(green / cycle, 4) if green is not None and cycle > 0 else None,
                "解析来源": row.get("source_remark") or row.get("remark") or "标准阶段配时表",
            }
        )
    if rows:
        return rows
    splits = control.get("phase_splits")
    if isinstance(splits, dict):
        return [
            {
                "阶段": str(phase),
                "相序": index,
                "放行车流": "空阶段",
                "绿灯时长": _optional_float(green),
                "黄灯时长": None,
                "最小绿": None,
                "最大绿": None,
                "绿信比": round(_as_float(green) / cycle, 4) if cycle > 0 else None,
            }
            for index, (phase, green) in enumerate(splits.items(), start=1)
        ]
    return [
        {
            "阶段": str(phase),
            "相序": index,
            "放行车流": "空阶段",
            "绿灯时长": None,
            "黄灯时长": None,
            "最小绿": None,
            "最大绿": None,
            "绿信比": None,
        }
        for index, phase in enumerate(_as_list(control.get("phase_sequence")), start=1)
    ]


def _min_green_rows(control: dict[str, Any]) -> list[dict[str, Any]]:
    detail = _as_list(control.get("min_green_detail"))
    rows: list[dict[str, Any]] = []
    for item in detail:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "link_id": item.get("link_id"),
                "turn_dir_no": item.get("turn_dir_no"),
                "最小绿": _optional_float(item.get("min_green_time")),
                "计划绿": _optional_float(item.get("green_time_plan")),
                "是否含行人": item.get("has_pedestrian"),
            }
        )
    if rows:
        return rows
    min_green = control.get("min_green_s")
    if isinstance(min_green, dict):
        return [
            {"转向": str(key), "最小绿": _optional_float(value), "计划绿": None, "是否含行人": None}
            for key, value in min_green.items()
        ]
    return [
        {
            "阶段": row.get("阶段"),
            "最小绿": row.get("最小绿"),
            "计划绿": row.get("绿灯时长"),
            "是否含行人": None,
        }
        for row in _phase_sequence_rows(control)
        if row.get("最小绿") is not None
    ]


def _time_segment_rows(raw: dict[str, Any], control: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    schedule_rows = [row for row in _as_list(raw.get("schedule_cfg")) if isinstance(row, dict)]
    rows_with_period = [row for row in schedule_rows if row.get("start_time") or row.get("period_seq_no") or row.get("period_plan_no")]
    for row in rows_with_period:
        start_time = _normalize_time(row.get("start_time"), default="")
        end_time = _normalize_time(row.get("end_time"), default="")
        normalized.append(
            {
                "时段名称": row.get("schedule_name") or row.get("schedule_no"),
                "调度编号": row.get("schedule_no"),
                "星期": row.get("week_day_no"),
                "日方案": row.get("day_plan_no"),
                "时段序号": row.get("period_seq_no"),
                "开始时间": start_time,
                "结束时间": end_time,
                "方案编号": row.get("period_plan_no") or row.get("plan_no"),
                "控制方式": _ctrl_mode_label(row.get("ctrl_mode")),
                "生效开始": row.get("start_day"),
                "生效结束": row.get("end_day"),
                "备注": row.get("period_remark") or row.get("remark"),
            }
        )
    if normalized:
        return sorted(
            normalized,
            key=lambda item: (
                str(item.get("星期") or ""),
                str(item.get("日方案") or ""),
                _time_minutes(str(item.get("开始时间") or "00:00")),
                _as_float(item.get("时段序号")),
            ),
        )

    rows: list[dict[str, Any]] = []
    for row in schedule_rows:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "时段名称": row.get("schedule_name") or row.get("schedule_no"),
                "调度编号": row.get("schedule_no"),
                "星期": row.get("week_day_no"),
                "日方案": row.get("day_plan_no"),
                "时段序号": None,
                "开始时间": "",
                "结束时间": "",
                "方案编号": row.get("plan_no"),
                "控制方式": _ctrl_mode_label(row.get("ctrl_mode")),
                "生效开始": row.get("start_day"),
                "生效结束": row.get("end_day"),
            }
        )
    if rows:
        return rows
    count = int(_as_float(control.get("time_plan_count")))
    if count > 0:
        return [
            {
                "时段名称": "当前方案",
                "调度编号": control.get("plan_no"),
                "星期": "",
                "日方案": control.get("plan_no"),
                "生效开始": "",
                "生效结束": "",
            }
        ]
    return []


def _build_signal_timing_features(raw: dict[str, Any], control: dict[str, Any]) -> dict[str, Any]:
    phase_rows = _phase_sequence_rows(control)
    min_green_rows = _min_green_rows(control)
    cycle = _optional_float(control.get("current_cycle_s"))
    ratios = [row.get("绿信比") for row in phase_rows if row.get("绿信比") is not None]
    min_greens = [row.get("最小绿") for row in min_green_rows if row.get("最小绿") is not None]
    time_segments = _time_segment_rows(raw, control)
    cycle_check = _cycle_consistency(cycle, phase_rows)
    summary_parts = []
    if time_segments:
        summary_parts.append(f"时段调度 {len(time_segments)} 段")
    if cycle is not None:
        summary_parts.append(f"周期 {cycle:.0f}s")
    if phase_rows:
        summary_parts.append(f"相位/阶段 {len(phase_rows)} 个")
    if ratios:
        summary_parts.append(f"绿信比 {min(ratios):.2f}~{max(ratios):.2f}")
    if min_greens:
        summary_parts.append(f"最小绿 {min(min_greens):.0f}~{max(min_greens):.0f}s")
    if cycle_check.get("status") == "mismatch":
        summary_parts.append(f"阶段总时长与周期相差 {cycle_check.get('diffSec')}s")
    return {
        "timeSegments": time_segments,
        "phaseSequence": phase_rows,
        "cycle": {
            "方案编号": control.get("plan_no"),
            "方案名称": control.get("plan_name"),
            "当前周期": cycle,
            "协调方式": control.get("coordination_mode"),
            "相位数": len(phase_rows) or None,
            "offset": _optional_float(control.get("offset_s")),
            "阶段总时长": cycle_check.get("stageTotalSec"),
            "周期校验": cycle_check.get("status"),
            "周期差值": cycle_check.get("diffSec"),
        },
        "greenRatios": [
            {"阶段": row.get("阶段"), "绿灯时长": row.get("绿灯时长"), "绿信比": row.get("绿信比")}
            for row in phase_rows
        ],
        "minGreens": min_green_rows,
        "summary": "；".join(summary_parts),
    }


def _display_peak_periods(period_flows: dict[str, Any] | None, fallback_period: str | None) -> dict[str, str]:
    values = {
        period: _optional_float((period_flows or {}).get(period))
        for period in PERIOD_ROW_ORDER
    }
    valid = {period: value for period, value in values.items() if value is not None and value > 0}
    if valid:
        peak_value = max(valid.values())
        peak_periods = {period for period, value in valid.items() if value == peak_value}
    elif fallback_period in DEFAULT_PERIOD_WINDOWS:
        peak_periods = {fallback_period}
    else:
        peak_periods = set(DEFAULT_PERIOD_WINDOWS)
    return {
        name: f"{start}-{end}" if name in peak_periods else ""
        for name, (start, end) in DEFAULT_PERIOD_WINDOWS.items()
    }


def _time_distribution(
    task: dict[str, Any],
    profile: dict[str, Any],
    period: str | None,
    period_flows: dict[str, Any] | None = None,
) -> dict[str, Any]:
    insights = profile.get("metrics_insights") or {}
    intersection = insights.get("intersection_saturation") if isinstance(insights, dict) else {}
    peak_time = (intersection or {}).get("peak_time")
    peak = (intersection or {}).get("peak_saturation")
    volume = _as_float((profile.get("demand_profile") or {}).get("volume"))
    period_values = _merge_period_values(period_flows or {}, _period_values(volume, period))
    return _keep_schema(
        {
            "curveShape": "双峰型" if period is None else "单峰型",
            "peakPeriods": _display_peak_periods(period_flows, period),
            "peakFlows": {**period_values, "peakToPeakRatio": round(_as_float(peak), 3) if peak else None},
            "flowConcentration": "",
            "growthRecession": {
                "早高峰": f"峰值约出现在 {peak_time}" if peak_time and period == "早高峰" else "",
                "晚高峰": f"峰值约出现在 {peak_time}" if peak_time and period == "晚高峰" else "",
            },
            "mainSubFlow": {"main": "", "sub": ""},
            "tidalCharacteristics": "",
        }
    )


def _fmt_number(value: Any, digits: int = 0) -> str:
    number = _optional_float(value)
    if number is None:
        return ""
    return f"{number:.{digits}f}"


def _window_text(window: dict[str, Any]) -> str:
    start = window.get("start")
    end = window.get("end")
    peak = _optional_float(window.get("peak"))
    text = f"{start}-{end}" if start and end else str(start or end or "")
    if peak is not None:
        text = f"{text}（峰值 {peak:.2f}）" if text else f"峰值 {peak:.2f}"
    return text


def _highlight_text(profile: dict[str, Any], keywords: tuple[str, ...]) -> str:
    interpretation = profile.get("metrics_interpretation") or {}
    for item in _as_list(interpretation.get("highlights")):
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic") or "")
        text = str(item.get("text") or "").strip()
        if text and any(keyword in topic or keyword in text for keyword in keywords):
            return text
    return ""


def _space_constraint_summary(profile: dict[str, Any], supply: dict[str, Any]) -> str:
    insights = profile.get("metrics_insights") or {}
    supply_constraints = insights.get("supply_constraints") if isinstance(insights, dict) else {}
    constraints = [
        str(item)
        for item in _as_list((supply_constraints or {}).get("static_constraints"))
        if str(item).strip()
    ]
    if constraints:
        return "；".join(constraints[:3])

    labels = {
        "funnel_effect": "进出口车道不匹配，车辆通过路口后容易收窄排队",
        "more_entrances_than_exits": "进口方向多于出口方向，进入路口的车流出口承接空间偏紧",
    }
    parts = []
    for flag in _as_list(supply.get("static_flags")):
        text = labels.get(str(flag), str(flag))
        if text:
            parts.append(text)
    parts.extend(str(item) for item in _as_list(supply.get("funnel_details")) if item)
    return "；".join(parts[:3])


def _flow_pattern_summary(profile: dict[str, Any], period_demands: dict[str, Any], fallback_volume: float) -> str:
    insights = profile.get("metrics_insights") or {}
    demand = insights.get("demand_pattern") if isinstance(insights, dict) else {}
    total = _optional_float((demand or {}).get("total_volume"))
    if total is None:
        values = [_optional_float(value) for value in period_demands.values()]
        total = sum(value for value in values if value is not None) or (fallback_volume if fallback_volume > 0 else None)
    if total is None:
        return ""

    parts = [f"全天总流量约 {total:.0f} pcu"]
    pattern = (demand or {}).get("demand_pattern")
    if pattern:
        parts.append(f"流量形态为{pattern}")
    peak_time = (demand or {}).get("peak_flow_time")
    peak_flow = _optional_float((demand or {}).get("peak_flow_volume"))
    if peak_time and peak_flow is not None:
        parts.append(f"流量峰值约 {peak_flow:.0f} pcu，出现在 {peak_time}")
    top = ((demand or {}).get("top_movements") or [{}])[0]
    if isinstance(top, dict) and top.get("label") and top.get("share_pct") is not None:
        parts.append(f"主流向为 {top['label']}，占比约 {_as_float(top.get('share_pct')):.1f}%")
    return "，".join(parts)


def _supply_demand_summary(profile: dict[str, Any], saturation: float) -> str:
    insights = profile.get("metrics_insights") or {}
    intersection = insights.get("intersection_saturation") if isinstance(insights, dict) else {}
    overs = _as_list((intersection or {}).get("oversaturation_windows"))
    highs = _as_list((intersection or {}).get("high_saturation_windows"))
    windows = [item for item in [*overs, *highs] if isinstance(item, dict)]
    if windows:
        ranges = "、".join(_window_text(item) for item in windows[:4] if _window_text(item))
        return f"高饱和主要集中在 {ranges}，峰值饱和度约 {_as_float((intersection or {}).get('peak_saturation') or saturation):.2f}"

    peak = _optional_float((intersection or {}).get("peak_saturation"))
    peak_time = (intersection or {}).get("peak_time")
    if peak is not None and peak > 0:
        suffix = f"，相对繁忙时段为 {peak_time}" if peak_time else ""
        return f"全天未达到高饱和，峰值饱和度约 {peak:.2f}{suffix}"
    return f"当前饱和度约 {saturation:.2f}，状态为 {_demand_status(saturation)}"


def _turn_feature_summary(profile: dict[str, Any], turn_flow_proportions: list[dict[str, Any]]) -> str:
    insights = profile.get("metrics_insights") or {}
    demand = insights.get("demand_pattern") if isinstance(insights, dict) else {}
    top_movements = [item for item in _as_list((demand or {}).get("top_movements")) if isinstance(item, dict) and item.get("label")]
    if top_movements:
        main = top_movements[0]
        parts = [f"主流向为 {main['label']}，占比约 {_as_float(main.get('share_pct')):.1f}%"]
        if len(top_movements) > 1:
            second = top_movements[1]
            parts.append(f"次流向为 {second['label']}，占比约 {_as_float(second.get('share_pct')):.1f}%")
        return "；".join(parts)
    if turn_flow_proportions:
        return "各进口转向占比已按早高峰、晚高峰、白平峰分时段统计。"
    return ""


def _operational_status_summary(profile: dict[str, Any], traffic: dict[str, Any], congestion: dict[str, Any]) -> str:
    highlighted = _highlight_text(profile, ("路口运行", "排队延误", "绿灯利用", "服务水平", "失衡"))
    if highlighted:
        return highlighted
    parts = []
    delay = _optional_float(traffic.get("avg_delay_s"))
    queue = _optional_float(traffic.get("queue_m"))
    imbalance = _optional_float(traffic.get("imbalance_index"))
    los = traffic.get("los") or congestion.get("los")
    if delay is not None:
        parts.append(f"平均延误约 {delay:.0f}s")
    if queue is not None:
        parts.append(f"最大排队约 {queue:.0f}m")
    if imbalance is not None:
        parts.append(f"失衡指数约 {imbalance:.2f}")
    if los:
        parts.append(f"服务水平 {los}")
    return "，".join(parts)


def _time_pattern_summary(profile: dict[str, Any]) -> str:
    insights = profile.get("metrics_insights") or {}
    demand = insights.get("demand_pattern") if isinstance(insights, dict) else {}
    if demand:
        parts = []
        if demand.get("demand_pattern"):
            parts.append(f"全天流量呈{demand['demand_pattern']}")
        if demand.get("peak_flow_time"):
            peak_flow = _fmt_number(demand.get("peak_flow_volume"), 0)
            parts.append(f"流量峰值出现在 {demand['peak_flow_time']}" + (f"，约 {peak_flow} pcu" if peak_flow else ""))
        top = ((demand.get("top_movements") or [{}])[0])
        if isinstance(top, dict) and top.get("label"):
            parts.append(f"主要流向为 {top['label']}")
        if parts:
            return "，".join(parts)

    narrative = str((profile.get("metrics_interpretation") or {}).get("narrative") or "").strip()
    if narrative:
        return narrative
    return ""


def _period_window(name: str) -> str:
    window = DEFAULT_PERIOD_WINDOWS.get(name)
    return f"{window[0]}-{window[1]}" if window else ""


def _flow_concentration_text(period_demands: dict[str, Any], daily_total: Any) -> str:
    total = _optional_float(daily_total)
    if total is None or total <= 0:
        return ""
    peak_total = sum(_as_float(period_demands.get(name)) / 12.0 for name in ("早高峰", "晚高峰"))
    return f"早晚高峰合计约占全天 {peak_total / total * 100:.1f}%"


def _attraction_sources(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_list(context.get("aoi_sources")):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "type": str(item.get("type") or "其他"),
                "name": str(item.get("name") or ""),
                "directionDistance": str(item.get("directionDistance") or ""),
                "impactTime": str(item.get("impactTime") or ""),
                "impactMethod": str(item.get("impactMethod") or ""),
                "distance_m": _optional_float(item.get("distance_m")),
                "accessRole": str(item.get("accessRole") or ""),
                "recordKind": str(item.get("recordKind") or ""),
            }
        )
    return rows


def _attraction_distance(item: dict[str, Any]) -> float | None:
    distance = _optional_float(item.get("distance_m"))
    if distance is not None:
        return distance
    import re

    match = re.search(r"(\d+(?:\.\d+)?)\s*m", str(item.get("directionDistance") or ""))
    return _optional_float(match.group(1)) if match else None


def _main_sub_flow_text(profile: dict[str, Any]) -> dict[str, str]:
    demand = ((profile.get("metrics_insights") or {}).get("demand_pattern") or {})
    top_movements = [item for item in _as_list(demand.get("top_movements")) if isinstance(item, dict)]
    main = top_movements[0] if top_movements else {}
    sub = top_movements[1] if len(top_movements) > 1 else {}
    return {
        "main": (
            f"{main.get('label')}，占比约 {_as_float(main.get('share_pct')):.1f}%"
            if main.get("label")
            else ""
        ),
        "sub": (
            f"{sub.get('label')}，占比约 {_as_float(sub.get('share_pct')):.1f}%"
            if sub.get("label")
            else ""
        ),
    }


CONGESTION_TIME_WINDOWS = (
    ("06:30", "07:00", "酝酿期"),
    ("07:00", "07:45", "上升期"),
    ("07:45", "08:30", "峰值平台期"),
    ("08:30", "09:00", "消散期"),
    ("09:00", "16:30", "白平峰期"),
    ("16:30", "17:15", "上升期"),
    ("17:15", "18:30", "峰值平台期"),
    ("18:30", "19:15", "消散期"),
)


def _congestion_degree_label(max_saturation: float) -> str:
    if max_saturation >= 1.05:
        return "重度"
    if max_saturation >= 0.85:
        return "中度-重度"
    if max_saturation >= 0.65:
        return "轻度"
    return "畅通"


def _congestion_time_profile_from_evaluation(rows: Any) -> list[dict[str, Any]]:
    samples: list[tuple[int, float]] = []
    for row in _as_list(rows):
        if not isinstance(row, dict):
            continue
        step = _optional_float(row.get("step_index"))
        saturation = _optional_float(row.get("saturation_max") or row.get("saturation_avg"))
        if step is None or saturation is None:
            continue
        samples.append((int(step) * 5, saturation))
    if not samples:
        return []

    result: list[dict[str, Any]] = []
    for start_label, end_label, stage in CONGESTION_TIME_WINDOWS:
        start = _time_minutes(start_label)
        end = _time_minutes(end_label)
        values = [sat for minutes, sat in samples if start <= minutes < end]
        if not values:
            continue
        min_sat = min(values)
        max_sat = max(values)
        result.append(
            {
                "时段区间": f"[{start_label}-{end_label}]",
                "拥堵程度": f"[{min_sat:.2f}-{max_sat:.2f} / {_congestion_degree_label(max_sat)}]",
                "发展阶段": stage,
            }
        )
    return result


def _congestion_profile_rows(profile: dict[str, Any], congestion: dict[str, Any], evaluation_rows: Any = None) -> list[dict[str, Any]]:
    timeline_rows = _congestion_time_profile_from_evaluation(evaluation_rows)
    if timeline_rows:
        return timeline_rows

    insights = profile.get("metrics_insights") or {}
    intersection = insights.get("intersection_saturation") if isinstance(insights, dict) else {}
    windows: list[dict[str, Any]] = []
    for kind, label in (("high_saturation_windows", "高饱和"), ("oversaturation_windows", "过饱和")):
        for window in _as_list((intersection or {}).get(kind)):
            if isinstance(window, dict):
                windows.append({**window, "程度标签": label})
    normalized_windows = []
    for window in windows:
        if not window.get("start") or not window.get("end"):
            continue
        start = _time_minutes(str(window.get("start") or ""))
        end = _time_minutes(str(window.get("end") or ""))
        if end <= start:
            end += 24 * 60
        if end <= start:
            continue
        normalized_windows.append({**window, "_start": start, "_end": end})
    normalized_windows.sort(key=lambda item: item["_start"])
    rows: list[dict[str, Any]] = []
    clusters: list[dict[str, Any]] = []
    for window in normalized_windows:
        if clusters and window["_start"] <= clusters[-1]["end"]:
            clusters[-1]["end"] = max(clusters[-1]["end"], window["_end"])
            clusters[-1]["windows"].append(window)
        else:
            clusters.append({"start": window["_start"], "end": window["_end"], "windows": [window]})

    for cluster in clusters:
        boundaries = sorted(
            set([cluster["start"], cluster["end"]] + [point for window in cluster["windows"] for point in (window["_start"], window["_end"])])
        )
        slices: list[dict[str, Any]] = []
        for index, start in enumerate(boundaries[:-1]):
            end = boundaries[index + 1]
            active = [window for window in cluster["windows"] if window["_start"] < end and window["_end"] > start]
            if end <= start or not active:
                continue
            peak = max(active, key=lambda item: (_severity_rank(str(item.get("程度标签") or "")), _as_float(item.get("peak"))))
            slices.append({"start": start, "end": end, "window": peak})
        for index, item in enumerate(slices):
            rows.append(
                {
                    "时段区间": f"{_minutes_label(item['start'])}-{_minutes_label(item['end'])}",
                    "拥堵程度": f"{_as_float(item['window'].get('peak')):.2f} / {item['window'].get('程度标签')}",
                    "发展阶段": _development_stage(index, len(slices), str(item["window"].get("程度标签") or "")),
                }
            )
    if rows:
        return rows[:8]
    return [
        {
            "时段区间": str(congestion.get("time_window") or ""),
            "拥堵程度": f"{_as_float((intersection or {}).get('peak_saturation') or 0):.2f} / {congestion.get('severity') or profile.get('pressure_level')}",
            "发展阶段": "上升期" if congestion.get("stage") == "萌芽期" else ("峰值平台期" if congestion.get("stage") == "扩散期" else "白平峰期"),
        }
    ]


def _severity_rank(label: str) -> int:
    if "过饱和" in label:
        return 3
    if "高饱和" in label:
        return 2
    if "拥堵" in label:
        return 1
    return 0


def _development_stage(index: int, total: int, severity: str) -> str:
    if total <= 1:
        return "峰值平台期" if "过饱和" in severity else "白平峰期"
    if index == 0:
        return "酝酿期"
    if index == total - 1:
        return "消散期"
    if index == 1 and total >= 4:
        return "上升期"
    return "峰值平台期"


def _minutes_label(minutes: int) -> str:
    minutes = max(0, min(24 * 60, minutes))
    if minutes == 24 * 60:
        return "24:00"
    minutes = minutes % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _queue_curve_rows(
    profile: dict[str, Any],
    queue_values: dict[str, Any],
    storage_ratio_values: dict[str, Any],
    raw_turn_perf: Any = None,
    supply_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    peak_rows = _queue_peak_rows(raw_turn_perf, supply_profile or {}, storage_ratio_values)
    if peak_rows:
        return peak_rows
    rows: list[dict[str, Any]] = []
    for period_name in PERIOD_ROW_ORDER:
        queue = _optional_float(queue_values.get(period_name))
        storage = _optional_float(storage_ratio_values.get(period_name))
        if queue is None and storage is None:
            continue
        rows.append(
            {
                "时段": period_name,
                "进口方向": "",
                "转向": "",
                "最大排队": queue,
                "存储比": storage,
                "描述": (
                    f"{period_name}最大排队约 {queue:.0f}m"
                    if queue is not None
                    else f"{period_name}有排队存储比记录"
                ),
            }
        )
    queue = (profile.get("metrics_insights") or {}).get("queue_delay") or {}
    if not rows and queue.get("peak_queue_m"):
        rows.append(
            {
                "时段": queue.get("peak_queue_time") or "峰值时段",
                "进口方向": "",
                "转向": "",
                "最大排队": queue.get("peak_queue_m"),
                "存储比": None,
                "描述": f"最大排队约 {_as_float(queue.get('peak_queue_m')):.0f}m",
            }
        )
    return rows


def _adjacent_relation_rows(supply: dict[str, Any], traffic: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_list(supply.get("adjacent_inter_spacing_detail")):
        if not isinstance(item, dict):
            continue
        spacing = _optional_float(item.get("spacing_m"))
        queue = _optional_float(traffic.get("queue_m"))
        relation = "上游" if item.get("relation_direction") == "upstream" else "下游"
        direction = _import_dir(item.get("dir4_label") or item.get("dir8_label"))
        rows.append(
            {
                "方向": direction,
                "关联方向": relation,
                "关联路口": item.get("adjacent_inter_name") or item.get("adjacent_inter_id") or item.get("upstream_inter_id") or "",
                "间距": spacing,
                "本方向最大排队": queue,
                "是否影响关联路口": queue >= spacing if queue is not None and spacing is not None else None,
            }
        )
    return rows


def _upstream_relations(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in relations if row.get("关联方向") == "上游" and str(row.get("方向") or "").strip()]


def _upstream_by_direction(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """List upstream intersection name and spacing per import direction for spatial summary."""
    rows: list[dict[str, Any]] = []
    for row in relations:
        if row.get("关联方向") != "上游":
            continue
        direction = str(row.get("方向") or "").strip()
        if not direction:
            continue
        rows.append(
            {
                "方向": direction,
                "上游路口": row.get("关联路口") or "",
                "距离": row.get("间距"),
            }
        )
    return sorted(rows, key=lambda item: DIRECTION_ORDER.get(str(item.get("方向") or ""), 99))


def _lane_totals(rows: Any) -> tuple[int, dict[str, int]]:
    by_dir = {"东": 0, "西": 0, "南": 0, "北": 0}
    seen: set[str] = set()
    total = 0
    for row in _as_list(rows):
        if not isinstance(row, dict):
            continue
        marker = str(row.get("link_id") or row.get("lane_id") or row)
        if marker in seen:
            continue
        seen.add(marker)
        count = int(_as_float(row.get("lane_num") or row.get("c_lane_num") or 0))
        if count <= 0 and row.get("lane_id"):
            count = 1
        total += count
        direction = _dir4_label(row.get("dir4_label") or row.get("dir8_label"))
        if direction in by_dir:
            by_dir[direction] += count
    return total, by_dir


def _scenario_comprehensive_tag(
    supply: dict[str, Any],
    profile: dict[str, Any],
    context: dict[str, Any],
    saturation: float,
) -> str:
    parts: list[str] = []
    if _as_float(supply.get("adjacent_inter_spacing_m")) and _as_float(supply.get("adjacent_inter_spacing_m")) <= _TH("static.adjacent_spacing_m"):
        parts.append("短间距串联")
    parts.extend(_poi_labels(context.get("poi"))[:2])
    demand = ((profile.get("metrics_insights") or {}).get("demand_pattern") or {})
    pattern = str(demand.get("demand_pattern") or "").strip()
    if "双峰" in pattern:
        parts.append("早晚双峰")
    status = _demand_status(saturation)
    if status:
        parts.append(f"{status}路口")
    if not parts:
        grade = str(supply.get("road_grade_combination") or "").strip()
        shape = _shape_label(supply.get("intersection_shape") or supply.get("inter_type"))
        parts = [item for item in (grade, shape, f"{status}路口") if item]
    return " + ".join(dict.fromkeys(parts))


def build_scenario_report(
    profile: dict[str, Any],
    task: dict[str, Any] | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standardized scene-cognition report without diagnosis or strategy content."""
    task = task or {}
    raw = raw or {}
    supply = profile.get("supply_profile") or {}
    demand = profile.get("demand_profile") or {}
    traffic = profile.get("traffic_state") or {}
    control = profile.get("control_profile") or {}
    congestion = profile.get("congestion_profile") or {}
    context = task.get("context") or {}
    period = _period_name(task, congestion)
    inbound_total, inbound_by_dir = _lane_totals(supply.get("approaches"))
    outbound_total, outbound_by_dir = _lane_totals(supply.get("exits"))
    saturation = _as_float(traffic.get("saturation"))
    capacity = _as_float(supply.get("capacity"))
    volume = _as_float(demand.get("volume"))
    turn_flows = _movement_period_table(raw.get("turn_flow"), supply, "turn_flow_total", "avg")
    if not turn_flows:
        turn_flows = _movement_table(demand.get("movement_volume"), supply, period, "")
    turn_flows = _complete_movement_rows(turn_flows, supply)
    turn_flow_proportions = _turn_flow_proportions(turn_flows, supply)
    if not turn_flow_proportions:
        turn_flow_proportions = _turn_proportions(demand, supply, period)
    flow_trace_rows = _flow_trace_rows(raw.get("flow_correlate"), turn_flows)
    turn_capacities = _lane_capacity_period_table(raw.get("lane_capacity"), supply)
    if not turn_capacities:
        turn_capacities = _movement_table(supply.get("movement_capacity"), supply, period, "")
    turn_capacities = _hourly_movement_period_rows(_complete_movement_rows(turn_capacities, supply), field="lane_capacity")
    turn_flows_hourly = _hourly_movement_period_rows(turn_flows, field="turn_flow_total")
    saturations = _movement_period_table(raw.get("turn_saturation"), supply, "turn_saturation", "max")
    if not saturations:
        saturations = _movement_table(traffic.get("movement_saturation"), supply, period, "")
    saturations = _complete_movement_rows(saturations, supply)

    raw_queue_values = _period_metric_values(raw.get("turn_perf"), "queue_len_max", "max")
    raw_delay_values = _period_metric_values(raw.get("turn_perf"), "delay_index", "avg")
    raw_stop_values = _period_metric_values(raw.get("turn_perf"), "stop_times", "avg")
    queue_values = _merge_period_values(raw_queue_values, _period_values(traffic.get("queue_m"), period))
    storage_ratio_values = _period_values(traffic.get("queue_storage_ratio"), period)
    delay_values = _merge_period_values(raw_delay_values, _period_values(traffic.get("avg_delay_s"), period))
    stop_values = _merge_period_values(raw_stop_values, _period_values(traffic.get("stop_count"), period))
    green_utilization = _optional_float(traffic.get("green_utilization"))
    empty_green_rate = _optional_float(traffic.get("empty_green_rate"))
    raw_green_values = _period_metric_values(raw.get("green_utilization"), "green_utilization", "avg")
    raw_green_values = {
        name: round(value * 100, 4) if value is not None else None
        for name, value in raw_green_values.items()
    }
    green_values = _merge_period_values(
        raw_green_values,
        _period_values(green_utilization * 100 if green_utilization is not None else None, period),
    )
    raw_empty_green_values = {
        name: round(max(0.0, 100 - value), 4) if value is not None else None
        for name, value in raw_green_values.items()
    }
    empty_green_values = _merge_period_values(
        raw_empty_green_values,
        _period_values(empty_green_rate * 100 if empty_green_rate is not None else None, period),
    )
    period_demands = _hourly_period_dict(_total_by_period(turn_flows_hourly), field="turn_flow_total")
    if all(value is None for value in period_demands.values()) and volume > 0:
        period_demands = _hourly_period_dict(_period_values(volume, period), field="turn_flow_total")
    period_capacities = _hourly_period_dict(_total_by_period(turn_capacities), field="lane_capacity")
    if all(value is None for value in period_capacities.values()) and capacity > 0:
        period_capacities = _hourly_period_dict(_period_values(capacity, period), field="lane_capacity")
    evaluation_rows = raw.get("inter_evaluation") or raw.get("evaluation")
    period_saturations = _period_metric_values(evaluation_rows, "saturation_max", "max")
    period_saturations = _merge_period_values(
        period_saturations,
        _merge_period_values(_ratio_by_period(period_demands, period_capacities), _period_values(saturation, period)),
    )
    imbalance_values = _merge_period_values(
        _period_metric_values(evaluation_rows, "unbalance_index", "max"),
        _period_values(traffic.get("imbalance_index"), period),
    )
    service_values = _period_los_values(evaluation_rows, traffic.get("los") or congestion.get("los"), period)
    signal_timing_features = _build_signal_timing_features(raw, control)
    flow_green_items = _TML.build_flow_green_items(demand.get("movement_volume") or {}, control.get("stage_detail") or [])
    if flow_green_items:
        signal_timing_features["flowGreenConsistency"] = _TML.flow_green_check(flow_green_items)
    demand_insights = ((profile.get("metrics_insights") or {}).get("demand_pattern") or {})
    daily_total = _optional_float(demand_insights.get("total_volume"))
    demand_period_rows = [
        {
            "时段": name,
            "状态判定": _demand_status(_as_float(period_saturations.get(name))) if period_saturations.get(name) is not None else "",
            "实际流量": period_demands.get(name),
            "剩余排队": _period_value(traffic.get("uncleared_cycles"), name, period),
            "估算总需求": period_demands.get(name),
        }
        for name in PERIOD_ROW_ORDER
    ]
    attraction_sources = _attraction_sources(context)
    adjacent_relations = _adjacent_relation_rows(supply, traffic)
    upstream_relations = _upstream_relations(adjacent_relations)
    upstream_by_direction = _upstream_by_direction(adjacent_relations)
    queue_curve_rows = _queue_curve_rows(profile, queue_values, storage_ratio_values, raw.get("turn_perf"), supply)
    queue_rows = _movement_period_table(raw.get("turn_perf"), supply, "queue_len_max", "max")
    delay_rows = _movement_period_table(raw.get("turn_perf"), supply, "delay_index", "avg")
    stop_rows = _movement_period_table(raw.get("turn_perf"), supply, "stop_times", "avg")
    green_utilization_rows = _movement_period_table(raw.get("green_utilization"), supply, "green_utilization", "avg")
    green_utilization_rows = [
        {**row, **{period_name: (round(_as_float(row.get(period_name)) * 100, 4) if row.get(period_name) is not None else None) for period_name in PERIOD_ROW_ORDER}}
        for row in green_utilization_rows
    ]
    queue_rows = [
        {**row, "平均排队长度": {name: row.get(name) for name in PERIOD_ROW_ORDER}, "最大排队长度": {name: row.get(name) for name in PERIOD_ROW_ORDER}, "排队存储比": storage_ratio_values}
        for row in queue_rows
    ]
    delay_rows = [
        {**row, "平均延误": {name: row.get(name) for name in PERIOD_ROW_ORDER}}
        for row in delay_rows
    ]
    stop_rows = [
        {**row, "平均停车次数": {name: row.get(name) for name in PERIOD_ROW_ORDER}}
        for row in stop_rows
    ]
    green_utilization_rows = [
        {**row, "绿灯利用率": {name: row.get(name) for name in PERIOD_ROW_ORDER}, "空放率": {name: (round(100 - _as_float(row.get(name)), 4) if row.get(name) is not None else None) for name in PERIOD_ROW_ORDER}}
        for row in green_utilization_rows
    ]
    movement_status_rows = _movement_status_rows(saturations, queue_rows, delay_rows, stop_rows, green_utilization_rows)
    overflow_rows = _TML.detect_overflows(
        queue_rows,
        adjacent_relations,
        queue_ratio_high=_TH("queue.queue_storage_ratio_high"),
    )
    conflict_rows = _TML.detect_stage_conflicts(control.get("stage_detail") or [])
    incident_impacts = [
        {"事件类型": "其他", "事件描述": str(item), "影响时段": str(context.get("time_window") or ""), "影响车道": "", "影响范围": None}
        for item in _as_list(context.get("events") or context.get("construction"))
        if item
    ]
    report = {
        "basicScenario": {
            "nodeAttributes": _keep_schema(
                {
                    "intersectionId": str(supply.get("intersection_id") or supply.get("name") or ""),
                    "roadGradeCombination": str(supply.get("road_grade_combination") or ""),
                    "roadFunction": _road_function_label(supply.get("intersection_importance")),
                    "geometryType": _shape_label(supply.get("intersection_shape") or supply.get("inter_type")),
                    "inboundLanes": {"total": inbound_total, **inbound_by_dir},
                    "outboundLanes": {"total": outbound_total, **outbound_by_dir},
                    "waitingArea": {"has": None, "type": ""},
                    "slowTrafficFacilities": {"bikeLane": "", "crosswalk": "", "safetyIsland": None},
                    "busFacilities": {"has": None, "location": "", "distanceToStopLine": None},
                    "turnProportions": turn_flow_proportions,
                }
            ),
            "spatialCoordination": {
                "upstreamIntersection": "、".join(str(row.get("关联路口")) for row in adjacent_relations if row.get("关联方向") == "上游" and row.get("关联路口")),
                "downstreamIntersection": "、".join(str(row.get("关联路口")) for row in adjacent_relations if row.get("关联方向") == "下游" and row.get("关联路口")),
                "upstreamByDirection": upstream_by_direction,
                "relations": upstream_relations,
                "seriesRelation": {
                    "type": "短间距串联" if _as_float(supply.get("adjacent_inter_spacing_m")) and _as_float(supply.get("adjacent_inter_spacing_m")) <= _TH("static.adjacent_spacing_m") else "独立路口",
                    "count": len(upstream_relations),
                },
                "storageSpace": {
                    "upstreamLength": _optional_float(supply.get("storage_m") or supply.get("adjacent_inter_spacing_m")),
                    "downstreamLength": _optional_float(supply.get("adjacent_inter_spacing_m")),
                },
            },
            "attractionSources": attraction_sources,
        },
        "flowAndDemand": {
            "turnFlows": turn_flows,
            "turnProportions": turn_flow_proportions,
            "timeDistribution": {
                **_time_distribution(task, profile, period, period_demands),
                "curveShape": demand_insights.get("demand_pattern") or _time_distribution(task, profile, period, period_demands).get("curveShape"),
                "flowConcentration": _flow_concentration_text(period_demands, daily_total),
                "mainSubFlow": _main_sub_flow_text(profile),
                "peakFlows": {
                    **_time_distribution(task, profile, period, period_demands).get("peakFlows", {}),
                    "全天总量": daily_total,
                },
            },
            "slowTraffic": [
                {
                    "时段": period or "",
                    "非机动车流量": _optional_float(demand.get("bike_volume")),
                    "行人流量": _optional_float(demand.get("pedestrian_volume")),
                    "过街方向": "",
                }
            ],
            "flowTrace": flow_trace_rows,
            "demandCharacteristics": demand_period_rows,
        },
        "capacityAndSupply": {
            "saturationFlowRates": _hourly_saturation_flow_rates(_saturation_flow_rates(raw.get("lane_saturation_headway"), supply)),
            "turnCapacities": turn_capacities,
            "totalCapacity": [
                {
                    "时段": name,
                    "路口总通行能力": period_capacities.get(name),
                    "实际总需求": period_demands.get(name),
                    "饱和度": period_saturations.get(name),
                }
                for name in PERIOD_ROW_ORDER
            ],
        },
        "operationalStatus": {
            "saturations": saturations,
            "queues": queue_rows or [
                {"进口道": "路口平均", "转向": "", "平均排队长度": queue_values, "最大排队长度": queue_values, "排队存储比": storage_ratio_values}
            ],
            "delaysAndStops": delay_rows or [
                {"进口道": "路口平均", "转向": "", "平均延误": delay_values, "平均停车次数": stop_values}
            ],
            "greenUtilization": green_utilization_rows or [
                {"进口道": "路口平均", "转向": "", "绿灯利用率": green_values, "空放率": empty_green_values}
            ],
            "movementStatus": movement_status_rows,
            "dataAvailability": _operational_data_availability(raw),
            "imbalanceAndService": [
                {
                    "时段": name,
                    "饱和度": period_saturations.get(name),
                    "失衡指数": imbalance_values.get(name),
                    "服务水平": service_values.get(name),
                }
                for name in PERIOD_ROW_ORDER
            ],
            "overflows": overflow_rows,
            "conflicts": conflict_rows,
        },
        "signalTimingFeatures": signal_timing_features,
        "spatiotemporalPatterns": {
            "congestionTimeProfile": _congestion_profile_rows(profile, congestion, evaluation_rows),
            "queueTimeCurve": {
                "早高峰": f"最大排队约 {traffic.get('queue_m', 0)}m" if period == "早高峰" else "",
                "晚高峰": f"最大排队约 {traffic.get('queue_m', 0)}m" if period == "晚高峰" else "",
                "白平峰": f"最大排队约 {traffic.get('queue_m', 0)}m" if period == "白平峰" else "",
                "queueSpillback": (
                    f"排队存储比约 {_as_float(traffic.get('queue_storage_ratio')):.2f}"
                    if _optional_float(traffic.get("queue_storage_ratio")) is not None
                    else ""
                ),
            },
            "queueTimeCurveRows": queue_curve_rows,
            "upstreamDownstream": {
                "relations": upstream_relations,
                "seriesPosition": "",
            },
            "attractionImpact": [
                {
                    "吸引源名称": item["name"],
                    "距离": _attraction_distance(item),
                    "影响方式": item.get("impactMethod", ""),
                    "对应时段": item.get("impactTime", ""),
                    "本路口对应状态": "",
                }
                for item in attraction_sources
            ],
            "incidentImpacts": incident_impacts,
        },
        "scenarioSummary": {
            "portrait": {
                "等级定位": str(supply.get("road_grade_combination") or supply.get("intersection_importance") or ""),
                "形态特征": _shape_label(supply.get("intersection_shape") or supply.get("inter_type")),
                "空间约束": _space_constraint_summary(profile, supply),
                "外部荷载": "、".join(
                    dict.fromkeys(
                        [
                            *[str(item.get("type") or item.get("name") or "") for item in attraction_sources if item.get("type") or item.get("name")],
                            *_poi_labels(context.get("poi")),
                        ]
                    )
                ),
                "流量规律": _flow_pattern_summary(profile, period_demands, volume),
                "转向特征": _turn_feature_summary(profile, turn_flow_proportions),
                "供需匹配": _supply_demand_summary(profile, saturation),
                "运行状态": _operational_status_summary(profile, traffic, congestion),
                "配时特征": signal_timing_features.get("summary") or "",
                "时间规律": _time_pattern_summary(profile),
            },
            "tags": {
                "static": " / ".join(_cn_label(item) for item in (supply.get("road_grade_combination"), _shape_label(supply.get("intersection_shape")), *(_as_list(supply.get("static_flags")))) if _cn_label(item)),
                "dynamic": f"{_demand_status(saturation)} / 压力{_pressure_label(profile.get('pressure_level'))}",
                "comprehensive": _scenario_comprehensive_tag(supply, profile, context, saturation),
            },
        },
    }
    return report


def build_traffic_context(task: dict[str, Any]) -> dict[str, Any]:
    metrics = task.get("metrics", {}) or {}
    scope = task.get("scope", {}) or {}
    context = task.get("context", {}) or {}
    level = str(scope.get("level", "intersection"))
    supply_profile = _build_supply_profile(task)
    demand_profile = _build_demand_profile(task)
    control_profile = _build_control_profile(task)
    traffic_state = _build_traffic_state(task, supply_profile)
    quality_tags, validation_errors = _quality_tags(task, traffic_state, control_profile)
    tags = _context_tags(context)
    pressure_level = _pressure_level(traffic_state)
    metrics_summary = {
        "volume": _as_float(metrics.get("volume")),
        "capacity": _as_float(metrics.get("capacity")),
        "saturation": traffic_state.get("saturation", 0),
        "avg_delay_s": traffic_state.get("avg_delay_s", 0),
        "queue_m": traffic_state.get("queue_m", 0),
        "spillback_risk": traffic_state.get("spillback_risk", 0),
        "empty_green_rate": traffic_state.get("empty_green_rate", 0),
        "green_wave_pass_rate": traffic_state.get("green_wave_pass_rate", 1.0),
        "imbalance_index": traffic_state.get("imbalance_index", 0),
        "los": traffic_state.get("los"),
    }
    evidence = [
        _evidence("volume", metrics_summary["volume"], "metrics", checklist_item_id="turn_flow"),
        _evidence("capacity", metrics_summary["capacity"], "metrics", checklist_item_id="lane_capacity"),
        _evidence("saturation", metrics_summary["saturation"], "derived", checklist_item_id="inter_evaluation"),
        _evidence("avg_delay_s", metrics_summary["avg_delay_s"], "metrics", checklist_item_id="turn_perf"),
        _evidence("queue_m", metrics_summary["queue_m"], "metrics", checklist_item_id="turn_perf"),
        _evidence("spillback_risk", metrics_summary["spillback_risk"], "metrics", checklist_item_id="turn_perf"),
        _evidence("imbalance_index", metrics_summary["imbalance_index"], "metrics", checklist_item_id="inter_evaluation"),
        _evidence("los", metrics_summary["los"], "metrics", checklist_item_id="inter_evaluation"),
    ]
    evidence_chain = _CFG.build_profile_evidence_refs({"evidence": evidence})
    uncertainty = [f"需补采或核验：{tag['value']}" for tag in quality_tags if tag["name"] == "missing_required_metric"]
    if any(tag["name"] == "missing_signal_profile" for tag in quality_tags):
        uncertainty.append("缺少信号控制画像，无法确认周期、相位相序和人工干预。")
    congestion_profile = _build_congestion_profile(task, traffic_state, demand_profile)
    profile = {
        "scene_type": _scene_type(level, context),
        "scope": scope,
        "pressure_level": pressure_level,
        "supply_profile": supply_profile,
        "demand_profile": demand_profile,
        "traffic_state": traffic_state,
        "control_profile": control_profile,
        "congestion_profile": congestion_profile,
        "context_tags": tags,
        "quality_tags": quality_tags,
        "metrics_summary": metrics_summary,
        "supply_demand_state": _supply_demand_state(supply_profile, demand_profile, traffic_state),
        "evidence": evidence,
        "evidence_chain": evidence_chain,
        "uncertainty": uncertainty,
        "validation_errors": validation_errors,
    }
    profile["scenario_report"] = build_scenario_report(profile, task)
    return profile
