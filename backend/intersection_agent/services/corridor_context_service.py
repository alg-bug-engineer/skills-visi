"""Corridor / line coordination context for single-intersection diagnosis."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.models.domain import NluResult
from intersection_agent.utils.data_window import build_data_window

logger = logging.getLogger(__name__)


class CorridorContextService:
    """Resolve whether the intersection sits on a coordinated corridor."""

    def __init__(
        self,
        pool: PostgresPool | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._pool = pool or PostgresPool()
        self._settings = settings or get_settings()

    async def build(
        self,
        inter_id: str,
        inter_name: str,
        nlu: NluResult,
    ) -> dict[str, Any]:
        if not nlu.time_period:
            return self._empty("missing_time_period")

        window = build_data_window(nlu.time_period)

        if self._settings.mock_db:
            return self._mock_context(inter_name)

        await self._pool.connect()
        flow_schema = self._settings.pg_flow_schema
        road_schema = self._settings.pgschema
        query_trace: list[dict[str, Any]] = []

        try:
            return await self._build_from_db(
                inter_id, inter_name, nlu, window, flow_schema, road_schema, query_trace
            )
        except Exception as exc:
            logger.warning("corridor_context build failed: %s", exc)
            return {
                "in_corridor": False,
                "reason": "query_failed",
                "narrative": f"干线协调上下文查询失败，已降级：{exc}",
                "query_trace": query_trace,
            }

    async def _build_from_db(
        self,
        inter_id: str,
        inter_name: str,
        nlu: NluResult,
        window: Any,
        flow_schema: str,
        road_schema: str,
        query_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        line_rows = await self._fetch(
            query_trace,
            "corridor_lines",
            f"""
            SELECT l.line_id, l.line_name, r.seq_no, r.inter_id, r.inter_name
            FROM {road_schema}.dim_line_inter_rltn r
            JOIN {road_schema}.dim_line_info l
              ON l.line_id = r.line_id
            WHERE r.inter_id = $1
              AND r.is_deleted = 0
              AND l.is_deleted = 0
            ORDER BY l.line_name, r.seq_no
            """,
            inter_id,
        )

        coord_rows = await self._fetch(
            query_trace,
            "corridor_coord_groups",
            f"""
            SELECT g.group_id, g.corridor_id, g.day_of_week, g.cycle_len_sec,
                   g.intersection_count, g.inter_ids_json, g.inter_names_json,
                   c.corridor_name, c.primary_road_name
            FROM {flow_schema}.dws_corridor_coord_group g
            JOIN {flow_schema}.dws_corridor_coord_cfg c
              ON c.corridor_id = g.corridor_id AND c.is_deleted = 0
            WHERE g.is_deleted = 0
              AND g.inter_ids_json::text LIKE '%' || $1 || '%'
            LIMIT 5
            """,
            inter_id,
        )

        line_metrics: list[dict[str, Any]] = []
        for line in line_rows[:3]:
            line_id = line.get("line_id")
            if not line_id:
                continue
            metric_row = await self._fetchrow(
                query_trace,
                f"line_val_{line_id}",
                f"""
                SELECT AVG(delay_index) AS delay_index,
                       AVG(travel_speed_kmh) AS travel_speed_kmh,
                       AVG(total_stop_times) AS total_stop_times,
                       AVG(stop_time_sec) AS stop_time_sec
                FROM {flow_schema}.dws_line_val_index_5min_mm
                WHERE line_id = $1
                  AND day_of_week = ANY($2::int[])
                  AND step_index BETWEEN $3 AND $4
                  AND is_deleted = 0
                """,
                line_id,
                list(window.dow_filter),
                window.step_start,
                window.step_end,
            )
            if metric_row:
                line_metrics.append(
                    {
                        "line_id": line_id,
                        "line_name": line.get("line_name"),
                        "delay_index": _float(metric_row, "delay_index"),
                        "travel_speed_kmh": _float(metric_row, "travel_speed_kmh"),
                        "total_stop_times": _float(metric_row, "total_stop_times"),
                        "stop_time_sec": _float(metric_row, "stop_time_sec"),
                    }
                )

        stop_rows: list[dict[str, Any]] = []
        if coord_rows:
            row0 = coord_rows[0]
            group_id = row0.get("group_id")
            dow = row0.get("day_of_week")
            if group_id is not None and dow is not None:
                stop_rows = await self._fetch(
                    query_trace,
                    "corridor_stop",
                    f"""
                    SELECT fwd_avg_total_stop_times, rev_avg_total_stop_times,
                           fwd_intersection_count, rev_intersection_count
                    FROM {flow_schema}.dws_corridor_coord_stop_mm
                    WHERE group_id = $1 AND day_of_week = $2 AND is_deleted = 0
                    """,
                    group_id,
                    int(dow),
                )

        in_corridor = bool(coord_rows)
        inter_ids_ordered: list[str] = []
        inter_names_ordered: list[str] = []
        corridor_name = ""
        cycle_len = None
        period_start_sec = None
        period_end_sec = None
        if coord_rows:
            row0 = coord_rows[0]
            corridor_name = str(row0.get("corridor_name") or row0.get("primary_road_name") or "")
            cycle_len = _float(row0, "cycle_len_sec")
            period_start_sec = row0.get("period_start_sec")
            period_end_sec = row0.get("period_end_sec")
            raw_ids = row0.get("inter_ids_json")
            inter_ids_ordered = _parse_json_list(raw_ids)
            inter_names_ordered = _parse_json_list(row0.get("inter_names_json"))

        corridor_nodes = await self._build_corridor_nodes(
            inter_id,
            inter_ids_ordered,
            inter_names_ordered,
            road_schema,
        )

        fwd_stop = _float(stop_rows[0], "fwd_avg_total_stop_times") if stop_rows else None
        rev_stop = _float(stop_rows[0], "rev_avg_total_stop_times") if stop_rows else None
        stop_candidates = [v for v in (fwd_stop, rev_stop) if v is not None]
        avg_stop_times = max(stop_candidates) if stop_candidates else None
        green_wave_break_risk = (
            avg_stop_times is not None and avg_stop_times >= 1.5
        ) or any(
            (m.get("total_stop_times") or 0) >= 1.5 for m in line_metrics
        )

        narrative_parts: list[str] = []
        if in_corridor:
            if inter_id in inter_ids_ordered:
                idx = inter_ids_ordered.index(inter_id)
                narrative_parts.append(
                    f"处于协调走廊「{corridor_name}」第 {idx + 1}/{len(inter_ids_ordered)} 个节点，"
                    f"组内周期 {cycle_len or '—'}s"
                )
            else:
                narrative_parts.append(f"处于协调走廊「{corridor_name}」")
            if green_wave_break_risk:
                narrative_parts.append(
                    "协调方向停车次数偏高，存在绿波断裂风险，不宜仅做单点加绿灯"
                )
        elif line_rows:
            narrative_parts.append("未纳入干线协调组，按单点场景分析")
        else:
            narrative_parts.append("未关联到已知干线走廊，按单点场景分析")

        return {
            "in_corridor": in_corridor,
            "corridor_name": corridor_name,
            "corridor_inter_count": len(inter_ids_ordered),
            "inter_position": (
                inter_ids_ordered.index(inter_id) + 1 if inter_id in inter_ids_ordered else None
            ),
            "coord_cycle_sec": cycle_len,
            "lines": [
                {
                    "line_id": r.get("line_id"),
                    "line_name": r.get("line_name"),
                    "seq_no": r.get("seq_no"),
                }
                for r in line_rows
            ],
            "line_metrics": line_metrics,
            "coord_groups": [
                {
                    "group_id": r.get("group_id"),
                    "corridor_id": r.get("corridor_id"),
                    "intersection_count": r.get("intersection_count"),
                    "cycle_len_sec": _float(r, "cycle_len_sec"),
                }
                for r in coord_rows
            ],
            "avg_coord_stop_times": avg_stop_times,
            "coord_stop_fwd": fwd_stop,
            "coord_stop_rev": rev_stop,
            "corridor_nodes": corridor_nodes,
            "period_start_sec": period_start_sec,
            "period_end_sec": period_end_sec,
            "green_wave_break_risk": green_wave_break_risk,
            "narrative": "；".join(narrative_parts),
            "query_trace": query_trace,
        }

    async def _build_corridor_nodes(
        self,
        current_inter_id: str,
        inter_ids: list[str],
        inter_names: list[str],
        road_schema: str,
    ) -> list[dict[str, Any]]:
        if not inter_ids:
            return []
        version_id = self._settings.pg_version_id
        rows = await self._pool.fetch(
            f"""
            SELECT inter_id, inter_name, geom_center
            FROM {road_schema}.dim_inter_info
            WHERE version_id = $1 AND inter_id = ANY($2::varchar[])
            """,
            version_id,
            inter_ids,
        )
        geo_map = {str(r["inter_id"]): r for r in rows}
        nodes: list[dict[str, Any]] = []
        for idx, iid in enumerate(inter_ids):
            row = geo_map.get(str(iid))
            name = (
                inter_names[idx]
                if idx < len(inter_names)
                else (row.get("inter_name") if row else str(iid))
            )
            lon, lat = _parse_point(row.get("geom_center") if row else None)
            nodes.append(
                {
                    "seq": idx + 1,
                    "inter_id": str(iid),
                    "inter_name": str(name),
                    "is_current": str(iid) == str(current_inter_id),
                    "lon": lon,
                    "lat": lat,
                }
            )
        return nodes

    async def _fetchrow(self, trace: list, label: str, sql: str, *params: Any) -> Any:
        row = await self._pool.fetchrow(sql, *params)
        trace.append({"label": label, "sql": sql, "params": [str(p) for p in params]})
        return row

    async def _fetch(self, trace: list, label: str, sql: str, *params: Any) -> list[Any]:
        rows = await self._pool.fetch(sql, *params)
        trace.append({"label": label, "sql": sql, "params": [str(p) for p in params]})
        return rows

    @staticmethod
    def _empty(reason: str) -> dict[str, Any]:
        return {
            "in_corridor": False,
            "reason": reason,
            "narrative": "干线协调上下文不可用",
            "query_trace": [],
        }

    @staticmethod
    def _mock_context(inter_name: str) -> dict[str, Any]:
        return {
            "in_corridor": True,
            "corridor_name": "经十路协调走廊（示例）",
            "corridor_inter_count": 5,
            "inter_position": 3,
            "coord_cycle_sec": 120.0,
            "lines": [{"line_id": "L-001", "line_name": "经十路", "seq_no": 3}],
            "line_metrics": [
                {
                    "line_id": "L-001",
                    "line_name": "经十路",
                    "delay_index": 1.72,
                    "travel_speed_kmh": 22.5,
                    "total_stop_times": 1.8,
                    "stop_time_sec": 48.0,
                }
            ],
            "coord_groups": [{"group_id": "G-001", "corridor_id": "CR-001", "intersection_count": 5}],
            "corridor_nodes": [
                {"seq": 1, "inter_id": "N1", "inter_name": "节点1", "is_current": False},
                {"seq": 2, "inter_id": "N2", "inter_name": "当前路口", "is_current": True},
                {"seq": 3, "inter_id": "N3", "inter_name": "节点3", "is_current": False},
            ],
            "avg_coord_stop_times": 1.6,
            "green_wave_break_risk": True,
            "narrative": (
                "处于协调走廊「经十路协调走廊（示例）」第 3/5 个节点，组内周期 120.0s；"
                "协调方向停车次数偏高，存在绿波断裂风险，不宜仅做单点加绿灯"
            ),
            "query_trace": [],
        }


def _float(row: Any, key: str, default: float | None = None) -> float | None:
    if row is None:
        return default
    value = row.get(key)
    if value is None:
        return default
    return float(value)


def _parse_json_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except json.JSONDecodeError:
            return []
    return []


def _parse_point(wkt: Any) -> tuple[float | None, float | None]:
    if not wkt:
        return None, None
    match = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", str(wkt), re.I)
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))
