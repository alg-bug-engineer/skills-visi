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
        action_module = _load_script_module("build_action_package.py")

        cause = context.artifacts.get("cause_analysis", {})
        diagnosis = context.artifacts.get("data_analysis_diagnosis", {})
        ticket = context.task.get("diagnosis_ticket", {})
        user_constraints = ticket.get("constraints") or context.task.get("constraints") or []

        downstream_diag = diagnosis.get("downstream_diagnosis", {})
        arterial = diagnosis.get("arterial_analysis", {})
        road_hint = ""
        for issue in (diagnosis.get("scenario_report") or {}).get("issues") or []:
            if isinstance(issue, dict) and issue.get("item_id") == "adjacent_spacing":
                road_hint = str(issue.get("summary") or "")
                break

        prompt = (
            f"成因分析: {cause.get('cause_analysis', {})}\n"
            f"溢出机制: {diagnosis.get('overflow_mechanism') or cause.get('overflow_mechanism')}\n"
            f"下游状态: {diagnosis.get('downstream_state')}\n"
            f"确定性成因评分: {cause.get('cause_scores', {})}\n"
            f"瓶颈: {diagnosis.get('bottleneck_analysis', {})}\n"
            f"下游判断: {downstream_diag.get('release_answer')} — {downstream_diag.get('narrative')}\n"
            f"干线分析: {arterial.get('summary')}\n"
            f"道路等级线索: {road_hint or '未提供'}\n"
            f"下游治理: {diagnosis.get('downstream_trace', {}).get('governance', {})}\n"
            f"治理对象: {ticket.get('intersection_name')}（{ticket.get('inter_id')}），"
            f"{ticket.get('direction', '')}{ticket.get('movement', '')}\n"
            f"用户约束: {user_constraints}\n"
            "请生成分层策略：①即刻可做动作（现场/检测/渠化/秩序）；"
            "②门控通过后拟实施配时（写清秒数与借绿来源）；"
            "③按道路等级给出非信控亮点建议。硬约束写成红线，但不能用红线替代动作。"
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
        profile["strategy"]["target_intersection"] = {
            "inter_id": ticket.get("inter_id"),
            "inter_name": ticket.get("intersection_name"),
            "direction": ticket.get("direction"),
            "movement": ticket.get("movement"),
        }
        profile["strategy"]["user_constraints"] = (
            user_constraints if isinstance(user_constraints, list) else [user_constraints]
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
        if profile.get("decision"):
            output["decision"] = profile["decision"]
            output["decision_mode"] = profile.get("decision_mode")

        action_package = action_module.build_action_package(
            diagnosis=diagnosis,
            strategy=output,
            ticket=ticket,
        )
        output["action_package"] = action_package
        output["strategy"]["recommended"] = action_module.merge_action_texts_into_recommended(
            output["strategy"].get("recommended") or [],
            action_package,
        )
        output["strategy"]["action_package"] = action_package

        logger.info(
            "策略生成完成 trace_id=%s package=%s decision_mode=%s",
            context.trace_id,
            output["strategy_package"],
            output.get("decision_mode"),
        )
        return SkillResult(
            skill_id=self.meta.skill_id,
            phase=self.meta.phase,
            success=True,
            output=output,
        )
