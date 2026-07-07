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


class CauseAnalysisSkill(BaseSkill):
    async def run(self, context: SkillContext, **deps: Any) -> SkillResult:
        llm: QwenClient = deps["llm"]
        case_service = deps.get("case_service")
        evidence_module = _load_script_module("build_evidence.py")

        diagnosis = context.artifacts.get("data_analysis_diagnosis", {})
        ticket = context.task.get("diagnosis_ticket", {})

        similar_cases = []
        if case_service:
            similar_cases = case_service.search_similar(
                problem_type=ticket.get("problem_type", "排队溢出"),
                limit=3,
            )

        prompt = (
            f"诊断工单: {ticket}\n"
            f"指标分析: {diagnosis}\n"
            f"相似案例: {similar_cases[:2]}\n"
            "请结合指标判断主因，并说明历史案例佐证。"
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
                errors=["成因分析返回非 JSON 结构"],
            )

        cause_ranking = llm_result.get("cause_ranking") or evidence_module.default_cause_ranking(
            diagnosis, llm_result
        )
        output = {
            "cause_analysis": llm_result,
            "cause_ranking": cause_ranking,
            "similar_cases": similar_cases,
            "evidence_summary": evidence_module.build_evidence(diagnosis),
            "arterial_coordination_needed": evidence_module.needs_arterial_coordination(diagnosis),
        }
        logger.info(
            "成因分析完成 trace_id=%s primary_cause=%s similar_cases=%d",
            context.trace_id,
            llm_result.get("primary_cause"),
            len(similar_cases),
        )
        return SkillResult(
            skill_id=self.meta.skill_id,
            phase=self.meta.phase,
            success=True,
            output=output,
        )
