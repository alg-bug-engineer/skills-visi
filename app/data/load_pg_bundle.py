"""Load diagnosis metrics/topology/signal bundle from PostgreSQL."""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.data.pg_adapters import (
    enrich_downstream_metrics,
    merge_pg_task_into_context,
    metrics_for_diagnosis,
    parse_day_of_week,
    parse_time_hhmm,
    topology_from_pg_raw,
)

logger = logging.getLogger(__name__)


def load_pg_diagnosis_bundle(
    task: dict[str, Any],
    ticket: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    if not settings.pg_dsn:
        return {"ok": False, "source": "pg", "reason": "PG_DSN 未配置"}

    try:
        from app.data.load_intersection_from_pg import load_intersection_from_pg
    except Exception as exc:
        return {"ok": False, "source": "pg", "reason": f"PG 加载模块不可用: {exc}"}

    inter_id = ticket.get("inter_id")
    inter_name = ticket.get("intersection_name")
    if not inter_id and not inter_name:
        return {"ok": False, "source": "pg", "reason": "缺少 inter_id 或 intersection_name"}

    try:
        loaded = load_intersection_from_pg(
            inter_id=str(inter_id) if inter_id else None,
            inter_name=str(inter_name) if inter_name else None,
            day_of_week=parse_day_of_week(ticket),
            time_hhmm=parse_time_hhmm(ticket.get("time_range")),
            time_range=ticket.get("time_range"),
        )
    except Exception as exc:
        logger.exception("PG 加载失败 inter_id=%s", inter_id)
        return {"ok": False, "source": "pg", "reason": str(exc)}

    if not loaded.get("ok"):
        return {
            "ok": False,
            "source": "pg",
            "reason": "; ".join(loaded.get("errors") or ["PG 加载失败"]),
        }

    pg_task = loaded.get("task") or {}
    raw = loaded.get("raw") or {}
    inter = raw.get("inter") or {}
    if isinstance(inter, list):
        inter = inter[0] if inter else {}

    pg_metrics = pg_task.get("metrics") or {}
    metrics = metrics_for_diagnosis(pg_metrics, ticket)
    topology = topology_from_pg_raw({**raw, "metrics": pg_metrics}, ticket, inter)

    # 轻量指标加载（跳过 AOI/几何/信号昂贵查询），避免逐下游节点整份检查单加载（需求21-R4）。
    from app.data.load_intersection_from_pg import load_intersection_metrics_only

    def _adjacent_metrics(adj_id: str) -> dict[str, Any] | None:
        adj = load_intersection_metrics_only(
            inter_id=str(adj_id),
            day_of_week=parse_day_of_week(ticket),
            time_hhmm=parse_time_hhmm(ticket.get("time_range")),
            time_range=ticket.get("time_range"),
        )
        if not adj.get("ok"):
            return None
        return adj.get("metrics") or None

    enrich_downstream_metrics(
        topology,
        load_pg_metrics=_adjacent_metrics,
        target_inter_id=str(ticket.get("inter_id") or ""),
    )

    merge_pg_task_into_context(task, pg_task)
    task["pg_raw"] = raw
    task["checklist_queries"] = loaded.get("checklist_queries")
    task["signal_source"] = "pg"

    quality = _assess_pg_data_quality(pg_metrics, pg_task.get("signal") or {}, raw)
    if not quality["usable"]:
        return {
            "ok": False,
            "source": "pg",
            "reason": quality["reason"],
            "data_quality": quality,
        }

    return {
        "ok": True,
        "source": "pg",
        "metrics": metrics,
        "topology": topology,
        "signal": pg_task.get("signal") or {},
        "scope": pg_task.get("scope") or {},
        "data_quality": quality,
    }


def _assess_pg_data_quality(
    pg_metrics: dict[str, Any],
    signal: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    has_queue = float(pg_metrics.get("queue_m") or 0) > 0
    has_volume = bool(pg_metrics.get("movement_volume")) or float(pg_metrics.get("volume") or 0) > 0
    has_saturation = float(pg_metrics.get("saturation") or 0) > 0 or bool(pg_metrics.get("movement_saturation"))
    has_perf = bool(raw.get("turn_perf"))
    has_signal = bool(
        signal.get("phase_stage_timing_list")
        or signal.get("phasePlanOfTimeList")
        or signal.get("stage_detail")
    )

    usable = has_queue or has_volume or has_saturation or has_perf
    warnings: list[str] = []
    if not has_signal:
        warnings.append("现状配时缺失（plan_cfg/stage_timing 无数据，方案生成将不可用）")

    return {
        "usable": usable,
        "has_metrics": usable,
        "has_signal": has_signal,
        "reason": "PG 动态指标为空（排队/流量/饱和度均无有效值）" if not usable else "",
        "warnings": warnings,
    }
