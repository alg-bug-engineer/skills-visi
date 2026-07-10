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


class StrategyGenerationSkill(BaseSkill):
    async def run(self, context: SkillContext, **deps: Any) -> SkillResult:
        llm: QwenClient = deps["llm"]
        profile_module = _load_script_module("build_strategy_profile.py")
        scope_module = _load_script_module("build_control_scope.py")
        package_module = _load_script_module("select_package.py")
        contrast_module = _load_script_module("build_experience_contrast.py")

        cause = context.artifacts.get("cause_analysis", {})
        diagnosis = context.artifacts.get("data_analysis_diagnosis", {})
        ticket = context.task.get("diagnosis_ticket", {})

        downstream_diag = diagnosis.get("downstream_diagnosis", {})
        arterial = diagnosis.get("arterial_analysis", {})

        prompt = (
            f"成因分析: {cause.get('cause_analysis', {})}\n"
            f"确定性成因评分: {cause.get('cause_scores', {})}\n"
            f"瓶颈: {diagnosis.get('bottleneck_analysis', {})}\n"
            f"下游判断: {downstream_diag.get('release_answer')} — {downstream_diag.get('narrative')}\n"
            f"干线分析: {arterial.get('summary')}\n"
            f"下游治理: {diagnosis.get('downstream_trace', {}).get('governance', {})}\n"
            f"约束: {context.task.get('diagnosis_ticket', {}).get('constraints', [])}\n"
            "请生成防溢流优先的治理策略，说明为何不推荐单点激进加绿。"
        )
        llm_result = await llm.chat(
            system_prompt=self.load_resource("system"),
            user_prompt=prompt,
            trace_id=context.trace_id,
        )
        if not isinstance(llm_result, dict):
            return SkillResult(
                skill_id=self.meta.skill_id,
                phase=self.meta.phase,
                success=False,
                errors=["策略生成返回非 JSON 结构"],
            )

        signal = context.task.get("signal") if isinstance(context.task.get("signal"), dict) else {}
        constraints = (
            context.task.get("constraints") if isinstance(context.task.get("constraints"), dict) else {}
        )
        profile = profile_module.build_strategy_profile(
            cause, diagnosis, llm_result, signal=signal, constraints=constraints
        )
        output = {
            "strategy": profile["strategy"],
            "strategy_package": profile["strategy_package"],
            "package_scores": profile["package_scores"],
            "strategy_instruction": profile["strategy_instruction"],
            "case_references": package_module.extract_case_lessons(cause),
            "reference_basis": package_module.build_reference_basis(
                cause, ticket, strategy_package=profile["strategy_package"]
            ),
            "control_scope_map": scope_module.build_control_scope_map(diagnosis, ticket),
            "experience_contrast": contrast_module.build_experience_contrast(
                cause=cause,
                diagnosis=diagnosis,
                strategy={
                    "strategy_package": profile["strategy_package"],
                    "package_scores": profile["package_scores"],
                    "strategy": profile["strategy"],
                },
                ticket=ticket,
            ),
        }
        logger.info(
            "策略生成完成 trace_id=%s package=%s",
            context.trace_id,
            output["strategy_package"],
        )
        return SkillResult(
            skill_id=self.meta.skill_id,
            phase=self.meta.phase,
            success=True,
            output=output,
        )
