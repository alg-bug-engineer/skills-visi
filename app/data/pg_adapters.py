"""Adapt PG task payloads for diagnosis and topology builders."""

from __future__ import annotations

import re
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


def _direction_for_dir8(dir8: Any) -> str | None:
    try:
        return _DIR8_TO_DIRECTION.get(int(dir8))
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


# Case A 集合保留兼容；目标指标一律按 movement 绑定（需求 34 G1/G2）。
CASE_A_APPROACH_QUEUE_TARGET_IDS = frozenset({"011wwe28fty00001"})


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
    for item in (scope or {}).get("adjacent_inter_spacing_detail") or []:
        if not isinstance(item, dict):
            continue
        item_dir = _row_dir8(item)
        if item_dir is None or int(item_dir) != int(dir8):
            continue
        spacing = _as_float_or_none(item.get("spacing_m") or item.get("length_m") or item.get("storage_m"))
        if spacing is None or spacing <= 0:
            continue
        evidence.update(
            {
                "available": True,
                "storage_source": "adjacent_inter_spacing_detail",
                "spacing_version_id": item.get("version_id") or item.get("link_id"),
                "link_id": item.get("link_id"),
            }
        )
        return float(spacing), evidence
    evidence["reason"] = "no_matching_approach_storage"
    return None, evidence


def metrics_for_diagnosis(
    pg_metrics: dict[str, Any],
    ticket: dict[str, Any],
    *,
    approach_queue_avg: bool = False,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    dir8, turn = resolve_dir8_turn(direction, movement)
    movement_key = f"d{dir8}_t{turn}"

    target_sat = _pick_row_metric(
        pg_metrics.get("turn_saturation_detail") or [],
        dir8,
        turn,
        ("turn_saturation", "saturation", "saturation_rate"),
    )
    if target_sat is None:
        target_sat = _pick_movement_metric(pg_metrics.get("movement_saturation") or {}, dir8, turn)
    saturation = float(target_sat) if target_sat is not None else None

    target_flow = _pick_row_metric(
        pg_metrics.get("turn_flow_detail") or [],
        dir8,
        turn,
        ("turn_flow_total", "flow_vph", "volume_vph", "volume"),
    )
    if target_flow is None:
        target_flow = _pick_movement_metric(pg_metrics.get("movement_volume") or {}, dir8, turn)
    volume = float(target_flow) if target_flow is not None else None

    queue_fields = ("queue_len_avg",) if approach_queue_avg else ("queue_len_avg", "queue_len_max")
    queue_m = _mean_row_metric(pg_metrics.get("turn_perf_detail") or [], dir8, turn, queue_fields)
    if queue_m is None:
        queue_m = _mean_row_metric(pg_metrics.get("turn_perf_detail") or [], dir8, turn, ("queue_len_max",))
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
        "dir8_code": dir8,
        "turn_dir_no": turn,
        "metrics_available": saturation is not None,
        "queue_available": queue_available,
        "storage_available": storage_available,
        "storage_evidence": storage_evidence,
        # 审计：路口级 MAX 仅作对照，不得覆盖目标字段
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
        downstream_nodes.append(
            {
                "inter_id": cor_id or None,
                "inter_name": row.get("adjacent_inter_name") or "下游信控节点",
                "role": "downstream",
                "lng": row.get("adjacent_lng"),
                "lat": row.get("adjacent_lat"),
                "share_pct": share,
                "link_id": row.get("link_id"),
                "receiving_dir8": link_dir8,
                "receiving_label": movement_label(link_dir8, 2) if link_dir8 is not None else None,
                "path": oriented,
                "path_source": "link_geom" if len(oriented) >= 2 else "correlate_exit",
            }
        )


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
    downstream_nodes: list[dict[str, Any]] = []
    seen_up: set[str] = set()
    seen_down: set[str] = set()

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
        elif relation == "downstream" and exit_dir8 is not None and link_dir8 == exit_dir8:
            if cor_id and cor_id in seen_down:
                continue
            seen_down.add(cor_id)
            # 下游去向在 flow_correlate 中 trace_type=UPSTREAM（对齐 map_scene._scene_trace_type）。
            share = _match_coverage(coverage, "UPSTREAM", cor_id)
            oriented = orient_path(path, target_lng, target_lat, adj_lng, adj_lat)
            downstream_nodes.append(
                {
                    "inter_id": cor_id or None,
                    "inter_name": cor_name or "下游信控节点",
                    "role": "downstream",
                    "lng": adj_lng,
                    "lat": adj_lat,
                    "share_pct": share,
                    "link_id": row.get("link_id"),
                    "receiving_dir8": exit_dir8,
                    "receiving_label": movement_label(exit_dir8, 2),
                    "path": oriented,
                    "path_source": "link_geom" if len(oriented) >= 2 else "none",
                }
            )

    _append_downstream_from_correlate_exit_links(
        downstream_nodes=downstream_nodes,
        seen_down=seen_down,
        geom_rows=geom_rows,
        correlate_rows=correlate_rows,
        coverage=coverage,
        dir8_code=dir8_code,
        turn_dir_no=turn_dir_no,
        target_lng=target_lng,
        target_lat=target_lat,
    )

    # 主来向占比降序（真实值优先），无占比排后
    upstream_nodes.sort(
        key=lambda n: (n["upstream_movements"][0].get("share_pct") or -1), reverse=True
    )
    downstream_nodes.sort(key=lambda n: (n.get("share_pct") or -1), reverse=True)

    volume_vph = float(metrics_for_diagnosis(raw.get("metrics") or {}, ticket).get("volume_vph") or 0)
    has_geometry = bool(upstream_nodes or downstream_nodes)

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
        "geometry_source": "dim_link_info.geom" if has_geometry else "unavailable",
        "caveat": "PG 拓扑：几何取自 dim_link_info.geom，占比取自 flow_correlate",
        "flow_trace_period_caveat": FLOW_TRACE_PERIOD_FILTER_CAVEAT,
    }


