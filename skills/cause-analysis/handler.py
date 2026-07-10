from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

from app.llm.qwen import QwenClient
from app.runtime.skill_types import BaseSkill, SkillContext, SkillResult
from app.trace.scenario_report import checklist_data_gaps

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
        context_module = _load_script_module("build_llm_cause_context.py")

        score_module = _load_script_module("score_cause_dimensions.py")

        diagnosis = context.artifacts.get("data_analysis_diagnosis", {})
        ticket = context.task.get("diagnosis_ticket", {})

        cause_scores = score_module.score_cause_dimensions(diagnosis, task=context.task)

        scenario_report = diagnosis.get("scenario_report") or {}
        checklist_gaps = checklist_data_gaps(scenario_report)

        similar_cases = []
        case_cards: dict[str, Any] = {"matched_count": 0, "high_similarity_count": 0, "cards": []}
        user_experience_refs: list[dict[str, Any]] = []
        if case_service:
            similar_cases = case_service.search_similar(
                problem_type=ticket.get("problem_type", "排队溢出"),
                limit=3,
            )
            case_cards = case_service.search_case_cards(
                problem_type=ticket.get("problem_type", "排队溢出"),
                limit=6,
            )

        experience_library = deps.get("experience_library")
        if experience_library:
            user_experience_refs = experience_library.search_diagnostic(
                inter_id=ticket.get("inter_id"),
                intersection_name=ticket.get("intersection_name"),
                cause_dimension=None,
                keywords=["学校", "接送", "下游", "上游"],
                limit=5,
            )

        evidence_summary = evidence_module.build_evidence(diagnosis)
        llm_context = context_module.build_llm_cause_context(
            diagnosis,
            cause_scores,
            ticket,
            similar_cases,
            user_experience_refs,
            evidence_summary,
        )

        prompt = (
            "请基于下列结构化事实判断主因，并说明历史案例佐证。"
            "数值引用必须与小数口径一致，禁止百分比。\n"
            f"{json.dumps(llm_context, ensure_ascii=False, indent=2)}"
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

        if checklist_gaps:
            merged_gaps = list(dict.fromkeys((llm_result.get("data_gaps") or []) + checklist_gaps))
            llm_result["data_gaps"] = merged_gaps

        cause_ranking = llm_result.get("cause_ranking") or score_module.build_cause_ranking_from_scores(
            cause_scores, diagnosis
        )

        output = {
            "cause_analysis": llm_result,
            "cause_scores": cause_scores,
            "cause_ranking": cause_ranking,
            "similar_cases": similar_cases,
            "case_cards": case_cards,
            "user_experience_refs": user_experience_refs,
            "evidence_summary": evidence_summary,
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
