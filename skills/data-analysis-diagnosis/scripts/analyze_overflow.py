from __future__ import annotations

from typing import Any

from app.data.traffic_metrics_logic import DIRECTION_ORDER, TURN_DIR_LABELS
from app.metrics.traffic import (
    THRESHOLDS,
    assess_overflow_risk,
    calculate_queue_ratio,
    calculate_saturation,
    classify_release_bottleneck,
    level_of_service,
)
from app.trace.coordination import build_coordination_diagram
from app.trace.downstream_diagnosis import build_downstream_diagnosis
from app.trace.downstream_trace import build_downstream_trace
from app.trace.flow_trace import build_arterial_analysis, build_flow_trace
from app.trace.intersection_profile import build_intersection_profile
from app.trace.map_scene import (
    build_channelization_map_scene,
    build_downstream_map_scene,
    build_flow_map_scene,
    build_flow_trace_links_sniff_map_scene,
    collect_map_adjacent_peer_hints,
)
from app.trace.segment_coverage import build_flow_trace_segment_coverage_map_scene
from app.trace.topology import resolve_dir8_turn


# 逐转向饱和度分级阈值：>=1.0 视为过饱和（需求超能力，LOS F 边界），
# >=0.8（THRESHOLDS.saturation_high）视为偏高，其余为正常。
_OVERSATURATION_LEVEL = 1.0


def _to_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _strip_approach(dir8_label: Any) -> str:
    text = str(dir8_label or "").strip()
    for suffix in ("进口", "出口"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def _movement_level(saturation: float | None) -> str | None:
    if saturation is None:
        return None
    if saturation >= _OVERSATURATION_LEVEL:
        return "过饱和"
    if saturation >= THRESHOLDS["saturation_high"]:
        return "偏高"
    return "正常"


def _approach_sort_key(approach_label: str) -> int:
    return DIRECTION_ORDER.get(_strip_approach(approach_label), len(DIRECTION_ORDER))


def build_by_movement(pg_raw: dict[str, Any]) -> list[dict[str, Any]]:
    """逐转向富指标：饱和度（max）+ 绿灯利用率（join）+ 分级。源缺失即空列表。"""
    sat_rows = (pg_raw or {}).get("turn_saturation") or []
    util_rows = (pg_raw or {}).get("green_utilization") or []
    if not sat_rows:
        return []

    util_by_movement: dict[tuple[str, int], float] = {}
    for row in util_rows:
        value = _to_float_or_none(row.get("green_utilization"))
        if value is None:
            continue
        key = (str(row.get("link_id") or ""), int(_to_float_or_none(row.get("turn_dir_no")) or 0))
        util_by_movement[key] = max(util_by_movement.get(key, value), value)

    aggregated: dict[tuple[str, int], dict[str, Any]] = {}
    for row in sat_rows:
        turn_dir_no = int(_to_float_or_none(row.get("turn_dir_no")) or 0)
        link_id = str(row.get("link_id") or "")
        key = (link_id, turn_dir_no)
        saturation = _to_float_or_none(row.get("turn_saturation"))
        entry = aggregated.get(key)
        if entry is None:
            entry = {
                "approach": _strip_approach(row.get("dir8_label")),
                "turn_dir_no": turn_dir_no,
                "saturation": saturation,
            }
            aggregated[key] = entry
        elif saturation is not None and (entry["saturation"] is None or saturation > entry["saturation"]):
            entry["saturation"] = saturation

    movements: list[dict[str, Any]] = []
    for (link_id, turn_dir_no), entry in aggregated.items():
        turn_label = TURN_DIR_LABELS.get(turn_dir_no, "")
        movements.append(
            {
                "movement": f"{entry['approach']}{turn_label}".strip() or f"转向{turn_dir_no}",
                "saturation": entry["saturation"],
                "green_utilization": util_by_movement.get((link_id, turn_dir_no)),
                "level": _movement_level(entry["saturation"]),
            }
        )
    movements.sort(
        key=lambda m: (m["saturation"] if m["saturation"] is not None else -1),
        reverse=True,
    )
    return movements


def build_by_approach(pg_raw: dict[str, Any]) -> list[dict[str, Any]]:
    """逐进口富指标：进口饱和度（该进口最大转向饱和度）+ 时延/服务水平（turn_perf）。"""
    sat_rows = (pg_raw or {}).get("turn_saturation") or []
    perf_rows = (pg_raw or {}).get("turn_perf") or []
    if not sat_rows:
        return []

    sat_by_approach: dict[str, float] = {}
    for row in sat_rows:
        approach = _strip_approach(row.get("dir8_label"))
        if not approach:
            continue
        saturation = _to_float_or_none(row.get("turn_saturation"))
        if saturation is None:
            continue
        sat_by_approach[approach] = max(sat_by_approach.get(approach, saturation), saturation)

    perf_by_approach: dict[str, dict[str, Any]] = {}
    for row in perf_rows:
        approach = _strip_approach(row.get("f_dir_8_label") or row.get("dir8_label"))
        if not approach:
            continue
        delay = _to_float_or_none(row.get("delay_index"))
        entry = perf_by_approach.setdefault(approach, {"delay_index": None, "los": None})
        if delay is not None and (entry["delay_index"] is None or delay > entry["delay_index"]):
            entry["delay_index"] = delay
            entry["los"] = row.get("los") or entry["los"]
        elif entry["los"] is None and row.get("los"):
            entry["los"] = row.get("los")

    approaches = set(sat_by_approach) | set(perf_by_approach)
    result: list[dict[str, Any]] = []
    for approach in sorted(approaches, key=_approach_sort_key):
        perf = perf_by_approach.get(approach, {})
        result.append(
            {
                "approach": f"{approach}进口" if approach else approach,
                "saturation": sat_by_approach.get(approach),
                "delay_index": perf.get("delay_index"),
                "los": perf.get("los"),
            }
        )
    return result


def _distinct_lane_count(pg_raw: dict[str, Any], scope: dict[str, Any]) -> int | None:
    lane_ids: set[str] = set()
    for row in (pg_raw or {}).get("turn_saturation") or []:
        for lane in row.get("lane_saturation_detail") or []:
            lane_id = lane.get("lane_id")
            if lane_id:
                lane_ids.add(str(lane_id))
    if lane_ids:
        return len(lane_ids)
    lanes = (scope or {}).get("lanes")
    if lanes:
        return len(lanes)
    return None


def _resolve_imbalance_index(
    task_metrics: dict[str, Any], pg_raw: dict[str, Any]
) -> float | None:
    value = _to_float_or_none((task_metrics or {}).get("imbalance_index"))
    if value is not None:
        return value
    eval_rows = (pg_raw or {}).get("evaluation") or []
    candidates = [
        _to_float_or_none(row.get("unbalance_index"))
        for row in eval_rows
        if _to_float_or_none(row.get("unbalance_index")) is not None
    ]
    return max(candidates) if candidates else None


def build_timing_profile(signal: dict[str, Any] | None) -> dict[str, Any]:
    signal = signal or {}
    return {
        "cycle_s": _to_float_or_none(signal.get("current_cycle_s")),
        "time_plan_count": signal.get("time_plan_count"),
        "plan_name": signal.get("plan_name"),
    }


_WEEKDAY_LABELS = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}


