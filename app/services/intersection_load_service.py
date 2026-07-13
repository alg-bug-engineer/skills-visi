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
    parse_day_of_week,
    parse_time_hhmm,
    topology_from_pg_raw,
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

        task = self._build_agent_task(loaded, ticket, day_of_week=dow, time_hhmm=hhmm, time_range=time_range)
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
    ) -> dict[str, Any]:
        pg_task = loaded.get("task") or {}
        raw = loaded.get("raw") or {}
        inter = raw.get("inter") or {}
        if isinstance(inter, list):
            inter = inter[0] if inter else {}

        task: dict[str, Any] = {}
        merge_pg_task_into_context(task, pg_task)
        pg_metrics = pg_task.get("metrics") or {}
        metrics = metrics_for_diagnosis(
            pg_metrics,
            ticket,
            scope=pg_task.get("scope") if isinstance(pg_task.get("scope"), dict) else None,
        )
        topology = topology_from_pg_raw({**raw, "metrics": pg_metrics}, ticket, inter)
        self._enrich_downstream(
            topology,
            day_of_week=day_of_week,
            time_hhmm=time_hhmm,
            time_range=time_range,
            target_inter_id=str(ticket.get("inter_id") or inter.get("inter_id") or ""),
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
    ) -> None:
        """为下游相邻节点注入真实 PG 运行指标（修复下游指标恒为 0，BUG-004）。

        使用轻量指标加载器（跳过 AOI/几何/信号等昂贵查询），避免首步阻塞（需求21-R4）。
        """
        try:
            from app.data.load_intersection_from_pg import load_intersection_metrics_only
        except Exception as exc:  # noqa: BLE001
            logger.warning("下游指标加载模块不可用：%s", exc)
            return

        def _adjacent_metrics(adj_id: str) -> dict[str, Any] | None:
            adj = load_intersection_metrics_only(
                inter_id=str(adj_id),
                day_of_week=day_of_week if day_of_week is not None else 5,
                time_hhmm=time_hhmm,
                time_range=time_range,
            )
            if not adj.get("ok"):
                return None
            return adj.get("metrics") or None

        enrich_downstream_metrics(
            topology,
            load_pg_metrics=_adjacent_metrics,
            target_inter_id=target_inter_id,
        )

    @staticmethod
    def _sse(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
