"""真实路网几何解析工具（流量溯源上下游 link 折线）。

数据真源（见 docs/rule.md 约束16/19）：link 折线来自 PG `road6.dim_link_info.geom`
（`ST_AsText` 输出 WKT `LINESTRING`），路口中心来自 `dim_inter_info.geom_center`。
本模块只做纯几何解析/定向，不合成、不伪造任何坐标。
"""

from __future__ import annotations

import re

LngLat = list[float]

_LINESTRING_RE = re.compile(r"LINESTRING\s*\(([^)]+)\)", re.IGNORECASE)
_POINT_RE = re.compile(r"POINT\s*\(([^)]+)\)", re.IGNORECASE)


def parse_linestring_wkt(wkt: str | None) -> list[LngLat]:
    """将 WKT `LINESTRING(...)` 解析为 [[lng,lat], ...]；无效返回 []。"""
    if not wkt:
        return []
    match = _LINESTRING_RE.search(str(wkt).strip())
    if not match:
        return []
    points: list[LngLat] = []
    for pair in match.group(1).split(","):
        parts = pair.strip().split()
        if len(parts) >= 2:
            try:
                points.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    return points


def parse_point_wkt(wkt: str | None) -> LngLat | None:
    """将 WKT `POINT(lng lat)` 解析为 [lng,lat]；无效返回 None。"""
    if not wkt:
        return None
    match = _POINT_RE.search(str(wkt).strip())
    if not match:
        return None
    parts = match.group(1).strip().split()
    if len(parts) < 2:
        return None
    try:
        return [float(parts[0]), float(parts[1])]
    except ValueError:
        return None


def _dist2(lng: float, lat: float, point: LngLat) -> float:
    return (point[0] - lng) ** 2 + (point[1] - lat) ** 2


def orient_path(
    path: list[LngLat],
    start_lng: float | None,
    start_lat: float | None,
    end_lng: float | None,
    end_lat: float | None,
) -> list[LngLat]:
    """定向折线，使 path[0] 靠近起点、path[-1] 靠近终点（就近翻转，不改坐标）。"""
    if len(path) < 2 or start_lng is None or start_lat is None or end_lng is None or end_lat is None:
        return path
    d_head_start = _dist2(start_lng, start_lat, path[0])
    d_head_end = _dist2(end_lng, end_lat, path[0])
    oriented = list(reversed(path)) if d_head_end < d_head_start else list(path)
    d_start = _dist2(start_lng, start_lat, oriented[0])
    d_end = _dist2(start_lng, start_lat, oriented[-1])
    if d_end < d_start:
        oriented = list(reversed(oriented))
    return oriented