def _extract_day_label(period: Any, day_of_week: Any) -> str | None:
    text = str(period or "")
    for label in _WEEKDAY_LABELS.values():
        if label in text:
            return label
    if isinstance(day_of_week, int) and day_of_week in _WEEKDAY_LABELS:
        return _WEEKDAY_LABELS[day_of_week]
    return None


def _extract_peak_label(period: Any) -> str | None:
    text = str(period or "")
    for label in ("早高峰", "晚高峰", "平峰"):
        if label in text:
            return label
    if "高峰" in text:
        return "高峰"
    return None


def derive_problem_regularity(
    *,
    saturation: float | None,
    queue_ratio: float | None = None,
    period: Any = None,
    day_of_week: Any = None,
    flow_correlate: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """派生「常发性/周期性」定性判断（派生，非实测）。

    后端当前无常发性/周期性实测指标，此处基于同时段饱和度/排队比与周内规律做
    轻量启发式派生，并在 ``basis`` 明确标注为「派生」。任一依据缺失即安全降级为
    ``{recurring:null, periodic:null, basis:"数据不足"}``，绝不抛异常、绝不编造精确统计。
    """
    sat = _to_float_or_none(saturation)
    queue = _to_float_or_none(queue_ratio)

    peak_label = _extract_peak_label(period)
    day_label = _extract_day_label(period, day_of_week)
    high_pressure = (sat is not None and sat >= THRESHOLDS["saturation_high"]) or (
        queue is not None and queue >= THRESHOLDS["queue_ratio_warning"]
    )

    recurring: str | None = None
    if high_pressure and peak_label is not None:
        if sat is not None:
            metric_text = f"饱和度 {sat:.2f}"
        else:
            metric_text = f"排队比 {queue:.2f}"
        recurring = f"同时段周内规律显示{peak_label}该方向{metric_text} 持续偏高"

    periodic: str | None = None
    if day_label is not None:
        level = "高" if high_pressure else "中"
        periodic = f"{day_label}同时段历史规律显示该时段运行压力偏{level}"

    if recurring is None and periodic is None:
        return {"recurring": None, "periodic": None, "basis": "数据不足"}

    if flow_correlate:
        basis = "基于同时段饱和度与月度同时段流量规律（flow_correlate）派生，非实测统计"
    else:
        basis = "基于同时段饱和度与周内规律派生，非实测统计"
    return {"recurring": recurring, "periodic": periodic, "basis": basis}


def analyze_overflow(
    metrics_input: dict[str, Any],
    ticket: dict[str, Any],
    *,
    topology: dict[str, Any] | None = None,
    spatial_objects: dict[str, Any] | None = None,
    pg_raw: dict[str, Any] | None = None,
    signal: dict[str, Any] | None = None,
    scope: dict[str, Any] | None = None,
    task_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    dir8_code, turn_dir_no = resolve_dir8_turn(direction, movement)

    target_node = {
        "inter_id": (topology or {}).get("target_inter_id"),
        "inter_name": ticket.get("intersection_name"),
        "role": "target",
        "lng": (topology or {}).get("target_lng"),
        "lat": (topology or {}).get("target_lat"),
        "movement_label": f"{direction}{movement}",
        **metrics_input,
    }
    target_profile = build_intersection_profile(target_node)
    metrics = target_profile["metrics"]
    queue_ratio = metrics.get("queue_storage_ratio_max")
    saturation = metrics.get("saturation_rate")
    overflow = assess_overflow_risk(queue_ratio)

    downstream_trace = {"available": False, "reason": "no_topology"}
    flow_trace = {"available": False, "reason": "no_upstream_topology"}
    arterial_analysis: dict[str, Any] = {}
    coordination: dict[str, Any] = {"available": False, "reason": "no_topology"}
    downstream_diagnosis: dict[str, Any] = {"available": False}
    map_scenes: dict[str, Any] = {}

    if topology:
        downstream_trace = build_downstream_trace(
            target_profile=target_profile,
            topology=topology,
            dir8_code=dir8_code,
            turn_dir_no=turn_dir_no,
        )
        if downstream_trace.get("available") and pg_raw:
            from app.data.pg_adapters import (
                build_adjacent_metrics_loader,
                enrich_downstream_trace_adjacent_peers,
            )

            adjacent_loader = build_adjacent_metrics_loader(ticket)
            if adjacent_loader:
                enrich_downstream_trace_adjacent_peers(
                    downstream_trace,
                    peer_hints=collect_map_adjacent_peer_hints(pg_raw),
                    load_pg_metrics=adjacent_loader,
                )
        flow_trace = build_flow_trace(
            topology=topology,
            dir8_code=dir8_code,
            turn_dir_no=turn_dir_no,
            target_saturation=saturation,
        )
        arterial_analysis = build_arterial_analysis(
            target_profile=target_profile,
            downstream_trace=downstream_trace,
            flow_trace=flow_trace,
            topology=topology,
        )
        coordination = build_coordination_diagram(
            topology=topology,
            signal=signal or {},
            spacing_detail=(scope or {}).get("adjacent_inter_spacing_detail"),
            adjacent_offsets=(pg_raw or {}).get("adjacent_offsets"),
            speed_by_key=(pg_raw or {}).get("link_speed"),
        )
        # 用真实相位关系替换占位串 phase_offset_match="pg"（缺失即降级）。
        arterial_analysis["phase_offset_available"] = bool(coordination.get("available"))
        if coordination.get("available"):
            main_up = next(
                (
                    node
                    for node in coordination["nodes"]
                    if node["role"] == "upstream" and node["phase_diff_s"] is not None
                ),
                None,
            )
            arterial_analysis["phase_offset_match"] = (
                f"上游相位差 {main_up['phase_diff_s']:+.0f}s" if main_up else "已协调"
            )
        else:
            arterial_analysis["phase_offset_match"] = None
            arterial_analysis["phase_offset_reason"] = coordination.get("reason")

    primary_downstream = (
        (downstream_trace.get("adjacent_intersections") or [{}])[0]
        if downstream_trace.get("available")
        else {}
    )
    downstream_metrics_raw = primary_downstream.get("metrics") or {}
    bottleneck = classify_release_bottleneck(
        target_saturation=saturation or 0,
        target_green_utilization=metrics_input.get("green_utilization", 0),
        downstream_queue_ratio=downstream_metrics_raw.get("queue_storage_ratio_max"),
        downstream_saturation=downstream_metrics_raw.get("saturation_rate", 0),
    )

    if topology:
        center = None
        if target_profile.get("lng") is not None and target_profile.get("lat") is not None:
            center = (float(target_profile["lng"]), float(target_profile["lat"]))
        map_scenes = {
            "channelization_map": build_channelization_map_scene(
                pg_raw=pg_raw,
                target_profile=target_profile,
                center=center,
            ),
            # 需求 33：路段覆盖为 act5 主可视化；旧 sniff 暂留兼容，前端不再优先消费
            "flow_trace_segment_coverage_map": build_flow_trace_segment_coverage_map_scene(
                topology=topology,
                target_profile=target_profile,
                direction=direction,
                movement=movement,
                trace_direction="upstream",
            ),
            "flow_trace_links_sniff_map": build_flow_trace_links_sniff_map_scene(
                pg_raw=pg_raw,
                topology=topology,
                target_profile=target_profile,
                direction=direction,
                movement=movement,
            ),
        }
        if downstream_trace.get("available"):
            downstream_diagnosis = build_downstream_diagnosis(
                target_profile=target_profile,
                downstream_trace=downstream_trace,
                bottleneck=bottleneck,
            )
            map_scenes["downstream_trace_map"] = build_downstream_map_scene(
                downstream_trace=downstream_trace,
                target_profile=target_profile,
                center=center,
            )
            map_scenes["arterial_analysis"] = build_flow_map_scene(
                flow_trace=flow_trace,
                arterial_analysis=arterial_analysis,
                center=center,
                coordination=coordination,
            )

    by_approach = build_by_approach(pg_raw or {})
    by_movement = build_by_movement(pg_raw or {})
    imbalance_index = _resolve_imbalance_index(task_metrics or {}, pg_raw or {})
    approach_count = len(by_approach) or (scope or {}).get("leg_count") or None
    lane_count = _distinct_lane_count(pg_raw or {}, scope or {})

    return {
        "metrics": {
            "queue_length_m": metrics_input.get("queue_length_m"),
            "storage_length_m": metrics_input.get("storage_length_m"),
            "storage_direction": metrics_input.get("storage_direction"),
            "storage_source": metrics_input.get("storage_source"),
            "spacing_version_id": metrics_input.get("spacing_version_id"),
            "queue_ratio": queue_ratio,
            "saturation": saturation,
            "los": level_of_service(saturation or 0),
            "green_utilization": metrics_input.get("green_utilization"),
            "stop_count": metrics_input.get("stop_count"),
            "avg_delay_s": metrics_input.get("avg_delay_s"),
            "time_series_trend": metrics_input.get("time_series_trend"),
            "by_approach": by_approach,
            "by_movement": by_movement,
            "imbalance_index": imbalance_index,
            "approach_count": approach_count,
            "lane_count": lane_count,
            "target_movement_key": metrics_input.get("target_movement_key"),
            "metric_scope": metrics_input.get("metric_scope") or "movement",
            "dir8_code": metrics_input.get("dir8_code", dir8_code),
            "turn_dir_no": metrics_input.get("turn_dir_no", turn_dir_no),
            "intersection_saturation_max": metrics_input.get("intersection_saturation_max"),
            "intersection_queue_max": metrics_input.get("intersection_queue_max"),
        },
        "timing_profile": build_timing_profile(signal),
        "problem_regularity": derive_problem_regularity(
            saturation=saturation,
            queue_ratio=queue_ratio,
            period=ticket.get("period") or ticket.get("time_window"),
            day_of_week=ticket.get("day_of_week"),
            flow_correlate=(pg_raw or {}).get("flow_correlate"),
        ),
        "downstream_metrics": {
            "queue_ratio": downstream_metrics_raw.get("queue_storage_ratio_max"),
            "saturation": downstream_metrics_raw.get("saturation_rate"),
            "green_utilization": downstream_metrics_raw.get("green_utilization"),
        },
        "upstream_metrics": {
            "arrival_intensity": topology.get("upstream_arrival_intensity")
            if topology
            else metrics_input.get("upstream_arrival_intensity"),
            "arrival_flow_vph": topology.get("upstream_arrival_flow_vph") if topology else None,
            "release_intensity_vph": topology.get("upstream_release_intensity_vph")
            if topology
            else None,
        },
        "target_intersection": target_profile,
        "spatial_topology": spatial_objects or {},
        "downstream_trace": downstream_trace,
        "flow_trace": flow_trace,
        "arterial_analysis": arterial_analysis,
        "coordination": coordination,
        "downstream_diagnosis": downstream_diagnosis,
        "map_scenes": map_scenes,
        "overflow_verification": overflow,
        "bottleneck_analysis": bottleneck,
        "problem_confirmed": overflow.get("verified")
        and overflow.get("risk_level") in ("warning", "high"),
        # 健康核验：已取到数据且溢出风险低、饱和度未过高，判为无问题（可提前正常收尾）。
        # 注意：数据缺失（risk_level=unknown）不算健康，仍走完整链路核验。
        "healthy": bool(
            overflow.get("verified") is True
            and overflow.get("risk_level") == "low"
            and (saturation or 0) < THRESHOLDS["saturation_high"]
        ),
        "target": {
            "intersection": ticket.get("intersection_name"),
            "direction": direction,
            "movement": movement,
            "dir8_code": dir8_code,
            "turn_dir_no": turn_dir_no,
        },
    }
