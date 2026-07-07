from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.data.diagnosis_input import resolve_diagnosis_inputs
from app.runtime.skill_types import BaseSkill, SkillContext, SkillResult
from app.trace.scenario_report import build_scenario_report

logger = logging.getLogger(__name__)


def _load_script_module(script_name: str):
    script_path = Path(__file__).resolve().parent / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(script_name.replace(".py", ""), script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载脚本: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DataAnalysisDiagnosisSkill(BaseSkill):
    async def run(self, context: SkillContext, **deps: Any) -> SkillResult:
        settings: Settings = deps.get("settings") or get_settings()
        ticket = context.task.get("diagnosis_ticket", {})
        spatial = context.task.get("spatial_objects") or context.artifacts.get(
            "intent_understanding", {}
        ).get("spatial_objects", {})

        resolved = resolve_diagnosis_inputs(context.task, settings, ticket=ticket)
        if not resolved.get("ok"):
            logger.warning(
                "诊断数据不可用 trace_id=%s reason=%s",
                context.trace_id,
                resolved.get("reason"),
            )
            return SkillResult(
                skill_id=self.meta.skill_id,
                phase=self.meta.phase,
                success=False,
                output={
                    "available": False,
                    "source": resolved.get("source", "none"),
                    "reason": resolved.get("reason"),
                },
                errors=[str(resolved.get("reason"))],
            )

        metrics_input = resolved["metrics"]
        topology = resolved["topology"]
        data_source = resolved.get("source", "unknown")

        analyze_module = _load_script_module("analyze_overflow.py")
        output = analyze_module.analyze_overflow(
            metrics_input,
            ticket,
            topology=topology,
            spatial_objects=spatial,
            pg_raw=context.task.get("pg_raw") or {},
            signal=context.task.get("signal") or {},
            scope=context.task.get("scope") or {},
        )
        output["scenario_report"] = build_scenario_report(
            context.task.get("checklist_queries"),
            output.get("metrics"),
            ticket=ticket,
        )
        output["topology"] = topology
        output["data_source"] = data_source
        if data_source == "mock":
            output["source"] = "mock"

        logger.info(
            "数据分析完成 trace_id=%s source=%s queue_ratio=%s downstream=%s flow_trace=%s",
            context.trace_id,
            data_source,
            output["metrics"]["queue_ratio"],
            output["downstream_trace"].get("available"),
            output["flow_trace"].get("available"),
        )
        return SkillResult(
            skill_id=self.meta.skill_id,
            phase=self.meta.phase,
            success=True,
            output=output,
        )
