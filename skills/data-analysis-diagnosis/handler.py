from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from app.runtime.skill_types import BaseSkill, SkillContext, SkillResult

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
        ticket = context.task.get("diagnosis_ticket", {})
        spatial = context.task.get("spatial_objects") or context.artifacts.get(
            "intent_understanding", {}
        ).get("spatial_objects", {})

        demo_module = _load_script_module("demo_metrics.py")
        topo_module = _load_script_module("demo_topology.py")
        metrics_input = context.task.get("metrics") or demo_module.DEMO_METRICS.copy()
        topology = context.task.get("topology") or topo_module.build_demo_topology(ticket)

        analyze_module = _load_script_module("analyze_overflow.py")
        output = analyze_module.analyze_overflow(
            metrics_input,
            ticket,
            topology=topology,
            spatial_objects=spatial,
        )

        logger.info(
            "数据分析完成 trace_id=%s queue_ratio=%s downstream=%s flow_trace=%s",
            context.trace_id,
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
