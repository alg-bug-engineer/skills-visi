"""Fetch intersection metrics from PostgreSQL."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.logging.helpers import log_event
from intersection_agent.models.domain import NluResult
from intersection_agent.utils.data_window import DataWindow, build_data_window, slot_times
from intersection_agent.utils.demo_config import resolve_reference_date
from intersection_agent.utils.saturation_granularity import (
    apply_canonical_saturation_to_payload,
    canonical_saturation_summary,
)
from intersection_agent.utils.traffic_labels import LOS_LABELS, TURN_DIR_LABELS, turn_label

logger = logging.getLogger(__name__)


class DataFetcher:
    """Aggregate signal, flow, channelization, and evaluation metrics."""

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
        nlu: NluResult,
        *,
        reference_date: date | None = None,
    ) -> dict[str, Any]:
        """Fetch and flatten metrics for rule engine."""
        assert nlu.time_period is not None
        ref = reference_date if reference_date is not None else resolve_reference_date()
        window = build_data_window(nlu.time_period, reference_date=ref)

        if self._settings.mock_db:
            return self._mock_payload(inter_id, inter_name, nlu, window)

        await self._pool.connect()
        flow_schema = self._settings.pg_flow_schema
        road_schema = self._settings.pgschema
        query_trace: list[dict[str, Any]] = []

        dwd_delay, dwd_samples = await self._fetch_dwd_delay(
            flow_schema,
            inter_id,
            nlu,
            window,
            query_trace=query_trace,
        )
        has_dwd = dwd_delay is not None and dwd_samples > 0

        # 近 7 日 DWD 无数据 → DWS 降级为提问日星期几（如周三 → day_of_week=3）
        dws_dow = _dws_dow_for_query(window, dwd_has_data=has_dwd)
        fallback_reason = None if has_dwd else "dwd_empty_rolling_7d"

        dws_eval = await self._fetch_dws_row(
            flow_schema,
            "dws_inter_evaluation_5min_mm",
            inter_id,
            window,
            dws_dow,
            [
                "AVG(saturation_max) AS saturation_max",
                "AVG(saturation_avg) AS saturation_avg",
                "AVG(unbalance_index) AS imbalance_index",
                "MODE() WITHIN GROUP (ORDER BY level_of_service) AS level_of_service",
            ],
            query_trace=query_trace,
        )
        dws_util = await self._fetch_dws_row(
            flow_schema,
            "dws_turn_green_utilization_5min_mm",
            inter_id,
            window,
            dws_dow,
            [
                "AVG(green_utilization) AS green_utilization",
                "AVG(CASE WHEN green_utilization < 0.3 THEN 1.0 ELSE 0.0 END) AS empty_green_rate",
            ],
            query_trace=query_trace,
        )
        dws_sat = await self._fetch_dws_row(
            flow_schema,
            "dws_turn_saturation_5min_mm",
            inter_id,
            window,
            dws_dow,
            [
                "MAX(turn_saturation) AS turn_saturation",
                "MIN(turn_saturation) AS turn_saturation_min",
                "MAX(turn_saturation) - MIN(turn_saturation) AS turn_saturation_spread",
            ],
            query_trace=query_trace,
        )

        by_approach = await self._safe_granularity(
            self._fetch_by_approach(flow_schema, inter_id, window, dws_dow, query_trace),
            label="by_approach",
        )
        by_turn = await self._safe_granularity(
            self._fetch_by_turn(flow_schema, inter_id, window, dws_dow, query_trace),
            label="by_turn",
        )
        by_lane = await self._safe_granularity(
            self._fetch_by_lane(
                flow_schema,
                road_schema,
                inter_id,
                window,
                dws_dow,
                query_trace,
            ),
            label="by_lane",
        )
        approach_stop_time_max = _max_metric(by_approach, "stop_time_sec")
        approach_stop_times_max = _max_metric(by_approach, "stop_times")

        plan_row = await self._fetchrow_trace(
            query_trace,
            "signal_plan",
            f"""
            SELECT AVG(p.cycle_len_sec) AS cycle_length,
                   AVG(t.green_sec::float / NULLIF(p.cycle_len_sec, 0)) AS green_ratio
            FROM {flow_schema}.dwd_ctl_inter_plan_cfg p
            JOIN {flow_schema}.dwd_ctl_inter_plan_stage_timing t
              ON p.inter_id = t.inter_id AND p.plan_no = t.plan_no
            WHERE p.inter_id = $1 AND p.is_deleted = 0 AND t.is_deleted = 0
            """,
            inter_id,
        )

        channel_rows = await self._fetch_trace(
            query_trace,
            "channelization",
            f"""
            SELECT turn_move, lane_info
            FROM {road_schema}.dwd_tfc_rltn_wide_inter_ft_link
            WHERE inter_id = $1 AND version_id = $2
            LIMIT 20
            """,
            inter_id,
            self._settings.pg_version_id,
        )

        has_mixed_left = any(
            "混合" in str(r.get("turn_move", "")) or "混合左转" in str(r.get("lane_info", ""))
            for r in channel_rows
        )

        has_dws = dws_eval is not None or dws_sat is not None
        missing_dws = not has_dwd and not has_dws
        if has_dwd:
            source_tier = "dwd_rolling_7d"
        elif has_dws:
            source_tier = "dws_weekday_pattern"
        else:
            source_tier = "none"

        lane_sat_max = _max_metric(by_lane, "lane_saturation")
        lane_capacity_min = _min_positive_metric(by_lane, "lane_capacity")
        sat_summary = canonical_saturation_summary(
            by_turn=by_turn,
            by_lane=by_lane,
            inter_saturation_max=_float(dws_eval, "saturation_max"),
            inter_saturation_avg=_float(dws_eval, "saturation_avg"),
        )
        saturation = sat_summary["saturation_rate"]
        saturation_raw = saturation
        turn_sat_max = sat_summary["turn_saturation_max"]
        turn_spread = sat_summary.get("turn_saturation_spread")
        saturation_granularity = sat_summary["granularity"]

        delay_index = (
            float(dwd_delay)
            if dwd_delay is not None
            else _float(dws_eval, "saturation_max", 1.0)
        )

        data_window_meta = window.to_meta(
            source_tier=source_tier,
            sample_count=dwd_samples if has_dwd else None,
            dws_dow_filter=dws_dow if not has_dwd else None,
            fallback_reason=fallback_reason if not has_dwd and has_dws else None,
        )

        los_code = str(dws_eval.get("level_of_service") or "C") if dws_eval else "C"

        payload = {
            "meta": {
                "inter_id": inter_id,
                "intersection": inter_name,
                "time_period": nlu.time_period.model_dump(),
                "data_window": data_window_meta,
                "missing_dws_coverage": missing_dws,
                "query_trace": query_trace,
            },
            "signal_plan": {
                "cycle_length": _float(plan_row, "cycle_length", 120.0),
                "green_ratio": _float(plan_row, "green_ratio", 0.33),
            },
            "traffic_flow": {
                "saturation_rate": saturation,
                "saturation_rate_raw": saturation_raw,
                "saturation_granularity": saturation_granularity,
                "turn_saturation_max": turn_sat_max,
                "turn_saturation_spread": turn_spread,
                "lane_saturation_max": lane_sat_max,
                "lane_capacity_min": lane_capacity_min,
            },
            "evaluation": {
                "delay_index": delay_index or 1.0,
                "imbalance_index": _float(dws_eval, "imbalance_index", 0.0),
                "green_utilization": _float(dws_util, "green_utilization", 0.6),
                "empty_green_rate": _float(dws_util, "empty_green_rate", 0.0),
                "level_of_service": los_code,
                "level_of_service_label": LOS_LABELS.get(los_code, los_code),
                "saturation_avg": _float(dws_eval, "saturation_avg"),
            },
            "granularity": {
                "by_approach": by_approach,
                "by_turn": by_turn,
                "by_lane": by_lane,
                "approach_stop_time_max": approach_stop_time_max,
                "approach_stop_times_max": approach_stop_times_max,
            },
            "channelization": {
                "has_mixed_left": has_mixed_left,
                "turn_types": "混合左转" if has_mixed_left else "",
            },
            "congestion_index": {
                "delay_index": delay_index or 1.0,
            },
        }
        apply_canonical_saturation_to_payload(payload)
        return payload

    async def approach_profiles(
        self,
        inter_id: str,
        *,
        window: DataWindow,
        dir8_filter: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """取某路口四进口道 profile（turn_saturation_max / green_util_min / queue）。"""
        if self._settings.mock_db:
            return _mock_approach_profiles(inter_id, dir8_filter)
        await self._pool.connect()
        flow_schema = self._settings.pg_flow_schema
        dow = window.dow_filter
        query_trace: list[dict[str, Any]] = []
        by_turn = await self._safe_granularity(
            self._fetch_by_turn(flow_schema, inter_id, window, dow, query_trace),
            label="by_turn",
        )
        by_approach = await self._safe_granularity(
            self._fetch_by_approach(flow_schema, inter_id, window, dow, query_trace),
            label="by_approach",
        )
        profiles = aggregate_approach_profiles(by_turn, by_approach)
        if dir8_filter is not None:
            allow = {int(d) for d in dir8_filter}
            profiles = [p for p in profiles if p["dir8_code"] in allow]
        return profiles

    async def _fetch_by_approach(
        self,
        schema: str,
        inter_id: str,
        window: DataWindow,
        dow_filter: tuple[int, ...],
        query_trace: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = await self._fetch_trace(
            query_trace,
            "granularity_by_approach",
            f"""
            SELECT link_id, dir8_code,
                   AVG(stop_time_sec) AS stop_time_sec,
                   AVG(stop_times) AS stop_times,
                   AVG(queue_len_est_m) AS queue_len_est_m,
                   AVG(delay_index) AS delay_index
            FROM {schema}.dws_inter_link_status_5min_mm
            WHERE inter_id = $1
              AND day_of_week = ANY($2::int[])
              AND step_index BETWEEN $3 AND $4
              AND is_deleted = 0
            GROUP BY link_id, dir8_code
            ORDER BY stop_time_sec DESC NULLS LAST
            LIMIT 8
            """,
            inter_id,
            list(dow_filter),
            window.step_start,
            window.step_end,
        )
        return [
            {
                "link_id": r.get("link_id"),
                "dir8_code": r.get("dir8_code"),
                "dir8_label": turn_label(int(r.get("dir8_code") or 0), 2)[:1] + "进口",
                "stop_time_sec": _float(r, "stop_time_sec"),
                "stop_times": _float(r, "stop_times"),
                "queue_len_est_m": _float(r, "queue_len_est_m"),
                "delay_index": _float(r, "delay_index"),
            }
            for r in rows
        ]

    async def _fetch_by_turn(
        self,
        schema: str,
        inter_id: str,
        window: DataWindow,
        dow_filter: tuple[int, ...],
        query_trace: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = await self._fetch_trace(
            query_trace,
            "granularity_by_turn",
            f"""
            SELECT ts.dir8_code, ts.turn_dir_no,
                   AVG(ts.turn_saturation) AS turn_saturation,
                   AVG(gu.green_utilization) AS green_utilization,
                   AVG(tf.turn_flow_total) AS turn_flow_total
            FROM {schema}.dws_turn_saturation_5min_mm ts
            LEFT JOIN {schema}.dws_turn_green_utilization_5min_mm gu
              ON gu.inter_id = ts.inter_id
             AND gu.link_id = ts.link_id
             AND gu.turn_dir_no = ts.turn_dir_no
             AND gu.day_of_week = ts.day_of_week
             AND gu.step_index = ts.step_index
             AND gu.is_deleted = 0
            LEFT JOIN {schema}.dws_inter_link_turn_flow_5min_mm tf
              ON tf.inter_id = ts.inter_id
             AND tf.dir8_code = ts.dir8_code
             AND tf.turn_dir_no = ts.turn_dir_no
             AND tf.day_of_week = ts.day_of_week
             AND tf.step_index = ts.step_index
             AND tf.is_deleted = 0
            WHERE ts.inter_id = $1
              AND ts.day_of_week = ANY($2::int[])
              AND ts.step_index BETWEEN $3 AND $4
              AND ts.is_deleted = 0
            GROUP BY ts.dir8_code, ts.turn_dir_no
            ORDER BY turn_saturation DESC NULLS LAST
            LIMIT 12
            """,
            inter_id,
            list(dow_filter),
            window.step_start,
            window.step_end,
        )
        return [
            {
                "label": turn_label(int(r.get("dir8_code") or 0), int(r.get("turn_dir_no") or 2)),
                "dir8_code": int(r.get("dir8_code") or 0),
                "turn_dir_no": int(r.get("turn_dir_no") or 2),
                "turn_saturation": _float(r, "turn_saturation"),
                "green_utilization": _float(r, "green_utilization"),
                "flow_vph": _float(r, "turn_flow_total"),
            }
            for r in rows
        ]

    async def _fetch_by_lane(
        self,
        schema: str,
        road_schema: str,
        inter_id: str,
        window: DataWindow,
        dow_filter: tuple[int, ...],
        query_trace: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # dws_lane_saturation_5min_mm 无 dir8_code，经 link_id 关联渠化宽表取方向
        rows = await self._fetch_trace(
            query_trace,
            "granularity_by_lane",
            f"""
            SELECT ls.lane_id, ls.link_id, ls.lane_no, ls.turn_dir_no,
                   ch.dir8_code, ch.dir8_label,
                   AVG(ls.lane_saturation) AS lane_saturation,
                   AVG(ls.lane_flow) AS lane_flow,
                   AVG(cap.lane_capacity) AS lane_capacity
            FROM {schema}.dws_lane_saturation_5min_mm ls
            LEFT JOIN {schema}.dws_lane_capacity_5min_mm cap
              ON cap.inter_id = ls.inter_id
             AND cap.lane_id = ls.lane_id
             AND cap.day_of_week = ls.day_of_week
             AND cap.step_index = ls.step_index
             AND cap.is_deleted = 0
            LEFT JOIN {road_schema}.dwd_tfc_rltn_wide_inter_ft_link ch
              ON ch.inter_id = ls.inter_id
             AND ch.link_id = ls.link_id
            WHERE ls.inter_id = $1
              AND ls.day_of_week = ANY($2::int[])
              AND ls.step_index BETWEEN $3 AND $4
              AND ls.is_deleted = 0
            GROUP BY ls.lane_id, ls.link_id, ls.lane_no, ls.turn_dir_no,
                     ch.dir8_code, ch.dir8_label
            ORDER BY lane_saturation DESC NULLS LAST
            LIMIT 8
            """,
            inter_id,
            list(dow_filter),
            window.step_start,
            window.step_end,
        )
        result: list[dict[str, Any]] = []
        for r in rows:
            dir8 = r.get("dir8_code")
            turn_dir = int(r.get("turn_dir_no") or 2)
            lane_no = r.get("lane_no")
            if dir8 is not None:
                dir_part = str(r.get("dir8_label") or turn_label(int(dir8), 2)[:1])
            else:
                link_id = str(r.get("link_id") or "")
                dir_part = link_id[-4:] if link_id else "进口"
            turn_part = TURN_DIR_LABELS.get(turn_dir, "直行")
            lane_part = f"第{lane_no}车道" if lane_no is not None else "车道"
            result.append(
                {
                    "lane_id": r.get("lane_id"),
                    "label": f"{dir_part}{lane_part}{turn_part}",
                    "lane_saturation": _float(r, "lane_saturation"),
                    "lane_flow": _float(r, "lane_flow"),
                    "lane_capacity": _float(r, "lane_capacity"),
                }
            )
        return result

    async def _safe_granularity(
        self,
        coro: Any,
        *,
        label: str,
    ) -> list[dict[str, Any]]:
        """Optional granularity query — failure should not abort diagnosis."""
        try:
            return await coro
        except Exception as exc:
            logger.warning("granularity %s failed: %s", label, exc)
            return []

    async def _fetch_dwd_delay(
        self,
        schema: str,
        inter_id: str,
        nlu: NluResult,
        window: DataWindow,
        *,
        query_trace: list[dict[str, Any]],
    ) -> tuple[float | None, int]:
        """Rolling calendar window on DWD perf table (Plan D primary)."""
        assert nlu.time_period is not None
        slot_start, slot_end = slot_times(nlu.time_period)
        row = await self._fetchrow_trace(
            query_trace,
            "dwd_delay",
            f"""
            SELECT AVG(delay_index) AS delay_index,
                   COUNT(*)::int AS sample_count
            FROM {schema}.dwd_tfc_inter_dir_perf_5min
            WHERE inter_id = $1 AND is_deleted = 0
              AND stat_time::date BETWEEN $2 AND $3
              AND stat_time::time >= $4 AND stat_time::time < $5
              AND EXTRACT(ISODOW FROM stat_time)::int = ANY($6::int[])
            """,
            inter_id,
            window.date_from_value,
            window.date_to_value,
            slot_start,
            slot_end,
            list(window.dow_filter),
        )
        if not row or row["sample_count"] == 0:
            return None, 0
        return _float(row, "delay_index"), int(row["sample_count"])

    async def _fetch_dws_row(
        self,
        schema: str,
        table: str,
        inter_id: str,
        window: DataWindow,
        dow_filter: tuple[int, ...],
        select_exprs: list[str],
        *,
        query_trace: list[dict[str, Any]],
    ) -> Any:
        """DWS query by day_of_week + step_index."""
        columns = ", ".join(select_exprs)
        return await self._fetchrow_trace(
            query_trace,
            f"dws_{table}",
            f"""
            SELECT {columns}
            FROM {schema}.{table}
            WHERE inter_id = $1
              AND day_of_week = ANY($2::int[])
              AND step_index BETWEEN $3 AND $4
              AND is_deleted = 0
            """,
            inter_id,
            list(dow_filter),
            window.step_start,
            window.step_end,
        )

    async def _fetchrow_trace(
        self,
        query_trace: list[dict[str, Any]],
        label: str,
        sql: str,
        *params: Any,
    ) -> Any:
        """Run fetchrow and retain SQL/row evidence for replay."""
        executable_sql = _render_executable_sql(sql, params)
        log_event(
            logger,
            logging.INFO,
            "data_fetch.sql",
            label=label,
            sql=executable_sql,
            params=[str(p) for p in params],
        )
        row = await self._pool.fetchrow(sql, *params)
        raw_data = _serialize_raw(row)
        log_event(logger, logging.INFO, "data_fetch.raw", label=label, raw_data=raw_data)
        query_trace.append(
            {
                "label": label,
                "sql": executable_sql,
                "params": [str(p) for p in params],
                "raw_data": raw_data,
            }
        )
        return row

    async def _fetch_trace(
        self,
        query_trace: list[dict[str, Any]],
        label: str,
        sql: str,
        *params: Any,
    ) -> list[Any]:
        """Run fetch and retain SQL/rows evidence for replay."""
        executable_sql = _render_executable_sql(sql, params)
        log_event(
            logger,
            logging.INFO,
            "data_fetch.sql",
            label=label,
            sql=executable_sql,
            params=[str(p) for p in params],
        )
        rows = await self._pool.fetch(sql, *params)
        raw_data = _serialize_raw(rows)
        log_event(logger, logging.INFO, "data_fetch.raw", label=label, raw_data=raw_data)
        query_trace.append(
            {
                "label": label,
                "sql": executable_sql,
                "params": [str(p) for p in params],
                "raw_data": raw_data,
            }
        )
        return rows

    @staticmethod
    def _mock_payload(
        inter_id: str,
        inter_name: str,
        nlu: NluResult,
        window: DataWindow,
    ) -> dict[str, Any]:
        """Deterministic mock metrics."""
        data_window_meta = window.to_meta(source_tier="mock", sample_count=42)
        base_meta = {
            "inter_id": inter_id,
            "intersection": inter_name,
            "time_period": nlu.time_period.model_dump() if nlu.time_period else {},
            "data_window": data_window_meta,
            "missing_dws_coverage": False,
        }
        if "低饱和" in inter_name:
            return {
                "meta": base_meta,
                "signal_plan": {"cycle_length": 120.0, "green_ratio": 0.40},
                "traffic_flow": {
                    "saturation_rate": 0.55,
                    "turn_saturation_max": 0.62,
                    "turn_saturation_spread": 0.18,
                },
                "evaluation": {
                    "delay_index": 1.2,
                    "imbalance_index": 0.15,
                    "green_utilization": 0.65,
                    "empty_green_rate": 0.05,
                    "level_of_service": "B",
                    "level_of_service_label": "B-稳定",
                    "saturation_avg": 0.52,
                },
                "granularity": _mock_granularity(low=True),
                "channelization": {"has_mixed_left": False, "turn_types": ""},
                "congestion_index": {"delay_index": 1.2},
            }
        return {
            "meta": base_meta,
            "signal_plan": {"cycle_length": 120.0, "green_ratio": 0.30},
            "traffic_flow": {
                "saturation_rate": 0.88,
                "turn_saturation_max": 0.95,
                "turn_saturation_spread": 0.42,
                "lane_saturation_max": 0.92,
                "lane_capacity_min": 480.0,
            },
            "evaluation": {
                "delay_index": 2.1,
                "imbalance_index": 0.35,
                "green_utilization": 0.45,
                "empty_green_rate": 0.22,
                "level_of_service": "E",
                "level_of_service_label": "E-拥堵",
                "saturation_avg": 0.78,
            },
            "granularity": _mock_granularity(low=False),
            "channelization": {"has_mixed_left": False, "turn_types": ""},
            "congestion_index": {"delay_index": 2.1},
        }


def _mock_granularity(*, low: bool) -> dict[str, Any]:
    if low:
        rows = {
            "by_approach": [
                {"dir8_label": "东进口", "stop_time_sec": 35.0, "stop_times": 0.8, "queue_len_est_m": 45.0},
            ],
            "by_turn": [
                {"label": "东直行", "turn_saturation": 0.58, "green_utilization": 0.62},
            ],
            "by_lane": [],
        }
    else:
        rows = {
            "by_approach": [
                {"dir8_label": "东进口", "stop_time_sec": 78.0, "stop_times": 1.9, "queue_len_est_m": 142.0},
                {"dir8_label": "西进口", "stop_time_sec": 32.0, "stop_times": 0.7, "queue_len_est_m": 38.0},
            ],
            "by_turn": [
                {"label": "东直行", "turn_saturation": 0.95, "green_utilization": 0.38},
                {"label": "西直行", "turn_saturation": 0.53, "green_utilization": 0.71},
            ],
            "by_lane": [
                {"label": "东车道", "lane_saturation": 0.92, "lane_flow": 420.0, "lane_capacity": 480.0},
            ],
        }
    rows["approach_stop_time_max"] = _max_metric(rows["by_approach"], "stop_time_sec")
    rows["approach_stop_times_max"] = _max_metric(rows["by_approach"], "stop_times")
    return rows


def _max_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(r[key]) for r in rows if r.get(key) is not None]
    return max(values) if values else None


def _min_positive_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(r[key]) for r in rows if r.get(key) is not None and float(r[key]) > 0]
    return min(values) if values else None


def _dws_dow_for_query(window: DataWindow, *, dwd_has_data: bool) -> tuple[int, ...]:
    """DWS day_of_week filter: full pattern when DWD hit; else提问日星期几."""
    if dwd_has_data:
        return window.dow_filter
    return (window.primary_dow,)


def _float(row: Any, key: str, default: float | None = None) -> float | None:
    """Safely extract float from asyncpg record."""
    if row is None:
        return default
    value = row.get(key)
    if value is None:
        return default
    return float(value)


def _normalize_sql(sql: str) -> str:
    """Collapse SQL whitespace for compact logs and replay metadata."""
    return " ".join(sql.split())


def _render_executable_sql(sql: str, params: tuple[Any, ...]) -> str:
    """Render asyncpg-style placeholders into a copy-pasteable SQL statement."""
    rendered = _normalize_sql(sql)
    for index in range(len(params), 0, -1):
        rendered = rendered.replace(f"${index}", _sql_literal(params[index - 1]))
    return rendered


def _sql_literal(value: Any) -> str:
    """Convert a Python value into a PostgreSQL literal for diagnostic SQL."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float | Decimal):
        return str(value)
    if isinstance(value, datetime | date | time):
        return f"'{value.isoformat()}'"
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return "ARRAY[" + ", ".join(_sql_literal(item) for item in value) + "]"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _serialize_raw(value: Any) -> Any:
    """Convert asyncpg records and scalar values into JSON-friendly raw data."""
    from intersection_agent.utils.json_safe import to_json_safe

    return to_json_safe(value)


