from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.data.load_signal_plan import resolve_signal_plan
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
        settings: Settings = deps.get("settings") or get_settings()
        llm: QwenClient = deps["llm"]

        strategy = context.artifacts.get("strategy_generation", {})
        ticket = context.task.get("diagnosis_ticket", {})
        diagnosis = context.artifacts.get("data_analysis_diagnosis", {})

        signal_resolved = resolve_signal_plan(context.task, ticket, settings)
        if not signal_resolved.get("ok"):
            return SkillResult(
                skill_id=self.meta.skill_id,
                phase=self.meta.phase,
                success=False,
                output={
                    "available": False,
                    "reason": signal_resolved.get("reason"),
                    "source": signal_resolved.get("source"),
                },
                errors=[str(signal_resolved.get("reason"))],
            )

        candidates_module = _load_script_module("build_candidates.py")
        timing_module = _load_script_module("generate_timing_plan.py")
        adjust_module = _load_script_module("adjust_phase_timing.py")
        guardrail_module = _load_script_module("validate_plan_guardrails.py")

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

        candidates = candidates_module.build_plan_candidates(
            strategy,
            ticket,
            diagnosis,
            signal=signal_resolved["signal"],
            constraints=signal_resolved.get("constraints") or {},
            generate_timing_plan=timing_module.generate_timing_plan,
            adjust_phase_timing=adjust_module.adjust_phase_timing,
            build_strategy_instruction=adjust_module.build_strategy_instruction,
            validate_plan_guardrails=guardrail_module.validate_plan_guardrails,
        )

        valid_candidates = [c for c in candidates if c.get("guardrail_pass")]
        if not valid_candidates:
            return SkillResult(
                skill_id=self.meta.skill_id,
                phase=self.meta.phase,
                success=False,
                output={
                    "candidates": candidates,
                    "all_guardrails_passed": False,
                    "signal_source": signal_resolved.get("source"),
                },
                errors=["所有候选方案未通过护栏校验"],
            )

        recommended_id = llm_result.get("recommended_plan_id") or strategy.get(
            "strategy_package", "arterial_coordination"
        )
        recommended = next(
            (c for c in valid_candidates if c["plan_id"] == recommended_id),
            valid_candidates[-1],
        )

        output = {
            "candidates": candidates,
            "recommended": recommended,
            "recommendation": llm_result,
            "all_guardrails_passed": all(c.get("guardrail_pass") for c in candidates),
            "signal_source": signal_resolved.get("source"),
            "rollback_conditions": [
                recommended.get("rollback_condition"),
                "下游排队比持续上升",
                "上游排队超过安全边界",
                "目标方向绿灯利用率异常下降",
            ],
        }
        logger.info(
            "方案生成完成 trace_id=%s recommended=%s valid=%d/%d",
            context.trace_id,
            recommended["plan_id"],
            len(valid_candidates),
            len(candidates),
        )
        return SkillResult(
            skill_id=self.meta.skill_id,
            phase=self.meta.phase,
            success=True,
            output=output,
        )
