"""溯源表全量路口 link 地图：dws_tfc_inter_turn_flow_correlate_m → 全部 distinct 上游路口 + dim_link_info。"""
from __future__ import annotations

import logging
import math
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.services.flow_trace_service import (
    FlowTraceService,
    day_labels_for_filter,
    period_type_from_label,
)
from intersection_agent.services.upstream_topology_service import parse_linestring_wkt
from intersection_agent.utils.data_window import DataWindow
from intersection_agent.utils.traffic_labels import DIR8_LABELS

logger = logging.getLogger(__name__)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class UpstreamCorrelateMapService:
    """从溯源表拉取某进口×转向的全部上游路口，并附带各路口 link geom。"""

    def __init__(
        self,
        flow_trace: FlowTraceService | None = None,
        pool: PostgresPool | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._flow_trace = flow_trace or FlowTraceService(settings=self._settings)
        self._pool = pool or PostgresPool(self._settings)

    async def build(
        self,
        inter_id: str,
        *,
        dir8: int,
        turn_no: int | None,
        approach: str,
        window: DataWindow,
        period_label: str | None,
        cognition: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if self._settings.mock_db:
            return self._mock_payload(inter_id, dir8, turn_no, approach, cognition)

        period_type = period_type_from_label(period_label)
        day_labels = day_labels_for_filter(window.dow_filter)
        rows = await self._flow_trace._fetch_upstream(inter_id, period_type, day_labels)
        if not rows:
            return None

        filtered = [
            r
            for r in rows
            if int(r.get("f_dir8_no") or -1) == int(dir8)
            and (turn_no is None or int(r.get("turn_dir_no") or -1) == int(turn_no))
        ]
        if not filtered:
            return None

        upstream_map: dict[str, dict[str, Any]] = {}
        for r in filtered:
            cid = str(r.get("cor_inter_id") or "")
            if not cid:
                continue
            cov = _as_float(r.get("flow_share_ratio"))
            if cov is None:
                continue
            cor_d8 = int(r["cor_f_dir8_no"])
            cor_turn = int(r["cor_turn_dir_no"])
            prev = upstream_map.get(cid)
            item = {
                "cor_inter_id": cid,
                "cor_inter_name": str(r.get("cor_inter_name") or cid),
                "cor_f_dir8_no": cor_d8,
                "cor_turn_dir_no": cor_turn,
                "path_coverage": cov,
                "lng": _as_float(r.get("cor_lng")),
                "lat": _as_float(r.get("cor_lat")),
            }
            if prev is None or cov > prev["path_coverage"]:
                upstream_map[cid] = item

        upstream_list = sorted(upstream_map.values(), key=lambda x: -x["path_coverage"])
        main_turn = turn_no if turn_no is not None else 2
        corridor_chain = [
            u
            for u in upstream_list
            if u["cor_f_dir8_no"] == dir8 and u["cor_turn_dir_no"] == main_turn
        ]
        corridor_ids = {u["cor_inter_id"] for u in corridor_chain}
        for i, u in enumerate(corridor_chain):
            u["corridor_hop"] = i + 1

        inter = (cognition or {}).get("intersection") or {}
        target_center = await self._inter_center(inter_id)
        if not target_center:
            lon = _as_float(inter.get("lng") or inter.get("lon"))
            lat = _as_float(inter.get("lat"))
            if lon is not None and lat is not None:
                target_center = (lon, lat)

        intersections: list[dict[str, Any]] = []
        if target_center:
            intersections.append(
                await self._node_payload(
                    inter_id,
                    str(inter.get("name") or inter_id),
                    target_center,
                    role="target",
                    path_coverage=None,
                    in_main_corridor=False,
                    corridor_hop=0,
                )
            )

        for u in upstream_list:
            center = await self._inter_center(u["cor_inter_id"])
            if not center and u.get("lng") is not None and u.get("lat") is not None:
                center = (float(u["lng"]), float(u["lat"]))
            if not center:
                continue
            intersections.append(
                await self._node_payload(
                    u["cor_inter_id"],
                    u["cor_inter_name"],
                    center,
                    role="upstream",
                    path_coverage=round(u["path_coverage"], 1),
                    cor_f_dir8_no=u["cor_f_dir8_no"],
                    cor_turn_dir_no=u["cor_turn_dir_no"],
                    in_main_corridor=u["cor_inter_id"] in corridor_ids,
                    corridor_hop=u.get("corridor_hop"),
                )
            )

        if len(intersections) < 2:
            return None

        return {
            "approach": approach,
            "dir8_code": dir8,
            "turn_dir_no": turn_no,
            "source": "dws_tfc_inter_turn_flow_correlate_m",
            "stats": {
                "raw_rows": len(filtered),
                "distinct_upstream": len(upstream_map),
                "rendered_upstream": len(intersections) - 1,
                "main_corridor_count": len(corridor_chain),
            },
            "main_corridor_chain": [
                {
                    "hop": i + 1,
                    "inter_id": u["cor_inter_id"],
                    "name": u["cor_inter_name"],
                    "path_coverage": round(u["path_coverage"], 1),
                }
                for i, u in enumerate(corridor_chain)
            ],
            "intersections": intersections,
        }

    async def _node_payload(
        self,
        inter_id: str,
        name: str,
        center: tuple[float, float],
        *,
        role: str,
        path_coverage: float | None,
        cor_f_dir8_no: int | None = None,
        cor_turn_dir_no: int | None = None,
        in_main_corridor: bool,
        corridor_hop: int | None,
    ) -> dict[str, Any]:
        return {
            "inter_id": inter_id,
            "name": name,
            "center": [center[0], center[1]],
            "role": role,
            "path_coverage": path_coverage,
            "cor_f_dir8_no": cor_f_dir8_no,
            "cor_turn_dir_no": cor_turn_dir_no,
            "in_main_corridor": in_main_corridor,
            "corridor_hop": corridor_hop,
            "links": await self._fetch_links(inter_id),
        }

    async def _inter_center(self, inter_id: str) -> tuple[float, float] | None:
        await self._pool.connect()
        rs, vid = self._settings.pgschema, self._settings.pg_version_id
        row = await self._pool.fetchrow(
            f"""
            SELECT ST_X(ST_GeomFromText(geom_center)) AS lon,
                   ST_Y(ST_GeomFromText(geom_center)) AS lat
            FROM {rs}.dim_inter_info
            WHERE inter_id = $1 AND version_id = $2
            """,
            inter_id,
            vid,
        )
        if not row or row["lon"] is None:
            return None
        return float(row["lon"]), float(row["lat"])

    async def _fetch_links(self, inter_id: str) -> list[dict[str, Any]]:
        await self._pool.connect()
        rs, vid = self._settings.pgschema, self._settings.pg_version_id
        rows = await self._pool.fetch(
            f"""
            SELECT r.link_id, r.link_role, r.dir4_label, r.dir8_label, r.lane_num,
                   l.road_name, ST_AsText(l.geom) AS geom_wkt
            FROM {rs}.dwd_tfc_rltn_wide_inter_ft_link r
            JOIN {rs}.dim_link_info l
              ON r.link_id = l.link_id AND r.version_id = l.version_id
            WHERE r.version_id = $1 AND r.inter_id = $2
            ORDER BY r.link_clockwise_seq NULLS LAST, r.link_id
            """,
            vid,
            inter_id,
        )
        links: list[dict[str, Any]] = []
        for row in rows:
            path = parse_linestring_wkt(row.get("geom_wkt"))
            if len(path) < 2:
                continue
            links.append(
                {
                    "link_id": str(row["link_id"]),
                    "link_role": str(row.get("link_role") or ""),
                    "dir4_label": str(row.get("dir4_label") or ""),
                    "dir8_label": str(row.get("dir8_label") or ""),
                    "lane_num": int(row.get("lane_num") or 0),
                    "road_name": str(row.get("road_name") or ""),
                    "path": path,
                }
            )
        return links

    def _mock_payload(
        self,
        inter_id: str,
        dir8: int,
        turn_no: int | None,
        approach: str,
        cognition: dict[str, Any] | None,
    ) -> dict[str, Any]:
        inter = (cognition or {}).get("intersection") or {}
        lon = _as_float(inter.get("lng") or inter.get("lon")) or 117.11
        lat = _as_float(inter.get("lat")) or 36.65
        label = DIR8_LABELS.get(dir8, "西")
        ups = [
            ("mock_up1", f"{label}向演示上游一", 0.01, 90.1, True, 1),
            ("mock_up2", f"{label}向演示上游二", 0.02, 76.5, True, 2),
            ("mock_up3", "其他来向演示路口", -0.01, 15.3, False, None),
        ]
        intersections: list[dict[str, Any]] = [
            {
                "inter_id": inter_id,
                "name": str(inter.get("name") or "演示路口"),
                "center": [lon, lat],
                "role": "target",
                "path_coverage": None,
                "in_main_corridor": False,
                "corridor_hop": 0,
                "links": self._mock_links(lon, lat, 4),
            }
        ]
        chain = []
        for i, (uid, name, dlon, cov, main, hop) in enumerate(ups, 1):
            ulon, ulat = lon + dlon, lat + dlon * 0.3
            intersections.append(
                {
                    "inter_id": uid,
                    "name": name,
                    "center": [ulon, ulat],
                    "role": "upstream",
                    "path_coverage": cov,
                    "cor_f_dir8_no": dir8,
                    "cor_turn_dir_no": turn_no or 2,
                    "in_main_corridor": main,
                    "corridor_hop": hop,
                    "links": self._mock_links(ulon, ulat, 3),
                }
            )
            if main and hop:
                chain.append({"hop": hop, "inter_id": uid, "name": name, "path_coverage": cov})
        return {
            "approach": approach,
            "dir8_code": dir8,
            "turn_dir_no": turn_no,
            "source": "mock",
            "stats": {
                "raw_rows": 3,
                "distinct_upstream": 3,
                "rendered_upstream": 3,
                "main_corridor_count": 2,
            },
            "main_corridor_chain": chain,
            "intersections": intersections,
        }

    @staticmethod
    def _mock_links(lon: float, lat: float, n: int) -> list[dict[str, Any]]:
        links = []
        for i in range(n):
            bearing = i * 90
            br = math.radians(bearing)
            end = [lon + math.sin(br) * 0.004, lat + math.cos(br) * 0.004]
            links.append(
                {
                    "link_id": f"mock_link_{i}",
                    "link_role": "entrance" if i % 2 == 0 else "exit",
                    "dir4_label": f"进口{i}",
                    "dir8_label": "",
                    "lane_num": 3,
                    "road_name": "",
                    "path": [[lon, lat], end],
                }
            )
        return links
