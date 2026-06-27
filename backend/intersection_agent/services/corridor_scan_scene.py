"""Build corridor_scan_scene map payload for frontend."""

from __future__ import annotations

from typing import Any


def build_corridor_scan_scene(scan: dict[str, Any]) -> dict[str, Any]:
    intersections = scan.get("intersections") or []
    polyline = scan.get("polyline") or []
    if not polyline:
        polyline = [
            [float(item["lon"]), float(item["lat"])]
            for item in intersections
            if item.get("lon") is not None and item.get("lat") is not None
        ]

    points = polyline if polyline else [
        [float(item["lon"]), float(item["lat"])]
        for item in intersections
        if item.get("lon") is not None and item.get("lat") is not None
    ]
    bounds = _bounds_from_points(points)

    ranked = [i for i in intersections if i.get("has_data") and i.get("rank")]
    ranked.sort(key=lambda x: int(x.get("rank") or 999))
    focus = ranked[0] if ranked else None
    focus_inter_id = focus.get("inter_id") if focus else None

    if focus and focus.get("lon") is not None and focus.get("lat") is not None:
        center = [float(focus["lon"]), float(focus["lat"])]
        zoom = 16.8
    else:
        center, zoom = _camera_from_bounds(bounds)

    markers: list[dict[str, Any]] = []
    for item in intersections:
        lon, lat = item.get("lon"), item.get("lat")
        if lon is None or lat is None:
            continue
        rank = item.get("rank")
        sat = (item.get("metrics") or {}).get("saturation_max")
        is_focus = str(item.get("inter_id")) == str(focus_inter_id) if focus_inter_id else False
        markers.append(
            {
                "id": f"corridor-scan-{item.get('inter_id')}",
                "lon": float(lon),
                "lat": float(lat),
                "kind": "corridor-scan",
                "variant": "rank" if rank else "no-data",
                "title": str(item.get("inter_name") or ""),
                "subtitle": item.get("annotation") or "",
                "value": f"{float(sat):.2f}" if sat is not None else "—",
                "severity": item.get("severity") or "unknown",
                "inter_id": item.get("inter_id"),
                "inter_name": item.get("inter_name"),
                "rank": rank,
                "selected": is_focus,
                "metrics": item.get("metrics") or {},
                "has_data": bool(item.get("has_data")),
            }
        )

    tp = scan.get("time_period") or {}
    lm = scan.get("line_metrics") or {}
    display_name = scan.get("road_name") or scan.get("line_name") or "干线"
    hud_metrics = [
        {
            "label": "信控路口",
            "value": f"{scan.get('data_coverage_count', 0)}/{scan.get('intersection_count', 0)}有数据",
        },
    ]
    if lm.get("delay_index") is not None:
        hud_metrics.append(
            {"label": "干线延误", "value": f"{float(lm['delay_index']):.2f}"}
        )

    return {
        "action": "corridor_scan_scene",
        "phase": "corridor_scan",
        "corridor": {
            "line_id": scan.get("line_id"),
            "line_name": display_name,
            "bounds": bounds,
            "polyline": polyline,
            "envelope_style": "path",
        },
        "time_period": tp,
        "intersections": intersections,
        "top3_inter_ids": scan.get("top3_inter_ids") or [],
        "focus_inter_id": focus_inter_id,
        "camera": {"center": center, "zoom": zoom},
        "center": center,
        "zoom": zoom,
        "hud": {
            "title": f"{display_name} · {tp.get('label', '时段')}",
            "icon": "🛣️",
            "metrics": hud_metrics,
        },
        "markers": markers,
        "highlight_dirs": [],
        "pulse_link_ids": [],
        "dim_other_links": False,
    }


def _bounds_from_points(points: list[list[float]]) -> dict[str, list[float]]:
    if not points:
        return {"sw": [117.0, 36.65], "ne": [117.12, 36.67]}
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    pad_lon = max((max(lons) - min(lons)) * 0.08, 0.003)
    pad_lat = max((max(lats) - min(lats)) * 0.08, 0.003)
    return {
        "sw": [min(lons) - pad_lon, min(lats) - pad_lat],
        "ne": [max(lons) + pad_lon, max(lats) + pad_lat],
    }


def _camera_from_bounds(bounds: dict[str, list[float]]) -> tuple[list[float], float]:
    sw, ne = bounds["sw"], bounds["ne"]
    center = [(sw[0] + ne[0]) / 2, (sw[1] + ne[1]) / 2]
    span = max(ne[0] - sw[0], ne[1] - sw[1])
    zoom = 13.0 if span > 0.06 else 13.8 if span > 0.03 else 14.5
    return center, zoom
