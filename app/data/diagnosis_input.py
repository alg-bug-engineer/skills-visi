"""Resolve diagnosis metrics/topology from task injection, PG, or explicit demo fallback."""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)

SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent / "skills"
FIXTURES_ROOT = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"


def resolve_diagnosis_inputs(
    task: dict[str, Any],
    settings: Settings,
    *,
    ticket: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return metrics + topology with explicit data source; never silent demo."""
    ticket = ticket or task.get("diagnosis_ticket") or {}

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
    if settings.pg_dsn and inter_id:
        loaded = _load_from_pg(inter_id=inter_id, ticket=ticket, settings=settings)
        if loaded.get("ok"):
            return loaded
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


def _load_from_pg(
    *,
    inter_id: str,
    ticket: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    """PG loader placeholder — implemented in stage A follow-up."""
    _ = settings
    logger.info("PG 加载尚未实现 inter_id=%s", inter_id)
    return {
        "ok": False,
        "available": False,
        "source": "pg",
        "reason": f"pg_loader_not_implemented: inter_id={inter_id}",
        "intersection_name": ticket.get("intersection_name"),
    }


def _load_demo_module(skill_scripts: str, module_name: str):
    script_path = SKILLS_ROOT / skill_scripts
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 demo 脚本: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_demo_data(ticket: dict[str, Any]) -> dict[str, Any]:
    fixture_metrics = FIXTURES_ROOT / "overflow_metrics.json"
    fixture_topology = FIXTURES_ROOT / "overflow_topology.json"
    if fixture_metrics.exists() and fixture_topology.exists():
        metrics = json.loads(fixture_metrics.read_text(encoding="utf-8"))
        topology = json.loads(fixture_topology.read_text(encoding="utf-8"))
        topology.setdefault("target_inter_name", ticket.get("intersection_name"))
        return {"metrics": metrics, "topology": topology}

    metrics_module = _load_demo_module(
        "data-analysis-diagnosis/scripts/demo_metrics.py",
        "demo_metrics",
    )
    topo_module = _load_demo_module(
        "data-analysis-diagnosis/scripts/demo_topology.py",
        "demo_topology",
    )
    return {
        "metrics": metrics_module.DEMO_METRICS.copy(),
        "topology": topo_module.build_demo_topology(ticket),
    }
