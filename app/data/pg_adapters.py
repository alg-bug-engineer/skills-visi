"""Adapt PG task payloads for diagnosis and topology builders."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import re
import threading
import time
from typing import Any

from app.trace.geometry import orient_path, parse_linestring_wkt, parse_point_wkt
from app.trace.topology import (
    DIR8_ENTRY,
    DIRECTION_MOVEMENT,
    TURN_LABEL,
    exit_dir8_for_turn,
    movement_label,
    resolve_dir8_turn,
)

# dir8 进口方向码 → 方向字符串（直行口径），用于反查相邻路口承接进口方向。
_DIR8_TO_DIRECTION = {pair[0]: label for label, pair in DIRECTION_MOVEMENT.items()}

# A diagnosis may request the same intersection several times (one per receiving
# movement, then again while enriching adjacent peers).  The SQL payload contains
# all movements, so keep a short-lived, process-local snapshot and select the
# requested movement in memory.  The TTL is deliberately short: it only coalesces
# one pipeline run and does not turn operational traffic data into a long-lived
# cache.
_WEEKLY_METRICS_CACHE_TTL_S = 60.0
_weekly_metrics_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_weekly_metrics_inflight: dict[tuple[Any, ...], Future[dict[str, Any]]] = {}
_weekly_metrics_lock = threading.Lock()


def _direction_for_dir8(dir8: Any) -> str | None:
    try:
        return _DIR8_TO_DIRECTION.get(int(dir8))
    except (TypeError, ValueError):
        return None


def _receiving_dir8_from_exit(exit_dir8: Any) -> int | None:
    """本路口出口方向 → 下游路口承接进口方向（对向）。"""
    try:
        return (int(exit_dir8) + 4) % 8
    except (TypeError, ValueError):
        return None


def parse_day_of_week(ticket: dict[str, Any]) -> int:
    period = str(ticket.get("period") or "")
    if "周六" in period or "周日" in period:
        return 6
    return 5


def parse_time_hhmm(time_range: str | None) -> str | None:
    if not time_range:
        return None
    match = re.search(r"(\d{1,2})[:：](\d{2})", str(time_range))
    if not match:
        return None
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def _hhmm_to_step(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 12 + int(minute) // 5


def parse_time_step_range(time_range: str | None) -> tuple[int | None, int | None]:
    """Parse time_range like 17:30-18:30 into 5-min step_index bounds."""
    if not time_range:
        return None, None
    matches = re.findall(r"(\d{1,2})[:：](\d{2})", str(time_range))
    if not matches:
        return None, None
    steps = [_hhmm_to_step(f"{int(h):02d}:{m}") for h, m in matches]
    if len(steps) == 1:
        return steps[0], steps[0]
    lo, hi = min(steps[0], steps[1]), max(steps[0], steps[1])
    return lo, hi


# 历史 Case A 硬编码已迁移到 data/typical_intersections.json；保留空集合兼容旧引用。
CASE_A_APPROACH_QUEUE_TARGET_IDS = frozenset()


def _storage_for_dir8(
    *,
    dir8: int,
    scope: dict[str, Any] | None,
) -> tuple[float | None, dict[str, Any]]:
    """按目标进口 dir8 取库容，禁止借用其他进口间距。"""
    evidence: dict[str, Any] = {
        "storage_direction": DIR8_ENTRY.get(int(dir8)),
        "storage_source": None,
        "scope": "approach_storage",
        "available": False,
    }
    candidates: list[tuple[float, dict[str, Any]]] = []
    for item in (scope or {}).get("adjacent_inter_spacing_detail") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("link_role") or "").lower()
        if role and role != "entrance":
            continue
        item_dir = _row_dir8(item)
        if item_dir is None or int(item_dir) != int(dir8):
            continue
        spacing = _as_float_or_none(item.get("spacing_m") or item.get("length_m") or item.get("storage_m"))
        if spacing is None or spacing <= 0:
            continue
        candidates.append((float(spacing), item))
    if candidates:
        spacing, item = min(candidates, key=lambda pair: pair[0])
        evidence.update(
            {
                "available": True,
                "storage_source": "adjacent_inter_spacing_detail_min_entrance",
                "spacing_version_id": item.get("version_id") or item.get("link_id"),
                "link_id": item.get("link_id"),
                "candidate_count": len(candidates),
            }
        )
        return spacing, evidence
    evidence["reason"] = "no_matching_approach_storage"
    return None, evidence


def metrics_for_diagnosis(
    pg_metrics: dict[str, Any],
    ticket: dict[str, Any],
    *,
    approach_queue_avg: bool = False,
    queue_mode: str = "movement",
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    dir8, turn = resolve_dir8_turn(direction, movement)
    movement_key = f"d{dir8}_t{turn}"

    # 多 step 行取窗口峰值（与 by_movement / 筛选口径一致），禁止取首行低估
    target_sat = _max_row_metric(
        pg_metrics.get("turn_saturation_detail") or [],
        dir8,
        turn,
        ("turn_saturation", "saturation", "saturation_rate"),
    )
    if target_sat is None:
        target_sat = _pick_movement_metric(pg_metrics.get("movement_saturation") or {}, dir8, turn)
    saturation = float(target_sat) if target_sat is not None else None

    target_flow = _max_row_metric(
        pg_metrics.get("turn_flow_detail") or [],
        dir8,
        turn,
        ("turn_flow_total", "flow_vph", "volume_vph", "volume"),
    )
    if target_flow is None:
        target_flow = _pick_movement_metric(pg_metrics.get("movement_volume") or {}, dir8, turn)
    volume = float(target_flow) if target_flow is not None else None

    selection_policy = pg_metrics.get("metric_selection_policy")
    peak_demo = selection_policy == "cross_week_movement_peak"
    mean_demo = selection_policy == "cross_week_movement_mean"
    configured_queue_field = str(pg_metrics.get("target_queue_field") or "").strip()
    if configured_queue_field not in {"queue_len_avg", "queue_len_max"}:
        configured_queue_field = "queue_len_avg"
    if approach_queue_avg or peak_demo or mean_demo:
        queue_fields = (configured_queue_field,)
    else:
        queue_fields = ("queue_len_avg", "queue_len_max")
    queue_fn = _max_row_metric if peak_demo else _mean_row_metric
    queue_m = queue_fn(pg_metrics.get("turn_perf_detail") or [], dir8, turn, queue_fields)
    if queue_m is None and configured_queue_field != "queue_len_max":
        queue_m = queue_fn(pg_metrics.get("turn_perf_detail") or [], dir8, turn, ("queue_len_max",))
    movement_queue_m = queue_m
    queue_source = "movement_window_mean"
    if queue_mode == "intersection_max_proxy":
        intersection_queue_m = _as_float_or_none(pg_metrics.get("queue_m"))
        if intersection_queue_m is not None:
            queue_m = intersection_queue_m
            queue_source = "intersection_window_max_proxy"
    queue_available = queue_m is not None

    storage_m, storage_evidence = _storage_for_dir8(dir8=dir8, scope=scope)
    storage_available = storage_m is not None and storage_m > 0

    util = _pick_row_metric(
        pg_metrics.get("turn_perf_detail") or [],
        dir8,
        turn,
        ("green_utilization",),
    )
    if util is None:
        util = _as_float_or_none(pg_metrics.get("green_utilization"))

    if saturation is not None and volume is not None and saturation > 0:
        capacity = volume / saturation
    else:
        capacity = _as_float_or_none(pg_metrics.get("capacity")) or 0.0

    return {
        "queue_length_m": float(queue_m) if queue_available else None,
        "storage_length_m": float(storage_m) if storage_available else None,
        "storage_direction": storage_evidence.get("storage_direction"),
        "storage_source": storage_evidence.get("storage_source"),
        "spacing_version_id": storage_evidence.get("spacing_version_id"),
        "volume_vph": float(volume) if volume is not None else 0.0,
        "capacity_vph": float(capacity) if capacity else 0.0,
        "saturation": saturation if saturation is not None else 0.0,
        "saturation_rate": saturation if saturation is not None else 0.0,
        "green_utilization": float(util) if util is not None else 0.0,
        "stop_count": float(_as_float_or_none(pg_metrics.get("stop_count")) or 0),
        "avg_delay_s": float(_as_float_or_none(pg_metrics.get("avg_delay_s")) or 0),
        "time_series_trend": "pg_loaded",
        "upstream_arrival_intensity": (
            "high" if saturation is not None and saturation >= 0.8 else "medium"
        ),
        "target_movement_key": movement_key,
        "metric_scope": "movement",
        "queue_statistic": (
            "cross_week_window_peak" if peak_demo
            else "cross_week_window_mean" if mean_demo
            else queue_source
        ),
        "queue_source": queue_source,
        "queue_is_direction_proxy": queue_source == "intersection_window_max_proxy",
        "movement_queue_length_m": (
            float(movement_queue_m) if movement_queue_m is not None else None
        ),
        "saturation_statistic": "window_peak",
        "statistic_scope": "selected_typical_day",
        "selected_day_of_week": pg_metrics.get("selected_day_of_week"),
        "metric_selection_policy": pg_metrics.get("metric_selection_policy"),
        "target_queue_field": configured_queue_field if (peak_demo or mean_demo or approach_queue_avg) else None,
        "typical_profile_id": pg_metrics.get("typical_profile_id"),
        "typical_profile_label": pg_metrics.get("typical_profile_label"),
        "queue_safety_peak_m": pg_metrics.get("selected_movement_queue_peak_m"),
        "queue_safety_peak_ratio": (
            round(float(pg_metrics["selected_movement_queue_peak_m"]) / float(storage_m), 4)
            if pg_metrics.get("selected_movement_queue_peak_m") is not None and storage_available
            else None
        ),
        "dir8_code": dir8,
        "turn_dir_no": turn,
        "metrics_available": saturation is not None,
        "queue_available": queue_available,
        "storage_available": storage_available,
        "storage_evidence": storage_evidence,
        # 审计：保留原始路口级 MAX；仅在显式 proxy 模式下覆盖目标展示排队。
        "intersection_saturation_max": _as_float_or_none(pg_metrics.get("saturation")),
        "intersection_queue_max": _as_float_or_none(pg_metrics.get("queue_m")),
    }



def _target_center(inter: dict[str, Any]) -> tuple[float | None, float | None]:
    """从 dim_inter_info.geom_center（WKT POINT）解析目标路口中心。"""
    point = parse_point_wkt(inter.get("geom_center"))
    if point:
        return point[0], point[1]
    return None, None


def _coverage_index(
    correlate_rows: list[dict[str, Any]], dir8_code: int, turn_dir_no: int
) -> dict[tuple[str, str], float]:
    """构建 (trace_type, cor_inter_id) → 覆盖率索引（限定基准进口方向）。

    上游来向（PG trace_type=DOWNSTREAM）采用同进口物理合流口径；下游去向
    （PG trace_type=UPSTREAM）保持目标转向的一跳严格口径。
    """
    best: dict[tuple[str, str], float] = {}
    for row in correlate_rows or []:
        try:
            row_dir8 = int(row.get("f_dir8_no"))
        except (TypeError, ValueError):
            continue
        if row_dir8 != int(dir8_code):
            continue
        cor_id = str(row.get("cor_inter_id") or "")
        if not cor_id:
            continue
        trace_type = str(row.get("trace_type") or "").upper()
        try:
            row_turn = int(row.get("turn_dir_no"))
            share = float(row.get("flow_share_ratio") or row.get("share_pct") or 0)
        except (TypeError, ValueError):
            continue
        # 上/下游均按目标转向约束，取 max 不跨转向累加（需求 34 G4 守恒）
        if row_turn != int(turn_dir_no):
            continue
        if share < 0 or share > 100:
            continue
        key = (trace_type, cor_id)
        prev = best.get(key)
        if prev is None or share > prev:
            best[key] = round(share, 2)
    return best


def _match_coverage(
    coverage: dict[tuple[str, str], float], preferred_trace: str, cor_id: str
) -> float | None:
    """按溯源类型匹配真实覆盖率；优先 preferred_trace，缺失回退另一类型。"""
    if not cor_id:
        return None
    other = "DOWNSTREAM" if preferred_trace == "UPSTREAM" else "UPSTREAM"
    for trace_type in (preferred_trace, other):
        val = coverage.get((trace_type, cor_id))
        if val is not None:
            return val
    return None


def _downstream_correlate_trace_type(turn_dir_no: int) -> str:
    """Align with map_scene._scene_trace_type for outgoing corridors."""
    return "UPSTREAM" if int(turn_dir_no) == 2 else "DOWNSTREAM"


def _best_downstream_correlate_shares(
    correlate_rows: list[dict[str, Any]], dir8_code: int, turn_dir_no: int
) -> dict[str, float]:
    trace_type = _downstream_correlate_trace_type(turn_dir_no)
    best: dict[str, float] = {}
    for row in correlate_rows or []:
        try:
            if int(row.get("f_dir8_no")) != int(dir8_code):
                continue
            if int(row.get("turn_dir_no")) != int(turn_dir_no):
                continue
            if str(row.get("trace_type") or "").upper() != trace_type:
                continue
            cor_id = str(row.get("cor_inter_id") or "")
            if not cor_id:
                continue
            share = float(row.get("flow_share_ratio") or row.get("share_pct") or 0)
        except (TypeError, ValueError):
            continue
        best[cor_id] = max(best.get(cor_id, 0.0), share)
    return {cor_id: round(share, 2) for cor_id, share in best.items()}


def _append_downstream_from_correlate_exit_links(
    *,
    downstream_nodes: list[dict[str, Any]],
    seen_down: set[str],
    geom_rows: list[dict[str, Any]],
    correlate_rows: list[dict[str, Any]],
    coverage: dict[tuple[str, str], float],
    dir8_code: int,
    turn_dir_no: int,
    target_lng: float | None,
    target_lat: float | None,
    max_nodes: int = 3,
) -> None:
    """When compass exit_dir8 misses real exit links, bind downstream via flow_correlate + exit geom."""
    if downstream_nodes:
        return
    shares = _best_downstream_correlate_shares(correlate_rows, dir8_code, turn_dir_no)
    if not shares:
        return
    preferred_trace = _downstream_correlate_trace_type(turn_dir_no)
    exit_by_adj: dict[str, list[dict[str, Any]]] = {}
    for row in geom_rows:
        if str(row.get("relation_direction") or "").lower() != "downstream":
            continue
        adj_id = str(row.get("adjacent_inter_id") or "")
        if adj_id:
            exit_by_adj.setdefault(adj_id, []).append(row)

    for cor_id, correlate_share in sorted(shares.items(), key=lambda item: -item[1]):
        if len(downstream_nodes) >= max_nodes:
            break
        if cor_id in seen_down:
            continue
        candidates = exit_by_adj.get(cor_id)
        if not candidates:
            continue
        row = max(candidates, key=lambda item: float(item.get("length_m") or 0))
        try:
            link_dir8 = int(row.get("dir8_code"))
        except (TypeError, ValueError):
            link_dir8 = None
        seen_down.add(cor_id)
        path = parse_linestring_wkt(row.get("geom_wkt"))
        oriented = orient_path(path, target_lng, target_lat, row.get("adjacent_lng"), row.get("adjacent_lat"))
        share = _match_coverage(coverage, preferred_trace, cor_id) or correlate_share
        recv = _receiving_dir8_from_exit(link_dir8)
        downstream_nodes.append(
            {
                "inter_id": cor_id or None,
                "inter_name": row.get("adjacent_inter_name") or "下游信控节点",
                "role": "downstream",
                "lng": row.get("adjacent_lng"),
                "lat": row.get("adjacent_lat"),
                "share_pct": share,
                "link_id": row.get("link_id"),
                # 出口 link 的 dir8 是本路口驶出方向；下游承接进口为其对向
                "receiving_dir8": recv,
                "receiving_turn_dir_no": turn_dir_no,
                "receiving_label": movement_label(recv, turn_dir_no) if recv is not None else None,
                "path": oriented,
                "path_source": "link_geom" if len(oriented) >= 2 else "correlate_exit",
            }
        )


def _downstream_nodes_for_turn(
    *,
    geom_rows: list[dict[str, Any]],
    correlate_rows: list[dict[str, Any]],
    dir8_code: int,
    turn_dir_no: int,
    target_lng: float | None,
    target_lat: float | None,
) -> list[dict[str, Any]]:
    """Build one-hop downstream nodes for one target-approach movement from real PG rows."""
    exit_dir8 = exit_dir8_for_turn(dir8_code, turn_dir_no)
    if exit_dir8 is None:
        return []

    coverage = _coverage_index(correlate_rows, dir8_code, turn_dir_no)
    preferred_trace = _downstream_correlate_trace_type(turn_dir_no)
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in geom_rows:
        try:
            link_dir8 = int(row.get("dir8_code"))
        except (TypeError, ValueError):
            continue
        if str(row.get("relation_direction") or "").lower() != "downstream":
            continue
        if link_dir8 != exit_dir8:
            continue

        cor_id = str(row.get("adjacent_inter_id") or "")
        # 同一下游可能有多条平行出口 link；一跳分析按相邻路口去重。
        if cor_id and cor_id in seen:
            continue
        seen.add(cor_id)
        adj_lng = row.get("adjacent_lng")
        adj_lat = row.get("adjacent_lat")
        path = parse_linestring_wkt(row.get("geom_wkt"))
        receiving_dir8 = _receiving_dir8_from_exit(exit_dir8)
        nodes.append(
            {
                "inter_id": cor_id or None,
                "inter_name": row.get("adjacent_inter_name") or "下游信控节点",
                "role": "downstream",
                "lng": adj_lng,
                "lat": adj_lat,
                "share_pct": _match_coverage(coverage, preferred_trace, cor_id),
                "link_id": row.get("link_id"),
                "origin_dir8": dir8_code,
                "origin_turn_dir_no": turn_dir_no,
                "origin_movement": movement_label(dir8_code, turn_dir_no),
                "exit_dir8": exit_dir8,
                "receiving_dir8": receiving_dir8,
                "receiving_turn_dir_no": turn_dir_no,
                "receiving_label": movement_label(receiving_dir8, turn_dir_no),
                "path": orient_path(path, target_lng, target_lat, adj_lng, adj_lat),
                "path_source": "link_geom" if len(path) >= 2 else "none",
            }
        )

    _append_downstream_from_correlate_exit_links(
        downstream_nodes=nodes,
        seen_down=seen,
        geom_rows=geom_rows,
        correlate_rows=correlate_rows,
        coverage=coverage,
        dir8_code=dir8_code,
        turn_dir_no=turn_dir_no,
        target_lng=target_lng,
        target_lat=target_lat,
    )
    for node in nodes:
        node.setdefault("origin_dir8", dir8_code)
        node.setdefault("origin_turn_dir_no", turn_dir_no)
        node.setdefault("origin_movement", movement_label(dir8_code, turn_dir_no))
        node.setdefault("exit_dir8", exit_dir8)
    nodes.sort(key=lambda node: (node.get("share_pct") or -1), reverse=True)
    return nodes


def topology_from_pg_raw(raw: dict[str, Any], ticket: dict[str, Any], inter: dict[str, Any]) -> dict[str, Any]:
    """基于真实路网几何（dim_link_info.geom）构建上下游一跳拓扑。

    方向为几何真源：problem 进口的 entrance link → 上游来向；对应转向的 exit link →
    下游去向。占比取自 flow_correlate（真实统计），缺失则为空。严禁合成坐标/折线。
    """
    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    dir8_code, turn_dir_no = resolve_dir8_turn(direction, movement)
    exit_dir8 = exit_dir8_for_turn(dir8_code, turn_dir_no)

    target_lng, target_lat = _target_center(inter)

    geom_rows = raw.get("trace_geometry") or []
    correlate_rows = raw.get("flow_correlate") or []
    coverage = _coverage_index(correlate_rows, dir8_code, turn_dir_no)

    upstream_nodes: list[dict[str, Any]] = []
    seen_up: set[str] = set()

    for row in geom_rows:
        try:
            link_dir8 = int(row.get("dir8_code"))
        except (TypeError, ValueError):
            continue
        relation = str(row.get("relation_direction") or "")
        cor_id = str(row.get("adjacent_inter_id") or "")
        cor_name = row.get("adjacent_inter_name")
        adj_lng = row.get("adjacent_lng")
        adj_lat = row.get("adjacent_lat")
        path = parse_linestring_wkt(row.get("geom_wkt"))

        if relation == "upstream" and link_dir8 == dir8_code:
            if cor_id and cor_id in seen_up:
                continue
            seen_up.add(cor_id)
            share = _match_coverage(coverage, "UPSTREAM", cor_id)
            oriented = orient_path(path, adj_lng, adj_lat, target_lng, target_lat)
            upstream_nodes.append(
                {
                    "upstream_inter_id": cor_id or None,
                    "upstream_inter_name": cor_name or "上一路口",
                    "upstream_lng": adj_lng,
                    "upstream_lat": adj_lat,
                    "vehicles_base": 100,
                    "link_id": row.get("link_id"),
                    "path": oriented,
                    "path_source": "link_geom" if len(oriented) >= 2 else "none",
                    "upstream_movements": [
                        {
                            "turn": movement,
                            "feed_direction": f"{direction}{movement}",
                            "share_pct": share,
                            "vehicles_of_100": int(round(share)) if share is not None else None,
                            "raw_coverage": share,
                        }
                    ],
                }
            )
    # 目标进口按左/直/右同时构建一跳去向；selected ``downstream_nodes`` 继续保留
    # 票据转向口径，避免现有诊断/配时护栏被其他转向污染。
    downstream_turn_nodes: list[dict[str, Any]] = []
    for approach_turn in (1, 2, 3):
        downstream_turn_nodes.extend(
            _downstream_nodes_for_turn(
                geom_rows=geom_rows,
                correlate_rows=correlate_rows,
                dir8_code=dir8_code,
                turn_dir_no=approach_turn,
                target_lng=target_lng,
                target_lat=target_lat,
            )
        )
    downstream_nodes = [
        node
        for node in downstream_turn_nodes
        if int(node.get("origin_turn_dir_no") or 0) == int(turn_dir_no)
    ]

    # 主来向占比降序（真实值优先），无占比排后
    upstream_nodes.sort(
        key=lambda n: (n["upstream_movements"][0].get("share_pct") or -1), reverse=True
    )
    downstream_nodes.sort(key=lambda n: (n.get("share_pct") or -1), reverse=True)

    volume_vph = float(metrics_for_diagnosis(raw.get("metrics") or {}, ticket).get("volume_vph") or 0)
    has_geometry = bool(upstream_nodes or downstream_turn_nodes)

    from app.data.ticket_nlu_schema import (
        FLOW_TRACE_PERIOD_FILTER_CAVEAT,
        infer_diagnosis_period_type,
    )

    period_type = infer_diagnosis_period_type(ticket)

    return {
        "target_inter_id": str(inter.get("inter_id") or ticket.get("inter_id") or ""),
        "target_inter_name": inter.get("inter_name") or ticket.get("intersection_name"),
        "target_lng": target_lng,
        "target_lat": target_lat,
        "dir8_code": dir8_code,
        "turn_dir_no": turn_dir_no,
        "exit_dir8": exit_dir8,
        "period_type": period_type,
        "day_basis": "工作日",
        "upstream_arrival_flow_vph": volume_vph,
        "upstream_release_intensity_vph": volume_vph * 0.95,
        "upstream_arrival_intensity": "high",
        "phase_offset_match": None,
        "upstream_nodes": upstream_nodes,
        "downstream_nodes": downstream_nodes,
        "downstream_turn_nodes": downstream_turn_nodes,
        "geometry_source": "dim_link_info.geom" if has_geometry else "unavailable",
        "caveat": "PG 拓扑：几何取自 dim_link_info.geom，占比取自 flow_correlate",
        "flow_trace_period_caveat": FLOW_TRACE_PERIOD_FILTER_CAVEAT,
    }


_ADJ_METRIC_FIELDS = (
    "queue_length_m",
    "movement_queue_length_m",
    "queue_statistic",
    "queue_source",
    "queue_is_direction_proxy",
    "selected_day_of_week",
    "metric_selection_policy",
    "queue_safety_peak_m",
    "queue_safety_peak_ratio",
    "storage_length_m",
    "volume_vph",
    "capacity_vph",
    "saturation",
    "saturation_rate",
    "green_utilization",
    "stop_count",
    "avg_delay_s",
)


def _pg_metrics_has_dynamic_data(pg_metrics: dict[str, Any] | None) -> bool:
    """PG 聚合指标是否含真实动态运行数据（非仅缺省 0 / 静态渠化）。"""
    if not pg_metrics:
        return False
    if pg_metrics.get("has_dynamic_metrics") is False:
        return False
    if pg_metrics.get("has_dynamic_metrics") is True:
        return True
    if pg_metrics.get("turn_saturation_detail") or pg_metrics.get("turn_flow_detail"):
        return True
    if float(pg_metrics.get("volume_vph") or pg_metrics.get("volume") or 0) > 0:
        return True
    if float(pg_metrics.get("queue_length_m") or pg_metrics.get("queue_m") or 0) > 0:
        return True
    if float(pg_metrics.get("green_utilization") or 0) > 0:
        return True
    return False


def enrich_downstream_metrics(
    topology: dict[str, Any],
    *,
    load_pg_metrics: Any,
    target_inter_id: str | None = None,
    approach_queue_avg: bool | None = None,
) -> dict[str, Any]:
    """为下游相邻节点注入真实运行指标（修复 BUG-004）。

    PG 拓扑构建仅写入几何/占比，未加载相邻路口自身指标，导致下游排队/饱和度恒为 0。
    这里按每个下游节点的承接进口方向 ``receiving_dir8`` 载入其真实 PG 指标并绑定。

    参数:
        load_pg_metrics: ``callable(inter_id) -> dict | None``，返回相邻路口原始
            聚合指标（``metrics_for_diagnosis`` 入参）；无数据返回 ``None``。
        approach_queue_avg: 典型路口策略可强制按接收进口均值排队判定。

    行为（rule 14/16）：取到真实指标 → ``metrics_available=True``；取不到 →
    ``metrics_available=False`` + ``metrics_reason``，绝不静默回落 0。

    典型路口 profile 可要求下游接收进口按 queue_len_avg 均值判定；
    未命中 profile 时，若上游已注入 cross_week_mean 策略，同样按均值字段聚合。
    """
    use_approach_queue = bool(approach_queue_avg) or (
        str(target_inter_id or "") in CASE_A_APPROACH_QUEUE_TARGET_IDS
    )
    # ``downstream_nodes`` 是目标转向兼容视图，元素与全转向列表共享引用；按对象
    # 去重可确保左/直/右全部富化，同时避免目标转向重复查询 PG。
    downstream_candidates = [
        *(topology.get("downstream_nodes") or []),
        *(topology.get("downstream_turn_nodes") or []),
    ]
    seen_nodes: set[int] = set()
    nodes_to_load: list[tuple[dict[str, Any], str, str | None, str]] = []
    for node in downstream_candidates:
        if not isinstance(node, dict):
            continue
        node_ref = id(node)
        if node_ref in seen_nodes:
            continue
        seen_nodes.add(node_ref)
        inter_id = node.get("inter_id")
        if not inter_id:
            node["metrics_available"] = False
            node["metrics_reason"] = "下游节点缺 inter_id，无法加载指标"
            continue
        receiving_dir8 = node.get("receiving_dir8")
        direction = _direction_for_dir8(receiving_dir8)
        movement = TURN_LABEL.get(int(node.get("receiving_turn_dir_no") or 2), "直行")
        nodes_to_load.append((node, str(inter_id), direction, movement))

    def _load_one(inter_id: str, direction: str | None, movement: str):
        try:
            return load_pg_metrics(inter_id, direction=direction, movement=movement), None
        except TypeError:
            try:
                return load_pg_metrics(inter_id), None
            except Exception as exc:  # noqa: BLE001
                return None, exc
        except Exception as exc:  # noqa: BLE001
            return None, exc

    # Different downstream intersections are independent.  Loading them in
    # parallel changes latency from the sum of remote round trips to roughly the
    # slowest node; duplicate movements share the weekly single-flight cache.
    loaded_by_node: dict[int, tuple[dict[str, Any] | None, Exception | None]] = {}
    if nodes_to_load:
        with ThreadPoolExecutor(max_workers=min(4, len(nodes_to_load))) as pool:
            futures = {
                id(node): pool.submit(_load_one, inter_id, direction, movement)
                for node, inter_id, direction, movement in nodes_to_load
            }
            loaded_by_node = {node_id: future.result() for node_id, future in futures.items()}

    for node, _inter_id, direction, _movement in nodes_to_load:
        pg_metrics, load_error = loaded_by_node[id(node)]
        if load_error is not None:
            node["metrics_available"] = False
            node["metrics_reason"] = f"下游路口指标加载失败：{load_error}"
            continue
        if not pg_metrics:
            node["metrics_available"] = False
            node["metrics_reason"] = "下游路口 PG 指标缺失"
            continue
        if not _pg_metrics_has_dynamic_data(pg_metrics):
            node["metrics_available"] = False
            node["metrics_reason"] = "相邻路口 PG 动态指标缺失（该时段无饱和度/排队/流量，仅有配时或绿灯利用率不足以判断承接）"
            continue
        receiving_turn = node.get("receiving_turn_dir_no")
        try:
            receiving_turn = int(receiving_turn)
        except (TypeError, ValueError):
            receiving_turn = 2
        adj_ticket = {
            "direction": direction or "东向西",
            "movement": TURN_LABEL.get(receiving_turn, "直行"),
        }
        mean_policy = str(pg_metrics.get("metric_selection_policy") or "") == "cross_week_movement_mean"
        metrics = metrics_for_diagnosis(
            pg_metrics,
            adj_ticket,
            approach_queue_avg=use_approach_queue or mean_policy,
            scope=pg_metrics if isinstance(pg_metrics.get("adjacent_inter_spacing_detail"), list) else None,
        )
        node["metrics_receiving_direction"] = direction
        node["metrics_receiving_turn_dir_no"] = receiving_turn
        # 饱和度未绑定到承接进口时，禁止用 0.0 冒充「空闲」（与嗅探/筛选 MAX 对不上的主因）
        sat_ok = bool(metrics.get("metrics_available"))
        if not sat_ok:
            node["metrics_available"] = False
            node["metrics_reason"] = (
                f"下游承接进口（{direction or '未知方向'}{TURN_LABEL.get(receiving_turn, '直行')}）"
                "该时段无转向饱和度，"
                "不可用 0 代替；请核对日型/时段或嗅探口径"
            )
            # 仍透出排队等非饱和字段供参考，但不宣称指标齐全
            for field in (
                "queue_length_m",
                "storage_length_m",
                "volume_vph",
                "avg_delay_s",
                "queue_statistic",
                "metric_selection_policy",
                "queue_safety_peak_m",
                "queue_safety_peak_ratio",
            ):
                if metrics.get(field) is not None:
                    node[field] = metrics[field]
            continue
        for field in _ADJ_METRIC_FIELDS:
            if metrics.get(field) is not None:
                node[field] = metrics[field]
        node["metrics_available"] = True
        node["metrics_source"] = "pg_adjacent"
        node["metrics_queue_mode"] = "receiving_approach_movement"
        if use_approach_queue:
            node["metrics_queue_field"] = "queue_len_avg"
    return topology


def build_adjacent_metrics_loader(ticket: dict[str, Any]):
    """Return ``load_pg_metrics(inter_id)`` when PG is configured; else ``None``."""
    try:
        from app.config import get_settings
        from app.data.typical_intersection_profiles import (
            metric_options_from_profile,
            resolve_typical_profile,
        )
    except Exception:
        return None

    settings = get_settings()
    if not settings.pg_dsn:
        return None

    opts = metric_options_from_profile(resolve_typical_profile(ticket))

    def _load(
        inter_id: str,
        *,
        direction: str | None = None,
        movement: str | None = None,
    ) -> dict[str, Any] | None:
        return load_cross_week_mean_movement_metrics(
            inter_id=str(inter_id),
            direction=direction or ticket.get("direction") or "东向西",
            movement=movement or ticket.get("movement") or "直行",
            time_range=ticket.get("time_range"),
            queue_field=str(opts.get("downstream_queue_field") or "queue_len_avg"),
            peak_disclose_field=str(
                opts.get("downstream_peak_disclose_field") or "queue_len_avg"
            ),
            typical_profile_id=opts.get("typical_profile_id"),
            typical_profile_label=opts.get("typical_profile_label"),
        )

    return _load


def _load_cross_week_metrics_bundle(
    *,
    inter_id: str,
    time_range: str | None,
) -> dict[str, Any]:
    """Load all seven day types once, coalescing duplicate concurrent callers."""
    from app.data.load_intersection_from_pg import load_intersection_metrics_only

    # Include the loader identity so monkeypatched loaders in tests cannot see a
    # result produced by another test (and hot-reloads naturally invalidate it).
    key = (
        id(load_intersection_metrics_only),
        str(inter_id),
        parse_time_hhmm(time_range),
        str(time_range or ""),
    )
    now = time.monotonic()
    owner = False
    with _weekly_metrics_lock:
        cached = _weekly_metrics_cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        future = _weekly_metrics_inflight.get(key)
        if future is None:
            future = Future()
            _weekly_metrics_inflight[key] = future
            owner = True

    if not owner:
        return future.result()

    try:
        loaded = load_intersection_metrics_only(
            inter_id=str(inter_id),
            day_of_week=None,
            time_hhmm=parse_time_hhmm(time_range),
            time_range=time_range,
        )
        with _weekly_metrics_lock:
            _weekly_metrics_cache[key] = (
                time.monotonic() + _WEEKLY_METRICS_CACHE_TTL_S,
                loaded,
            )
        future.set_result(loaded)
        return loaded
    except BaseException as exc:
        future.set_exception(exc)
        raise
    finally:
        with _weekly_metrics_lock:
            _weekly_metrics_inflight.pop(key, None)


def load_cross_week_peak_movement_metrics(
    *,
    inter_id: str,
    direction: str,
    movement: str,
    time_range: str | None,
    queue_field: str = "queue_len_avg",
    typical_profile_id: str | None = None,
    typical_profile_label: str | None = None,
) -> dict[str, Any] | None:
    """跨周日型中选择目标进口转向排队峰值最大的一天，并实时读 PG。

    ``queue_field`` 默认 ``queue_len_avg``（项目固定逻辑）；典型路口可配
    ``queue_len_max``，以与筛选口径对齐。
    """
    field = queue_field if queue_field in {"queue_len_avg", "queue_len_max"} else "queue_len_avg"
    dir8, turn = resolve_dir8_turn(direction, movement)
    loaded = _load_cross_week_metrics_bundle(inter_id=inter_id, time_range=time_range)
    if not loaded.get("ok"):
        return None
    best: dict[str, Any] | None = None
    best_queue = -1.0
    for dow, metrics in sorted((loaded.get("metrics_by_day") or {}).items()):
        queue_peak = _max_row_metric(
            metrics.get("turn_perf_detail") or [],
            dir8,
            turn,
            (field,),
        )
        if queue_peak is None or queue_peak <= best_queue:
            continue
        best_queue = float(queue_peak)
        best = dict(metrics)
        best["selected_day_of_week"] = dow
        best["selected_movement_queue_peak_m"] = round(best_queue, 2)
        best["metric_selection_policy"] = "cross_week_movement_peak"
        best["target_queue_field"] = field
        if typical_profile_id:
            best["typical_profile_id"] = typical_profile_id
        if typical_profile_label:
            best["typical_profile_label"] = typical_profile_label
    return best


def load_cross_week_mean_movement_metrics(
    *,
    inter_id: str,
    direction: str,
    movement: str,
    time_range: str | None,
    queue_field: str = "queue_len_avg",
    peak_disclose_field: str = "queue_len_avg",
    typical_profile_id: str | None = None,
    typical_profile_label: str | None = None,
) -> dict[str, Any] | None:
    """下游承接进口：一周同窗样本均值 + 峰值披露；一律实时 PG。

    默认 mean/peak 都看 ``queue_len_avg``；典型路口可把峰值披露切到
    ``queue_len_max``，与筛选审计字段对齐。
    """
    mean_field = queue_field if queue_field in {"queue_len_avg", "queue_len_max"} else "queue_len_avg"
    peak_field = (
        peak_disclose_field
        if peak_disclose_field in {"queue_len_avg", "queue_len_max"}
        else mean_field
    )
    dir8, turn = resolve_dir8_turn(direction, movement)
    loaded = _load_cross_week_metrics_bundle(inter_id=inter_id, time_range=time_range)
    if not loaded.get("ok"):
        return None
    # ``metrics`` was aggregated from the same all-days query result.  Copy the
    # top-level mapping because selection metadata below is movement-specific.
    merged = dict(loaded.get("metrics") or {})
    if not merged:
        return None
    valid_days: list[int] = []
    for dow, metrics in sorted((loaded.get("metrics_by_day") or {}).items()):
        if _max_row_metric(
            metrics.get("turn_perf_detail") or [],
            dir8,
            turn,
            (mean_field, "queue_len_avg", "queue_len_max"),
        ) is not None:
            valid_days.append(dow)
    target_rows = merged.get("turn_perf_detail") or []
    queue_mean = _mean_row_metric(target_rows, dir8, turn, (mean_field,))
    queue_peak = _max_row_metric(target_rows, dir8, turn, (peak_field,))
    if queue_mean is None:
        return None
    merged["selected_day_of_week"] = None
    merged["included_day_of_week"] = valid_days
    merged["selected_movement_queue_mean_m"] = round(float(queue_mean), 2)
    merged["selected_movement_queue_peak_m"] = round(float(queue_peak), 2) if queue_peak is not None else None
    merged["metric_selection_policy"] = "cross_week_movement_mean"
    merged["target_queue_field"] = mean_field
    merged["downstream_peak_disclose_field"] = peak_field
    if typical_profile_id:
        merged["typical_profile_id"] = typical_profile_id
    if typical_profile_label:
        merged["typical_profile_label"] = typical_profile_label
    return merged


def _adjacent_profile_has_metrics(profile: dict[str, Any]) -> bool:
    metrics = profile.get("metrics") or {}
    for key in ("saturation", "saturation_rate", "queue_storage_ratio_max", "green_utilization"):
        val = metrics.get(key)
        if val is None:
            continue
        try:
            if float(val) > 0:
                return True
        except (TypeError, ValueError):
            continue
    if profile.get("metrics_available") is False:
        return False
    if profile.get("metrics_available") is True:
        return True
    return False


def enrich_downstream_trace_adjacent_peers(
    downstream_trace: dict[str, Any],
    *,
    peer_hints: list[dict[str, Any]],
    load_pg_metrics: Any,
) -> dict[str, Any]:
    """Enrich map ``adjacent_intersections`` for all channelization exit peers (not only flow_correlate hop)."""
    from app.trace.intersection_profile import build_intersection_profile

    merged: dict[str, dict[str, Any]] = {}
    for item in downstream_trace.get("adjacent_intersections") or []:
        inter_id = str(item.get("inter_id") or "")
        if inter_id:
            merged[inter_id] = dict(item)

    peer_loads: dict[str, tuple[dict[str, Any] | None, Exception | None]] = {}
    peer_requests: dict[str, str] = {}
    for hint in peer_hints:
        inter_id = str(hint.get("inter_id") or "")
        if not inter_id:
            continue
        existing = merged.get(inter_id)
        if existing and _adjacent_profile_has_metrics(existing):
            continue
        peer_requests[inter_id] = _direction_for_dir8(hint.get("receiving_dir8")) or "东向西"

    def _load_peer(inter_id: str, direction: str):
        try:
            return load_pg_metrics(inter_id, direction=direction, movement="直行"), None
        except TypeError:
            try:
                return load_pg_metrics(inter_id), None
            except Exception as exc:  # noqa: BLE001
                return None, exc
        except Exception as exc:  # noqa: BLE001
            return None, exc

    if peer_requests:
        with ThreadPoolExecutor(max_workers=min(4, len(peer_requests))) as pool:
            futures = {
                inter_id: pool.submit(_load_peer, inter_id, direction)
                for inter_id, direction in peer_requests.items()
            }
            peer_loads = {inter_id: future.result() for inter_id, future in futures.items()}

    for hint in peer_hints:
        inter_id = str(hint.get("inter_id") or "")
        if not inter_id:
            continue
        existing = merged.get(inter_id)
        if existing and _adjacent_profile_has_metrics(existing):
            continue

        receiving_dir8 = hint.get("receiving_dir8")
        direction = _direction_for_dir8(receiving_dir8) or "东向西"
        node: dict[str, Any] = {
            "inter_id": inter_id,
            "inter_name": hint.get("inter_name") or (existing or {}).get("inter_name"),
            "lng": hint.get("lng") if hint.get("lng") is not None else (existing or {}).get("lng"),
            "lat": hint.get("lat") if hint.get("lat") is not None else (existing or {}).get("lat"),
            "receiving_dir8": receiving_dir8,
            "role": "adjacent_peer",
        }
        pg_metrics, load_error = peer_loads.get(inter_id, (None, None))
        if load_error is not None:
            node["metrics_available"] = False
            node["metrics_reason"] = f"相邻路口指标加载失败：{load_error}"
            merged[inter_id] = build_intersection_profile(node)
            continue

        if not pg_metrics:
            node["metrics_available"] = False
            node["metrics_reason"] = "相邻路口 PG 指标缺失"
            merged[inter_id] = build_intersection_profile(node)
            continue

        if not _pg_metrics_has_dynamic_data(pg_metrics):
            node["metrics_available"] = False
            node["metrics_reason"] = "相邻路口 PG 动态指标缺失（该时段无饱和度/排队/流量，仅有配时或绿灯利用率不足以判断承接）"
            merged[inter_id] = build_intersection_profile(node)
            continue

        adj_ticket = {"direction": direction, "movement": "直行"}
        metrics = metrics_for_diagnosis(pg_metrics, adj_ticket)
        if not metrics.get("metrics_available"):
            node["metrics_available"] = False
            node["metrics_reason"] = (
                f"相邻路口承接进口（{direction}直行）该时段无转向饱和度，不可用 0 代替"
            )
            for field in ("queue_length_m", "storage_length_m", "volume_vph", "avg_delay_s"):
                if metrics.get(field) is not None:
                    node[field] = metrics[field]
            merged[inter_id] = build_intersection_profile(node)
            continue
        for field in _ADJ_METRIC_FIELDS:
            if metrics.get(field) is not None:
                node[field] = metrics[field]
        node["metrics_available"] = True
        node["metrics_source"] = "pg_adjacent_peer"
        merged[inter_id] = build_intersection_profile(node)

    downstream_trace["adjacent_intersections"] = list(merged.values())
    return downstream_trace


def merge_pg_task_into_context(task: dict[str, Any], pg_task: dict[str, Any]) -> None:
    for key in ("scope", "signal", "context", "metrics", "constraints"):
        if key in pg_task and pg_task[key]:
            task[key] = {**(task.get(key) or {}), **pg_task[key]}


def _as_float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_dir8(row: dict[str, Any]) -> int | None:
    for key in ("dir8No", "dir8_no", "f_dir_8", "f_dir8_no", "dir8_code", "dir8"):
        value = _as_float_or_none(row.get(key))
        if value is not None:
            return int(value)
    for key in ("dir8_label", "f_dir_8_label", "dir4_label"):
        label = str(row.get(key) or "").strip()
        if not label:
            continue
        compact = label.replace("进口", "").replace("出口", "")
        # 先精确匹配，避免「南进口」误命中「东南进口」
        for code, name in DIR8_ENTRY.items():
            if name == label or name.replace("进口", "") == compact:
                return int(code)
    return None


def _row_turn(row: dict[str, Any]) -> int | None:
    for key in ("turnDirNo", "turn_dir_no", "turn"):
        value = _as_float_or_none(row.get(key))
        if value is not None:
            return int(value)
    return None


def _pick_row_metric(
    rows: list[dict[str, Any]],
    dir8: int,
    turn: int,
    fields: tuple[str, ...],
) -> float | None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _row_dir8(row) != int(dir8) or _row_turn(row) != int(turn):
            continue
        for field in fields:
            value = _as_float_or_none(row.get(field))
            if value is not None:
                return value
    return None


def _max_row_metric(
    rows: list[dict[str, Any]],
    dir8: int,
    turn: int,
    fields: tuple[str, ...],
) -> float | None:
    """Peak value across all matching dir8+turn rows (multi-step windows)."""
    values: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _row_dir8(row) != int(dir8) or _row_turn(row) != int(turn):
            continue
        for field in fields:
            value = _as_float_or_none(row.get(field))
            if value is not None:
                values.append(value)
                break
    if not values:
        return None
    return max(values)


def _mean_row_metric(
    rows: list[dict[str, Any]],
    dir8: int,
    turn: int,
    fields: tuple[str, ...],
) -> float | None:
    """Mean of the first available field across matching dir8+turn rows."""
    values: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _row_dir8(row) != int(dir8) or _row_turn(row) != int(turn):
            continue
        for field in fields:
            value = _as_float_or_none(row.get(field))
            if value is not None:
                values.append(value)
                break
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _metric_value(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("value", "saturation", "saturation_rate", "volume", "flow_vph", "turn_flow_total"):
            parsed = _as_float_or_none(value.get(key))
            if parsed is not None:
                return parsed
        return None
    return _as_float_or_none(value)


def _movement_key_matches(text: str, dir8: int, turn: int) -> bool:
    normalized = text.strip()
    candidates = {
        f"d{dir8}_t{turn}",
        f"dir{dir8}_turn{turn}",
        movement_label(dir8, turn),
    }
    turn_label = TURN_LABEL.get(int(turn))
    if turn_label:
        candidates.add(f"{dir8}_{turn_label}")
        entry = DIR8_ENTRY.get(int(dir8), "")
        if entry:
            candidates.add(f"{entry}{turn_label}")
            candidates.add(f"{entry.replace('进口', '')}{turn_label}")
    return any(candidate and candidate in normalized for candidate in candidates)


def _pick_movement_metric(mapping: dict[str, Any], dir8: int, turn: int) -> float | None:
    for key, value in mapping.items():
        if isinstance(value, dict) and _row_dir8(value) == int(dir8) and _row_turn(value) == int(turn):
            return _metric_value(value)
        if _movement_key_matches(str(key), dir8, turn):
            return _metric_value(value)
    # 禁止「仅一条就取用」：会把他向指标错绑到目标转向（需求 34 E1/E6）
    return None
