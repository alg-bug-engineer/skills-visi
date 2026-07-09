"""投诉地点与 PG 路网 dim_inter_info 匹配。"""

from __future__ import annotations

import math
import os
import re
from typing import Any

from data.metric_reader import parse_geom_center
from data.pg_reader import connect_pg

_SPATIAL_THRESHOLD_M = 150.0


def normalize_location_name(name: str) -> str:
    text = (name or "").strip()
    text = re.sub(r"(路口|交叉口|交叉路口)$", "", text)
    text = re.sub(r"\s+", "", text)
    text = text.replace("与", "-").replace("—", "-").replace("－", "-")
    parts = [p for p in re.split(r"[-－—]", text) if p]
    parts.sort()
    return "".join(parts)


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def load_inter_catalog() -> list[dict[str, Any]]:
    with connect_pg() as conn:
        schema = os.getenv("PGSCHEMA", "road6")
        table = os.getenv("PG_DIM_INTER_TABLE", "dim_inter_info")
        qualified = f'"{schema}"."{table}"'
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT inter_id::text AS inter_id, inter_name, geom_center::text AS geom_center
                FROM {qualified}
                WHERE inter_name IS NOT NULL AND btrim(inter_name) <> ''
                """
            )
            rows = cur.fetchall()
    catalog: list[dict[str, Any]] = []
    for row in rows:
        inter_id = str(row.get("inter_id") or "").strip()
        inter_name = str(row.get("inter_name") or "").strip()
        coords = parse_geom_center(row.get("geom_center"))
        if not inter_id or not inter_name:
            continue
        catalog.append(
            {
                "inter_id": inter_id,
                "inter_name": inter_name,
                "norm_name": normalize_location_name(inter_name),
                "lon": coords[0] if coords else None,
                "lat": coords[1] if coords else None,
            }
        )
    return catalog


def match_location_to_inter(
    *,
    location_text: str,
    geocode_name: str = "",
    lon: float | None = None,
    lat: float | None = None,
    catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    catalog = catalog or load_inter_catalog()
    loc_norm = normalize_location_name(location_text)
    geo_norm = normalize_location_name(geocode_name) if geocode_name else ""

    if loc_norm:
        for item in catalog:
            if item["norm_name"] == loc_norm:
                return _result(item, "exact_normalized", 1.0, lon, lat)
    if geo_norm:
        for item in catalog:
            if item["norm_name"] == geo_norm:
                return _result(item, "exact_normalized", 1.0, lon, lat)

    road_parts = _road_parts(location_text) or _road_parts(geocode_name)
    if len(road_parts) >= 2:
        candidates = []
        for item in catalog:
            if all(part in item["inter_name"] for part in road_parts):
                candidates.append(item)
        if len(candidates) == 1:
            return _result(candidates[0], "contains_parts", 0.85, lon, lat)
        if len(candidates) > 1 and lon is not None and lat is not None:
            best = min(
                candidates,
                key=lambda c: _haversine_m(lon, lat, c["lon"], c["lat"])
                if c["lon"] is not None
                else 1e9,
            )
            dist = _haversine_m(lon, lat, best["lon"], best["lat"]) if best["lon"] is not None else None
            if dist is not None and dist <= _SPATIAL_THRESHOLD_M:
                score = min(0.8, 1.0 - dist / _SPATIAL_THRESHOLD_M * 0.2)
                return _result(best, "contains_parts_spatial", score, lon, lat, dist)

    if lon is not None and lat is not None:
        nearest = None
        nearest_dist = 1e9
        for item in catalog:
            if item["lon"] is None or item["lat"] is None:
                continue
            dist = _haversine_m(lon, lat, item["lon"], item["lat"])
            if dist < nearest_dist:
                nearest_dist = dist
                nearest = item
        if nearest and nearest_dist <= _SPATIAL_THRESHOLD_M:
            score = min(0.8, 1.0 - nearest_dist / _SPATIAL_THRESHOLD_M * 0.2)
            return _result(nearest, "spatial_nearest", score, lon, lat, nearest_dist)

    return {
        "inter_id": None,
        "inter_name": geocode_name or location_text,
        "match_method": "unmatched",
        "match_score": 0.0,
        "match_distance_m": None,
        "match_status": "pending_geocode" if lon is None else "unmatched",
        "roadnet_lon": None,
        "roadnet_lat": None,
    }


def _road_parts(name: str) -> list[str]:
    text = re.sub(r"(路口|交叉口|交叉路口|路段|门口)$", "", (name or "").strip())
    parts = re.split(r"[-－—与\s]+", text)
    return [p for p in parts if len(p) >= 2]


def _result(
    item: dict[str, Any],
    method: str,
    score: float,
    lon: float | None,
    lat: float | None,
    dist: float | None = None,
) -> dict[str, Any]:
    if dist is None and lon is not None and lat is not None and item.get("lon") is not None:
        dist = _haversine_m(lon, lat, item["lon"], item["lat"])
    return {
        "inter_id": item["inter_id"],
        "inter_name": item["inter_name"],
        "match_method": method,
        "match_score": round(score, 4),
        "match_distance_m": round(dist, 2) if dist is not None else None,
        "match_status": "matched",
        "roadnet_lon": item.get("lon"),
        "roadnet_lat": item.get("lat"),
    }