def aggregate_approach_profiles(
    by_turn: list[dict[str, Any]],
    by_approach: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """聚合为每进口道一条 profile：取该进口道最大 turn_saturation 与最小 green_util。"""
    queue_by_dir8: dict[int, float] = {}
    for r in by_approach:
        d8 = r.get("dir8_code")
        if d8 is None:
            continue
        q = r.get("queue_len_est_m")
        if q is not None:
            queue_by_dir8[int(d8)] = max(queue_by_dir8.get(int(d8), 0.0), float(q))

    acc: dict[int, dict[str, Any]] = {}
    for r in by_turn:
        d8 = r.get("dir8_code")
        if d8 is None:
            continue
        d8 = int(d8)
        sat = r.get("turn_saturation")
        gu = r.get("green_utilization")
        node = acc.setdefault(
            d8, {"dir8_code": d8, "turn_saturation_max": None, "green_util_min": None}
        )
        if sat is not None:
            node["turn_saturation_max"] = max(node["turn_saturation_max"] or 0.0, float(sat))
        if gu is not None:
            cur = node["green_util_min"]
            node["green_util_min"] = float(gu) if cur is None else min(cur, float(gu))
    for d8, node in acc.items():
        node["queue_len_est_m"] = queue_by_dir8.get(d8)
    return sorted(acc.values(), key=lambda n: n["dir8_code"])


def _mock_approach_profiles(
    inter_id: str, dir8_filter: list[int] | None = None
) -> list[dict[str, Any]]:
    """MOCK_DB：可治理上游(含 'gov' / mock_up_)留一进口未饱和，其余路口四向全饱和。"""
    if "gov" in inter_id or inter_id.startswith("mock_up_"):
        profiles = [
            {"dir8_code": 0, "turn_saturation_max": 0.70, "green_util_min": 0.62,
             "queue_len_est_m": 40.0},
        ] + [
            {"dir8_code": d, "turn_saturation_max": 0.95, "green_util_min": 0.60,
             "queue_len_est_m": 120.0}
            for d in (2, 4, 6)
        ]
    else:
        profiles = [
            {"dir8_code": d, "turn_saturation_max": 0.95, "green_util_min": 0.60,
             "queue_len_est_m": 130.0}
            for d in (0, 2, 4, 6)
        ]
    if dir8_filter is not None:
        allow = {int(d) for d in dir8_filter}
        profiles = [p for p in profiles if p["dir8_code"] in allow]
    return profiles
