"""Load diagnosis metrics/topology/signal bundle from PostgreSQL."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Any

from app.config import Settings
from app.data.pg_adapters import (
    enrich_downstream_metrics,
    merge_pg_task_into_context,
    metrics_for_diagnosis,
    load_cross_week_peak_movement_metrics,
    load_cross_week_mean_movement_metrics,
    parse_day_of_week,
    parse_time_hhmm,
    topology_from_pg_raw,
)
from app.data.typical_intersection_profiles import (
    metric_options_from_profile,
    resolve_typical_profile,
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

    profile_opts = metric_options_from_profile(resolve_typical_profile(ticket))
    # Cross-week target metrics and the full static/signal/topology checklist are
    # independent reads.  Run them together: peak metrics overwrite the dynamic
    # slice below, while the checklist's requested workday remains the topology
    # and signal context.  This hides the target metric round trips behind AOI /
    # signal loading instead of adding them to cold latency.
    resolved_inter_id = str(inter_id or "")
    initial_dow = parse_day_of_week(ticket)

    def _load_full():
        return load_intersection_from_pg(
            inter_id=resolved_inter_id or None,
            inter_name=str(inter_name) if inter_name else None,
            day_of_week=int(initial_dow),
            time_hhmm=parse_time_hhmm(ticket.get("time_range")),
            time_range=ticket.get("time_range"),
        )

    try:
        if resolved_inter_id:
            with ThreadPoolExecutor(max_workers=2) as pool:
                peak_future = pool.submit(
                    load_cross_week_peak_movement_metrics,
                    inter_id=resolved_inter_id,
                    direction=str(ticket.get("direction") or "东向西"),
                    movement=str(ticket.get("movement") or "直行"),
                    time_range=ticket.get("time_range"),
                    queue_field=str(profile_opts.get("target_queue_field") or "queue_len_avg"),
                    typical_profile_id=profile_opts.get("typical_profile_id"),
                    typical_profile_label=profile_opts.get("typical_profile_label"),
                )
                full_future = pool.submit(_load_full)
                peak = peak_future.result()
                loaded = full_future.result()
        else:
            peak = None
            loaded = _load_full()
    except Exception as exc:
        logger.exception("PG 加载失败 inter_id=%s", inter_id)
        return {"ok": False, "source": "pg", "reason": str(exc)}

    if not loaded.get("ok"):
        return {
            "ok": False,
            "source": "pg",
            "reason": "; ".join(loaded.get("errors") or ["PG 加载失败"]),
        }

    if not resolved_inter_id:
        resolved_inter_id = str(
            (((loaded.get("task") or {}).get("scope") or {}).get("intersection_id")) or ""
        )
        if resolved_inter_id and peak is None:
            resolved_ticket = {**ticket, "inter_id": resolved_inter_id}
            profile_opts = metric_options_from_profile(resolve_typical_profile(resolved_ticket))
            peak = load_cross_week_peak_movement_metrics(
                inter_id=resolved_inter_id,
                direction=str(ticket.get("direction") or "东向西"),
                movement=str(ticket.get("movement") or "直行"),
                time_range=ticket.get("time_range"),
                queue_field=str(profile_opts.get("target_queue_field") or "queue_len_avg"),
                typical_profile_id=profile_opts.get("typical_profile_id"),
                typical_profile_label=profile_opts.get("typical_profile_label"),
            )

    pg_task = loaded.get("task") or {}
    raw = loaded.get("raw") or {}
    inter = raw.get("inter") or {}
    if isinstance(inter, list):
        inter = inter[0] if inter else {}

    pg_metrics = pg_task.get("metrics") or {}
    peak_metrics = peak
    if peak_metrics is None:
        peak_metrics = load_cross_week_peak_movement_metrics(
            inter_id=str(ticket.get("inter_id") or inter.get("inter_id") or ""),
            direction=str(ticket.get("direction") or "东向西"),
            movement=str(ticket.get("movement") or "直行"),
            time_range=ticket.get("time_range"),
            queue_field=str(profile_opts.get("target_queue_field") or "queue_len_avg"),
            typical_profile_id=profile_opts.get("typical_profile_id"),
            typical_profile_label=profile_opts.get("typical_profile_label"),
        )
    if peak_metrics:
        pg_metrics = {**pg_metrics, **peak_metrics}
        pg_task["metrics"] = pg_metrics
        raw["metrics"] = pg_metrics
        # The checklist branch intentionally runs with the requested workday so
        # it can overlap the peak lookup.  Rebind movement-level raw series to
        # the selected peak day before downstream diagnostics consume them.
        for raw_key, metric_key in (
            ("turn_perf", "turn_perf_detail"),
            ("turn_saturation", "turn_saturation_detail"),
            ("turn_flow", "turn_flow_detail"),
            ("green_utilization", "green_utilization_detail"),
        ):
            if peak_metrics.get(metric_key):
                raw[raw_key] = peak_metrics[metric_key]
    metrics = metrics_for_diagnosis(
        pg_metrics,
        ticket,
        scope=pg_task.get("scope") if isinstance(pg_task.get("scope"), dict) else None,
    )
    if profile_opts.get("typical_profile_id"):
        metrics["typical_profile_id"] = profile_opts.get("typical_profile_id")
        metrics["typical_profile_label"] = profile_opts.get("typical_profile_label")
        metrics["typical_opt_type"] = profile_opts.get("typical_opt_type")
    topology = topology_from_pg_raw({**raw, "metrics": pg_metrics}, ticket, inter)

    def _adjacent_metrics(
        adj_id: str,
        *,
        direction: str | None = None,
        movement: str | None = None,
    ) -> dict[str, Any] | None:
        return load_cross_week_mean_movement_metrics(
            inter_id=str(adj_id),
            direction=direction or "东向西",
            movement=movement or "直行",
            time_range=ticket.get("time_range"),
            queue_field=str(profile_opts.get("downstream_queue_field") or "queue_len_avg"),
            peak_disclose_field=str(
                profile_opts.get("downstream_peak_disclose_field") or "queue_len_avg"
            ),
            typical_profile_id=profile_opts.get("typical_profile_id"),
            typical_profile_label=profile_opts.get("typical_profile_label"),
        )

    enrich_downstream_metrics(
        topology,
        load_pg_metrics=_adjacent_metrics,
        target_inter_id=str(ticket.get("inter_id") or resolved_inter_id or ""),
        approach_queue_avg=bool(profile_opts.get("downstream_approach_queue_avg")),
    )

    merge_pg_task_into_context(task, pg_task)
    task["pg_raw"] = raw
    task["checklist_queries"] = loaded.get("checklist_queries")
    task["signal_source"] = "pg"
    task["typical_metric_profile"] = {
        "id": profile_opts.get("typical_profile_id"),
        "label": profile_opts.get("typical_profile_label"),
        "opt_type": profile_opts.get("typical_opt_type"),
        "use_typical_policy": bool(profile_opts.get("use_typical_policy")),
        "target_queue_field": profile_opts.get("target_queue_field"),
        "downstream_queue_field": profile_opts.get("downstream_queue_field"),
        "downstream_peak_disclose_field": profile_opts.get("downstream_peak_disclose_field"),
    }

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
        "typical_metric_profile": task["typical_metric_profile"],
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
