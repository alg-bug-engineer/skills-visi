"""进口 link 内外侧判定与排序（主辅路等多 link 同方位场景）。

判定口径（中国右行）：
    1. 取 link 几何：停止线 = dim_link_info.geom 终点，来向 = 起点 → 终点；
    2. 取路口中心 = dim_inter_info.geom_center；
    3. 将「中心 → 停止线」向量投影到行进方向的「司机左手」法向；
    4. 投影值越大越靠内侧（靠近中央分隔带 / 主路走廊中心），越小越靠外侧。

同一 dir8_code 下按 lateralOffset 降序排列（内侧 link 在前），供渠化合并与
lane_info 顺序（中心线 → 外侧）对齐。
"""

from __future__ import annotations

import math
from typing import Any


def ll_to_local_m(lon: float, lat: float, ref_lat: float) -> tuple[float, float]:
    x = lon * 111_320.0 * math.cos(math.radians(ref_lat))
    y = lat * 110_540.0
    return x, y


def compute_lateral_offset(
    *,
    stop_lon: float,
    stop_lat: float,
    start_lon: float,
    start_lat: float,
    center_lon: float,
    center_lat: float,
) -> float | None:
    """进口 link 横向偏移（兼容旧调用）：停止线在终点，来向为起点→终点。"""
    return compute_side_offset(
        point_lon=stop_lon,
        point_lat=stop_lat,
        travel_from_lon=start_lon,
        travel_from_lat=start_lat,
        travel_to_lon=stop_lon,
        travel_to_lat=stop_lat,
        center_lon=center_lon,
        center_lat=center_lat,
    )


def compute_side_offset(
    *,
    point_lon: float,
    point_lat: float,
    travel_from_lon: float,
    travel_from_lat: float,
    travel_to_lon: float,
    travel_to_lat: float,
    center_lon: float,
    center_lat: float,
) -> float | None:
    """路口断面处横向偏移（米）：正值 = 司机左手 = 内侧。

    point_* 取 link 在路口一侧的断面坐标；travel_from→travel_to 为离开路口时的行进方向。
    """
    ref_lat = center_lat
    sx, sy = ll_to_local_m(travel_from_lon, travel_from_lat, ref_lat)
    ex, ey = ll_to_local_m(travel_to_lon, travel_to_lat, ref_lat)
    tx, ty = ex - sx, ey - sy
    length = math.hypot(tx, ty)
    if length < 1e-6:
        return None
    ux, uy = tx / length, ty / length
    lx, ly = -uy, ux
    cx, cy = ll_to_local_m(center_lon, center_lat, ref_lat)
    px, py = ll_to_local_m(point_lon, point_lat, ref_lat)
    vx, vy = px - cx, py - cy
    return vx * lx + vy * ly


def compute_distance_to_center(
    *,
    stop_lon: float,
    stop_lat: float,
    center_lon: float,
    center_lat: float,
) -> float:
    ref_lat = center_lat
    cx, cy = ll_to_local_m(center_lon, center_lat, ref_lat)
    px, py = ll_to_local_m(stop_lon, stop_lat, ref_lat)
    return math.hypot(px - cx, py - cy)


def _side_label_for_group(rank: int, group_size: int) -> str | None:
    if group_size <= 1:
        return None
    if rank == 1:
        return "inner"
    if rank == group_size:
        return "outer"
    return "middle"


def annotate_lane_sides(lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """lane_info 顺序：第 1 条靠中心线（内侧），最后一条最外侧。"""
    total = len(lanes)
    annotated: list[dict[str, Any]] = []
    for idx, lane in enumerate(lanes, start=1):
        item = dict(lane)
        item["laneNo"] = idx
        if total <= 1:
            item["laneSide"] = "inner"
        elif idx == 1:
            item["laneSide"] = "inner"
        elif idx == total:
            item["laneSide"] = "outer"
        else:
            item["laneSide"] = "middle"
        annotated.append(item)
    return annotated


def annotate_and_sort_approaches(
    approaches: list[dict[str, Any]],
    *,
    center_lon: float | None,
    center_lat: float | None,
) -> list[dict[str, Any]]:
    """为各进口 link 标注内外侧并排序；无几何数据时保持原序。"""
    if not approaches:
        return []

    enriched: list[dict[str, Any]] = []
    for approach in approaches:
        item = dict(approach)
        lanes = item.get("lanes") or []
        item["lanes"] = annotate_lane_sides(lanes)
        link_role = str(item.get("linkRole") or "entrance")

        pos_lon = _to_float(item.pop("_positionLon", None))
        pos_lat = _to_float(item.pop("_positionLat", None))
        travel_from_lon = _to_float(item.pop("_travelFromLon", None))
        travel_from_lat = _to_float(item.pop("_travelFromLat", None))
        travel_to_lon = _to_float(item.pop("_travelToLon", None))
        travel_to_lat = _to_float(item.pop("_travelToLat", None))

        stop_lon = _to_float(item.pop("_stopLon", None))
        stop_lat = _to_float(item.pop("_stopLat", None))
        start_lon = _to_float(item.pop("_startLon", None))
        start_lat = _to_float(item.pop("_startLat", None))

        if pos_lon is None and stop_lon is not None:
            pos_lon = stop_lon
            pos_lat = stop_lat
        if travel_from_lon is None and start_lon is not None and stop_lon is not None:
            travel_from_lon = start_lon
            travel_from_lat = start_lat
            travel_to_lon = stop_lon
            travel_to_lat = stop_lat

        lateral = None
        distance = None
        if (
            center_lon is not None
            and center_lat is not None
            and pos_lon is not None
            and pos_lat is not None
            and travel_from_lon is not None
            and travel_from_lat is not None
            and travel_to_lon is not None
            and travel_to_lat is not None
        ):
            lateral = compute_side_offset(
                point_lon=pos_lon,
                point_lat=pos_lat,
                travel_from_lon=travel_from_lon,
                travel_from_lat=travel_from_lat,
                travel_to_lon=travel_to_lon,
                travel_to_lat=travel_to_lat,
                center_lon=center_lon,
                center_lat=center_lat,
            )
            distance = compute_distance_to_center(
                stop_lon=pos_lon,
                stop_lat=pos_lat,
                center_lon=center_lon,
                center_lat=center_lat,
            )

        item["lateralOffset"] = round(lateral, 2) if lateral is not None else None
        item["distanceToCenter"] = round(distance, 2) if distance is not None else None
        if pos_lon is not None and pos_lat is not None:
            item["stopLon"] = pos_lon
            item["stopLat"] = pos_lat
        item["linkRole"] = link_role
        enriched.append(item)

    by_group: dict[tuple[int | None, str], list[dict[str, Any]]] = {}
    for item in enriched:
        dir8 = _to_int(item.get("dir8Code"))
        role = str(item.get("linkRole") or "entrance")
        by_group.setdefault((dir8, role), []).append(item)

    ordered: list[dict[str, Any]] = []
    for dir8, role in sorted(by_group, key=lambda key: (key[0] is None, key[0] if key[0] is not None else -1, key[1])):
        group = by_group[(dir8, role)]
        if center_lon is not None and any(row.get("lateralOffset") is not None for row in group):
            group.sort(
                key=lambda row: (
                    row.get("lateralOffset") is None,
                    -(row.get("lateralOffset") or 0.0),
                    str(row.get("linkId") or ""),
                )
            )
        else:
            group.sort(key=lambda row: str(row.get("linkId") or ""))

        for rank, row in enumerate(group, start=1):
            row["sideRank"] = rank
            row["sideLabel"] = _side_label_for_group(rank, len(group))
            ordered.append(row)

    return ordered


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