_ADJ_METRIC_FIELDS = (
    "queue_length_m",
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
    return False


def enrich_downstream_metrics(
    topology: dict[str, Any],
    *,
    load_pg_metrics: Any,
    target_inter_id: str | None = None,
) -> dict[str, Any]:
    """为下游相邻节点注入真实运行指标（修复 BUG-004）。

    PG 拓扑构建仅写入几何/占比，未加载相邻路口自身指标，导致下游排队/饱和度恒为 0。
    这里按每个下游节点的承接进口方向 ``receiving_dir8`` 载入其真实 PG 指标并绑定。

    参数:
        load_pg_metrics: ``callable(inter_id) -> dict | None``，返回相邻路口原始
            聚合指标（``metrics_for_diagnosis`` 入参）；无数据返回 ``None``。

    行为（rule 14/16）：取到真实指标 → ``metrics_available=True``；取不到 →
    ``metrics_available=False`` + ``metrics_reason``，绝不静默回落 0。

    Case A（坤顺×奥体西）额外按下游接收进口道方向用 queue_len_avg 均值判定；
    其他目标路口保持整路口 queue_m（max）原逻辑。
    """
    use_approach_queue = str(target_inter_id or "") in CASE_A_APPROACH_QUEUE_TARGET_IDS
    for node in topology.get("downstream_nodes") or []:
        if not isinstance(node, dict):
            continue
        inter_id = node.get("inter_id")
        if not inter_id:
            node["metrics_available"] = False
            node["metrics_reason"] = "下游节点缺 inter_id，无法加载指标"
            continue
        receiving_dir8 = node.get("receiving_dir8")
        direction = _direction_for_dir8(receiving_dir8)
        try:
            pg_metrics = load_pg_metrics(str(inter_id))
        except Exception as exc:  # noqa: BLE001 - 记录降级原因，不中断主流程
            node["metrics_available"] = False
            node["metrics_reason"] = f"下游路口指标加载失败：{exc}"
            continue
        if not pg_metrics:
            node["metrics_available"] = False
            node["metrics_reason"] = "下游路口 PG 指标缺失"
            continue
        if not _pg_metrics_has_dynamic_data(pg_metrics):
            node["metrics_available"] = False
            node["metrics_reason"] = "相邻路口 PG 动态指标缺失（该时段无饱和度/排队/流量，仅有配时或绿灯利用率不足以判断承接）"
            continue
        adj_ticket = {
            "direction": direction or "东向西",
            "movement": "直行",
        }
        metrics = metrics_for_diagnosis(
            pg_metrics,
            adj_ticket,
            approach_queue_avg=use_approach_queue,
        )
        for field in _ADJ_METRIC_FIELDS:
            if metrics.get(field) is not None:
                node[field] = metrics[field]
        node["metrics_available"] = True
        node["metrics_source"] = "pg_adjacent"
        node["metrics_receiving_direction"] = direction
        if use_approach_queue:
            node["metrics_queue_mode"] = "approach_avg"
    return topology


def build_adjacent_metrics_loader(ticket: dict[str, Any]):
    """Return ``load_pg_metrics(inter_id)`` when PG is configured; else ``None``."""
    try:
        from app.config import get_settings
        from app.data.load_intersection_from_pg import load_intersection_metrics_only
    except Exception:
        return None

    settings = get_settings()
    if not settings.pg_dsn:
        return None

    day_of_week = parse_day_of_week(ticket)
    time_hhmm = parse_time_hhmm(ticket.get("time_range"))
    time_range = ticket.get("time_range")

    def _load(inter_id: str) -> dict[str, Any] | None:
        loaded = load_intersection_metrics_only(
            inter_id=str(inter_id),
            day_of_week=day_of_week,
            time_hhmm=time_hhmm,
            time_range=time_range,
        )
        if not loaded.get("ok"):
            return None
        return loaded.get("metrics") or None

    return _load


def _adjacent_profile_has_metrics(profile: dict[str, Any]) -> bool:
    if profile.get("metrics_available") is False:
        return False
    if profile.get("metrics_available") is True:
        return True
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
        try:
            pg_metrics = load_pg_metrics(inter_id)
        except Exception as exc:  # noqa: BLE001
            node["metrics_available"] = False
            node["metrics_reason"] = f"相邻路口指标加载失败：{exc}"
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
