"""Map scene payload aligned with references/流量溯源 frontend types/map.ts."""

from __future__ import annotations

import re
from typing import Any

from app.trace.geometry import orient_path, parse_linestring_wkt

MIN_PATH_COVERAGE = 10.0

# flow_correlate.period_type 映射与推断见 app.data.ticket_nlu_schema（与意图 NLU 共用配置）。
from app.data.ticket_nlu_schema import (
    FLOW_TRACE_PERIOD_FILTER_CAVEAT,
    FLOW_TRACE_PERIOD_FILTER_ENABLED,
    infer_diagnosis_period_type,
    period_db_codes as _period_db_codes,
    resolve_correlate_period,
)

_PERIOD_CODE_BY_CN = _period_db_codes()
_PERIOD_CODES = frozenset(_PERIOD_CODE_BY_CN.values())


def effective_flow_trace_period_type(topology: dict[str, Any] | None) -> str | None:
    """流量溯源实际使用的 period_type；关闭时间片过滤时恒为 None（全时段）。"""
    if not FLOW_TRACE_PERIOD_FILTER_ENABLED:
        return None
    topo = topology or {}
    return resolve_correlate_period(topo.get("period_type"))


def _scene_trace_type(trace_direction: str, turn_dir_no: int) -> str:
    """库 `trace_type` 与业务来/去向的映射（西进口经十路已验证的转向相关反转）。

    对齐 references/流量溯源（incoming/outgoing_db_trace_type）：
    - 来向(任意转向)：沿进口道驶来的记录落在 `DOWNSTREAM`。
    - 去向直行：沿出口道驶离落在 `UPSTREAM`；去向左/右/掉头(垂直出口)落在 `DOWNSTREAM`。
    """
    if trace_direction == "downstream":
        return "UPSTREAM" if int(turn_dir_no) == 2 else "DOWNSTREAM"
    return "DOWNSTREAM"


def _period_match(row: dict[str, Any], period_type: str | None) -> bool:
    if not period_type:
        return True
    return str(row.get("period_type") or "").upper() == period_type


def _json_number(value: Any) -> int | float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _peer_visible(node: dict[str, Any]) -> bool:
    number = _json_number(node.get("path_coverage"))
    if number is None:
        return bool(node.get("in_main_corridor") or node.get("is_topo_anchor"))
    return float(number) >= MIN_PATH_COVERAGE


