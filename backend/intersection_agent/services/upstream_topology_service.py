"""拓扑一跳流量溯源：link/干线 geom 为主真值，flow_correlate 为辅证。

层 1：dim_link_info + dwd_tfc_rltn_wide_inter_ft_link → 进口邻接上一路口
层 2：flow_correlate 仅在拓扑候选集内取流量占比
层 3：路径仅来自 link.geom（禁止飞线 fallback）
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.services.flow_trace_service import (
    day_labels_for_filter,
    period_type_from_label,
    turn_split_for_upstream,
)
from intersection_agent.utils.data_window import DataWindow
from intersection_agent.utils.traffic_labels import DIR8_LABELS

logger = logging.getLogger(__name__)

_DIR8_KEYWORDS = {
    0: "北", 1: "东北", 2: "东", 3: "东南",
    4: "南", 5: "西南", 6: "西", 7: "西北",
}
# 自目标路口看向拓扑上一跳的期望方位角（度）
_DIR8_UPSTREAM_BEARING: dict[int, float] = {
    0: 0.0, 1: 45.0, 2: 90.0, 3: 135.0,
    4: 180.0, 5: 225.0, 6: 270.0, 7: 315.0,
}
_BEARING_TOLERANCE_DEG = 45.0


def _bearing_deg(from_lon: float, from_lat: float, to_lon: float, to_lat: float) -> float:
    d_lon = math.radians(to_lon - from_lon)
    lat1 = math.radians(from_lat)
    lat2 = math.radians(to_lat)
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def parse_linestring_wkt(wkt: str | None) -> list[list[float]]:
    if not wkt:
        return []
    m = re.match(r"LINESTRING\s*\((.+)\)", wkt.strip(), re.I)
    if not m:
        return []
    pts: list[list[float]] = []
    for pair in m.group(1).split(","):
        parts = pair.strip().split()
        if len(parts) >= 2:
            pts.append([float(parts[0]), float(parts[1])])
    return pts


def orient_path_upstream_to_target(
    path: list[list[float]],
    upstream_lon: float,
    upstream_lat: float,
    target_lon: float,
    target_lat: float,
) -> list[list[float]]:
    """折线方向：上游路口 → 目标路口。"""
    if len(path) < 2:
        return path

    def dist2(lon: float, lat: float, pt: list[float]) -> float:
        return (pt[0] - lon) ** 2 + (pt[1] - lat) ** 2

    d0_up = dist2(upstream_lon, upstream_lat, path[0])
    d0_tgt = dist2(target_lon, target_lat, path[0])
    if d0_tgt < d0_up:
        path = list(reversed(path))
    d_start_up = dist2(upstream_lon, upstream_lat, path[0])
    d_end_up = dist2(upstream_lon, upstream_lat, path[-1])
    if d_end_up < d_start_up:
        path = list(reversed(path))
    return path


def _filter_correlate_rows(
    rows: list[dict[str, Any]],
    *,
    dir8: int,
    turn: int | None,
    allowed_ids: set[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            if int(r["f_dir8_no"]) != int(dir8):
                continue
            if turn is not None and int(r["turn_dir_no"]) != int(turn):
                continue
        except (TypeError, ValueError, KeyError):
            continue
        cid = str(r.get("cor_inter_id") or "")
        if allowed_ids and cid not in allowed_ids:
            continue
        cov = r.get("flow_share_ratio")
        if cov is None:
            continue
        out.append(r)
    out.sort(key=lambda r: float(r.get("flow_share_ratio") or 0), reverse=True)
    return out


class UpstreamTopologyService:
    """沿进口道 link geom / 干线 seq 选取地理上一跳。"""

    def __init__(self, settings: Settings | None = None, pool: PostgresPool | None = None) -> None:
        self._settings = settings or get_settings()
        self._pool = pool or PostgresPool(self._settings)

    async def resolve_approach_link(
        self,
        inter_id: str,
        dir8: int,
        *,
        cognition: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """目标路口指定进口的邻接 link（含 geom 与 upstream_inter_id）。"""
        if self._settings.mock_db:
            return self._mock_link(inter_id, dir8)
        await self._pool.connect()
        rs, vid = self._settings.pgschema, self._settings.pg_version_id
        row = await self._pool.fetchrow(
            f"""
            SELECT l.link_id, l.f_inter_id AS upstream_inter_id, fi.inter_name AS upstream_name,
                   ST_AsText(l.geom) AS geom_wkt,
                   ST_Length(l.geom::geography) AS len_m,
                   wl.dir8_code
            FROM {rs}.dwd_tfc_rltn_wide_inter_ft_link wl
            JOIN {rs}.dim_link_info l ON l.link_id = wl.link_id AND l.version_id = wl.version_id
            LEFT JOIN {rs}.dim_inter_info fi
              ON fi.inter_id = l.f_inter_id AND fi.version_id = l.version_id
            WHERE wl.inter_id = $1 AND wl.version_id = $2
              AND wl.link_role IN ('entrance', '进口')
              AND wl.dir8_code::int = $3
            ORDER BY ST_Length(l.geom::geography) DESC NULLS LAST
            LIMIT 1
            """,
            inter_id,
            vid,
            dir8,
        )
        if row:
            return self._row_to_link(dict(row))
        return self._link_from_cognition(cognition, inter_id, dir8)

    async def resolve_line_prev_candidates(self, inter_id: str) -> list[dict[str, Any]]:
        if self._settings.mock_db:
            return []
        await self._pool.connect()
        rs = self._settings.pgschema
        rows = await self._pool.fetch(
            f"""
            SELECT prev.inter_id AS upstream_inter_id, prev.inter_name AS upstream_name,
                   prev.seq_no, l.line_name, l.line_id
            FROM {rs}.dim_line_inter_rltn cur
            JOIN {rs}.dim_line_inter_rltn prev
              ON prev.line_id = cur.line_id AND prev.seq_no = cur.seq_no - 1
            JOIN {rs}.dim_line_info l ON l.line_id = cur.line_id
            WHERE cur.inter_id = $1 AND cur.is_deleted = 0 AND prev.is_deleted = 0
            ORDER BY l.line_name
            """,
            inter_id,
        )
        return [dict(r) for r in rows]

    async def inter_center(self, inter_id: str) -> tuple[float, float] | None:
        if self._settings.mock_db:
            suffix = sum(ord(c) for c in inter_id) % 10
            return (117.11 + suffix * 0.01, 36.65)
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

    async def pick_upstream_hop(
        self,
        inter_id: str,
        dir8: int,
        *,
        turn: int | None = None,
        correlate_rows: list[dict[str, Any]] | None = None,
        cognition: dict[str, Any] | None = None,
        target_lon: float | None = None,
        target_lat: float | None = None,
    ) -> dict[str, Any] | None:
        """拓扑一跳 + correlate 佐证；返回 hop 元数据含 geom path。"""
        link = await self.resolve_approach_link(inter_id, dir8, cognition=cognition)
        if not link or not link.get("upstream_inter_id"):
            return None

        topo_id = str(link["upstream_inter_id"])
        topo_name = link.get("upstream_name")
        line_prevs = await self.resolve_line_prev_candidates(inter_id)
        allowed = {topo_id}
        for lp in line_prevs:
            allowed.add(str(lp["upstream_inter_id"]))

        if target_lon is None or target_lat is None:
            center = await self.inter_center(inter_id)
            if center:
                target_lon, target_lat = center

        up_center = await self.inter_center(topo_id)
        bearing_ok = True
        if target_lon is not None and target_lat is not None and up_center:
            bearing = _bearing_deg(target_lon, target_lat, up_center[0], up_center[1])
            expected = _DIR8_UPSTREAM_BEARING.get(dir8, 0.0)
            bearing_ok = _angle_diff(bearing, expected) <= _BEARING_TOLERANCE_DEG

        coverage: float | None = None
        source = "topo"
        if correlate_rows:
            filtered = _filter_correlate_rows(
                correlate_rows, dir8=dir8, turn=turn, allowed_ids=allowed
            )
            if filtered:
                coverage = float(filtered[0]["flow_share_ratio"])
                source = "merged" if topo_id == str(filtered[0]["cor_inter_id"]) else "topo"
            else:
                raw_best = _filter_correlate_rows(
                    correlate_rows, dir8=dir8, turn=turn, allowed_ids=set()
                )
                correlate_top = raw_best[0] if raw_best else None
                if correlate_top and not bearing_ok:
                    logger.info(
                        "upstream_topology: correlate hop %s bearing mismatch, keep topo %s",
                        correlate_top.get("cor_inter_id"),
                        topo_id,
                    )

        path = link.get("path") or []
        if path and up_center and target_lon is not None and target_lat is not None:
            path = orient_path_upstream_to_target(
                path, up_center[0], up_center[1], target_lon, target_lat
            )

        feeding_dir8 = int(link.get("dir8_code") or dir8)
        return {
            "cor_inter_id": topo_id,
            "cor_inter_name": topo_name,
            "feeding_dir8": feeding_dir8,
            "coverage": coverage,
            "lng": up_center[0] if up_center else None,
            "lat": up_center[1] if up_center else None,
            "path": path,
            "path_source": "link_geom" if len(path) >= 2 else "none",
            "hop_source": source,
            "bearing_ok": bearing_ok,
            "link_id": link.get("link_id"),
        }

    async def build_hop_path(
        self,
        upstream_inter_id: str,
        target_inter_id: str,
        approach_dir8: int,
        *,
        cognition: dict[str, Any] | None = None,
    ) -> list[list[float]]:
        link = await self.resolve_approach_link(
            target_inter_id, approach_dir8, cognition=cognition
        )
        if not link or str(link.get("upstream_inter_id")) != str(upstream_inter_id):
            return []
        path = list(link.get("path") or [])
        if len(path) < 2:
            return []
        up = await self.inter_center(upstream_inter_id)
        tgt = await self.inter_center(target_inter_id)
        if up and tgt:
            return orient_path_upstream_to_target(path, up[0], up[1], tgt[0], tgt[1])
        return path

    def enrich_hop_turn_split(
        self,
        hop: dict[str, Any],
        correlate_rows: list[dict[str, Any]],
        dir8: int,
    ) -> None:
        cid = hop.get("cor_inter_id")
        if cid:
            hop["turn_split"] = turn_split_for_upstream(correlate_rows, dir8, str(cid))

    async def resolve_feed_segments(
        self,
        inter_id: str,
        turn_split: list[dict[str, Any]],
        *,
        node_id: str | None = None,
        cognition: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """上游路口 turn_split → 各来流进口道完整 link geom（上游路口的上游 → 本路口）。"""
        if not inter_id or not turn_split:
            return []
        nid = node_id or inter_id
        center = await self.inter_center(inter_id)
        if not center:
            return []
        center_lon, center_lat = center
        out: list[dict[str, Any]] = []
        for row in turn_split:
            cor_dir8 = row.get("cor_dir8")
            cor_turn = row.get("cor_turn")
            share = row.get("share_pct")
            if cor_dir8 is None or cor_turn is None or share is None:
                continue
            try:
                pct = float(share)
                d8 = int(cor_dir8)
                ct = int(cor_turn)
            except (TypeError, ValueError):
                continue
            if pct <= 0:
                continue
            link = await self.resolve_approach_link(inter_id, d8, cognition=cognition)
            seg = await self._feed_segment_from_link(
                link,
                inter_id=inter_id,
                center_lon=center_lon,
                center_lat=center_lat,
                dir8=d8,
                cor_turn=ct,
                node_id=nid,
                share_pct=pct,
                feed_direction=row.get("feed_direction"),
            )
            if seg:
                out.append(seg)
        out.sort(key=lambda s: (-float(s.get("share_pct") or 0), s.get("cor_dir8") or 0))
        return out

    async def _feed_segment_from_link(
        self,
        link: dict[str, Any] | None,
        *,
        inter_id: str,
        center_lon: float,
        center_lat: float,
        dir8: int,
        cor_turn: int,
        node_id: str,
        share_pct: float,
        feed_direction: Any,
    ) -> dict[str, Any] | None:
        """进口 link 全折线：f_inter（上游的上游）→ t_inter（本上游路口）。"""
        raw_path = list((link or {}).get("path") or [])
        upstream_id = str(link.get("upstream_inter_id") or "") if link else ""
        upstream_name = link.get("upstream_name") if link else None
        len_m = link.get("len_m") if link else None
        path_source = "link_geom" if len(raw_path) >= 2 else "none"

        up_center = await self.inter_center(upstream_id) if upstream_id else None
        if len(raw_path) >= 2 and up_center:
            path = orient_path_upstream_to_target(
                raw_path, up_center[0], up_center[1], center_lon, center_lat
            )
        elif up_center:
            path = orient_path_upstream_to_target(
                [[up_center[0], up_center[1]], [center_lon, center_lat]],
                up_center[0],
                up_center[1],
                center_lon,
                center_lat,
            )
            path_source = "center_line"
        elif len(raw_path) >= 2:
            path = orient_path_outer_to_center(raw_path, center_lon, center_lat)
        else:
            path = self._synthetic_feed_path(center_lon, center_lat, dir8)
            path_source = "synthetic"

        if len(path) < 2:
            return None

        return {
            "id": feed_segment_id(node_id, dir8, cor_turn),
            "cor_dir8": dir8,
            "cor_turn": cor_turn,
            "feed_direction": feed_direction,
            "share_pct": round(share_pct, 1),
            "from_inter_id": upstream_id or None,
            "from_inter_name": upstream_name,
            "len_m": float(len_m) if len_m is not None else None,
            "path": path,
            "path_source": path_source,
        }

    @staticmethod
    def _synthetic_feed_path(
        center_lon: float, center_lat: float, dir8: int, *, span_deg: float = 0.012
    ) -> list[list[float]]:
        """无 link / 无上游路口时，沿期望方位生成较长示意折线（外侧→中心）。"""
        br = math.radians(_DIR8_UPSTREAM_BEARING.get(dir8, 270.0))
        outer = [
            center_lon + math.sin(br) * span_deg,
            center_lat + math.cos(br) * span_deg,
        ]
        mid = [
            center_lon + math.sin(br) * span_deg * 0.55,
            center_lat + math.cos(br) * span_deg * 0.55,
        ]
        return [outer, mid, [center_lon, center_lat]]

    @staticmethod
    def _row_to_link(row: dict[str, Any]) -> dict[str, Any]:
        path = parse_linestring_wkt(row.get("geom_wkt"))
        if not path and row.get("path"):
            path = row["path"]
        return {
            "link_id": row.get("link_id"),
            "upstream_inter_id": row.get("upstream_inter_id"),
            "upstream_name": row.get("upstream_name"),
            "path": path,
            "len_m": float(row["len_m"]) if row.get("len_m") is not None else None,
            "dir8_code": int(row["dir8_code"]) if row.get("dir8_code") is not None else None,
        }

    @staticmethod
    def _link_from_cognition(
        cognition: dict[str, Any] | None, inter_id: str, dir8: int
    ) -> dict[str, Any] | None:
        if not cognition:
            return None
        kw = _DIR8_KEYWORDS.get(dir8, "")
        best: dict[str, Any] | None = None
        best_len = 0
        for link in cognition.get("links") or []:
            role = str(link.get("link_role") or "")
            if role not in ("entrance", "进口"):
                continue
            label = str(link.get("dir8_label") or link.get("dir4_label") or "")
            if kw and kw not in label:
                continue
            raw = link.get("path") or []
            path = [[float(p[0]), float(p[1])] for p in raw if len(p) >= 2]
            if len(path) > best_len:
                best_len = len(path)
                best = {
                    "link_id": link.get("link_id"),
                    "upstream_inter_id": link.get("f_inter_id"),
                    "upstream_name": None,
                    "path": path,
                    "dir8_code": dir8,
                }
        return best

    @staticmethod
    def _mock_link(inter_id: str, dir8: int) -> dict[str, Any]:
        """MOCK：沿 dir8 方向生成 4 点折线。"""
        base_lon, base_lat = 117.11, 36.65
        if inter_id.startswith("mock_"):
            base_lon += dir8 * 0.01
        # 上游在期望方位约 0.008° 处
        br = math.radians(_DIR8_UPSTREAM_BEARING.get(dir8, 270.0))
        up_lon = base_lon + math.sin(br) * 0.008
        up_lat = base_lat + math.cos(br) * 0.008
        path = [
            [up_lon, up_lat],
            [up_lon + math.sin(br) * 0.002, up_lat + math.cos(br) * 0.002],
            [base_lon - math.sin(br) * 0.002, base_lat - math.cos(br) * 0.002],
            [base_lon, base_lat],
        ]
        names = {6: "经十路与转山西路路口", 0: "奥体西路与解放东路路口"}
        return {
            "link_id": f"mock_link_{dir8}",
            "upstream_inter_id": f"mock_up_{dir8}",
            "upstream_name": names.get(dir8, "上游演示路口"),
            "path": path,
            "dir8_code": dir8,
            "len_m": 800.0,
        }


def _dist2(lon: float, lat: float, pt: list[float]) -> float:
    return (pt[0] - lon) ** 2 + (pt[1] - lat) ** 2


def _segment_length_m(a: list[float], b: list[float]) -> float:
    lat_mid = math.radians((a[1] + b[1]) / 2.0)
    dx = (b[0] - a[0]) * math.cos(lat_mid) * 111320.0
    dy = (b[1] - a[1]) * 111320.0
    return math.hypot(dx, dy)


def orient_path_outer_to_center(
    path: list[list[float]],
    center_lon: float,
    center_lat: float,
) -> list[list[float]]:
    """折线方向：外侧 → 路口中心（用于进口道高亮段）。"""
    if len(path) < 2:
        return path
    if _dist2(center_lon, center_lat, path[0]) < _dist2(center_lon, center_lat, path[-1]):
        path = list(reversed(path))
    return path


def truncate_path_from_outer(
    path: list[list[float]], *, max_len_m: float = 80.0
) -> list[list[float]]:
    """从 path[0]（外侧）向内截取不超过 max_len_m 的子折线。"""
    if len(path) < 2:
        return path
    out = [path[0]]
    acc = 0.0
    for i in range(1, len(path)):
        seg = _segment_length_m(path[i - 1], path[i])
        if acc + seg >= max_len_m and acc > 0:
            ratio = (max_len_m - acc) / seg if seg > 0 else 0.0
            ratio = max(0.0, min(1.0, ratio))
            mid = [
                path[i - 1][0] + (path[i][0] - path[i - 1][0]) * ratio,
                path[i - 1][1] + (path[i][1] - path[i - 1][1]) * ratio,
            ]
            out.append(mid)
            break
        acc += seg
        out.append(path[i])
    return out if len(out) >= 2 else path[:2]


def feed_segment_id(node_id: str, cor_dir8: int, cor_turn: int) -> str:
    return f"feed:{node_id}:{cor_dir8}:{cor_turn}"


def period_context_from_window(window: DataWindow, period_label: str | None) -> tuple[str, list[str]]:
    return period_type_from_label(period_label), day_labels_for_filter(window.dow_filter)
