from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from app.llm.qwen import QwenClient
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


class PlanGenerationSkill(BaseSkill):
    async def run(self, context: SkillContext, **deps: Any) -> SkillResult:
        llm: QwenClient = deps["llm"]
        candidates_module = _load_script_module("build_candidates.py")

        strategy = context.artifacts.get("strategy_generation", {})
        ticket = context.task.get("diagnosis_ticket", {})
        diagnosis = context.artifacts.get("data_analysis_diagnosis", {})

        llm_result = await llm.chat(
            system_prompt=self.load_resource("system"),
            user_prompt=f"策略: {strategy}\n工单: {ticket}",
            trace_id=context.trace_id,
        )
        if not isinstance(llm_result, dict):
            return SkillResult(
                skill_id=self.meta.skill_id,
                phase=self.meta.phase,
                success=False,
                errors=["方案生成返回非 JSON 结构"],
            )

        candidates = candidates_module.build_plan_candidates(strategy, ticket, diagnosis)
        recommended_id = llm_result.get("recommended_plan_id") or strategy.get(
            "strategy_package", "arterial_coordination"
        )
        recommended = next(
            (c for c in candidates if c["plan_id"] == recommended_id),
            candidates[-1],
        )

        output = {
            "candidates": candidates,
            "recommended": recommended,
            "recommendation": llm_result,
            "rollback_conditions": [
                "下游排队比持续上升",
                "上游排队超过安全边界",
                "目标方向绿灯利用率异常下降",
            ],
        }
        logger.info(
            "方案生成完成 trace_id=%s recommended=%s candidates=%d",
            context.trace_id,
            recommended_id,
            len(candidates),
        )
        return SkillResult(
            skill_id=self.meta.skill_id,
            phase=self.meta.phase,
            success=True,
            output=output,
        )
