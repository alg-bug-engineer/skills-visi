"""Resolve diagnosis metrics/topology from task injection, PG, or explicit demo fallback."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import Settings
from app.data.intersection_registry import enrich_ticket

logger = logging.getLogger(__name__)

FIXTURES_ROOT = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"


def resolve_diagnosis_inputs(
    task: dict[str, Any],
    settings: Settings,
    *,
    ticket: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return metrics + topology with explicit data source; never silent demo."""
    ticket = ticket or task.get("diagnosis_ticket") or {}
    ticket = enrich_ticket(ticket)

    injected_metrics = task.get("metrics")
    injected_topology = task.get("topology")
    if injected_metrics and injected_topology:
        return {
            "ok": True,
            "metrics": injected_metrics,
            "topology": injected_topology,
            "source": "task_injection",
        }

    inter_id = ticket.get("inter_id") or task.get("inter_id")
    if settings.pg_dsn and (inter_id or ticket.get("intersection_name")):
        from app.data.load_pg_bundle import load_pg_diagnosis_bundle

        loaded = load_pg_diagnosis_bundle(task, ticket, settings)
        if loaded.get("ok"):
            return {
                "ok": True,
                "metrics": loaded["metrics"],
                "topology": loaded["topology"],
                "source": "pg",
            }
        if not settings.allow_demo_fallback:
            return loaded

    if settings.allow_demo_fallback:
        demo = _load_demo_data(ticket)
        demo["ok"] = True
        demo["source"] = "mock"
        demo["reason"] = "allow_demo_fallback=true"
        logger.warning("使用 demo 数据 source=mock inter=%s", ticket.get("intersection_name"))
        return demo

    return {
        "ok": False,
        "available": False,
        "source": "none",
        "reason": (
            "缺少 metrics/topology 注入，且未配置 PG 或 allow_demo_fallback=false。"
            "请通过 task.metrics + task.topology 注入，或配置 PG_DSN。"
        ),
    }

def _load_demo_data(ticket: dict[str, Any]) -> dict[str, Any]:
    """Explicit test-only demo path: fixtures only, never skill demo scripts."""
    fixture_metrics = FIXTURES_ROOT / "overflow_metrics.json"
    fixture_topology = FIXTURES_ROOT / "overflow_topology.json"
    if not (fixture_metrics.exists() and fixture_topology.exists()):
        return {
            "metrics": {},
            "topology": {},
            "reason": "demo fixture 缺失：tests/fixtures/overflow_metrics.json",
        }
    metrics = json.loads(fixture_metrics.read_text(encoding="utf-8"))
    topology = json.loads(fixture_topology.read_text(encoding="utf-8"))
    topology.setdefault("target_inter_name", ticket.get("intersection_name"))
    return {"metrics": metrics, "topology": topology}


def _load_demo_module(skill_scripts: str, module_name: str):
    raise RuntimeError(
        "生产路径禁止加载 skills 内 demo 脚本；请使用 PG/task 注入，"
        "或测试环境 ALLOW_DEMO_FALLBACK=true + tests/fixtures"
    )
