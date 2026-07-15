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

MECHANISM_CAUSE_LABEL: dict[str, str] = {
    "downstream_blocked": "下游回堵",
    "local_release_insufficient": "本路口放行不足",
    "discharge_anomaly": "放行效率异常，待核验",
    "upstream_arrival_shock": "上游冲击",
    "evidence_insufficient": "证据不足，待补盲",
}


def _align_cause_with_mechanism(
    llm_result: dict[str, Any],
    *,
    overflow_mechanism: dict[str, Any],
    diagnosis: dict[str, Any],
    cause_scores: dict[str, Any],
    score_module: Any,
) -> list[dict[str, Any]]:
    """机制锁定时统一主因 ranking 与 narrative，避免 LLM 输出「信号控制不当」等与主链矛盾。"""
    code = str(overflow_mechanism.get("primary") or "")
    label = MECHANISM_CAUSE_LABEL.get(code, code)
    llm_result["primary_cause"] = label

    ranked = score_module.build_cause_ranking_from_scores(cause_scores, diagnosis)
    secondary = next((item for item in ranked if item.get("role") != "主因"), None)
    cause_ranking = [{"rank": 1, "role": "主因", "cause": label}]
    if secondary:
        cause_ranking.append(
            {
                "rank": 2,
                "role": secondary.get("role") or "次因",
                "cause": secondary.get("cause") or "交通需求压力",
            }
        )
    for idx, item in enumerate(ranked[2:4], start=3):
        cause_ranking.append(
            {
                "rank": idx,
                "role": item.get("role") or "诱因",
                "cause": item.get("cause") or "",
            }
        )

    direct = (diagnosis.get("downstream_state") or {}).get("direct_downstream_inter_name") or "直接下游"
    tm = diagnosis.get("metrics") or {}
    q = tm.get("queue_ratio")
    u = tm.get("green_utilization")
    q_text = f"{q:.4f}" if isinstance(q, (int, float)) else "—"
    u_text = f"{u:.4f}" if isinstance(u, (int, float)) else "—"
    if code == "discharge_anomaly":
        llm_result["narrative"] = (
            f"溢出机制为{label}：排队比 {q_text} 与绿灯利用率 {u_text} 呈高排队低放行特征。"
            f"直接下游 {direct} 初步有余量，需先完成出口/检测/绿灯末端队列核验，不宜在未核验前加绿。"
        )
    gaps = llm_result.get("data_gaps") or []
    llm_result["data_gaps"] = [
        str(g).replace("奥体西路与解放东路路口", direct) for g in gaps if g
    ]
    return cause_ranking


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
            query_profile = case_service.build_query_profile(ticket, diagnosis)
            similar_cases = case_service.search_similar(
                problem_type=ticket.get("problem_type", "排队溢出"),
                query_profile=query_profile,
                limit=3,
            )
            case_cards = case_service.search_case_cards(
                problem_type=ticket.get("problem_type", "排队溢出"),
                query_profile=query_profile,
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

        # 需求 35：确定性溢出机制已由诊断给出时，LLM 只解释，不得改写机制编码
        overflow_mechanism = diagnosis.get("overflow_mechanism") or {}
        if overflow_mechanism.get("primary"):
            llm_context["overflow_mechanism"] = overflow_mechanism
            llm_context["downstream_state"] = diagnosis.get("downstream_state")
            prompt = (
                "下列结构化事实中的 overflow_mechanism.primary 与 downstream_state.decision "
                "为确定性结论，禁止修改编码或下游状态。"
                "请解释支持证据、反证、缺失证据，并生成核验任务；"
                "primary_cause 须与机制含义一致，不得另立互相矛盾的主因。"
                "数值引用必须与小数口径一致，禁止百分比。\n"
                f"{json.dumps(llm_context, ensure_ascii=False, indent=2)}"
            )
        else:
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

        # 冻结机制：输出带回诊断机制，LLM 不得覆盖
        if overflow_mechanism.get("primary"):
            llm_result["overflow_mechanism"] = overflow_mechanism
            llm_result["mechanism_locked"] = True
            cause_ranking = _align_cause_with_mechanism(
                llm_result,
                overflow_mechanism=overflow_mechanism,
                diagnosis=diagnosis,
                cause_scores=cause_scores,
                score_module=score_module,
            )
        else:
            cause_ranking = llm_result.get("cause_ranking") or score_module.build_cause_ranking_from_scores(
                cause_scores, diagnosis
            )
            # 清洗明显与 slack 冲突的「下游接不住」主因表述
            primary_cause = str(llm_result.get("primary_cause") or "")
            ds = (diagnosis.get("downstream_state") or {}).get("decision")
            if ds == "slack" and ("接不住" in primary_cause or "承接不足" in primary_cause):
                llm_result["primary_cause"] = "放行效率异常，待核验"
                llm_result["primary_cause_overridden"] = True

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
        if overflow_mechanism.get("primary"):
            output["overflow_mechanism"] = overflow_mechanism
        logger.info(
            "成因分析完成 trace_id=%s primary_cause=%s mechanism=%s similar_cases=%d",
            context.trace_id,
            llm_result.get("primary_cause"),
            (overflow_mechanism or {}).get("primary"),
            len(similar_cases),
        )
        return SkillResult(
            skill_id=self.meta.skill_id,
            phase=self.meta.phase,
            success=True,
            output=output,
        )
