"""Fetch 5-minute series and evaluate sustained imbalance / empty-green (checklist-lite)."""

from __future__ import annotations

import logging
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.models.domain import NluResult
from intersection_agent.utils.data_window import DataWindow, build_data_window
from intersection_agent.utils.demo_config import resolve_reference_date
from intersection_agent.utils.sustained_windows import (
    find_sustained_windows,
    min_sustained_steps,
    movement_saturation_gap_series,
    scalar_series,
)
from intersection_agent.utils.thresholds_loader import load_thresholds, threshold_value

logger = logging.getLogger(__name__)

CHECKLIST_REFS = {
    "service_imbalance": "inter_evaluation",
    "empty_green": "green_utilization",
    "spillback": "turn_perf",
}


class SustainedMetricsService:
    """Evaluate checklist sustained windows for demo four-dimension diagnosis."""

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
        nlu: NluResult,
        *,
        data_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not nlu.time_period:
            return self._empty("missing_time_period")

        ref = resolve_reference_date()
        window = build_data_window(nlu.time_period, reference_date=ref)
        thresholds = load_thresholds()

        if self._settings.mock_db:
            return self._mock()

        await self._pool.connect()
        flow_schema = self._settings.pg_flow_schema
        has_dwd = bool(
            (data_payload or {}).get("meta", {}).get("data_window", {}).get("source_tier")
            == "dwd_rolling_7d"
        )
        dow_filter = window.dow_filter if has_dwd else (window.primary_dow,)

        eval_rows = await self._fetch_series(
            flow_schema,
            "dws_inter_evaluation_5min_mm",
            inter_id,
            dow_filter,
            window,
            ["step_index", "unbalance_index", "saturation_max"],
        )
        green_rows = await self._fetch_series(
            flow_schema,
            "dws_turn_green_utilization_5min_mm",
            inter_id,
            dow_filter,
            window,
            ["step_index", "green_utilization"],
        )
        turn_rows = await self._fetch_series(
            flow_schema,
            "dws_turn_saturation_5min_mm",
            inter_id,
            dow_filter,
            window,
            ["step_index", "turn_saturation"],
        )

        sustained_min = int(threshold_value("imbalance", "sustained_minutes", default=15))
        step_min = int(threshold_value("imbalance", "sustained_step_minutes", default=5))
        min_steps = min_sustained_steps(sustained_min, step_min)

        imb_thresh = threshold_value("imbalance", "diagnosis", default=0.30)
        gap_thresh = threshold_value("imbalance", "movement_saturation_gap", default=0.60)
        low_util = threshold_value("green", "low_utilization_diagnosis", default=0.60)

        imb_series = scalar_series(eval_rows, "unbalance_index")
        gap_series = movement_saturation_gap_series(turn_rows)

        imb_windows = find_sustained_windows(
            imb_series, imb_thresh, min_steps=min_steps, above=True
        )
        gap_windows = find_sustained_windows(
            gap_series, gap_thresh, min_steps=min_steps, above=True
        )

        green_by_step: dict[int, list[float]] = {}
        for row in green_rows:
            step = row.get("step_index")
            if step is None:
                continue
            try:
                value = float(row.get("green_utilization") or 0)
            except (TypeError, ValueError):
                continue
            green_by_step.setdefault(int(step), []).append(value)
        green_min_series = {
            step: min(values) for step, values in green_by_step.items() if values
        }
        empty_windows = find_sustained_windows(
            green_min_series, low_util, min_steps=min_steps, above=False
        )

        imbalance_triggered = bool(imb_windows or gap_windows)
        empty_triggered = bool(empty_windows)

        checklist_items = [
            _checklist_item(
                "service_imbalance",
                triggered=imbalance_triggered,
                summary=_imbalance_summary(imb_windows, gap_windows),
                evidence=_imbalance_evidence(imb_windows, gap_windows),
            ),
            _checklist_item(
                "empty_green",
                triggered=empty_triggered,
                summary=_empty_summary(empty_windows),
                evidence=_empty_evidence(empty_windows, low_util),
            ),
        ]

        return {
            "sustained_minutes": sustained_min,
            "imbalance_windows": imb_windows[:3],
            "movement_gap_windows": gap_windows[:3],
            "empty_green_windows": empty_windows[:3],
            "checklist_items": checklist_items,
            "dimensions": {
                "imbalance_sustained": imbalance_triggered,
                "empty_green_sustained": empty_triggered,
            },
        }

    async def _fetch_series(
        self,
        schema: str,
        table: str,
        inter_id: str,
        dow_filter: tuple[int, ...],
        window: DataWindow,
        columns: list[str],
    ) -> list[dict[str, Any]]:
        cols = ", ".join(columns)
        sql = f"""
            SELECT {cols}
            FROM {schema}.{table}
            WHERE inter_id = $1
              AND day_of_week = ANY($2::int[])
              AND step_index BETWEEN $3 AND $4
              AND is_deleted = 0
            ORDER BY step_index
        """
        try:
            rows = await self._pool.fetch(
                sql,
                inter_id,
                list(dow_filter),
                window.step_start,
                window.step_end,
            )
            return [dict(row) for row in rows]
        except Exception as exc:
            logger.warning("sustained metrics query failed %s: %s", table, exc)
            return []

    @staticmethod
    def _empty(reason: str) -> dict[str, Any]:
        return {
            "reason": reason,
            "checklist_items": [],
            "dimensions": {},
        }

    @staticmethod
    def _mock() -> dict[str, Any]:
        return {
            "sustained_minutes": 15,
            "imbalance_windows": [
                {
                    "start": "17:15",
                    "end": "18:00",
                    "duration_min": 45,
                    "average": 0.36,
                    "peak": 0.41,
                }
            ],
            "empty_green_windows": [
                {
                    "start": "17:30",
                    "end": "18:15",
                    "duration_min": 45,
                    "average": 0.48,
                    "peak": 0.55,
                }
            ],
            "movement_gap_windows": [],
            "checklist_items": [
                _checklist_item(
                    "service_imbalance",
                    triggered=True,
                    summary="失衡指数连续15分钟超阈值",
                    evidence=[{"metric": "imbalance_index", "value": 0.36, "threshold": 0.30}],
                ),
                _checklist_item(
                    "empty_green",
                    triggered=True,
                    summary="绿灯利用率连续15分钟低于0.60",
                    evidence=[{"metric": "green_utilization", "value": 0.48, "threshold": 0.60}],
                ),
            ],
            "dimensions": {
                "imbalance_sustained": True,
                "empty_green_sustained": True,
            },
        }


