"""Map scene payload aligned with references/流量溯源 frontend types/map.ts."""

from __future__ import annotations

from typing import Any

from app.trace.geometry import orient_path, parse_linestring_wkt


def _json_number(value: Any) -> int | float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


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


def _metric_by_link(raw: dict[str, Any], key: str) -> dict[str, float]:
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
                out[link_id] = float(row[metric_key])
                break
            except (TypeError, ValueError):
                continue
    return out


def _channelization_by_link(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in raw.get("channelization") or []:
        link_id = str(row.get("link_id") or "")
        if link_id:
            out[link_id] = row
    return out


def _best_share_by_inter(raw: dict[str, Any], dir8_code: int, turn_dir_no: int) -> dict[str, float]:
    """Return real flow-correlate share by correlated intersection id.

    Preferred rows match the problem movement; same-entry fallback is retained because the
    reference sniff view shows all real peers rather than fabricating missing percentages.
    """
    best: dict[str, tuple[float, float]] = {}
    for row in raw.get("flow_correlate") or []:
        try:
            row_dir8 = int(row.get("f_dir8_no"))
        except (TypeError, ValueError):
            continue
        if row_dir8 != int(dir8_code):
            continue
        cor_id = str(row.get("cor_inter_id") or "")
        if not cor_id:
            continue
        try:
            share = float(row.get("flow_share_ratio") or row.get("share_pct") or 0)
        except (TypeError, ValueError):
            continue
        movement_bonus = 1000.0 if int(row.get("turn_dir_no") or 0) == int(turn_dir_no) else 0.0
        score = movement_bonus + share
        prev = best.get(cor_id)
        if prev is None or score > prev[0]:
            best[cor_id] = (score, share)
    return {inter_id: share for inter_id, (_, share) in best.items()}


def _correlate_peers(
    raw: dict[str, Any],
    *,
    dir8_code: int,
    turn_dir_no: int,
    trace_direction: str,
) -> list[dict[str, Any]]:
    """Aggregate all real flow-correlate peers for the requested movement."""
    trace_type = "UPSTREAM" if trace_direction == "downstream" else "DOWNSTREAM"
    peers: dict[str, dict[str, Any]] = {}
    for row in raw.get("flow_correlate") or []:
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
            share = float(row.get("flow_share_ratio") or row.get("share_pct") or 0)
        except (TypeError, ValueError):
            continue
        try:
            cor_d8 = int(row.get("cor_f_dir8_no"))
        except (TypeError, ValueError):
            cor_d8 = None
        try:
            cor_turn = int(row.get("cor_turn_dir_no"))
        except (TypeError, ValueError):
            cor_turn = None
        prev = peers.get(cor_id)
        if prev is None or share > float(prev.get("path_coverage") or -1):
            peers[cor_id] = {
                "cor_inter_id": cor_id,
                "cor_inter_name": row.get("cor_inter_name") or cor_id,
                "cor_f_dir8_no": cor_d8,
                "cor_turn_dir_no": cor_turn,
                "path_coverage": share,
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
    shares = _best_share_by_inter(raw, dir8_code, turn_dir_no)
    channel_by_link = _channelization_by_link(raw)

    target_links: list[dict[str, Any]] = []
    for row in geom_rows:
        link_id = str(row.get("link_id") or "")
        path = parse_linestring_wkt(row.get("geom_wkt"))
        if len(path) < 2:
            continue
        target_links.append(_link_payload(row, channel_by_link.get(link_id, {}), path))

    if not target_links:
        return {"action": "map_scene", "phase": "flow_trace_links_sniff_map", "available": False, "reason": "no_link_geometry"}

    trace_dir = "downstream" if trace_direction == "downstream" else "upstream"
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
    )
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
        in_main = peer.get("cor_f_dir8_no") == dir8_code and peer.get("cor_turn_dir_no") == 2
        corridor_hop = idx if in_main else 0
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
            "links": geometry.get("links") or [],
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

    peer_list = list(peers.values())
    peer_list.sort(
        key=lambda n: (
            0 if n.get("in_main_corridor") else 1,
            n.get("corridor_hop") or 999,
            -(n.get("path_coverage") or 0),
        )
    )

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
    main_chain = [
        {
            "hop": node.get("corridor_hop"),
            "inter_id": node.get("inter_id"),
            "name": node.get("name"),
            "coverage": node.get("path_coverage"),
        }
        for node in peer_list
        if node.get("in_main_corridor")
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
        "logic": "real link geometry + flow_correlate share; target/main/other grouped like link sniff reference",
        "stats": {
            "raw_rows": len(raw.get("flow_correlate") or []),
            "distinct_peers": len(peer_list),
            "rendered": len(intersections),
            "main_corridor": len(main_chain),
            "missing_center": sum(1 for n in peer_list if not n.get("center")),
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
                    "saturation": saturation.get(link_id),
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
                "downstream_inter_id": item.get("downstream_inter_id"),
                "name": item.get("downstream_inter_name"),
                "share_pct": item.get("share_pct"),
                "path": item.get("path"),
                "lon": item.get("lng"),
                "lat": item.get("lat"),
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
            }
        )

    governance = downstream_trace.get("governance") or {}
    return {
        "action": "map_scene",
        "phase": "downstream_trace_map",
        "available": True,
        "center": center_tuple,
        "trace_direction": "downstream",
        "turn_traces": turn_traces,
        "adjacent_intersections": adjacent,
        "hud": {
            "title": "下游一跳去向",
            "metrics": [
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
    }
