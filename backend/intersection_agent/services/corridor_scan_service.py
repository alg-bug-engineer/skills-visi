"""Batch metrics and ranking for intersections along a corridor."""

from __future__ import annotations

import logging
import re
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.models.domain import CorridorScanNlu
from intersection_agent.services.line_resolver import LineResolutionResult
from intersection_agent.utils.corridor_metrics import (
    congestion_score,
    format_annotation,
    level_label,
    severity_level,
)
from intersection_agent.utils.corridor_geometry import (
    build_centerline_from_inter_chain,
    snap_intersections_to_polyline,
)
from intersection_agent.utils.data_window import build_data_window

logger = logging.getLogger(__name__)


class CorridorScanService:
    def __init__(
        self,
        pool: PostgresPool | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._pool = pool or PostgresPool()
        self._settings = settings or get_settings()

    async def scan(
        self,
        line_resolution: LineResolutionResult,
        scan_nlu: CorridorScanNlu,
    ) -> dict[str, Any]:
        assert scan_nlu.time_period is not None
        line_name = line_resolution.line_name or scan_nlu.corridor or ""
        if self._settings.mock_db:
            return self._mock_scan(line_name, scan_nlu.time_period)

        await self._pool.connect()
        road_schema = self._settings.pgschema
        flow_schema = self._settings.pg_flow_schema
        version_id = self._settings.pg_version_id
        window = build_data_window(scan_nlu.time_period)
        query_trace: list[dict[str, Any]] = []

        if line_resolution.scan_mode == "road_intersections":
            inter_rows = line_resolution.intersection_rows
        else:
            assert line_resolution.line_id
            inter_rows = await self._fetch(
                query_trace,
                "line_intersections",
                f"""
                SELECT r.seq_no, r.inter_id, r.inter_name, r.gap_to_prev_m,
                       i.geom_center
                FROM {road_schema}.dim_line_inter_rltn r
                LEFT JOIN {road_schema}.dim_inter_info i
                  ON i.inter_id = r.inter_id AND i.version_id = $2
                WHERE r.line_id = $1 AND r.is_deleted = 0
                ORDER BY r.seq_no
                """,
                line_resolution.line_id,
                version_id,
            )
            inter_rows = [dict(r) for r in inter_rows]

        inter_ids = [str(r["inter_id"]) for r in inter_rows if r.get("inter_id")]
        metrics_map = await self._batch_inter_metrics(
            flow_schema, inter_ids, window, query_trace
        )

        line_metrics = None
        if line_resolution.line_id and not str(line_resolution.line_id).startswith("road:"):
            line_metrics = await self._fetchrow(
                query_trace,
                "line_val_index",
                f"""
                SELECT AVG(delay_index) AS delay_index,
                       AVG(total_stop_times) AS total_stop_times,
                       AVG(travel_speed_kmh) AS travel_speed_kmh
                FROM {flow_schema}.dws_line_val_index_5min_mm
                WHERE line_id = $1
                  AND day_of_week = ANY($2::int[])
                  AND step_index BETWEEN $3 AND $4
                  AND is_deleted = 0
                """,
                line_resolution.line_id,
                list(window.dow_filter),
                window.step_start,
                window.step_end,
            )

        intersections = self._build_intersection_list(inter_rows, metrics_map)
        ranked = self._apply_ranking(intersections)
        top3 = [r["inter_id"] for r in ranked if r.get("rank") is not None][:3]

        line_paths: list[dict[str, Any]] = []
        polyline: list[list[float]] = []
        if line_resolution.line_id and not str(line_resolution.line_id).startswith("road:"):
            line_paths, polyline = await self._fetch_line_geometry(
                str(line_resolution.line_id),
                inter_ids,
                line_resolution.road_name or scan_nlu.corridor,
                road_schema,
                version_id,
                query_trace,
            )
        elif line_resolution.scan_mode == "road_intersections" and inter_ids:
            line_paths, polyline = await self._fetch_road_geometry_by_inters(
                line_resolution.road_name or scan_nlu.corridor or "",
                inter_ids,
                road_schema,
                version_id,
                query_trace,
            )

        if polyline:
            ranked = snap_intersections_to_polyline(ranked, polyline)

        return {
            "line_id": line_resolution.line_id,
            "line_name": line_name,
            "road_name": line_resolution.road_name or scan_nlu.corridor,
            "scan_mode": line_resolution.scan_mode,
            "time_period": scan_nlu.time_period.model_dump(),
            "intersection_count": len(inter_rows),
            "data_coverage_count": sum(1 for r in ranked if r.get("has_data")),
            "line_metrics": {
                "delay_index": _float(line_metrics, "delay_index"),
                "total_stop_times": _float(line_metrics, "total_stop_times"),
                "travel_speed_kmh": _float(line_metrics, "travel_speed_kmh"),
            },
            "intersections": ranked,
            "top3_inter_ids": top3,
            "line_paths": line_paths,
            "polyline": polyline,
            "overall_pattern": self._overall_pattern(ranked),
            "data_window": window.to_meta(source_tier="dws_weekday_pattern"),
            "query_trace": query_trace,
        }

    async def _fetch_line_geometry(
        self,
        line_id: str,
        inter_ids: list[str],
        road_name_hint: str | None,
        road_schema: str,
        version_id: str,
        query_trace: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[list[float]]]:
        rows = await self._fetch(
            query_trace,
            "line_link_geometry",
            f"""
            SELECT ll.link_id, l.geom, l.road_name, l.f_inter_id, l.t_inter_id
            FROM {road_schema}.dim_line_link_rltn ll
            JOIN {road_schema}.dim_link_info l
              ON l.link_id = ll.link_id AND l.version_id = $2
            WHERE ll.line_id = $1 AND ll.is_deleted = 0
            """,
            line_id,
            version_id,
        )
        links = [dict(r) for r in rows]
        polyline, used = build_centerline_from_inter_chain(
            inter_ids,
            links,
            road_name_hint=road_name_hint,
        )
        return used, polyline

    async def _fetch_road_geometry_by_inters(
        self,
        road_name: str,
        inter_ids: list[str],
        road_schema: str,
        version_id: str,
        query_trace: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[list[float]]]:
        if not inter_ids:
            return [], []
        rows = await self._fetch(
            query_trace,
            "road_link_geometry",
            f"""
            SELECT link_id, geom, road_name, f_inter_id, t_inter_id
            FROM {road_schema}.dim_link_info
            WHERE version_id = $1
              AND f_inter_id = ANY($2::varchar[])
              AND t_inter_id = ANY($2::varchar[])
              AND road_name ILIKE $3
            """,
            version_id,
            inter_ids,
            f"%{road_name}%",
        )
        links = [dict(r) for r in rows]
        polyline, used = build_centerline_from_inter_chain(
            inter_ids,
            links,
            road_name_hint=road_name,
        )
        return used, polyline

    def _build_intersection_list(
        self,
        inter_rows: list[dict[str, Any]],
        metrics_map: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in inter_rows:
            iid = str(row.get("inter_id") or "")
            metrics = metrics_map.get(iid) or {}
            sat = _float(metrics, "saturation_max")
            imb = _float(metrics, "unbalance_index")
            has_data = sat is not None
            lon, lat = _parse_point(row.get("geom_center"))
            items.append(
                {
                    "seq_no": row.get("seq_no"),
                    "inter_id": iid,
                    "inter_name": str(row.get("inter_name") or iid),
                    "lon": lon,
                    "lat": lat,
                    "gap_to_prev_m": _float(row, "gap_to_prev_m"),
                    "has_data": has_data,
                    "rank": None,
                    "score": congestion_score(sat, unbalance_index=imb) if has_data else None,
                    "severity": severity_level(sat, has_data=has_data),
                    "metrics": {
                        "saturation_max": sat,
                        "unbalance_index": imb,
                        "level_label": level_label(sat, has_data=has_data),
                    },
                    "annotation": format_annotation(sat, has_data=has_data),
                }
            )
        return items

    @staticmethod
    def _apply_ranking(intersections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scored = [i for i in intersections if i.get("has_data")]
        scored.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
        for idx, item in enumerate(scored, start=1):
            item["rank"] = idx
        no_data = [i for i in intersections if not i.get("has_data")]
        return scored + no_data

    @staticmethod
    def _overall_pattern(ranked: list[dict[str, Any]]) -> str:
        with_data = [r for r in ranked if r.get("has_data")]
        if not with_data:
            return "当前时段暂无运行数据，请换时段或联系数据管理员。"
        if len(with_data) < 2:
            return "仅部分路口有数据，建议结合现场情况判断。"
        mid = len(with_data) // 2
        head = sum(float(r.get("score") or 0) for r in with_data[:mid]) / max(mid, 1)
        tail = sum(float(r.get("score") or 0) for r in with_data[mid:]) / max(
            len(with_data) - mid, 1
        )
        if head > tail * 1.12:
            return "干线前段路口拥堵水平整体高于后段，瓶颈可能集中在路段前部。"
        if tail > head * 1.12:
            return "干线后段路口拥堵水平整体高于前段，需关注下游节点传导。"
        return "各路口拥堵水平差异明显，建议优先关注排名靠前的节点。"

    async def _batch_inter_metrics(
        self,
        schema: str,
        inter_ids: list[str],
        window: Any,
        query_trace: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        if not inter_ids:
            return {}
        rows = await self._fetch(
            query_trace,
            "batch_inter_evaluation",
            f"""
            SELECT inter_id,
                   AVG(saturation_max) AS saturation_max,
                   AVG(saturation_avg) AS saturation_avg,
                   AVG(unbalance_index) AS unbalance_index
            FROM {schema}.dws_inter_evaluation_5min_mm
            WHERE inter_id = ANY($1::varchar[])
              AND day_of_week = ANY($2::int[])
              AND step_index BETWEEN $3 AND $4
              AND is_deleted = 0
            GROUP BY inter_id
            """,
            inter_ids,
            list(window.dow_filter),
            window.step_start,
            window.step_end,
        )
        return {str(r["inter_id"]): dict(r) for r in rows}

    async def _fetch(self, trace: list, label: str, sql: str, *params: Any) -> list[Any]:
        rows = await self._pool.fetch(sql, *params)
        trace.append({"label": label, "sql": sql, "params": [str(p) for p in params]})
        return rows

    async def _fetchrow(self, trace: list, label: str, sql: str, *params: Any) -> Any:
        row = await self._pool.fetchrow(sql, *params)
        trace.append({"label": label, "sql": sql, "params": [str(p) for p in params]})
        return row

    @staticmethod
    def _mock_scan(line_name: str, time_period: Any) -> dict[str, Any]:
        from intersection_agent.models.domain import TimePeriod

        tp = time_period if isinstance(time_period, TimePeriod) else TimePeriod(**time_period)
        items = []
        for seq, (iid, name, sat) in enumerate(
            [
                ("m1", "奥体西路与工业南路路口", 1.54),
                ("m2", "奥体西路与经十路路口", 1.24),
                ("m3", "坤顺路与奥体西路路口", 1.15),
            ],
            start=1,
        ):
            items.append(
                {
                    "seq_no": seq,
                    "inter_id": iid,
                    "inter_name": name,
                    "lon": 117.11 + seq * 0.005,
                    "lat": 36.65 - seq * 0.004,
                    "has_data": True,
                    "rank": None,
                    "score": congestion_score(sat),
                    "severity": severity_level(sat, has_data=True),
                    "metrics": {
                        "saturation_max": sat,
                        "level_label": level_label(sat, has_data=True),
                    },
                    "annotation": format_annotation(sat, has_data=True),
                }
            )
        ranked = CorridorScanService._apply_ranking(items)
        return {
            "line_id": "mock",
            "line_name": line_name,
            "time_period": tp.model_dump(),
            "intersection_count": len(items),
            "data_coverage_count": len(items),
            "line_metrics": {"delay_index": 1.65},
            "intersections": ranked,
            "top3_inter_ids": [r["inter_id"] for r in ranked[:3]],
            "overall_pattern": "演示数据",
            "data_window": build_data_window(tp).to_meta(source_tier="mock"),
            "query_trace": [],
        }


def _float(row: Any, key: str) -> float | None:
    if row is None:
        return None
    value = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
    return float(value) if value is not None else None


def _parse_point(wkt: Any) -> tuple[float | None, float | None]:
    if not wkt:
        return None, None
    match = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", str(wkt), re.I)
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))
