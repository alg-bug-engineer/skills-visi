"""Load intersection data from PG for frontend task injection."""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from app.config import Settings
from app.data.pg_adapters import (
    enrich_downstream_metrics,
    merge_pg_task_into_context,
    metrics_for_diagnosis,
    load_movement_metrics_by_selection,
    parse_day_of_week,
    parse_time_hhmm,
    topology_from_pg_raw,
)
from app.data.typical_intersection_profiles import (
    apply_screening_anchor_to_metrics,
    metric_options_from_profile,
    resolve_typical_profile,
)

logger = logging.getLogger(__name__)


class IntersectionLoadService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def load(
        self,
        *,
        inter_id: str | None = None,
        intersection_name: str | None = None,
        time_range: str | None = None,
        day_of_week: int | None = None,
        time_hhmm: str | None = None,
        direction: str = "东向西",
        movement: str = "直行",
    ) -> dict[str, Any]:
        if not self.settings.pg_dsn:
            return {
                "ok": False,
                "reason": "pg_dsn_not_configured",
                "task": {},
                "checklist_queries": [],
                "errors": ["PG_DSN 未配置"],
            }

        if not inter_id and not intersection_name:
            return {
                "ok": False,
                "reason": "missing_intersection",
                "task": {},
                "checklist_queries": [],
                "errors": ["缺少 inter_id 或 intersection_name"],
            }

        try:
            from app.data.load_intersection_from_pg import load_intersection_from_pg
        except Exception as exc:
            return {
                "ok": False,
                "reason": "pg_module_unavailable",
                "task": {},
                "checklist_queries": [],
                "errors": [str(exc)],
            }

        ticket = {
            "inter_id": inter_id,
            "intersection_name": intersection_name,
            "direction": direction,
            "movement": movement,
            "time_range": time_range,
            "period": "晚高峰",
        }
        dow = day_of_week if day_of_week is not None else parse_day_of_week(ticket)
        hhmm = time_hhmm or parse_time_hhmm(time_range)

        try:
            loaded = load_intersection_from_pg(
                inter_id=str(inter_id) if inter_id else None,
                inter_name=str(intersection_name) if intersection_name else None,
                day_of_week=dow,
                time_hhmm=hhmm,
                time_range=time_range,
            )
        except Exception as exc:
            logger.exception("路口 PG 加载失败 inter_id=%s", inter_id)
            return {
                "ok": False,
                "reason": "pg_load_failed",
                "task": {},
                "checklist_queries": [],
                "errors": [str(exc)],
            }

        if not loaded.get("ok"):
            return {
                "ok": False,
                "reason": "pg_load_failed",
                "task": {},
                "checklist_queries": loaded.get("checklist_queries") or [],
                "errors": loaded.get("errors") or ["PG 加载失败"],
            }

        # 演示口径以目标转向跨周峰值日为主日型；配时、时段表和流量优先使用
        # 同一天，避免目标指标与现状方案日型互相错位。
        # 典型路口命中 profile 时改用配置字段（如 queue_len_max）；否则固定 queue_len_avg。
        resolved_inter_id = str(inter_id or ((loaded.get("task") or {}).get("scope") or {}).get("intersection_id") or "")
        profile_ticket = {
            **ticket,
            "inter_id": resolved_inter_id or ticket.get("inter_id"),
        }
        profile_opts = metric_options_from_profile(resolve_typical_profile(profile_ticket))
        peak = load_movement_metrics_by_selection(
            inter_id=resolved_inter_id,
            direction=direction,
            movement=movement,
            time_range=time_range,
            selection=str(profile_opts.get("target_selection") or "cross_week_peak"),
            queue_field=str(profile_opts.get("target_queue_field") or "queue_len_avg"),
            typical_profile_id=profile_opts.get("typical_profile_id"),
            typical_profile_label=profile_opts.get("typical_profile_label"),
        ) if resolved_inter_id else None
        peak_dow = (peak or {}).get("selected_day_of_week")
        if peak_dow and int(peak_dow) != int(dow):
            loaded = load_intersection_from_pg(
                inter_id=resolved_inter_id,
                day_of_week=int(peak_dow),
                time_hhmm=hhmm,
                time_range=time_range,
            )
            dow = int(peak_dow)

        task = self._build_agent_task(
            loaded,
            ticket,
            day_of_week=dow,
            time_hhmm=hhmm,
            time_range=time_range,
            peak_metrics=peak,
            profile_opts=profile_opts,
        )
        checklist = loaded.get("checklist_queries") or []
        has_data = sum(1 for item in checklist if item.get("status") == "has_data")
        return {
            "ok": True,
            "task": task,
            "checklist_queries": checklist,
            "checklist_summary": {
                "total": len(checklist),
                "has_data": has_data,
            },
            "errors": loaded.get("errors") or {},
        }

    def iter_load_events(
        self,
        *,
        inter_id: str | None = None,
        intersection_name: str | None = None,
        time_range: str | None = None,
        day_of_week: int | None = None,
        time_hhmm: str | None = None,
        direction: str = "东向西",
        movement: str = "直行",
    ) -> Iterator[str]:
        if not self.settings.pg_dsn:
            yield self._sse("error", {"reason": "pg_dsn_not_configured"})
            return

        if not inter_id and not intersection_name:
            yield self._sse("error", {"reason": "missing_intersection"})
            return

        from app.data.load_intersection_from_pg import iter_checklist_load

        ticket = {
            "inter_id": inter_id,
            "intersection_name": intersection_name,
            "direction": direction,
            "movement": movement,
            "time_range": time_range,
        }
        dow = day_of_week if day_of_week is not None else parse_day_of_week(ticket)
        hhmm = time_hhmm or parse_time_hhmm(time_range)

        for event in iter_checklist_load(
            inter_id=str(inter_id) if inter_id else None,
            inter_name=str(intersection_name) if intersection_name else None,
            day_of_week=dow,
            time_hhmm=hhmm,
            time_range=time_range,
        ):
            if event.get("type") == "checklist_item":
                yield self._sse("checklist_item", event.get("item") or {})
            elif event.get("type") == "error":
                yield self._sse("error", {"message": event.get("message")})
                return
            elif event.get("type") == "complete":
                task = self._build_agent_task(
                    event, ticket, day_of_week=dow, time_hhmm=hhmm, time_range=time_range
                )
                yield self._sse(
                    "complete",
                    {
                        "ok": True,
                        "task": task,
                        "checklist_queries": event.get("checklist_queries") or [],
                        "checklist_summary": {
                            "total": len(event.get("checklist_queries") or []),
                            "has_data": sum(
                                1
                                for item in event.get("checklist_queries") or []
                                if item.get("status") == "has_data"
                            ),
                        },
                    },
                )

    def _build_agent_task(
        self,
        loaded: dict[str, Any],
        ticket: dict[str, Any],
        *,
        day_of_week: int | None = None,
        time_hhmm: str | None = None,
        time_range: str | None = None,
        peak_metrics: dict[str, Any] | None = None,
        profile_opts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pg_task = loaded.get("task") or {}
        raw = loaded.get("raw") or {}
        inter = raw.get("inter") or {}
        if isinstance(inter, list):
            inter = inter[0] if inter else {}

        task: dict[str, Any] = {}
        merge_pg_task_into_context(task, pg_task)
        pg_metrics = pg_task.get("metrics") or {}
        profile_ticket = {
            **ticket,
            "inter_id": ticket.get("inter_id") or inter.get("inter_id"),
            "intersection_name": ticket.get("intersection_name") or inter.get("inter_name"),
        }
        opts = profile_opts or metric_options_from_profile(resolve_typical_profile(profile_ticket))
        if peak_metrics is None:
            peak_metrics = load_movement_metrics_by_selection(
                inter_id=str(ticket.get("inter_id") or inter.get("inter_id") or ""),
                direction=str(ticket.get("direction") or "东向西"),
                movement=str(ticket.get("movement") or "直行"),
                time_range=time_range or ticket.get("time_range"),
                selection=str(opts.get("target_selection") or "cross_week_peak"),
                queue_field=str(opts.get("target_queue_field") or "queue_len_avg"),
                typical_profile_id=opts.get("typical_profile_id"),
                typical_profile_label=opts.get("typical_profile_label"),
            )
        if peak_metrics:
            pg_metrics = {**pg_metrics, **peak_metrics}
            pg_task["metrics"] = pg_metrics
            raw["metrics"] = pg_metrics
        metrics = metrics_for_diagnosis(
            pg_metrics,
            ticket,
            scope=pg_task.get("scope") if isinstance(pg_task.get("scope"), dict) else None,
        )
        metrics = apply_screening_anchor_to_metrics(metrics, opts.get("screening_anchor"))
        if opts.get("typical_profile_id"):
            metrics["typical_profile_id"] = opts.get("typical_profile_id")
            metrics["typical_profile_label"] = opts.get("typical_profile_label")
            metrics["typical_opt_type"] = opts.get("typical_opt_type")
        topology = topology_from_pg_raw({**raw, "metrics": pg_metrics}, ticket, inter)
        self._enrich_downstream(
            topology,
            day_of_week=day_of_week,
            time_hhmm=time_hhmm,
            time_range=time_range,
            target_inter_id=str(ticket.get("inter_id") or inter.get("inter_id") or ""),
            profile_opts=opts,
        )

        diagnosis_ticket = {
            **ticket,
            "inter_id": ticket.get("inter_id") or inter.get("inter_id") or inter.get("intersection_id"),
            "intersection_name": ticket.get("intersection_name")
            or inter.get("inter_name")
            or inter.get("intersection_name"),
            "lng": inter.get("lng") or inter.get("lon"),
            "lat": inter.get("lat"),
        }

        task.update(
            {
                "diagnosis_ticket": diagnosis_ticket,
                "metrics": metrics,
                "topology": topology,
                "signal": pg_task.get("signal") or {},
                "checklist_queries": loaded.get("checklist_queries") or [],
                "pg_raw": raw,
                "signal_source": "pg",
                "typical_metric_profile": {
                    "id": opts.get("typical_profile_id"),
                    "label": opts.get("typical_profile_label"),
                    "opt_type": opts.get("typical_opt_type"),
                    "use_typical_policy": bool(opts.get("use_typical_policy")),
                    "target_queue_field": opts.get("target_queue_field"),
                    "target_selection": opts.get("target_selection"),
                    "downstream_queue_field": opts.get("downstream_queue_field"),
                    "downstream_selection": opts.get("downstream_selection"),
                    "downstream_peak_disclose_field": opts.get("downstream_peak_disclose_field"),
                },
            }
        )
        return task

    def _enrich_downstream(
        self,
        topology: dict[str, Any],
        *,
        day_of_week: int | None,
        time_hhmm: str | None,
        time_range: str | None,
        target_inter_id: str | None = None,
        profile_opts: dict[str, Any] | None = None,
    ) -> None:
        """为下游相邻节点注入真实 PG 运行指标（修复下游指标恒为 0，BUG-004）。

        使用轻量指标加载器（跳过 AOI/几何/信号等昂贵查询），避免首步阻塞（需求21-R4）。
        """
        try:
            from app.data.load_intersection_from_pg import load_intersection_metrics_only
        except Exception as exc:  # noqa: BLE001
            logger.warning("下游指标加载模块不可用：%s", exc)
            return

        opts = profile_opts or {}

        def _adjacent_metrics(
            adj_id: str,
            *,
            direction: str | None = None,
            movement: str | None = None,
        ) -> dict[str, Any] | None:
            return load_movement_metrics_by_selection(
                inter_id=str(adj_id),
                direction=direction or "东向西",
                movement=movement or "直行",
                time_range=time_range,
                selection=str(opts.get("downstream_selection") or "cross_week_mean"),
                queue_field=str(opts.get("downstream_queue_field") or "queue_len_avg"),
                peak_disclose_field=str(
                    opts.get("downstream_peak_disclose_field") or "queue_len_avg"
                ),
                typical_profile_id=opts.get("typical_profile_id"),
                typical_profile_label=opts.get("typical_profile_label"),
            )

        enrich_downstream_metrics(
            topology,
            load_pg_metrics=_adjacent_metrics,
            target_inter_id=target_inter_id,
            approach_queue_avg=bool(opts.get("downstream_approach_queue_avg")),
        )

    @staticmethod
    def _sse(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
