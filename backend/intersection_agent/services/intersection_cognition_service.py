"""Fetch static intersection cognition: geometry, channelization, direction metrics."""

from __future__ import annotations

import logging
import math
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.models.domain import NluResult
from intersection_agent.utils.data_window import build_data_window
from intersection_agent.utils.demo_config import resolve_reference_date

logger = logging.getLogger(__name__)

# 济南市中心（GCJ-02），用于全市视角
JINAN_CENTER = {"lon": 117.000923, "lat": 36.675807, "zoom": 11}

DIR4_TO_GROUP = {
    "东": "东西向",
    "西": "东西向",
    "南": "南北向",
    "北": "南北向",
    "东南": "东南向",
    "西南": "西南向",
    "东北": "东北向",
    "西北": "西北向",
}

GROUP_ORDER = ("东西向", "南北向", "东南向", "西南向", "东北向", "西北向")


class IntersectionCognitionService:
    """Load channelization and per-direction metrics for map presentation."""

    def __init__(
        self,
        pool: PostgresPool | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._pool = pool or PostgresPool()
        self._settings = settings or get_settings()

    async def fetch(
        self,
        inter_id: str,
        inter_name: str,
        nlu: NluResult | None = None,
    ) -> dict[str, Any]:
        """Return cognition payload for frontend map channelization."""
        if self._settings.mock_db:
            return self._mock_payload(inter_id, inter_name, nlu)

        await self._pool.connect()
        road_schema = self._settings.pgschema
        version_id = self._settings.pg_version_id

        inter_row = await self._pool.fetchrow(
            f"""
            SELECT inter_id, inter_name, is_signalized, inter_type, inter_proto, entr_cnt,
                   ST_X(ST_GeomFromText(geom_center)) AS center_lon,
                   ST_Y(ST_GeomFromText(geom_center)) AS center_lat
            FROM {road_schema}.dim_inter_info
            WHERE version_id = $1 AND inter_id = $2
            LIMIT 1
            """,
            version_id,
            inter_id,
        )
        if not inter_row:
            return self._empty_payload(inter_id, inter_name)

        lon = _float_or(inter_row, "center_lon")
        lat = _float_or(inter_row, "center_lat")

        link_rows = await self._pool.fetch(
            f"""
            SELECT link_id, link_role, dir4_label, dir8_label, dir8_code,
                   lane_num, c_lane_num, lane_info, turn_move,
                   link_clockwise_seq, approach_angle
            FROM {road_schema}.dwd_tfc_rltn_wide_inter_ft_link
            WHERE version_id = $1 AND inter_id = $2
            ORDER BY link_clockwise_seq NULLS LAST, link_id
            """,
            version_id,
            inter_id,
        )

        lane_rows = await self._pool.fetch(
            f"""
            SELECT link_id, lane_id, lane_no, turn_move, lane_func_code
            FROM {road_schema}.dwd_tfc_rltn_wide_inter_ft_lane
            WHERE version_id = $1 AND inter_id = $2
            ORDER BY link_id, lane_no
            """,
            version_id,
            inter_id,
        )

        lanes_by_link: dict[str, list[dict[str, Any]]] = {}
        for lr in lane_rows:
            lid = str(lr["link_id"])
            lanes_by_link.setdefault(lid, []).append(
                {
                    "lane_id": str(lr["lane_id"]),
                    "lane_seq": int(lr["lane_no"] or 0),
                    "turn_move": str(lr.get("turn_move") or ""),
                    "lane_func_code": str(lr.get("lane_func_code") or ""),
                }
            )

        arms: list[dict[str, Any]] = []
        entrance_arms: list[dict[str, Any]] = []
        for row in link_rows:
            role = str(row.get("link_role") or "")
            dir4 = str(row.get("dir4_label") or row.get("dir8_label") or "")
            link_id = str(row["link_id"])
            arm = {
                "link_id": link_id,
                "link_role": role,
                "dir4_label": dir4,
                "dir8_label": str(row.get("dir8_label") or dir4),
                "dir8_code": row.get("dir8_code"),
                "lane_num": int(row.get("lane_num") or row.get("c_lane_num") or 0),
                "lane_info": str(row.get("lane_info") or ""),
                "turn_move": str(row.get("turn_move") or ""),
                "clockwise_seq": int(row.get("link_clockwise_seq") or 0),
                "entrance_angle": _float_or(row, "approach_angle"),
                "lanes": lanes_by_link.get(link_id, []),
            }
            arms.append(arm)
            if role == "entrance" or role == "进口":
                entrance_arms.append(arm)

        if not entrance_arms:
            entrance_arms = [a for a in arms if a["dir4_label"]]

        entrance_arms = _merge_entrance_arms(entrance_arms)

        geo_rows = await self._pool.fetch(
            f"""
            SELECT r.link_id, r.link_role, r.dir4_label, r.dir8_label, r.lane_num,
                   l.geom, l.road_name
            FROM {road_schema}.dwd_tfc_rltn_wide_inter_ft_link r
            JOIN {road_schema}.dim_link_info l
              ON r.link_id = l.link_id AND r.version_id = l.version_id
            WHERE r.version_id = $1 AND r.inter_id = $2
            ORDER BY r.link_clockwise_seq NULLS LAST, r.link_id
            """,
            version_id,
            inter_id,
        )
        links = [_link_from_row(row) for row in geo_rows if _parse_linestring(row.get("geom"))]

        metrics_by_arm = await self._fetch_arm_metrics(inter_id, nlu)
        metrics_by_arm = _merge_metrics_by_direction(metrics_by_arm)
        direction_groups = _build_direction_groups(entrance_arms, metrics_by_arm)

        total_lanes = sum(a["lane_num"] for a in entrance_arms) or sum(
            len(a["lanes"]) for a in entrance_arms
        )
        arm_count = len(entrance_arms) or int(inter_row.get("entr_cnt") or 0) or len(arms)

        return {
            "city": JINAN_CENTER,
            "intersection": {
                "inter_id": inter_id,
                "name": inter_name,
                "lon": lon or JINAN_CENTER["lon"],
                "lat": lat or JINAN_CENTER["lat"],
                "zoom": 18,
                "is_signalized": bool(inter_row.get("is_signalized")),
                "inter_form": str(
                    inter_row.get("inter_type") or inter_row.get("inter_proto") or ""
                ),
                "arm_count": arm_count,
                "total_lanes": total_lanes,
            },
            "arms": entrance_arms or arms,
            "links": links,
            "direction_groups": direction_groups,
            "metrics_by_arm": metrics_by_arm,
            "available_directions": _available_direction_hints(direction_groups, entrance_arms),
        }

    async def _fetch_arm_metrics(
        self,
        inter_id: str,
        nlu: NluResult | None,
    ) -> list[dict[str, Any]]:
        """Per-arm saturation / flow from DWS when time period is known."""
        if not nlu or not nlu.time_period:
            return []

        flow_schema = self._settings.pg_flow_schema
        window = build_data_window(nlu.time_period, reference_date=resolve_reference_date())
        dws_dow = (window.primary_dow,)

        rows = await self._pool.fetch(
            f"""
            SELECT l.link_id, l.dir4_label, l.dir8_label,
                   AVG(s.turn_saturation) AS saturation,
                   MAX(s.turn_saturation) AS saturation_max
            FROM {self._settings.pgschema}.dwd_tfc_rltn_wide_inter_ft_link l
            LEFT JOIN {flow_schema}.dws_turn_saturation_5min_mm s
              ON l.inter_id = s.inter_id AND l.link_id = s.link_id
             AND s.day_of_week = ANY($2::int[])
             AND s.step_index BETWEEN $3 AND $4
             AND s.is_deleted = 0
            WHERE l.version_id = $5 AND l.inter_id = $1
              AND (l.link_role = 'entrance' OR l.link_role = '进口')
            GROUP BY l.link_id, l.dir4_label, l.dir8_label
            ORDER BY saturation_max DESC NULLS LAST
            """,
            inter_id,
            list(dws_dow),
            window.step_start,
            window.step_end,
            self._settings.pg_version_id,
        )

        result: list[dict[str, Any]] = []
        for row in rows:
            sat = _float_or(row, "saturation_max") or _float_or(row, "saturation")
            result.append(
                {
                    "link_id": str(row["link_id"]),
                    "dir4_label": str(row.get("dir4_label") or ""),
                    "dir8_label": str(row.get("dir8_label") or ""),
                    "saturation": round(sat, 3) if sat is not None else None,
                    "level": _saturation_level(sat),
                }
            )
        return result

    @staticmethod
    def _mock_payload(
        inter_id: str,
        inter_name: str,
        nlu: NluResult | None,
    ) -> dict[str, Any]:
        """Deterministic mock for dev without DB."""
        arms = [
            {
                "link_id": "mock_e",
                "link_role": "entrance",
                "dir4_label": "东",
                "dir8_label": "东",
                "lane_num": 5,
                "lane_info": "左转|直行|直行|直行|右转",
                "turn_move": "左转,直行,右转",
                "clockwise_seq": 0,
                "entrance_angle": 90.0,
                "lanes": [
                    {"lane_id": "e1", "lane_seq": 1, "turn_move": "左转"},
                    {"lane_id": "e2", "lane_seq": 2, "turn_move": "直行"},
                    {"lane_id": "e3", "lane_seq": 3, "turn_move": "直行"},
                    {"lane_id": "e4", "lane_seq": 4, "turn_move": "直行"},
                    {"lane_id": "e5", "lane_seq": 5, "turn_move": "右转"},
                ],
            },
            {
                "link_id": "mock_w",
                "link_role": "entrance",
                "dir4_label": "西",
                "dir8_label": "西",
                "lane_num": 4,
                "lane_info": "左转|直行|直行|右转",
                "turn_move": "左转,直行,右转",
                "clockwise_seq": 2,
                "entrance_angle": 270.0,
                "lanes": [
                    {"lane_id": "w1", "lane_seq": 1, "turn_move": "左转"},
                    {"lane_id": "w2", "lane_seq": 2, "turn_move": "直行"},
                    {"lane_id": "w3", "lane_seq": 3, "turn_move": "直行"},
                    {"lane_id": "w4", "lane_seq": 4, "turn_move": "右转"},
                ],
            },
            {
                "link_id": "mock_s",
                "link_role": "entrance",
                "dir4_label": "南",
                "dir8_label": "南",
                "lane_num": 3,
                "lane_info": "左转|直行|右转",
                "turn_move": "左转,直行,右转",
                "clockwise_seq": 1,
                "entrance_angle": 180.0,
                "lanes": [
                    {"lane_id": "s1", "lane_seq": 1, "turn_move": "左转"},
                    {"lane_id": "s2", "lane_seq": 2, "turn_move": "直行"},
                    {"lane_id": "s3", "lane_seq": 3, "turn_move": "右转"},
                ],
            },
            {
                "link_id": "mock_n",
                "link_role": "entrance",
                "dir4_label": "北",
                "dir8_label": "北",
                "lane_num": 3,
                "lane_info": "左转|直行|右转",
                "turn_move": "左转,直行,右转",
                "clockwise_seq": 3,
                "entrance_angle": 0.0,
                "lanes": [
                    {"lane_id": "n1", "lane_seq": 1, "turn_move": "左转"},
                    {"lane_id": "n2", "lane_seq": 2, "turn_move": "直行"},
                    {"lane_id": "n3", "lane_seq": 3, "turn_move": "右转"},
                ],
            },
        ]
        metrics_by_arm = [
            {
                "link_id": "mock_w",
                "dir4_label": "西",
                "dir8_label": "西",
                "saturation": 0.92,
                "level": "high",
            },
            {
                "link_id": "mock_e",
                "dir4_label": "东",
                "dir8_label": "东",
                "saturation": 0.78,
                "level": "medium",
            },
            {
                "link_id": "mock_s",
                "dir4_label": "南",
                "dir8_label": "南",
                "saturation": 0.55,
                "level": "low",
            },
            {
                "link_id": "mock_n",
                "dir4_label": "北",
                "dir8_label": "北",
                "saturation": 0.48,
                "level": "low",
            },
        ]
        direction_groups = _build_direction_groups(arms, metrics_by_arm)

        display_name = inter_name or "经十路与历山路路口"
        if "历山" in display_name or "奥体" in display_name:
            lon, lat = 117.038, 36.656
        else:
            lon, lat = 117.120, 36.668

        links = _mock_links(lon, lat, arms)
        return {
            "city": JINAN_CENTER,
            "intersection": {
                "inter_id": inter_id,
                "name": display_name,
                "lon": lon,
                "lat": lat,
                "zoom": 18,
                "is_signalized": True,
                "inter_form": "十字",
                "arm_count": 4,
                "total_lanes": 15,
            },
            "arms": arms,
            "links": links,
            "direction_groups": direction_groups,
            "metrics_by_arm": metrics_by_arm,
            "available_directions": _available_direction_hints(direction_groups, arms),
        }

    @staticmethod
    def _empty_payload(inter_id: str, inter_name: str) -> dict[str, Any]:
        return {
            "city": JINAN_CENTER,
            "intersection": {
                "inter_id": inter_id,
                "name": inter_name,
                "lon": JINAN_CENTER["lon"],
                "lat": JINAN_CENTER["lat"],
                "zoom": 16,
                "arm_count": 0,
                "total_lanes": 0,
            },
            "arms": [],
            "links": [],
            "direction_groups": [],
            "metrics_by_arm": [],
            "available_directions": [],
        }


def _parse_linestring(geom: Any) -> list[list[float]]:
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


def _link_from_row(row: Any) -> dict[str, Any]:
    role = str(row.get("link_role") or "")
    return {
        "link_id": str(row["link_id"]),
        "link_role": role,
        "dir4_label": str(row.get("dir4_label") or ""),
        "dir8_label": str(row.get("dir8_label") or ""),
        "lane_num": int(row.get("lane_num") or 0),
        "road_name": str(row.get("road_name") or ""),
        "path": _parse_linestring(row.get("geom")),
    }


def _mock_links(lon: float, lat: float, arms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Synthetic link polylines radiating from intersection center."""
    links: list[dict[str, Any]] = []
    span = 0.0028
    for arm in arms:
        bearing = math.radians(float(arm.get("entrance_angle") or 0))
        end_lon = lon + math.sin(bearing) * span
        end_lat = lat + math.cos(bearing) * span
        links.append(
            {
                "link_id": str(arm["link_id"]),
                "link_role": str(arm.get("link_role") or "entrance"),
                "dir4_label": str(arm.get("dir4_label") or ""),
                "dir8_label": str(arm.get("dir8_label") or ""),
                "lane_num": int(arm.get("lane_num") or 0),
                "road_name": "",
                "path": [[lon, lat], [end_lon, end_lat]],
            }
        )
    return links


def _normalize_dir_label(label: str) -> str:
    """北进口 → 北"""
    text = str(label or "").replace("进口", "").replace("出口", "").strip()
    for key in ("东北", "东南", "西北", "西南", "东", "西", "南", "北"):
        if key in text:
            return key
    return text or str(label or "")


def _merge_entrance_arms(arms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同方向多 link 时保留车道数最多的一条作为主进口。"""
    by_dir: dict[str, dict[str, Any]] = {}
    for arm in arms:
        key = _normalize_dir_label(arm.get("dir4_label", ""))
        normalized = {**arm, "dir4_label": key, "dir_label": f"{key}进口"}
        current = by_dir.get(key)
        if current is None or normalized.get("lane_num", 0) > current.get("lane_num", 0):
            by_dir[key] = normalized
    return sorted(by_dir.values(), key=lambda a: float(a.get("entrance_angle") or 0))


def _merge_metrics_by_direction(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同进口方向合并，取最大饱和度。"""
    by_dir: dict[str, dict[str, Any]] = {}
    for m in metrics:
        key = _normalize_dir_label(m.get("dir4_label", ""))
        item = {**m, "dir4_label": key}
        cur = by_dir.get(key)
        if cur is None or (item.get("saturation") or 0) > (cur.get("saturation") or 0):
            by_dir[key] = item
    return list(by_dir.values())


def fill_arm_metrics_from_overall(
    arms: list[dict[str, Any]],
    metrics_by_arm: list[dict[str, Any]],
    overall_sat: float,
) -> list[dict[str, Any]]:
    """Fill missing per-arm saturation from intersection-level rate."""
    metrics_map = {m["link_id"]: m for m in metrics_by_arm}
    dir_map = {_normalize_dir_label(m.get("dir4_label", "")): m for m in metrics_by_arm}
    filled = list(metrics_by_arm)
    for arm in arms:
        role = str(arm.get("link_role") or "")
        if role not in ("entrance", "进口"):
            continue
        link_id = arm["link_id"]
        existing = metrics_map.get(link_id)
        if (
            existing
            and existing.get("saturation") is not None
            and float(existing.get("saturation") or 0) > 0
        ):
            continue
        dir_key = _normalize_dir_label(arm.get("dir4_label", ""))
        dir_existing = dir_map.get(dir_key)
        if (
            dir_existing
            and dir_existing.get("saturation") is not None
            and float(dir_existing.get("saturation") or 0) > 0
        ):
            continue
        filled.append(
            {
                "link_id": link_id,
                "dir4_label": dir_key,
                "dir8_label": arm.get("dir8_label") or dir_key,
                "saturation": round(float(overall_sat), 3),
                "level": _saturation_level(overall_sat),
            }
        )
    return filled


def _build_direction_groups(
    arms: list[dict[str, Any]],
    metrics_by_arm: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate per-arm metrics into 东西向 / 南北向 groups."""
    metrics_map = {m["link_id"]: m for m in metrics_by_arm}
    dir_metrics_map = {_normalize_dir_label(m.get("dir4_label", "")): m for m in metrics_by_arm}
    dir_sat: dict[str, list[float]] = {}
    for arm in arms:
        key = _normalize_dir_label(arm.get("dir4_label", ""))
        m = metrics_map.get(arm["link_id"]) or dir_metrics_map.get(key)
        if not m or m.get("saturation") is None:
            continue
        sat = float(m["saturation"])
        if sat <= 0:
            continue
        group = DIR4_TO_GROUP.get(key, key or "其他")
        dir_sat.setdefault(group, []).append(sat)

    groups: list[dict[str, Any]] = []
    for group_name in GROUP_ORDER:
        sats = dir_sat.get(group_name)
        if not sats:
            continue
        avg_sat = sum(sats) / len(sats)
        max_sat = max(sats)
        groups.append(
            {
                "group": group_name,
                "saturation_avg": round(avg_sat, 3),
                "saturation_max": round(max_sat, 3),
                "level": _saturation_level(max_sat),
                "arm_labels": [
                    _normalize_dir_label(a.get("dir4_label", ""))
                    for a in arms
                    if DIR4_TO_GROUP.get(_normalize_dir_label(a.get("dir4_label", "")))
                    == group_name
                ],
            }
        )
    return groups


def _available_direction_hints(
    direction_groups: list[dict[str, Any]],
    arms: list[dict[str, Any]],
) -> list[str]:
    """Hints for follow-up: 东西向、南北向 etc."""
    if direction_groups:
        return [g["group"] for g in direction_groups]
    labels = sorted(
        {_normalize_dir_label(a.get("dir4_label", "")) for a in arms if a.get("dir4_label")}
    )
    hints: list[str] = []
    if "东" in labels and "西" in labels:
        hints.append("东西向")
    if "南" in labels and "北" in labels:
        hints.append("南北向")
    for label in labels:
        if label and label not in ("东", "西", "南", "北"):
            hints.append(f"{label}向")
    return hints or ["东西向", "南北向"]


def _saturation_level(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 0.85:
        return "high"
    if value >= 0.65:
        return "medium"
    return "low"


def _float_or(row: Any, key: str) -> float | None:
    if row is None:
        return None
    value = row.get(key)
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None
