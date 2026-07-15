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
        overflow_plan_module = _load_script_module("validate_overflow_plan.py")
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

        constraints = dict(signal_resolved.get("constraints") or {})
        # 策略硬约束与配时约束取更严上限（需求 34 E7：策略 180 必须进入护栏）
        strat_body = strategy.get("strategy") if isinstance(strategy.get("strategy"), dict) else strategy
        quant = (
            (strat_body or {}).get("quantitative_constraints")
            if isinstance(strat_body, dict)
            else None
        )
        if isinstance(quant, dict) and quant.get("max_cycle_s") is not None:
            try:
                qmax = float(quant["max_cycle_s"])
                existing = constraints.get("max_cycle_s")
                if existing is None:
                    constraints["max_cycle_s"] = qmax
                else:
                    constraints["max_cycle_s"] = min(float(existing), qmax)
            except (TypeError, ValueError):
                pass

        # 诊断与方案配时基线一致性（需求 34 G5）
        diag_cycle = (diagnosis.get("timing_profile") or {}).get("cycle_s")
        sig_cycle = (signal_resolved.get("signal") or {}).get("current_cycle_s")
        try:
            if diag_cycle is not None and sig_cycle is not None:
                if abs(float(diag_cycle) - float(sig_cycle)) > 2.0:
                    return SkillResult(
                        skill_id=self.meta.skill_id,
                        phase=self.meta.phase,
                        success=False,
                        output={
                            "available": False,
                            "reason": "signal_plan_snapshot_drift",
                            "diagnosis_cycle_s": diag_cycle,
                            "signal_cycle_s": sig_cycle,
                            "all_guardrails_passed": False,
                            "signal_source": signal_resolved.get("source"),
                        },
                        errors=[
                            f"配时基线不一致：诊断周期 {diag_cycle}s 与方案快照 {sig_cycle}s 偏差超过容差"
                        ],
                    )
        except (TypeError, ValueError):
            pass

        candidates, optimizer_engine = candidates_module.build_plan_candidates(
            strategy,
            ticket,
            diagnosis,
            signal=signal_resolved["signal"],
            constraints=constraints,
            generate_timing_plan=timing_module.generate_timing_plan,
            adjust_phase_timing=adjust_module.adjust_phase_timing,
            build_strategy_instruction=adjust_module.build_strategy_instruction,
            validate_plan_guardrails=guardrail_module.validate_plan_guardrails,
            run_single_point_optimizer=optimizer_module.run_single_point_optimizer,
            validate_overflow_plan=overflow_plan_module.validate_overflow_plan,
            build_plan_contract=overflow_plan_module.build_plan_contract_from_strategy,
            pg_raw=context.task.get("pg_raw") if isinstance(context.task.get("pg_raw"), dict) else None,
            day_of_week=(
                (context.task.get("context") or {}).get("day_of_week")
                or context.task.get("day_of_week")
            ),
        )

        valid_candidates = [c for c in candidates if c.get("guardrail_pass")]
        has_feasible_candidate = bool(valid_candidates)
        all_candidates_passed = bool(candidates) and all(c.get("guardrail_pass") for c in candidates)
        if not valid_candidates:
            return SkillResult(
                skill_id=self.meta.skill_id,
                phase=self.meta.phase,
                success=False,
                output={
                    "candidates": candidates,
                    "recommended_plan_id": None,
                    "all_guardrails_passed": False,
                    "has_feasible_candidate": False,
                    "all_candidates_passed": False,
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
            "recommended_plan_id": recommended["plan_id"],
            "recommendation": llm_result,
            "all_guardrails_passed": all_candidates_passed,
            "has_feasible_candidate": has_feasible_candidate,
            "all_candidates_passed": all_candidates_passed,
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
