"""Build quantitative problem-validation evidence for user feedback."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.models.domain import NluResult
from intersection_agent.utils.data_window import DataWindow, build_data_window, slot_times
from intersection_agent.utils.direction_groups import (
    GROUP_ORDER,
    direction_to_group,
    primary_groups_from_nlu,
)
from intersection_agent.utils.dow_parser import dow_label, extract_explicit_dow
from intersection_agent.utils.demo_config import resolve_reference_date
from intersection_agent.utils.saturation_granularity import canonical_saturation_summary
from intersection_agent.utils.thresholds_loader import load_thresholds, threshold_value

logger = logging.getLogger(__name__)

F_DIR8_TO_GROUP: dict[str, str] = {
    "南向北": "南北向",
    "北向南": "南北向",
    "东向西": "东西向",
    "西向东": "东西向",
    "西南向东北": "西南向",
    "东北向西南": "东北向",
    "西北向东南": "西北向",
    "东南向西北": "东南向",
}


class ProblemEvidenceService:
    """Aggregate evidence that validates the user's congestion claim."""

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
        *,
        data_payload: dict[str, Any] | None = None,
        user_context: str = "",
        reference_date: date | None = None,
    ) -> dict[str, Any]:
        """Return structured problem evidence bundle."""
        if not nlu.time_period:
            return self._empty_evidence("missing_time_period")

        window = build_data_window(
            nlu.time_period,
            reference_date=reference_date or resolve_reference_date(),
        )
        thresholds = load_thresholds()
        target_dow = extract_explicit_dow(user_context) or window.primary_dow

        if self._settings.mock_db:
            return self._mock_evidence(inter_id, inter_name, nlu, window, target_dow, data_payload)

        await self._pool.connect()
        query_trace: list[dict[str, Any]] = []
        flow_schema = self._settings.pg_flow_schema

        daily_rows = await self._fetch_daily_dwd(
            flow_schema, inter_id, nlu, window, query_trace
        )
        has_dwd = bool(daily_rows)

        direction_rows = await self._fetch_direction_metrics(
            flow_schema, inter_id, window, query_trace, has_dwd=has_dwd
        )
        saturation_row = await self._fetch_intersection_saturation(
            flow_schema, inter_id, window, has_dwd, query_trace
        )

        chronic = self._assess_chronic(daily_rows, saturation_row, thresholds, window)
        dow_pattern = self._assess_dow_pattern(
            daily_rows, target_dow, thresholds, window, saturation_row=saturation_row
        )
        metrics = self._aggregate_metrics(
            daily_rows, direction_rows, saturation_row, data_payload
        )
        by_direction = self._build_direction_breakdown(
            direction_rows, cognition=(data_payload or {}).get("cognition"),
            focus_groups=primary_groups_from_nlu(nlu.directions),
        )

        source_tier = "dwd_rolling_7d" if has_dwd else (
            "dws_weekday_pattern" if direction_rows else "none"
        )

        evidence = {
            "inter_id": inter_id,
            "intersection": inter_name,
            "time_label": nlu.time_period.label,
            "source_tier": source_tier,
            "target_dow": target_dow,
            "target_dow_label": dow_label(target_dow),
            "chronic": chronic,
            "dow_pattern": dow_pattern,
            "metrics": metrics,
            "by_direction": by_direction,
            "thresholds_used": {
                "min_congested_days": int(
                    thresholds.get("chronic", {}).get("min_congested_days", 4)
                ),
                "window_days": int(thresholds.get("chronic", {}).get("window_days", 7)),
                "excess_delay_s": threshold_value("delay", "excess_delay_s", default=60),
                "long_queue_m": threshold_value("queue", "long_queue_m", default=100),
                "saturation_high": threshold_value("saturation", "high", default=0.80),
                "queue_storage_ratio_high": threshold_value(
                    "queue", "queue_storage_ratio_high", default=0.80
                ),
            },
            "summary": self._build_summary(chronic, dow_pattern, metrics, nlu),
            "query_trace": query_trace,
        }
        self._merge_extended_profiles(evidence, data_payload)
        evidence["diagnosis_story"] = self._build_diagnosis_story(evidence)
        evidence["summary"] = self._enrich_summary(evidence)
        return evidence

    async def _fetch_daily_dwd(
        self,
        schema: str,
        inter_id: str,
        nlu: NluResult,
        window: DataWindow,
        query_trace: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        assert nlu.time_period is not None
        slot_start, slot_end = slot_times(nlu.time_period)
        sql = f"""
            SELECT stat_time::date AS stat_date,
                   EXTRACT(ISODOW FROM stat_time)::int AS dow,
                   AVG(stop_time) AS avg_stop_time,
                   AVG(queue_len_avg) AS avg_queue_m,
                   MAX(queue_len_max) AS max_queue_m,
                   AVG(delay_index) AS delay_index
            FROM {schema}.dwd_tfc_inter_dir_perf_5min
            WHERE inter_id = $1 AND is_deleted = 0
              AND stat_time::date BETWEEN $2 AND $3
              AND stat_time::time >= $4 AND stat_time::time < $5
            GROUP BY 1, 2
            ORDER BY 1
        """
        rows = await self._pool.fetch(
            sql, inter_id, window.date_from_value, window.date_to_value, slot_start, slot_end
        )
        query_trace.append(
            {
                "label": "evidence_daily_dwd",
                "sql": sql.strip(),
                "row_count": len(rows),
            }
        )
        return [dict(row) for row in rows]

    async def _fetch_direction_metrics(
        self,
        schema: str,
        inter_id: str,
        window: DataWindow,
        query_trace: list[dict[str, Any]],
        *,
        has_dwd: bool,
    ) -> list[dict[str, Any]]:
        dow_filter = window.dow_filter if has_dwd else (window.primary_dow,)
        sql = f"""
            SELECT f_dir_8_label,
                   AVG(queue_len_avg) AS avg_queue_m,
                   MAX(queue_len_max) AS max_queue_m,
                   AVG(stop_time) AS avg_stop_time,
                   AVG(delay_index) AS delay_index,
                   AVG(queue_len_avg / NULLIF(rid_length_m, 0)) AS queue_storage_ratio
            FROM {schema}.dws_inter_dir_turn_perf_5min_mm
            WHERE inter_id = $1
              AND day_of_week = ANY($2::int[])
              AND step_index BETWEEN $3 AND $4
              AND is_deleted = 0
            GROUP BY f_dir_8_label
        """
        rows = await self._pool.fetch(
            sql,
            inter_id,
            list(dow_filter),
            window.step_start,
            window.step_end,
        )
        query_trace.append(
            {
                "label": "evidence_direction_dws",
                "sql": sql.strip(),
                "row_count": len(rows),
            }
        )
        return [dict(row) for row in rows]

    async def _fetch_intersection_saturation(
        self,
        schema: str,
        inter_id: str,
        window: DataWindow,
        has_dwd: bool,
        query_trace: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        dow_filter = window.dow_filter if has_dwd else (window.primary_dow,)
        sql = f"""
            SELECT AVG(saturation_max) AS saturation_max,
                   AVG(saturation_avg) AS saturation_avg,
                   AVG(unbalance_index) AS imbalance_index
            FROM {schema}.dws_inter_evaluation_5min_mm
            WHERE inter_id = $1
              AND day_of_week = ANY($2::int[])
              AND step_index BETWEEN $3 AND $4
              AND is_deleted = 0
        """
        row = await self._pool.fetchrow(
            sql,
            inter_id,
            list(dow_filter),
            window.step_start,
            window.step_end,
        )
        query_trace.append({"label": "evidence_saturation_dws", "sql": sql.strip()})
        return dict(row) if row else None

    def _is_congested_day(
        self,
        row: dict[str, Any],
        saturation_max: float | None,
        thresholds: dict[str, Any],
    ) -> bool:
        excess_delay = float(thresholds.get("delay", {}).get("excess_delay_s", 60))
        long_queue = float(thresholds.get("queue", {}).get("long_queue_m", 100))
        sat_high = float(thresholds.get("saturation", {}).get("high", 0.80))
        storage_high = float(
            thresholds.get("queue", {}).get("queue_storage_ratio_high", 0.80)
        )

        avg_stop = _float(row.get("avg_stop_time"))
        max_queue = _float(row.get("max_queue_m"))
        avg_queue = _float(row.get("avg_queue_m"))

        if avg_stop is not None and avg_stop >= excess_delay:
            return True
        if max_queue is not None and max_queue >= long_queue:
            return True
        if saturation_max is not None and saturation_max >= sat_high:
            return True
        if avg_queue is not None and avg_queue >= long_queue * 0.8:
            return True
        if _float(row.get("queue_storage_ratio")) is not None:
            if float(row["queue_storage_ratio"]) >= storage_high:
                return True
        return False

    def _assess_chronic(
        self,
        daily_rows: list[dict[str, Any]],
        saturation_row: dict[str, Any] | None,
        thresholds: dict[str, Any],
        window: DataWindow,
    ) -> dict[str, Any]:
        min_days = int(thresholds.get("chronic", {}).get("min_congested_days", 4))
        window_days = int(thresholds.get("chronic", {}).get("window_days", 7))
        sat_max = _float(saturation_row.get("saturation_max")) if saturation_row else None

        if daily_rows:
            congested_dates = [
                str(row["stat_date"])
                for row in daily_rows
                if self._is_congested_day(row, sat_max, thresholds)
            ]
            total_days = len(daily_rows)
            congested_count = len(congested_dates)
            rate = congested_count / max(total_days, 1)
            return {
                "is_chronic": congested_count >= min_days,
                "congested_days": congested_count,
                "window_days": total_days,
                "rate": round(rate, 3),
                "congested_dates": congested_dates,
                "verdict": (
                    f"近{total_days}日中{congested_count}日该时段运行指标超标"
                    + ("，属常发性拥堵" if congested_count >= min_days else "，暂未达到常发标准")
                ),
                "method": "dwd_calendar",
            }

        if sat_max is not None and sat_max >= float(
            thresholds.get("saturation", {}).get("high", 0.80)
        ):
            return {
                "is_chronic": True,
                "congested_days": None,
                "window_days": window_days,
                "rate": None,
                "congested_dates": [],
                "verdict": f"同时段周内规律显示该时段饱和度 {sat_max:.2f} 持续偏高",
                "method": "dws_pattern_estimate",
            }

        return {
            "is_chronic": False,
            "congested_days": 0,
            "window_days": window_days,
            "rate": 0.0,
            "congested_dates": [],
            "verdict": "",
            "method": "insufficient_data",
        }

    def _assess_dow_pattern(
        self,
        daily_rows: list[dict[str, Any]],
        target_dow: int,
        thresholds: dict[str, Any],
        window: DataWindow,
        *,
        saturation_row: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        hit_rate_high = float(thresholds.get("chronic", {}).get("dow_hit_rate_high", 0.75))
        label = dow_label(target_dow)

        if daily_rows:
            target_days = [row for row in daily_rows if int(row.get("dow") or 0) == target_dow]
            if not target_days:
                return {
                    "target_dow": target_dow,
                    "dow_label": label,
                    "hit_days": 0,
                    "total_days": 0,
                    "hit_rate": 0.0,
                    "verdict": "",
                    "method": "dwd_calendar",
                }
            congested = [
                row
                for row in target_days
                if self._is_congested_day(row, None, thresholds)
            ]
            total = len(target_days)
            hits = len(congested)
            rate = hits / max(total, 1)
            recurring = rate >= hit_rate_high and hits >= 1
            return {
                "target_dow": target_dow,
                "dow_label": label,
                "hit_days": hits,
                "total_days": total,
                "hit_rate": round(rate, 3),
                "verdict": (
                    f"{label}该时段 {hits}/{total} 日指标超标"
                    + ("，呈周期性拥堵" if recurring else "，周期性不明显")
                ),
                "method": "dwd_calendar",
            }

        sat_max = _float(saturation_row.get("saturation_max")) if saturation_row else None
        sat_high = float(thresholds.get("saturation", {}).get("high", 0.80))
        if sat_max is not None and sat_max >= sat_high:
            return {
                "target_dow": target_dow,
                "dow_label": label,
                "hit_days": None,
                "total_days": None,
                "hit_rate": None,
                "verdict": f"{label}同时段历史规律显示该时段运行压力偏高",
                "method": "dws_weekday_pattern",
            }

        return {
            "target_dow": target_dow,
            "dow_label": label,
            "hit_days": None,
            "total_days": None,
            "hit_rate": None,
            "verdict": "",
            "method": "dws_weekday_pattern",
        }

    def _aggregate_metrics(
        self,
        daily_rows: list[dict[str, Any]],
        direction_rows: list[dict[str, Any]],
        saturation_row: dict[str, Any] | None,
        data_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        eval_metrics = (data_payload or {}).get("evaluation", {})
        traffic = (data_payload or {}).get("traffic_flow", {})

        avg_stop = _mean([_float(r.get("avg_stop_time")) for r in daily_rows])
        max_queue = _max([_float(r.get("max_queue_m")) for r in daily_rows])
        avg_queue = _mean(
            [_float(r.get("avg_queue_m")) for r in daily_rows]
            or [_float(r.get("avg_queue_m")) for r in direction_rows]
        )
        if avg_queue is None and direction_rows:
            avg_queue = _mean([_float(r.get("avg_queue_m")) for r in direction_rows])
        if max_queue is None and direction_rows:
            max_queue = _max([_float(r.get("max_queue_m")) for r in direction_rows])

        storage_ratio = _max([_float(r.get("queue_storage_ratio")) for r in direction_rows])
        spillback_risk = storage_ratio
        if spillback_risk is None:
            max_queue = _max([_float(r.get("max_queue_m")) for r in direction_rows])
            long_queue = threshold_value("queue", "long_queue_m", default=100)
            if max_queue is not None and max_queue >= long_queue:
                spillback_risk = min(1.0, max_queue / max(long_queue, 1))

        gran = (data_payload or {}).get("granularity") or {}
        sat_summary = canonical_saturation_summary(
            by_turn=gran.get("by_turn"),
            by_lane=gran.get("by_lane"),
            inter_saturation_max=_float(saturation_row.get("saturation_max"))
            if saturation_row
            else _float(eval_metrics.get("saturation_max")),
            inter_saturation_avg=_float(eval_metrics.get("saturation_avg")),
        )
        sat_rate = sat_summary.get("saturation_rate") or traffic.get("saturation_rate")
        return {
            "avg_delay_s": round(avg_stop, 1) if avg_stop is not None else None,
            "delay_index": eval_metrics.get("delay_index"),
            "saturation_rate": sat_rate,
            "imbalance_index": eval_metrics.get("imbalance_index")
            or (_float(saturation_row.get("imbalance_index")) if saturation_row else None),
            "avg_queue_m": round(avg_queue, 1) if avg_queue is not None else None,
            "max_queue_m": round(max_queue, 1) if max_queue is not None else None,
            "queue_storage_ratio_max": round(storage_ratio, 3)
            if storage_ratio is not None
            else None,
            "spillback_risk_max": round(spillback_risk, 3)
            if spillback_risk is not None
            else None,
        }

    def _build_direction_breakdown(
        self,
        direction_rows: list[dict[str, Any]],
        *,
        cognition: dict[str, Any] | None,
        focus_groups: list[str],
    ) -> list[dict[str, Any]]:
        group_acc: dict[str, dict[str, Any]] = {}

        for row in direction_rows:
            label = str(row.get("f_dir_8_label") or "")
            group = F_DIR8_TO_GROUP.get(label) or direction_to_group(label)
            item = group_acc.setdefault(
                group,
                {
                    "group": group,
                    "avg_queue_m": [],
                    "max_queue_m": [],
                    "avg_stop_time": [],
                    "queue_storage_ratio": [],
                    "saturation": [],
                },
            )
            for key, target in (
                ("avg_queue_m", "avg_queue_m"),
                ("max_queue_m", "max_queue_m"),
                ("avg_stop_time", "avg_stop_time"),
                ("queue_storage_ratio", "queue_storage_ratio"),
            ):
                value = _float(row.get(key))
                if value is not None:
                    item[target].append(value)

        cognition_groups = {
            g["group"]: g for g in (cognition or {}).get("direction_groups", [])
        }
        for group_name, cg in cognition_groups.items():
            item = group_acc.setdefault(
                group_name,
                {
                    "group": group_name,
                    "avg_queue_m": [],
                    "max_queue_m": [],
                    "avg_stop_time": [],
                    "queue_storage_ratio": [],
                    "saturation": [],
                },
            )
            sat = _float(cg.get("saturation_max"))
            if sat is not None:
                item["saturation"].append(sat)

        breakdown: list[dict[str, Any]] = []
        for group_name in GROUP_ORDER:
            if group_name not in group_acc:
                continue
            raw = group_acc[group_name]
            breakdown.append(
                {
                    "group": group_name,
                    "focused": group_name in focus_groups,
                    "avg_queue_m": _round_or_none(_mean(raw["avg_queue_m"])),
                    "max_queue_m": _round_or_none(_max(raw["max_queue_m"])),
                    "avg_delay_s": _round_or_none(_mean(raw["avg_stop_time"])),
                    "queue_storage_ratio": _round_or_none(_max(raw["queue_storage_ratio"])),
                    "saturation": _round_or_none(_max(raw["saturation"])),
                }
            )
        return breakdown

    def _build_summary(
        self,
        chronic: dict[str, Any],
        dow_pattern: dict[str, Any],
        metrics: dict[str, Any],
        nlu: NluResult,
    ) -> str:
        parts: list[str] = []
        if _is_display_verdict(chronic.get("verdict")):
            parts.append(str(chronic["verdict"]))
        if _is_display_verdict(dow_pattern.get("verdict")):
            parts.append(str(dow_pattern["verdict"]))
        dirs = "、".join(nlu.directions) if nlu.directions else "全方向"
        sat = metrics.get("saturation_rate")
        delay = metrics.get("avg_delay_s")
        queue = metrics.get("avg_queue_m")
        metric_bits: list[str] = []
        if sat is not None:
            metric_bits.append(f"饱和度 {float(sat):.2f}")
        if delay is not None:
            metric_bits.append(f"平均停车 {delay}s")
        if queue is not None:
            metric_bits.append(f"平均排队约 {queue}m")
        if metric_bits:
            parts.append(f"关注方向 {dirs}：" + "，".join(metric_bits))
        return "；".join(parts)

    @staticmethod
    def _merge_extended_profiles(
        evidence: dict[str, Any],
        data_payload: dict[str, Any] | None,
    ) -> None:
        payload = data_payload or {}
        gran = payload.get("granularity") or {}
        evidence["by_turn"] = gran.get("by_turn") or []
        evidence["by_approach"] = gran.get("by_approach") or []
        evidence["by_lane"] = gran.get("by_lane") or []
        evidence["timing_profile"] = payload.get("timing_profile") or {}
        evidence["corridor_context"] = payload.get("corridor_context") or {}
        evidence["external_evidence"] = payload.get("external_evidence") or {}
        evidence["flow_trace"] = payload.get("flow_trace") or {}
        eval_metrics = payload.get("evaluation") or {}
        if eval_metrics.get("level_of_service"):
            evidence.setdefault("metrics", {})
            evidence["metrics"]["level_of_service"] = eval_metrics.get("level_of_service")
            evidence["metrics"]["level_of_service_label"] = eval_metrics.get("level_of_service_label")

    @staticmethod
    def _build_diagnosis_story(evidence: dict[str, Any]) -> list[dict[str, str]]:
        """Ordered narrative beats for frontend storytelling."""
        beats: list[dict[str, str]] = []
        chronic = evidence.get("chronic") or {}
        if _is_display_verdict(chronic.get("verdict")):
            beats.append({"phase": "chronic", "title": "常发性", "text": str(chronic["verdict"])})
        dow = evidence.get("dow_pattern") or {}
        if _is_display_verdict(dow.get("verdict")):
            beats.append({"phase": "dow", "title": "周期性", "text": str(dow["verdict"])})

        metrics = evidence.get("metrics") or {}
        metric_bits: list[str] = []
        if metrics.get("saturation_rate") is not None:
            metric_bits.append(f"饱和度 {float(metrics['saturation_rate']):.2f}")
        if metrics.get("level_of_service_label"):
            metric_bits.append(f"服务水平 {metrics['level_of_service_label']}")
        if metric_bits:
            beats.append(
                {
                    "phase": "metrics",
                    "title": "运行状态",
                    "text": "，".join(metric_bits),
                }
            )

        timing = evidence.get("timing_profile") or {}
        if timing.get("narrative"):
            beats.append({"phase": "timing", "title": "配时画像", "text": str(timing["narrative"])})

        return beats

    @staticmethod
    def _enrich_summary(evidence: dict[str, Any]) -> str:
        parts = [str(evidence.get("summary") or "")]
        for beat in evidence.get("diagnosis_story") or []:
            text = str(beat.get("text") or "")
            if text and _is_display_narrative(text) and text not in parts[0]:
                parts.append(text)
        return "；".join(p for p in parts if p)

    @staticmethod
    def _mock_evidence(
        inter_id: str,
        inter_name: str,
        nlu: NluResult,
        window: DataWindow,
        target_dow: int,
        data_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        eval_metrics = (data_payload or {}).get("evaluation", {})
        traffic = (data_payload or {}).get("traffic_flow", {})
        gran = (data_payload or {}).get("granularity") or {}
        sat_summary = canonical_saturation_summary(
            by_turn=gran.get("by_turn"),
            by_lane=gran.get("by_lane"),
            inter_saturation_max=_float(eval_metrics.get("saturation_max")),
            inter_saturation_avg=_float(eval_metrics.get("saturation_avg")),
        )
        sat = sat_summary.get("saturation_rate") or float(traffic.get("saturation_rate") or 0.88)
        thresholds = load_thresholds()
        min_days = int(thresholds.get("chronic", {}).get("min_congested_days", 4))

        chronic = {
            "is_chronic": True,
            "congested_days": 5,
            "window_days": 7,
            "rate": 0.714,
            "congested_dates": [],
            "verdict": f"近7日中5日该时段运行指标超标，属常发性拥堵",
            "method": "mock",
            "congested_dates": [
                "2026-06-10",
                "2026-06-11",
                "2026-06-12",
                "2026-06-17",
                "2026-06-18",
            ],
        }
        dow_pattern = {
            "target_dow": target_dow,
            "dow_label": dow_label(target_dow),
            "hit_days": 1,
            "total_days": 1,
            "hit_rate": 1.0,
            "verdict": f"{dow_label(target_dow)}该时段指标超标，呈周期性拥堵",
            "method": "mock",
        }
        metrics = {
            "avg_delay_s": 72.0,
            "delay_index": eval_metrics.get("delay_index", 2.1),
            "saturation_rate": sat,
            "imbalance_index": eval_metrics.get("imbalance_index", 0.35),
            "avg_queue_m": 96.0,
            "max_queue_m": 138.0,
            "queue_storage_ratio_max": 0.72,
            "spillback_risk_max": 0.72,
        }
        by_direction = [
            {
                "group": "南北向",
                "focused": "南北向" in primary_groups_from_nlu(nlu.directions),
                "avg_queue_m": 112.0,
                "max_queue_m": 138.0,
                "avg_delay_s": 78.0,
                "queue_storage_ratio": 0.68,
                "saturation": 0.92,
            },
            {
                "group": "东西向",
                "focused": False,
                "avg_queue_m": 48.0,
                "max_queue_m": 72.0,
                "avg_delay_s": 32.0,
                "queue_storage_ratio": 0.42,
                "saturation": 0.55,
            },
        ]
        evidence = {
            "inter_id": inter_id,
            "intersection": inter_name,
            "time_label": nlu.time_period.label if nlu.time_period else "",
            "source_tier": "mock",
            "coverage_warning": None,
            "target_dow": target_dow,
            "target_dow_label": dow_label(target_dow),
            "chronic": chronic,
            "dow_pattern": dow_pattern,
            "metrics": metrics,
            "by_direction": by_direction,
            "thresholds_used": {
                "min_congested_days": min_days,
                "window_days": 7,
            },
            "summary": (
                f"近7日中5日该时段运行指标超标，属常发性拥堵；"
                f"{dow_label(target_dow)}该时段指标超标；"
                f"关注方向 {'、'.join(nlu.directions) or '南北向'}：饱和度 {sat:.2f}，平均排队约 96m"
            ),
            "query_trace": [],
        }
        ProblemEvidenceService._merge_extended_profiles(evidence, data_payload)
        evidence["diagnosis_story"] = ProblemEvidenceService._build_diagnosis_story(evidence)
        evidence["summary"] = ProblemEvidenceService._enrich_summary(evidence)
        return evidence

    @staticmethod
    def _empty_evidence(reason: str) -> dict[str, Any]:
        return {
            "summary": "缺少时段信息，无法生成问题验证证据",
            "reason": reason,
            "chronic": {},
            "dow_pattern": {},
            "metrics": {},
            "by_direction": [],
        }


def _flow_trace_beat_text(flow_trace: dict[str, Any]) -> str:
    """流量溯源叙事 beat：进口道 100 辆 / 上一路口左直右（近月规律）。"""
    if not flow_trace or not flow_trace.get("available"):
        return ""
    entries = flow_trace.get("entry_traces") or []
    if entries:
        top = max(entries, key=lambda e: float(e.get("entry_max_saturation") or 0))
        narrative = str(top.get("narrative") or "").strip()
        if narrative:
            return f"{narrative}（近月同时段规律）"
    turns = flow_trace.get("problem_turns") or []
    for turn in turns:
        if turn.get("source_pattern") == "multi_corridor":
            return (
                f"{turn.get('entry')}{turn.get('turn')}车流来自多个上游方向，"
                "宜区域协同治理（近月同时段规律）"
            )
    return ""


def _is_display_verdict(verdict: Any) -> bool:
    """Skip empty, insufficient-data, or internal methodology verdicts from user-facing cards."""
    return _is_display_narrative(verdict)


def _is_display_narrative(text: Any) -> bool:
    """User-facing cards only show lines backed by real evidence."""
    value = str(text or "").strip()
    if not value:
        return False
    hidden_markers = (
        "无逐日",
        "无日历明细",
        "同时段的周内规律分析",
        "DWS",
        "DWD",
        "数据不足",
        "暂无法判定",
        "暂无投诉",
        "诊断完全基于运行数据",
        "无样本",
    )
    return not any(marker in value for marker in hidden_markers)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _max(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    return max(nums) if nums else None


def _round_or_none(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    return round(value, digits)
