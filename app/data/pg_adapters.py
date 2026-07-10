"""Adapt PG task payloads for diagnosis and topology builders."""

from __future__ import annotations

import re
from typing import Any

from app.trace.geometry import orient_path, parse_linestring_wkt, parse_point_wkt
from app.trace.topology import (
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


def metrics_for_diagnosis(pg_metrics: dict[str, Any], ticket: dict[str, Any]) -> dict[str, Any]:
    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    dir8, turn = resolve_dir8_turn(direction, movement)

    target_sat = _pick_row_metric(
        pg_metrics.get("turn_saturation_detail") or [],
        dir8,
        turn,
        ("turn_saturation", "saturation", "saturation_rate"),
    )
    if target_sat is None:
        target_sat = _pick_movement_metric(pg_metrics.get("movement_saturation") or {}, dir8, turn)
    saturation = float(target_sat if target_sat is not None else pg_metrics.get("saturation") or 0)

    target_flow = _pick_row_metric(
        pg_metrics.get("turn_flow_detail") or [],
        dir8,
        turn,
        ("turn_flow_total", "flow_vph", "volume_vph", "volume"),
    )
    if target_flow is None:
        target_flow = _pick_movement_metric(pg_metrics.get("movement_volume") or {}, dir8, turn)
    volume = float(target_flow if target_flow is not None else pg_metrics.get("volume") or 0)

    return {
        "queue_length_m": float(pg_metrics.get("queue_m") or 0),
        "storage_length_m": float(pg_metrics.get("storage_m") or 200),
        "volume_vph": volume,
        "capacity_vph": float(pg_metrics.get("capacity") or 0) or max(volume / max(saturation or 0.8, 0.1), 1),
        "saturation": saturation,
        "saturation_rate": saturation,
        "green_utilization": float(pg_metrics.get("green_utilization") or 0),
        "stop_count": float(pg_metrics.get("stop_count") or 0),
        "avg_delay_s": float(pg_metrics.get("avg_delay_s") or 0),
        "time_series_trend": "pg_loaded",
        "upstream_arrival_intensity": "high" if saturation >= 0.8 else "medium",
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
    combined_upstream: dict[tuple[str, str], float] = {}
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
        key = (trace_type, cor_id)
        if trace_type == "DOWNSTREAM":
            combined_upstream[key] = combined_upstream.get(key, 0.0) + share
            continue
        if row_turn != int(turn_dir_no):
            continue
        prev = best.get(key)
        if prev is None or share > prev:
            best[key] = share
    for key, share in combined_upstream.items():
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
) -> dict[str, Any]:
    """为下游相邻节点注入真实运行指标（修复 BUG-004）。

    PG 拓扑构建仅写入几何/占比，未加载相邻路口自身指标，导致下游排队/饱和度恒为 0。
    这里按每个下游节点的承接进口方向 ``receiving_dir8`` 载入其真实 PG 指标并绑定。

    参数:
        load_pg_metrics: ``callable(inter_id) -> dict | None``，返回相邻路口原始
            聚合指标（``metrics_for_diagnosis`` 入参）；无数据返回 ``None``。

    行为（rule 14/16）：取到真实指标 → ``metrics_available=True``；取不到 →
    ``metrics_available=False`` + ``metrics_reason``，绝不静默回落 0。
    """
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
        metrics = metrics_for_diagnosis(pg_metrics, adj_ticket)
        for field in _ADJ_METRIC_FIELDS:
            if metrics.get(field) is not None:
                node[field] = metrics[field]
        node["metrics_available"] = True
        node["metrics_source"] = "pg_adjacent"
        node["metrics_receiving_direction"] = direction
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
    for key in ("dir8No", "dir8_no", "f_dir_8", "f_dir8_no", "dir8"):
        value = _as_float_or_none(row.get(key))
        if value is not None:
            return int(value)
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
    return any(candidate and candidate in normalized for candidate in candidates)


def _pick_movement_metric(mapping: dict[str, Any], dir8: int, turn: int) -> float | None:
    for key, value in mapping.items():
        if isinstance(value, dict) and _row_dir8(value) == int(dir8) and _row_turn(value) == int(turn):
            return _metric_value(value)
        if _movement_key_matches(str(key), dir8, turn):
            return _metric_value(value)
    if len(mapping) == 1:
        return _metric_value(next(iter(mapping.values())))
    return None
