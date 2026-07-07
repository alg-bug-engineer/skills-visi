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
    if isinstance(injected, dict):
        if injected.get("stage_detail") and not injected.get("phase_stage_timing_list"):
            injected = _normalize_pg_signal(injected)
        if injected.get("phase_stage_timing_list") or injected.get("phasePlanOfTimeList"):
            return {
                "ok": True,
                "signal": injected,
                "source": task.get("signal_source") or "task_injection",
                "constraints": _merge_constraints(task, injected),
            }

    inter_id = ticket.get("inter_id") or task.get("inter_id")
    if inter_id and settings.allow_demo_fallback:
        fixture = FIXTURES_ROOT / f"signal_plan_{inter_id}.json"
        if fixture.exists():
            signal = json.loads(fixture.read_text(encoding="utf-8"))
            logger.warning("使用 signal fixture source=fixture_registry inter_id=%s", inter_id)
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


def _normalize_pg_signal(signal: dict[str, Any]) -> dict[str, Any]:
    if signal.get("phase_stage_timing_list"):
        return signal
    stages = []
    for row in signal.get("stage_detail") or []:
        green = int(row.get("green_sec") or row.get("greenTime") or 0)
        stages.append(
            {
                "phase_stage_id": str(row.get("stage_no") or row.get("phase_stage_id") or ""),
                "phase_stage_name": row.get("release_movements") or row.get("phase_stage_name") or "",
                "greenTime": green,
                "yellowTime": int(row.get("yellow_sec") or row.get("yellowTime") or 3),
                "allRedTime": int(row.get("all_red_sec") or row.get("allRedTime") or 2),
                "minGreenTime": int(row.get("min_green_sec") or row.get("minGreenTime") or 15),
                "maxGreenTime": int(row.get("max_green_sec") or row.get("maxGreenTime") or green + 30),
                "movement_key": row.get("release_movements") or row.get("movement_key"),
            }
        )
    normalized = dict(signal)
    normalized["phase_stage_timing_list"] = stages
    return normalized