def _checklist_item(
    item_id: str,
    *,
    triggered: bool,
    summary: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "status": "triggered" if triggered else "passed",
        "triggered": triggered,
        "summary": summary,
        "evidence": evidence,
        "profile_checklist_ref": CHECKLIST_REFS.get(item_id),
    }


def _imbalance_summary(
    imb_windows: list[dict[str, Any]],
    gap_windows: list[dict[str, Any]],
) -> str:
    if imb_windows:
        w = imb_windows[0]
        return f"失衡指数在 {w['start']}-{w['end']} 连续 {w['duration_min']} 分钟超阈"
    if gap_windows:
        w = gap_windows[0]
        return f"转向饱和度极差在 {w['start']}-{w['end']} 连续 {w['duration_min']} 分钟超阈"
    return "未发现持续服务失衡"


def _imbalance_evidence(
    imb_windows: list[dict[str, Any]],
    gap_windows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    if imb_windows:
        w = imb_windows[0]
        evidence.append(
            {
                "metric": "imbalance_index",
                "value": w.get("peak"),
                "threshold": w.get("threshold"),
                "window": f"{w.get('start')}-{w.get('end')}",
            }
        )
    if gap_windows:
        w = gap_windows[0]
        evidence.append(
            {
                "metric": "movement_saturation_gap",
                "value": w.get("peak"),
                "threshold": w.get("threshold"),
                "window": f"{w.get('start')}-{w.get('end')}",
            }
        )
    return evidence


def _empty_summary(windows: list[dict[str, Any]]) -> str:
    if not windows:
        return "未发现持续空放"
    w = windows[0]
    return f"绿灯利用率在 {w['start']}-{w['end']} 连续 {w['duration_min']} 分钟低于阈值"


def _empty_evidence(windows: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    if not windows:
        return []
    w = windows[0]
    return [
        {
            "metric": "green_utilization",
            "value": w.get("average"),
            "threshold": threshold,
            "window": f"{w.get('start')}-{w.get('end')}",
        }
    ]
