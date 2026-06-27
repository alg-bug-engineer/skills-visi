"""Parse, chain, and merge corridor link geometries for traffic visualization."""

from __future__ import annotations

import math
import re
from collections import deque
from typing import Any


def parse_linestring(geom: Any) -> list[list[float]]:
    """Parse LINESTRING(lon lat, ...) into [[lon, lat], ...]."""
    if not geom:
        return []
    text = str(geom).strip()
    if not text.upper().startswith("LINESTRING"):
        return []
    inner = text[text.index("(") + 1 : text.rindex(")")]
    points: list[list[float]] = []
    for pair in inner.split(","):
        parts = pair.strip().split()
        if len(parts) >= 2:
            try:
                points.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    return points


def parse_point(geom: Any) -> list[float] | None:
    """Parse POINT(lon lat) into [lon, lat]."""
    if not geom:
        return None
    text = str(geom).strip()
    if not text.upper().startswith("POINT"):
        return None
    inner = text[text.index("(") + 1 : text.rindex(")")]
    parts = inner.strip().split()
    if len(parts) < 2:
        return None
    try:
        return [float(parts[0]), float(parts[1])]
    except ValueError:
        return None


def normalize_road_token(name: str) -> str:
    """Normalize口语道路名，如「奥体西」→「奥体西路」。"""
    token = name.strip().replace("交叉口", "").replace("路口", "")
    if not token:
        return token
    if re.fullmatch(r"奥体西", token):
        return "奥体西路"
    if "奥体西" in token and "奥体西路" not in token:
        token = token.replace("奥体西", "奥体西路")
    if token and not re.search(r"(路|街|大道|线)$", token) and len(token) <= 10:
        return f"{token}路"
    return token


def extract_junction_roads(text: str) -> tuple[str, str] | None:
    """Extract two road names from 「A与B」 style phrases."""
    cleaned = text.strip().replace("交叉口", "").replace("路口", "")
    match = re.search(
        r"([\u4e00-\u9fff]{2,14}?)与([\u4e00-\u9fff]{2,14}?)",
        cleaned,
    )
    if not match:
        return None
    return normalize_road_token(match.group(1)), normalize_road_token(match.group(2))


def merge_paths(segments: list[list[list[float]]]) -> list[list[float]]:
    """Concatenate link paths, dropping duplicate junction points."""
    merged: list[list[float]] = []
    for path in segments:
        if not path:
            continue
        if not merged:
            merged.extend(path)
            continue
        if _same_point(merged[-1], path[0]):
            merged.extend(path[1:])
        else:
            merged.extend(path)
    return merged


def build_centerline_from_inter_chain(
    inter_ids: list[str],
    links: list[dict[str, Any]],
    *,
    road_name_hint: str | None = None,
) -> tuple[list[list[float]], list[dict[str, Any]]]:
    """
    Build a single corridor centerline by chaining link geometry between
    consecutive intersections (dim_line_inter_rltn order), not by link seq_no.
    """
    if len(inter_ids) < 2:
        return [], []

    edge_map: dict[tuple[str, str], list[list[float]]] = {}
    adj: dict[str, list[str]] = {}
    link_meta: dict[tuple[str, str], dict[str, Any]] = {}

    for row in links:
        f_id = str(row.get("f_inter_id") or "")
        t_id = str(row.get("t_inter_id") or "")
        if not f_id or not t_id:
            continue
        path = parse_linestring(row.get("geom"))
        if len(path) < 2:
            continue
        score = _road_match_score(str(row.get("road_name") or ""), road_name_hint)
        for a, b, pts in ((f_id, t_id, path), (t_id, f_id, list(reversed(path)))):
            key = (a, b)
            prev = link_meta.get(key)
            if prev is None or score > int(prev.get("_score") or 0):
                edge_map[key] = pts
                link_meta[key] = {
                    "link_id": row.get("link_id"),
                    "road_name": row.get("road_name"),
                    "_score": score,
                }
        adj.setdefault(f_id, []).append(t_id)
        adj.setdefault(t_id, []).append(f_id)

    segments: list[list[list[float]]] = []
    used_links: list[dict[str, Any]] = []

    for idx in range(len(inter_ids) - 1):
        start = str(inter_ids[idx])
        goal = str(inter_ids[idx + 1])
        path_nodes = _shortest_path(adj, start, goal)
        if not path_nodes or len(path_nodes) < 2:
            continue
        for hop in range(len(path_nodes) - 1):
            a, b = path_nodes[hop], path_nodes[hop + 1]
            seg = edge_map.get((a, b))
            if not seg:
                continue
            segments.append(seg)
            meta = link_meta.get((a, b))
            if meta and meta.get("link_id"):
                used_links.append(
                    {
                        "link_id": meta["link_id"],
                        "road_name": meta.get("road_name"),
                        "from_inter_id": a,
                        "to_inter_id": b,
                    }
                )

    polyline = merge_paths(segments)
    return polyline, used_links


def snap_point_to_polyline(
    lon: float,
    lat: float,
    polyline: list[list[float]],
) -> list[float]:
    """Project a point onto the nearest location on the corridor polyline."""
    if not polyline:
        return [lon, lat]
    if len(polyline) == 1:
        return polyline[0]

    best = [lon, lat]
    best_dist = math.inf
    px, py = lon, lat

    for i in range(len(polyline) - 1):
        ax, ay = polyline[i]
        bx, by = polyline[i + 1]
        proj = _project_on_segment(px, py, ax, ay, bx, by)
        dist = _dist2(px, py, proj[0], proj[1])
        if dist < best_dist:
            best_dist = dist
            best = proj
    return best


def snap_intersections_to_polyline(
    intersections: list[dict[str, Any]],
    polyline: list[list[float]],
) -> list[dict[str, Any]]:
    """Snap intersection lon/lat to corridor centerline for map markers."""
    if not polyline:
        return intersections
    snapped: list[dict[str, Any]] = []
    for item in intersections:
        lon, lat = item.get("lon"), item.get("lat")
        if lon is None or lat is None:
            snapped.append(item)
            continue
        pt = snap_point_to_polyline(float(lon), float(lat), polyline)
        updated = dict(item)
        updated["lon"] = pt[0]
        updated["lat"] = pt[1]
        updated["geom_center_raw"] = [float(lon), float(lat)]
        snapped.append(updated)
    return snapped


def _shortest_path(adj: dict[str, list[str]], start: str, goal: str) -> list[str] | None:
    if start == goal:
        return [start]
    queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
    seen = {start}
    while queue:
        node, path = queue.popleft()
        for nb in adj.get(node, []):
            if nb in seen:
                continue
            next_path = path + [nb]
            if nb == goal:
                return next_path
            seen.add(nb)
            queue.append((nb, next_path))
    return None


def _road_match_score(road_name: str, hint: str | None) -> int:
    if not hint:
        return 0
    hint = hint.replace("路", "")
    if hint in road_name:
        return 2
    if road_name and road_name.split(":")[0].startswith(hint):
        return 1
    return 0


def _project_on_segment(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> list[float]:
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return [ax, ay]
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return [ax + t * dx, ay + t * dy]


def _dist2(ax: float, ay: float, bx: float, by: float) -> float:
    return (ax - bx) ** 2 + (ay - by) ** 2


def _same_point(a: list[float], b: list[float], eps: float = 1e-6) -> bool:
    return abs(a[0] - b[0]) < eps and abs(a[1] - b[1]) < eps
