"""Signal timing profile: min-green deficit, plan granularity, flow-green fit."""

from __future__ import annotations

import logging
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.models.domain import NluResult
from intersection_agent.services.ring_diagram_service import RingDiagramService
from intersection_agent.utils.data_window import DataWindow, build_data_window
from intersection_agent.utils.flow_green_consistency import flow_green_check
from intersection_agent.utils.thresholds_loader import load_thresholds, threshold_value
from intersection_agent.utils.traffic_labels import turn_label

logger = logging.getLogger(__name__)


class TimingProfileService:
    """Build timing adaptation profile for diagnosis (no optimization output)."""

    def __init__(
        self,
        pool: PostgresPool | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._pool = pool or PostgresPool()
        self._settings = settings or get_settings()
        self._ring = RingDiagramService(pool=self._pool, settings=self._settings)

    async def build(
        self,
        inter_id: str,
        nlu: NluResult,
        *,
        data_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not nlu.time_period:
            return self._empty("missing_time_period")

        window = build_data_window(nlu.time_period)

        if self._settings.mock_db:
            profile = self._mock_profile(data_payload)
            profile["ring_diagram"] = (await self._ring.build(inter_id))
            return profile

        await self._pool.connect()
        flow_schema = self._settings.pg_flow_schema
        query_trace: list[dict[str, Any]] = []

        try:
            return await self._build_from_db(
                inter_id, nlu, window, flow_schema, query_trace, data_payload
            )
        except Exception as exc:
            logger.warning("timing_profile build failed: %s", exc)
            return {
                "reason": "query_failed",
                "narrative": f"配时画像查询失败，已降级：{exc}",
                "query_trace": query_trace,
            }

    async def _build_from_db(
        self,
        inter_id: str,
        nlu: NluResult,
        window: DataWindow,
        flow_schema: str,
        query_trace: list[dict[str, Any]],
        data_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        thresholds = load_thresholds()
        dwd_has = bool(
            (data_payload or {}).get("meta", {}).get("data_window", {}).get("source_tier")
            == "dwd_rolling_7d"
        )
        dow_filter = window.dow_filter if dwd_has else (window.primary_dow,)

        plan_row = await self._fetchrow(
            query_trace,
            "timing_plan_summary",
            f"""
            SELECT AVG(p.cycle_len_sec) AS cycle_length,
                   COUNT(DISTINCT p.plan_no) AS plan_count
            FROM {flow_schema}.dwd_ctl_inter_plan_cfg p
            WHERE p.inter_id = $1 AND p.is_deleted = 0
            """,
            inter_id,
        )
        cycle_length = _float(plan_row, "cycle_length", 120.0)
        plan_count = int(plan_row.get("plan_count") or 0) if plan_row else 0

        period_row = await self._fetchrow(
            query_trace,
            "timing_period_count",
            f"""
            SELECT COUNT(DISTINCT start_time::text || '-' || end_time::text) AS period_count
            FROM {flow_schema}.dwd_ctl_inter_day_plan_period
            WHERE inter_id = $1 AND is_deleted = 0
            """,
            inter_id,
        )
        period_count = int(period_row.get("period_count") or 0) if period_row else 0

        min_green_rows = await self._fetch(
            query_trace,
            "timing_min_green",
            f"""
            SELECT dir8_code, turn_dir_no,
                   AVG(green_time_plan) AS green_time_plan,
                   AVG(min_green_time) AS min_green_time,
                   MAX(turn_saturation) AS turn_saturation
            FROM {flow_schema}.dws_turn_min_green_5min_mm mg
            LEFT JOIN LATERAL (
                SELECT MAX(ts.turn_saturation) AS turn_saturation
                FROM {flow_schema}.dws_turn_saturation_5min_mm ts
                WHERE ts.inter_id = mg.inter_id
                  AND ts.link_id = mg.link_id
                  AND ts.turn_dir_no = mg.turn_dir_no
                  AND ts.day_of_week = ANY($2::int[])
                  AND ts.step_index BETWEEN $3 AND $4
                  AND ts.is_deleted = 0
            ) ts ON TRUE
            WHERE mg.inter_id = $1
              AND mg.day_of_week = ANY($2::int[])
              AND mg.step_index BETWEEN $3 AND $4
              AND mg.is_deleted = 0
            GROUP BY dir8_code, turn_dir_no
            """,
            inter_id,
            list(dow_filter),
            window.step_start,
            window.step_end,
        )

        flow_rows = await self._fetch(
            query_trace,
            "timing_turn_flow",
            f"""
            SELECT dir8_code, turn_dir_no,
                   AVG(turn_flow_total) AS turn_flow_total
            FROM {flow_schema}.dws_inter_link_turn_flow_5min_mm
            WHERE inter_id = $1
              AND day_of_week = ANY($2::int[])
              AND step_index BETWEEN $3 AND $4
              AND is_deleted = 0
            GROUP BY dir8_code, turn_dir_no
            """,
            inter_id,
            list(dow_filter),
            window.step_start,
            window.step_end,
        )
        flow_map = {
            (int(r.get("dir8_code") or 0), int(r.get("turn_dir_no") or 2)): _float(r, "turn_flow_total")
            for r in flow_rows
        }

        deficit_turns: list[dict[str, Any]] = []
        flow_green_items: list[dict[str, Any]] = []
        for row in min_green_rows:
            plan_green = _float(row, "green_time_plan")
            min_green = _float(row, "min_green_time")
            dir8 = int(row.get("dir8_code") or 0)
            turn_dir = int(row.get("turn_dir_no") or 2)
            label = turn_label(dir8, turn_dir)
            if plan_green is not None and min_green is not None and min_green > 0:
                deficit_ratio = (min_green - plan_green) / min_green
                if deficit_ratio > 0.05:
                    deficit_turns.append(
                        {
                            "label": label,
                            "green_time_plan": round(plan_green, 1),
                            "min_green_time": round(min_green, 1),
                            "deficit_ratio": round(deficit_ratio, 3),
                            "turn_saturation": _float(row, "turn_saturation"),
                        }
                    )
                flow_green_items.append(
                    {
                        "label": label,
                        "movement_key": f"{dir8}-{turn_dir}",
                        "flow_vph": flow_map.get((dir8, turn_dir)),
                        "green_time_plan": plan_green,
                        "effective_green_s": plan_green,
                    }
                )

        deficit_turns.sort(key=lambda x: x.get("deficit_ratio", 0), reverse=True)
        max_deficit = deficit_turns[0]["deficit_ratio"] if deficit_turns else 0.0
        flow_green = flow_green_check(flow_green_items)

        cycle_min = threshold_value("cycle", "min_s", default=60)
        cycle_max = threshold_value("cycle", "max_s", default=190)
        min_plans = int(threshold_value("plan", "min_time_plans", default=5))

        cycle_issue = None
        if cycle_length > cycle_max:
            cycle_issue = "too_long"
        elif cycle_length < cycle_min:
            cycle_issue = "too_short"

        plan_granularity_low = period_count > 0 and period_count <= min_plans

        narrative_parts: list[str] = [
            f"当前方案周期约 {cycle_length:.0f}s，日计划时段 {period_count or '—'} 个"
        ]

        return {
            "cycle_length": round(cycle_length, 1),
            "cycle_issue": cycle_issue,
            "plan_count": plan_count,
            "period_count": period_count,
            "plan_granularity_low": plan_granularity_low,
            "green_deficit_ratio_max": round(max_deficit, 3),
            "deficit_turns": deficit_turns[:5],
            "flow_green_fit": flow_green,
            "narrative": "；".join(narrative_parts),
            "query_trace": query_trace,
            "ring_diagram": await self._ring.build(inter_id),
        }

    async def _fetchrow(
        self,
        query_trace: list[dict[str, Any]],
        label: str,
        sql: str,
        *params: Any,
    ) -> Any:
        row = await self._pool.fetchrow(sql, *params)
        query_trace.append({"label": label, "sql": sql, "params": [str(p) for p in params], "raw_data": _serialize(row)})
        return row

    async def _fetch(
        self,
        query_trace: list[dict[str, Any]],
        label: str,
        sql: str,
        *params: Any,
    ) -> list[Any]:
        rows = await self._pool.fetch(sql, *params)
        query_trace.append({"label": label, "sql": sql, "params": [str(p) for p in params], "raw_data": _serialize(rows)})
        return rows

    @staticmethod
    def _empty(reason: str) -> dict[str, Any]:
        return {"reason": reason, "narrative": "配时画像数据不可用", "query_trace": []}

    @staticmethod
    def _mock_profile(data_payload: dict[str, Any] | None) -> dict[str, Any]:
        signal = (data_payload or {}).get("signal_plan", {})
        cycle = float(signal.get("cycle_length") or 120)
        return {
            "cycle_length": cycle,
            "cycle_issue": None,
            "plan_count": 3,
            "period_count": 4,
            "plan_granularity_low": True,
            "green_deficit_ratio_max": 0.18,
            "deficit_turns": [
                {
                    "label": "东直行",
                    "green_time_plan": 28.0,
                    "min_green_time": 34.0,
                    "deficit_ratio": 0.176,
                    "turn_saturation": 0.91,
                }
            ],
            "flow_green_fit": {
                "spearman_tau": 0.42,
                "verdict": "weak",
                "narrative": "流量与绿信比存在一定偏差，东直行高流量但绿灯占比偏低",
                "items": [],
            },
            "narrative": f"当前方案周期约 {cycle:.0f}s，日计划时段 4 个",
            "query_trace": [],
        }


def _float(row: Any, key: str, default: float | None = None) -> float | None:
    if row is None:
        return default
    value = row.get(key) if hasattr(row, "get") else None
    if value is None:
        return default
    return float(value)


def _serialize(value: Any) -> Any:
    from intersection_agent.utils.json_safe import to_json_safe

    return to_json_safe(value)