def _link_geometry_index(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    links: dict[str, dict[str, Any]] = {}
    for row in raw.get("trace_geometry") or []:
        link_id = str(row.get("link_id") or "")
        if not link_id:
            continue
        path = parse_linestring_wkt(row.get("geom_wkt"))
        if len(path) >= 2:
            links[link_id] = {
                "path": path,
                "adjacent_inter_id": row.get("adjacent_inter_id"),
                "adjacent_inter_name": row.get("adjacent_inter_name"),
                "adjacent_lng": row.get("adjacent_lng"),
                "adjacent_lat": row.get("adjacent_lat"),
                "relation_direction": row.get("relation_direction"),
                "length_m": _json_number(row.get("length_m")),
            }
    return links


def collect_map_adjacent_peer_hints(pg_raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Collect exit-link adjacent intersections for map topology metrics enrichment."""
    raw = pg_raw or {}
    channel_by_link = {
        str(row.get("link_id") or ""): row for row in raw.get("channelization") or [] if row.get("link_id")
    }
    hints: dict[str, dict[str, Any]] = {}
    for row in raw.get("trace_geometry") or []:
        if str(row.get("relation_direction") or "").lower() != "downstream":
            continue
        inter_id = str(row.get("adjacent_inter_id") or "")
        if not inter_id:
            continue
        link_id = str(row.get("link_id") or "")
        channel = channel_by_link.get(link_id) or {}
        receiving_dir8: int | None = None
        for source in (channel, row):
            try:
                exit_or_link_dir8 = int(source.get("dir8_code"))
                # 出口 link 方向 → 下游承接进口对向
                receiving_dir8 = (exit_or_link_dir8 + 4) % 8
                break
            except (TypeError, ValueError):
                continue
        hints[inter_id] = {
            "inter_id": inter_id,
            "inter_name": row.get("adjacent_inter_name"),
            "lng": row.get("adjacent_lng"),
            "lat": row.get("adjacent_lat"),
            "receiving_dir8": receiving_dir8,
        }
    return list(hints.values())


def _strip_approach(dir8_label: Any) -> str | None:
    text = str(dir8_label or "").strip()
    for suffix in ("进口", "出口"):
        if text.endswith(suffix):
            return text[: -len(suffix)] or None
    return text or None


def _metric_by_link(raw: dict[str, Any], key: str) -> dict[str, float]:
    """Aggregate turn-level rows to link_id; same link multi-turn takes max (align by_approach)."""
    out: dict[str, float] = {}
    for row in raw.get(key) or []:
        link_id = str(row.get("link_id") or "")
        if not link_id:
            continue
        for metric_key in (
            "turn_saturation",
            "green_utilization",
            "queue_len_max",
            "queue_len_avg",
            "turn_flow_total",
            "lane_capacity",
        ):
            if row.get(metric_key) is None:
                continue
            try:
                value = float(row[metric_key])
            except (TypeError, ValueError):
                continue
            out[link_id] = max(out.get(link_id, value), value)
            break
    return out


def _saturation_by_approach(raw: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in raw.get("turn_saturation") or []:
        approach = _strip_approach(row.get("dir8_label"))
        if not approach:
            continue
        try:
            value = float(row["turn_saturation"])
        except (TypeError, ValueError, KeyError):
            continue
        out[approach] = max(out.get(approach, value), value)
    return out


def _channelization_by_link(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in raw.get("channelization") or []:
        link_id = str(row.get("link_id") or "")
        if link_id:
            out[link_id] = row
    return out


def _best_share_by_inter(
    raw: dict[str, Any],
    dir8_code: int,
    turn_dir_no: int,
    trace_direction: str,
    period_type: str | None = None,
) -> dict[str, float]:
    """Return real flow-correlate share by correlated intersection id.

    Upstream incoming trace uses same-entry combined share; downstream outgoing trace keeps
    the target-turn share so direct downstream capacity is not diluted by unrelated turns.
    ``period_type`` limits rows to a single diagnosis period (真实单时段口径)。
    """
    trace_type = _scene_trace_type(trace_direction, turn_dir_no)
    combined: dict[str, float] = {}
    best: dict[str, float] = {}
    for row in raw.get("flow_correlate") or []:
        if not _period_match(row, period_type):
            continue
        try:
            row_dir8 = int(row.get("f_dir8_no"))
            row_turn = int(row.get("turn_dir_no"))
        except (TypeError, ValueError):
            continue
        if row_dir8 != int(dir8_code):
            continue
        if str(row.get("trace_type") or "").upper() != trace_type:
            continue
        cor_id = str(row.get("cor_inter_id") or "")
        if not cor_id:
            continue
        try:
            share = float(row.get("flow_share_ratio") or row.get("share_pct") or 0)
        except (TypeError, ValueError):
            continue
        if trace_direction == "upstream":
            combined[cor_id] = combined.get(cor_id, 0.0) + share
            continue
        if row_turn != int(turn_dir_no):
            continue
        prev = best.get(cor_id)
        if prev is None or share > prev:
            best[cor_id] = share
    if trace_direction == "upstream":
        return {inter_id: round(share, 2) for inter_id, share in combined.items()}
    return best


def _row_in_corridor(
    dir8_code: int,
    turn_dir_no: int,
    trace_direction: str,
    cor_d8: int | None,
    cor_turn: int | None,
) -> bool:
    """以「进口道(dir8)+转向(turn)」约束 correlate 行是否属当前溯源走廊。

    对齐 references/流量溯源 correlate_sniff_map_service（incoming/outgoing_row_in_corridor）：
    - 来向(任意转向) 与 去向直行：同进口道直行走廊 `cor_f_dir8==dir8 且 cor_turn==2`
      （关联侧沿该进口道直行驶来/驶离 = 真正沿走廊上/下游一跳）。
    - 去向左/右/掉头：垂直出口走廊，排除进口直行 OD 蔓延（保留非「进口直行」的其它去向行）。
    缺 cor_f_dir8/cor_turn 的行无法归属走廊，判为不在走廊（交由几何兜底路径处理）。
    """
    if cor_d8 is None or cor_turn is None:
        return False
    is_arterial_straight = cor_d8 == int(dir8_code) and cor_turn == 2
    if trace_direction == "downstream" and int(turn_dir_no) != 2:
        return not is_arterial_straight
    return is_arterial_straight


def _correlate_peers(
    raw: dict[str, Any],
    *,
    dir8_code: int,
    turn_dir_no: int,
    trace_direction: str,
    period_type: str | None = None,
) -> list[dict[str, Any]]:
    """按「进口道+转向」约束聚合真实 flow-correlate 走廊 peer（对齐 sniff 参考）。

    仅保留目标 movement（`f_dir8==dir8` 且 `turn==turn_dir_no`）的 correlate 行，再以
    ``_row_in_corridor`` 约束到当前溯源走廊；每个 peer 取占比最大行。``period_type`` 限定
    单一诊断时段（真实单时段口径，见 BUG-002），禁止跨时段聚合虚增。不再对来向做跨转向
    求和、也不塌缩为单一上游——由调用方渲染完整多跳走廊链。
    """
    trace_type = _scene_trace_type(trace_direction, turn_dir_no)
    peers: dict[str, dict[str, Any]] = {}
    for row in raw.get("flow_correlate") or []:
        if not _period_match(row, period_type):
            continue
        try:
            row_dir8 = int(row.get("f_dir8_no"))
            row_turn = int(row.get("turn_dir_no"))
        except (TypeError, ValueError):
            continue
        if row_dir8 != int(dir8_code) or row_turn != int(turn_dir_no):
            continue
        if str(row.get("trace_type") or "").upper() != trace_type:
            continue
        cor_id = str(row.get("cor_inter_id") or "")
        if not cor_id:
            continue
        try:
            cor_d8 = int(row.get("cor_f_dir8_no"))
        except (TypeError, ValueError):
            cor_d8 = None
        try:
            cor_turn = int(row.get("cor_turn_dir_no"))
        except (TypeError, ValueError):
            cor_turn = None
        if not _row_in_corridor(dir8_code, turn_dir_no, trace_direction, cor_d8, cor_turn):
            continue
        try:
            share = float(row.get("flow_share_ratio") or row.get("share_pct") or 0)
        except (TypeError, ValueError):
            continue
        prev = peers.get(cor_id)
        if prev is None or share > float(prev.get("path_coverage") or -1):
            peers[cor_id] = {
                "cor_inter_id": cor_id,
                "cor_inter_name": row.get("cor_inter_name") or cor_id,
                "cor_f_dir8_no": cor_d8,
                "cor_turn_dir_no": cor_turn,
                "path_coverage": round(share, 2),
            }
    return sorted(peers.values(), key=lambda p: float(p.get("path_coverage") or 0), reverse=True)


def _peer_link_geometry_from_raw(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for row in raw.get("peer_link_geometry") or []:
        inter_id = str(row.get("inter_id") or "")
        if not inter_id:
            continue
        path = row.get("path") or parse_linestring_wkt(row.get("geom_wkt"))
        if len(path) < 2:
            continue
        node = nodes.setdefault(
            inter_id,
            {
                "inter_id": inter_id,
                "name": row.get("inter_name") or row.get("name") or inter_id,
                "center": [float(row["lng"]), float(row["lat"])]
                if row.get("lng") is not None and row.get("lat") is not None
                else None,
                "links": [],
            },
        )
        node["links"].append(_link_payload(row, row, path))
    return nodes


def _fetch_peer_link_geometry(inter_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch real channel links for correlate peers from PG when available."""
    if not inter_ids:
        return {}
    try:
        from app.config import get_settings
        from app.data.pg_client import read_pg_rows
    except Exception:
        return {}

    settings = get_settings()
    if not settings.pg_dsn:
        return {}

    road = settings.pg_schema
    channel_table = settings.pg_channel_table
    inter_table = settings.pg_dim_inter_table
    placeholders = ", ".join(f":id_{i}" for i in range(len(inter_ids)))
    params = {f"id_{i}": inter_id for i, inter_id in enumerate(inter_ids)}
    sql = f"""
        SELECT r.inter_id::text AS inter_id,
               i.inter_name::text AS inter_name,
               ST_X(ST_GeomFromText(i.geom_center)) AS lng,
               ST_Y(ST_GeomFromText(i.geom_center)) AS lat,
               r.link_id::text AS link_id,
               r.link_role::text AS link_role,
               r.dir4_label::text AS dir4_label,
               r.dir8_code::text AS dir8_code,
               r.dir8_label::text AS dir8_label,
               r.lane_num::numeric AS lane_num,
               l.road_name::text AS road_name,
               ST_AsText(l.geom) AS geom_wkt
        FROM {road}.{channel_table} r
        JOIN {road}.dim_link_info l
          ON r.link_id = l.link_id AND r.version_id = l.version_id
        LEFT JOIN {road}.{inter_table} i
          ON i.inter_id = r.inter_id AND i.version_id = r.version_id
        WHERE r.inter_id IN ({placeholders})
          AND LOWER(r.link_role) IN ('entrance', 'exit', '进口', '出口')
        ORDER BY r.inter_id, r.link_clockwise_seq NULLS LAST, r.link_id
    """
    try:
        rows = read_pg_rows(sql, params, limit=max(500, len(inter_ids) * 16))
    except Exception:
        return {}
    return _peer_link_geometry_from_raw({"peer_link_geometry": rows})


def _link_payload(row: dict[str, Any], channel: dict[str, Any], path: list[list[float]]) -> dict[str, Any]:
    return {
        "link_id": row.get("link_id"),
        "link_role": channel.get("link_role") or row.get("link_role"),
        "dir4_label": channel.get("dir4_label"),
        "dir8_code": channel.get("dir8_code") or row.get("dir8_code"),
        "dir8_label": channel.get("dir8_label") or row.get("dir8_label"),
        "lane_num": _json_number(channel.get("lane_num") if channel.get("lane_num") is not None else row.get("lane_num")),
        "road_name": row.get("road_name"),
        "path": path,
        "adjacent_inter_id": row.get("adjacent_inter_id"),
        "adjacent_inter_name": row.get("adjacent_inter_name"),
        "length_m": _json_number(row.get("length_m")),
    }


def build_flow_trace_links_sniff_map_scene(
    *,
    pg_raw: dict[str, Any] | None,
    topology: dict[str, Any] | None,
    target_profile: dict[str, Any],
    direction: str,
    movement: str,
    trace_direction: str = "upstream",
) -> dict[str, Any]:
    """Build the standard link-sniff flow-trace scene used by the frontend.

    This payload mirrors ``flow-trace-links-sniff.html``: target intersection with real
    channel links, peer intersections grouped by real link geometry, main-corridor flags
    from the resolved topology, and real flow-correlate percentages when available.
    """
    raw = pg_raw or {}
    topo = topology or {}
    geom_rows = raw.get("trace_geometry") or []
    if not geom_rows:
        return {"action": "map_scene", "phase": "flow_trace_links_sniff_map", "available": False, "reason": "no_trace_geometry"}

    target_lng = target_profile.get("lng") if target_profile.get("lng") is not None else topo.get("target_lng")
    target_lat = target_profile.get("lat") if target_profile.get("lat") is not None else topo.get("target_lat")
    if target_lng is None or target_lat is None:
        return {"action": "map_scene", "phase": "flow_trace_links_sniff_map", "available": False, "reason": "no_target_center"}
    center = [float(target_lng), float(target_lat)]

    dir8_code = int(topo.get("dir8_code") or 0)
    turn_dir_no = int(topo.get("turn_dir_no") or 2)
    period_type = effective_flow_trace_period_type(topo)
    trace_dir = "downstream" if trace_direction == "downstream" else "upstream"
    shares = _best_share_by_inter(raw, dir8_code, turn_dir_no, trace_dir, period_type)
    channel_by_link = _channelization_by_link(raw)

    raw_target_links: list[dict[str, Any]] = []
    for row in geom_rows:
        link_id = str(row.get("link_id") or "")
        path = parse_linestring_wkt(row.get("geom_wkt"))
        if len(path) < 2:
            continue
        raw_target_links.append(_link_payload(row, channel_by_link.get(link_id, {}), path))

    # 目标路口渲染其完整 link「十字」（真实进/出口全集），不再按转向裁到单条（对齐参考 sniff，
    # 此前裁剪是「太短」的直接来源之一）。
    target_links = raw_target_links

    if not raw_target_links:
        return {"action": "map_scene", "phase": "flow_trace_links_sniff_map", "available": False, "reason": "no_link_geometry"}

    peer_relation = "downstream" if trace_dir == "downstream" else "upstream"
    topo_nodes = topo.get("downstream_nodes") if trace_dir == "downstream" else topo.get("upstream_nodes")
    main_order: dict[str, int] = {}
    main_share: dict[str, float | None] = {}
    for idx, node in enumerate(topo_nodes or [], start=1):
        inter_id = str(node.get("inter_id") or node.get("upstream_inter_id") or "")
        if not inter_id:
            continue
        main_order[inter_id] = idx
        if trace_dir == "downstream":
            main_share[inter_id] = node.get("share_pct")
        else:
            dom = (node.get("upstream_movements") or [{}])[0]
            main_share[inter_id] = dom.get("share_pct")

    correlate_peers = _correlate_peers(
        raw,
        dir8_code=dir8_code,
        turn_dir_no=turn_dir_no,
        trace_direction=trace_dir,
        period_type=period_type,
    )
    period_applied = period_type
    if FLOW_TRACE_PERIOD_FILTER_ENABLED and not correlate_peers and period_type:
        # 该时段无 flow_correlate 行（真实数据缺口）时回退全时段，避免溯源空场景；不合成。
        correlate_peers = _correlate_peers(
            raw,
            dir8_code=dir8_code,
            turn_dir_no=turn_dir_no,
            trace_direction=trace_dir,
            period_type=None,
        )
        period_applied = None
    peer_geometry = _peer_link_geometry_from_raw(raw)
    missing_geometry_ids = [
        str(peer.get("cor_inter_id"))
        for peer in correlate_peers
        if str(peer.get("cor_inter_id")) and str(peer.get("cor_inter_id")) not in peer_geometry
    ]
    peer_geometry.update(_fetch_peer_link_geometry(missing_geometry_ids))

    peers: dict[str, dict[str, Any]] = {}
    for idx, peer in enumerate(correlate_peers, start=1):
        inter_id = str(peer.get("cor_inter_id") or "")
        geometry = peer_geometry.get(inter_id)
        if not geometry or not geometry.get("links"):
            continue
        # peer 渲染其完整 link「十字」（真实进/出口全集），不再按转向裁剪（对齐参考 sniff）。
        cross_links = [
            link for link in (geometry.get("links") or []) if len(link.get("path") or []) >= 2
        ]
        if not cross_links:
            continue
        # _correlate_peers 已按进口道+转向约束到走廊，返回的 peer 均在当前溯源走廊内：
        # 直行走廊要求关联侧沿同进口道直行；去向左/右为该转向垂直出口走廊。
        # 命中拓扑一跳（物理主上/下游）的 peer 一律视为主走廊，避免物理来向被判为旁支隐藏。
        in_main = inter_id in main_order or (
            True
            if trace_dir == "downstream" and turn_dir_no != 2
            else peer.get("cor_f_dir8_no") == dir8_code and peer.get("cor_turn_dir_no") == 2
        )
        corridor_hop = main_order.get(inter_id) or (idx if in_main else 0)
        peers[inter_id] = {
            "inter_id": inter_id,
            "name": geometry.get("name") or peer.get("cor_inter_name") or inter_id,
            "center": geometry.get("center"),
            "role": trace_dir,
            "path_coverage": peer.get("path_coverage"),
            "cor_f_dir8_no": peer.get("cor_f_dir8_no"),
            "cor_turn_dir_no": peer.get("cor_turn_dir_no"),
            "in_main_corridor": in_main,
            "corridor_hop": corridor_hop,
            "exit_dir8": topo.get("exit_dir8") if trace_dir == "downstream" else None,
            "is_topo_anchor": main_order.get(inter_id) == 1,
            "links": cross_links,
        }

    # 始终注入拓扑一跳主走廊锚点：物理来向/去向的主上/下游一跳即便未被单一时段 correlate
    # 命中，也必须呈现（对齐参考 sniff 的 topo_one_hop 锚点必现）。否则该时段 correlate 稀疏
    # 时会丢失物理主走廊，表现为「溯源效果消失」。锚点几何取真实全 link 十字。
    anchor_ids = [inter_id for inter_id in main_order if inter_id and inter_id not in peers]
    if anchor_ids:
        anchor_geometry = {iid: peer_geometry[iid] for iid in anchor_ids if iid in peer_geometry}
        anchor_geometry.update(
            _fetch_peer_link_geometry([iid for iid in anchor_ids if iid not in anchor_geometry])
        )
        for inter_id in anchor_ids:
            geometry = anchor_geometry.get(inter_id)
            if not geometry:
                continue
            cross_links = [
                link for link in (geometry.get("links") or []) if len(link.get("path") or []) >= 2
            ]
            if not cross_links:
                continue
            peers[inter_id] = {
                "inter_id": inter_id,
                "name": geometry.get("name") or inter_id,
                "center": geometry.get("center"),
                "role": trace_dir,
                "path_coverage": main_share.get(inter_id),
                "cor_f_dir8_no": dir8_code,
                "cor_turn_dir_no": 2,
                "in_main_corridor": True,
                "corridor_hop": main_order.get(inter_id),
                "exit_dir8": topo.get("exit_dir8") if trace_dir == "downstream" else None,
                "is_topo_anchor": main_order.get(inter_id) == 1,
                "links": cross_links,
            }

    if not peers:
        for row in geom_rows:
            if str(row.get("relation_direction") or "") != peer_relation:
                continue
            inter_id = str(row.get("adjacent_inter_id") or "")
            if not inter_id:
                continue
            path = parse_linestring_wkt(row.get("geom_wkt"))
            if len(path) < 2:
                continue
            adj_lng = row.get("adjacent_lng")
            adj_lat = row.get("adjacent_lat")
            oriented = (
                orient_path(path, adj_lng, adj_lat, target_lng, target_lat)
                if trace_dir == "upstream"
                else orient_path(path, target_lng, target_lat, adj_lng, adj_lat)
            )
            if len(oriented) < 2:
                continue
            peer = peers.setdefault(
                inter_id,
                {
                    "inter_id": inter_id,
                    "name": row.get("adjacent_inter_name") or inter_id,
                    "center": [float(adj_lng), float(adj_lat)] if adj_lng is not None and adj_lat is not None else oriented[0 if trace_dir == "upstream" else -1],
                    "role": trace_dir,
                    "path_coverage": main_share.get(inter_id, shares.get(inter_id)),
                    "cor_f_dir8_no": None,
                    "cor_turn_dir_no": None,
                    "in_main_corridor": inter_id in main_order,
                    "corridor_hop": main_order.get(inter_id, 0),
                    "exit_dir8": topo.get("exit_dir8") if trace_dir == "downstream" else None,
                    "is_topo_anchor": main_order.get(inter_id) == 1,
                    "links": [],
                },
            )
            link_id = str(row.get("link_id") or "")
            peer["links"].append(_link_payload(row, channel_by_link.get(link_id, {}), oriented))

    all_peer_list = list(peers.values())
    peer_list = [node for node in all_peer_list if _peer_visible(node)]
    hidden_non_main = len(all_peer_list) - len(peer_list)
    peer_list.sort(
        key=lambda n: (
            0 if n.get("in_main_corridor") else 1,
            n.get("corridor_hop") or 999,
            -(n.get("path_coverage") or 0),
        )
    )

    # 来向/去向溯源保留完整多跳走廊链（对齐 flow-trace-links-sniff 参考：目标 + 主走廊多跳
    # + 其它同走廊 peer）；不再塌缩为单一上游——这是此前「太短」的直接来源。走廊范围已由
    # 进口道+转向在 _correlate_peers 行级约束，避免无关路口的「来向 bleed」。

    target_intersection = {
        "inter_id": target_profile.get("inter_id") or topo.get("target_inter_id"),
        "name": target_profile.get("inter_name") or topo.get("target_inter_name"),
        "center": center,
        "role": "target",
        "path_coverage": None,
        "cor_f_dir8_no": None,
        "cor_turn_dir_no": None,
        "in_main_corridor": False,
        "corridor_hop": 0,
        "exit_dir8": None,
        "is_topo_anchor": False,
        "links": target_links,
    }
    intersections = [target_intersection, *peer_list]
    main_nodes = [node for node in peer_list if node.get("in_main_corridor")]
    # 主走廊链按渲染顺序重排 hop（锚点在前、占比降序），避免多个 peer 携带重复 hop 号。
    for hop_index, node in enumerate(main_nodes, start=1):
        node["corridor_hop"] = hop_index
    main_chain = [
        {
            "hop": node.get("corridor_hop"),
            "inter_id": node.get("inter_id"),
            "name": node.get("name"),
            "coverage": node.get("path_coverage"),
        }
        for node in main_nodes
    ]

    return {
        "action": "map_scene",
        "phase": "flow_trace_links_sniff_map",
        "available": True,
        "center": center,
        "trace_direction": trace_dir,
        "business_direction": "outgoing" if trace_dir == "downstream" else "incoming",
        "target_inter_id": target_intersection["inter_id"],
        "title": f"{target_intersection['name'] or ''} · {direction}{movement} · {'去向' if trace_dir == 'downstream' else '来向'}溯源",
        "logic": (
            "real link geometry + flow_correlate share; upstream locked to single topo one-hop"
            " (exclude secondary correlated upstreams)"
            if trace_dir == "upstream"
            else "real link geometry + flow_correlate share; target/main/other grouped like link sniff reference"
        ),
        "stats": {
            "raw_rows": len(raw.get("flow_correlate") or []),
            "distinct_peers": len(all_peer_list),
            "rendered": len(intersections),
            "main_corridor": len(main_chain),
            "missing_center": sum(1 for n in peer_list if not n.get("center")),
            "hidden_non_main": hidden_non_main,
            "period_type": period_applied,
            "period_filter_enabled": FLOW_TRACE_PERIOD_FILTER_ENABLED,
            "period_filter_caveat": (
                None if FLOW_TRACE_PERIOD_FILTER_ENABLED else FLOW_TRACE_PERIOD_FILTER_CAVEAT
            ),
        },
        "main_corridor_chain": main_chain,
        "intersections": intersections,
        "hud": {
            "title": "流量/去向溯源",
            "metrics": [
                {"label": "真实 link", "value": str(sum(len(n.get("links") or []) for n in intersections))},
                {"label": "主走廊", "value": str(len(main_chain))},
                {"label": "相邻路口", "value": str(len(peer_list))},
            ],
        },
    }


def build_channelization_map_scene(
    *,
    pg_raw: dict[str, Any] | None,
    target_profile: dict[str, Any],
    center: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Build frontend channelization scene from real PG link/lane rows.

    The frontend derives lane polygons from real link geometry, lane_info and lane counts,
    matching references/frontend-v2. If those real fields are absent, the scene is unavailable.
    """
    raw = pg_raw or {}
    channel_rows = raw.get("channelization") or []
    if not channel_rows:
        return {"action": "map_scene", "phase": "channelization_map", "available": False, "reason": "no_channelization"}

    geometries = _link_geometry_index(raw)
    saturation = _metric_by_link(raw, "turn_saturation")
    saturation_by_approach = _saturation_by_approach(raw)
    green = _metric_by_link(raw, "green_utilization")
    queue_max = _metric_by_link(raw, "turn_perf")
    flow = _metric_by_link(raw, "turn_flow")
    capacity = _metric_by_link(raw, "lane_capacity")

    links: list[dict[str, Any]] = []
    for row in channel_rows:
        link_id = str(row.get("link_id") or "")
        geometry = geometries.get(link_id) or {}
        path = geometry.get("path") or []
        if len(path) < 2:
            continue
        link_sat = saturation.get(link_id)
        approach = _strip_approach(row.get("dir8_label"))
        approach_sat = saturation_by_approach.get(approach) if approach else None
        if link_sat is not None and approach_sat is not None:
            link_sat = max(link_sat, approach_sat)
        elif approach_sat is not None:
            link_sat = approach_sat
        links.append(
            {
                "link_id": link_id,
                "link_role": row.get("link_role"),
                "dir8_code": row.get("dir8_code"),
                "dir8_label": row.get("dir8_label"),
                "dir4_label": row.get("dir4_label"),
                "lane_num": _json_number(row.get("lane_num")),
                "c_lane_num": _json_number(row.get("c_lane_num")),
                "lane_info": row.get("lane_info"),
                "turn_move": row.get("turn_move"),
                "path": path,
                "adjacent_inter_id": geometry.get("adjacent_inter_id"),
                "adjacent_inter_name": geometry.get("adjacent_inter_name"),
                "adjacent_lng": geometry.get("adjacent_lng"),
                "adjacent_lat": geometry.get("adjacent_lat"),
                "relation_direction": geometry.get("relation_direction"),
                "length_m": geometry.get("length_m"),
                "metrics": {
                    "saturation": link_sat,
                    "green_utilization": green.get(link_id),
                    "queue_m": queue_max.get(link_id),
                    "flow_vph": flow.get(link_id),
                    "capacity": capacity.get(link_id),
                },
            }
        )

    if not links:
        return {"action": "map_scene", "phase": "channelization_map", "available": False, "reason": "no_channelization_geometry"}

    lng = target_profile.get("lng")
    lat = target_profile.get("lat")
    center_tuple: list[float] | None = None
    if center:
        center_tuple = [center[0], center[1]]
    elif lng is not None and lat is not None:
        center_tuple = [float(lng), float(lat)]

    return {
        "action": "map_scene",
        "phase": "channelization_map",
        "available": True,
        "center": center_tuple,
        "target_intersection": {
            "inter_id": target_profile.get("inter_id"),
            "inter_name": target_profile.get("inter_name"),
            "lng": lng,
            "lat": lat,
        },
        "links": links,
        "hud": {
            "title": "渠化车道与运行指标",
            "metrics": [
                {"label": "link", "value": str(len(links))},
                {"label": "进口", "value": str(sum(1 for l in links if str(l.get("link_role")).lower() == "entrance"))},
                {"label": "出口", "value": str(sum(1 for l in links if str(l.get("link_role")).lower() == "exit"))},
            ],
        },
    }


def build_downstream_map_scene(
    *,
    downstream_trace: dict[str, Any],
    target_profile: dict[str, Any],
    center: tuple[float, float] | None = None,
) -> dict[str, Any]:
    if not downstream_trace.get("available"):
        return {"action": "map_scene", "phase": "downstream_trace_map", "available": False}

    lng = target_profile.get("lng")
    lat = target_profile.get("lat")
    center_tuple: list[float] | None = None
    if center:
        center_tuple = [center[0], center[1]]
    elif lng is not None and lat is not None:
        center_tuple = [float(lng), float(lat)]

    turn_traces = []
    for item in downstream_trace.get("turn_traces") or []:
        turn_traces.append(
            {
                "movement": item.get("movement"),
                "turn_label": item.get("turn_label"),
                "dir8_code": item.get("dir8_code"),
                "turn_dir_no": item.get("turn_dir_no"),
                "selected": item.get("selected"),
                "exit_dir8": item.get("exit_dir8"),
                "downstream_inter_id": item.get("downstream_inter_id"),
                "name": item.get("downstream_inter_name"),
                "share_pct": item.get("share_pct"),
                "path": item.get("path"),
                "path_source": item.get("path_source"),
                "receiving_dir8": item.get("receiving_dir8"),
                "receiving_label": item.get("receiving_label"),
                "lon": item.get("lng"),
                "lat": item.get("lat"),
                "metrics_available": item.get("metrics_available"),
                "metrics_reason": item.get("metrics_reason"),
                "downstream_metrics": item.get("downstream_metrics"),
                "capacity": {
                    "blocked": (item.get("capacity") or {}).get("blocked"),
                    "can_release": (item.get("capacity") or {}).get("can_release"),
                },
                "trace_kind": "downstream",
            }
        )

    adjacent = []
    for node in downstream_trace.get("adjacent_intersections") or []:
        adjacent.append(
            {
                "inter_id": node.get("inter_id"),
                "inter_name": node.get("inter_name"),
                "lng": node.get("lng"),
                "lat": node.get("lat"),
                "metrics": node.get("metrics"),
                "by_turn": node.get("by_turn"),
                "remaining_storage_m": node.get("remaining_storage_m"),
                "capacity": node.get("capacity"),
                "linked_movements": node.get("linked_movements"),
                "movement_metrics": node.get("movement_metrics"),
            }
        )

    governance = downstream_trace.get("governance") or {}
    movement_summary = downstream_trace.get("movement_summary") or []
    return {
        "action": "map_scene",
        "phase": "downstream_trace_map",
        "available": True,
        "center": center_tuple,
        "trace_direction": "downstream",
        "scope": downstream_trace.get("scope"),
        "target_approach": downstream_trace.get("target_approach"),
        "selected_turn_dir_no": downstream_trace.get("selected_turn_dir_no"),
        "turn_traces": turn_traces,
        "movement_summary": movement_summary,
        "adjacent_intersections": adjacent,
        "hud": {
            "title": "下游一跳去向",
            "metrics": [
                {
                    "label": "已溯源转向",
                    "value": "/".join(
                        str(item.get("turn_label"))
                        for item in movement_summary
                        if item.get("available") and item.get("turn_label")
                    )
                    or "-",
                },
                {
                    "label": "治理落点",
                    "value": governance.get("landing", "-"),
                    "severity": "high" if governance.get("downstream_blocked") else "low",
                },
                {
                    "label": "建议",
                    "value": governance.get("recommendation", "-"),
                },
            ],
        },
    }


def build_flow_map_scene(
    *,
    flow_trace: dict[str, Any],
    arterial_analysis: dict[str, Any],
    center: tuple[float, float] | None = None,
    coordination: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not flow_trace.get("available"):
        return {"action": "map_scene", "phase": "upstream_correlate_map", "available": False}

    entry_traces = []
    for item in flow_trace.get("entry_traces") or []:
        dom = item.get("dominant_movement") or {}
        entry_traces.append(
            {
                "entry": item.get("entry"),
                "dir8_code": item.get("dir8_code"),
                "upstream_inter_id": item.get("upstream_inter_id"),
                "name": item.get("upstream_inter_name"),
                "narrative": item.get("narrative"),
                "lon": item.get("upstream_lng"),
                "lat": item.get("upstream_lat"),
                "dominant_turn": dom.get("turn"),
                "vehicles_of_100": dom.get("vehicles_of_100"),
                "movements": [
                    {
                        "turn": mv.get("turn"),
                        "vehicles_of_100": mv.get("vehicles_of_100"),
                        "feed_direction": mv.get("feed_direction"),
                    }
                    for mv in item.get("upstream_movements") or []
                ],
                "path": item.get("path"),
                "dominant": True,
            }
        )

    center_tuple = [center[0], center[1]] if center else None
    return {
        "action": "map_scene",
        "phase": "arterial_analysis",
        "available": True,
        "center": center_tuple,
        "trace_direction": "upstream",
        "entry_traces": entry_traces,
        "hud": {
            "title": "干线协调分析",
            "metrics": [
                {"label": "上游到达流量", "value": str(arterial_analysis.get("upstream_arrival_flow_vph") or "-")},
                {"label": "上游放行强度", "value": str(arterial_analysis.get("upstream_release_intensity_vph") or "-")},
                {
                    "label": "目标剩余空间(m)",
                    "value": str(arterial_analysis.get("target_remaining_storage_m") or "-"),
                },
                {
                    "label": "下游剩余空间(m)",
                    "value": str(arterial_analysis.get("downstream_remaining_storage_m") or "-"),
                },
                {
                    "label": "相位差匹配",
                    "value": str(arterial_analysis.get("phase_offset_match") or "-"),
                },
                {
                    "label": "上游控流",
                    "value": "需要" if arterial_analysis.get("need_upstream_metering") else "暂不需要",
                    "severity": "high" if arterial_analysis.get("need_upstream_metering") else "low",
                },
            ],
        },
        "speakable": arterial_analysis.get("summary"),
        "coordination": coordination or {"available": False, "reason": "no_coordination"},
    }
