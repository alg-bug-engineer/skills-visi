from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from app.services.plan_fingerprint import (
    build_metrics_summary,
    build_topology_hash,
)
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

        experience_library = deps.get("experience_library")
        feedback_service = deps.get("feedback_service")
        user_solution_refs: list[dict[str, Any]] = []
        accepted_plan_refs: list[dict[str, Any]] = []
        rejected_plan_avoidance: list[dict[str, Any]] = []

        fingerprint = {
            "problem_type": ticket.get("problem_type"),
            "topology_hash": build_topology_hash(diagnosis.get("topology") or context.task.get("topology")),
            "metrics_summary": build_metrics_summary(diagnosis),
        }
        if experience_library:
            user_solution_refs = experience_library.search_solution(
                inter_id=ticket.get("inter_id"),
                intersection_name=ticket.get("intersection_name"),
                limit=5,
            )
        if feedback_service:
            accepted_plan_refs = feedback_service.search_accepted_plans(
                fingerprint=fingerprint,
                inter_id=ticket.get("inter_id"),
                problem_type=ticket.get("problem_type"),
                limit=3,
            )
            rejected_plan_avoidance = feedback_service.search_rejected_patterns(
                inter_id=ticket.get("inter_id"),
                problem_type=ticket.get("problem_type"),
                limit=5,
            )

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
        optimizer_module = _load_script_module("run_single_point_optimizer.py")

        llm_result = await llm.chat(
            system_prompt=self.load_resource("system"),
            user_prompt=(
                f"策略: {strategy}\n工单: {ticket}\n"
                f"用户方案经验: {user_solution_refs[:2]}\n"
                f"已接受方案: {accepted_plan_refs[:1]}\n"
                f"否决规避: {rejected_plan_avoidance[:2]}"
            ),
            trace_id=context.trace_id,
        )
        if not isinstance(llm_result, dict):
            return SkillResult(
                skill_id=self.meta.skill_id,
                phase=self.meta.phase,
                success=False,
                errors=["方案生成返回非 JSON 结构"],
            )

        candidates, optimizer_engine = candidates_module.build_plan_candidates(
            strategy,
            ticket,
            diagnosis,
            signal=signal_resolved["signal"],
            constraints=signal_resolved.get("constraints") or {},
            generate_timing_plan=timing_module.generate_timing_plan,
            adjust_phase_timing=adjust_module.adjust_phase_timing,
            build_strategy_instruction=adjust_module.build_strategy_instruction,
            validate_plan_guardrails=guardrail_module.validate_plan_guardrails,
            run_single_point_optimizer=optimizer_module.run_single_point_optimizer,
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

        rejected_ids = {item.get("plan_id") for item in rejected_plan_avoidance}
        if recommended_id in rejected_ids or recommended["plan_id"] in rejected_ids:
            recommended["risk_warning"] = "该策略类型曾被专家否决，请谨慎采用"
        for candidate in candidates:
            if candidate.get("plan_id") in rejected_ids:
                candidate["risk_warning"] = "类似策略曾被否决"
            if user_solution_refs:
                candidate["user_experience_basis"] = user_solution_refs[0].get("content")
            if accepted_plan_refs:
                candidate["provenance"] = {
                    "accepted_plan_ref": {
                        "trace_id": accepted_plan_refs[0].get("trace_id"),
                        "plan_id": accepted_plan_refs[0].get("plan_id"),
                    }
                }

        output = {
            "candidates": candidates,
            "recommended": recommended,
            "recommendation": llm_result,
            "all_guardrails_passed": all(c.get("guardrail_pass") for c in candidates),
            "signal_source": signal_resolved.get("source"),
            "optimizer_engine": optimizer_engine,
            "user_solution_refs": user_solution_refs,
            "accepted_plan_refs": accepted_plan_refs,
            "rejected_plan_avoidance": rejected_plan_avoidance,
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
