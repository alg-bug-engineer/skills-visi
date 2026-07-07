"""Resolve current signal plan from task injection or fixture registry."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)

FIXTURES_ROOT = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"


def resolve_signal_plan(
    task: dict[str, Any],
    ticket: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    """Return signal plan with explicit source; never silent invent."""
    injected = task.get("signal")
    if isinstance(injected, dict) and injected.get("phase_stage_timing_list"):
        return {
            "ok": True,
            "signal": injected,
            "source": "task_injection",
            "constraints": _merge_constraints(task, injected),
        }

    inter_id = ticket.get("inter_id") or task.get("inter_id")
    if inter_id:
        fixture = FIXTURES_ROOT / f"signal_plan_{inter_id}.json"
        if fixture.exists():
            signal = json.loads(fixture.read_text(encoding="utf-8"))
            return {
                "ok": True,
                "signal": signal,
                "source": "fixture_registry",
                "constraints": _merge_constraints(task, signal),
            }

    if settings.allow_demo_fallback:
        fallback = FIXTURES_ROOT / "signal_plan_demo_wenhua_shunhua.json"
        if fallback.exists():
            signal = json.loads(fallback.read_text(encoding="utf-8"))
            logger.warning("使用 signal fixture source=mock inter_id=%s", signal.get("inter_id"))
            return {
                "ok": True,
                "signal": signal,
                "source": "mock",
                "constraints": _merge_constraints(task, signal),
            }

    return {
        "ok": False,
        "source": "none",
        "reason": "缺少 task.signal 或 inter_id 对应配时 fixture；生产环境请注入现状配时。",
    }


def _merge_constraints(task: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
    task_constraints = task.get("constraints") if isinstance(task.get("constraints"), dict) else {}
    return {
        "max_cycle_s": task_constraints.get("max_cycle_s") or signal.get("max_cycle_s"),
        "default_cycle_s": signal.get("current_cycle_s"),
    }
