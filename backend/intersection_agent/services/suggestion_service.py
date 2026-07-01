"""Generate governance suggestions."""

from __future__ import annotations

import logging
from typing import Any

from intersection_agent.llm.qwen_client import QwenClient
from intersection_agent.models.domain import SuggestionResult
from intersection_agent.services.governance_guidance import format_category_guidance_block
from intersection_agent.services.governance_action_plan_service import format_action_plan_for_prompt
from intersection_agent.logging.helpers import log_event, safe_preview
from intersection_agent.services.suggestion_context import (
    compose_suggestion_narrative,
    format_upstream_trace_for_prompt,
    format_user_experience_for_prompt,
    narrative_echoes_diagnosis,
    prepare_suggestion_data,
)
from intersection_agent.utils.problem_type_narrative import format_suggestion_problem_type_guidance

logger = logging.getLogger(__name__)

NARRATIVE_PROMPT = """
你是交通信号优化专家。请深度融合「用户经验 + 同类案例 + 上游流量溯源」三源信息，结合诊断结果与四维信控分析，生成一段有理有据、可行可落地的治理建议（不超过220字，中文）。

## 诊断上下文
- 路口：{intersection}
- 时段：{time_label}
- 规则结论：{conclusion}
- 流量-配时匹配：{flow_timing_match}
- 四维问题摘要：{focus_problems}
- 分维度治理方向（已由专业规则判定，必须作为建议依据）：
{category_guidance}
- 结构化动作方案（数据推导，秒数与转向不可改写）：
{action_plan_block}
- 用户约束或建议：{user_suggestion}
- 量化约束：{quantitative_constraints}
- 同类场景专家治理经验（来自经验库，仅供表述与方向参考，不可改写量化动作）：
{case_experience}
- 上游流量溯源（必须体现具体路口名、治理落点与汇入转向）：
{upstream_trace}
- 用户经验与约束（必须优先回应，不得忽略）：
{user_experience}

## 四类问题治理建议参考（须结合数据与主问题类型选用，不可生搬硬套）
{problem_type_guidance}

## 专业原则（必须遵守）
1. 若绿灯利用率已偏高或存在空放/失衡，禁止简单建议「一律加绿灯」；应优先绿信比再分配、压缩空放相位。
2. 若各转向普遍过饱和（能力瓶颈），应指出单点加绿空间有限，给出周期/协调/渠化/控流等出路。
3. 溢出风险时优先防锁死与上游控流，不单靠加绿。
4. 用户约束不为「无」时，正文必须优先回应；量化约束不为「无」时说明边界内方案。
5. 结构化动作方案中的秒数、供绿/受绿转向、动作类型为硬约束，只可润色表述，禁止另起炉灶。
6. 有上游溯源时，必须点名至少一个上游路口及治理落点，说明与本路口问题的关联；禁止泛泛而谈。
7. 禁止输出与数据矛盾的加绿建议（如向已过饱和方向继续加绿）。
8. 禁止复述 primary_diagnosis 的 headline 句式；正文须是 action_plan 的可执行措施与边界说明。
9. 必须深度融合三源信息：用户经验（要回应并采纳/校正）、同类案例（借鉴其治理思路与适用条件）、上游溯源（点名上游落点）。融合后须让建议体现「依据来源」——即每条核心举措能对应到来自用户经验、同类案例或上游溯源中的哪一源，做到有理有据、可信可落地。

参考量化幅度（与结构化方案一致时直接沿用）：{direction_text}绿灯约 {delta} 秒。

只输出建议正文，不要标题。
""".strip()


class SuggestionService:
    """Compute delta and generate narrative via Qwen."""

    def __init__(self, llm: QwenClient | None = None) -> None:
        self._llm = llm or QwenClient()

    async def generate(
        self,
        rule: dict[str, Any],
        data: dict[str, Any],
        *,
        user_suggestion: str | None = None,
        quantitative_constraints: dict[str, Any] | None = None,
        delta_override: int | None = None,
        direction_override: str | None = None,
        case_experience: str | None = None,
    ) -> SuggestionResult:
        """Build suggestion from matched rule."""
        data = prepare_suggestion_data(data)
        action = rule["action"]
        formula = action["formula"]
        delta = (
            delta_override
            if delta_override is not None
            else evaluate_formula(formula, data)
        )
        direction = direction_override or action.get("direction", "increase")

        meta = data.get("meta", {})
        tf = data.get("traffic_flow", {})
        sp = data.get("signal_plan", {})
        ev = data.get("evaluation", {})

        direction_text = "增加" if direction == "increase" else "减少"
        if direction == "reallocate":
            direction_text = "挪绿"
        tp = meta.get("time_period", {})
        delay_index = ev.get("delay_index") or data.get("congestion_index", {}).get(
            "delay_index", 0
        )
        governance = data.get("flow_timing_governance") or {}
        action_plan = governance.get("action_plan") or {}
        focus_problems = "、".join(
            p.get("label", "")
            for p in governance.get("problems", [])
            if p.get("detected")
        ) or "无显著异常"
        category_guidance = format_category_guidance_block(data)
        action_plan_block = format_action_plan_for_prompt(action_plan)
        composed = compose_suggestion_narrative(
            data,
            user_suggestion=user_suggestion,
            quantitative_constraints=quantitative_constraints,
        )
        upstream_trace_text = format_upstream_trace_for_prompt(data)
        user_experience_text = format_user_experience_for_prompt(data, user_suggestion)
        problem_type_guidance = format_suggestion_problem_type_guidance(data)
        prompt = NARRATIVE_PROMPT.format(
            intersection=meta.get("intersection", ""),
            time_label=tp.get("label", ""),
            conclusion=rule.get("conclusion", ""),
            direction_text=direction_text,
            delta=delta,
            flow_timing_match=governance.get("match_narrative") or "待评估",
            focus_problems=focus_problems,
            category_guidance=category_guidance,
            action_plan_block=action_plan_block,
            user_suggestion=user_suggestion or "无",
            quantitative_constraints=(
                quantitative_constraints.get("narrative")
                if quantitative_constraints
                else "无"
            ),
            case_experience=case_experience or "无同类场景经验。",
            upstream_trace=upstream_trace_text,
            user_experience=user_experience_text,
            problem_type_guidance=problem_type_guidance,
        )

        log_event(
            logger,
            logging.INFO,
            "suggestion.prepare",
            rule_id=rule.get("id"),
            action_type=action_plan.get("action_type"),
            action_plan_headline=action_plan.get("headline"),
            composed_narrative=composed,
            upstream_trace=upstream_trace_text,
            user_experience=user_experience_text,
            case_experience=case_experience,
            prompt_preview=prompt,
        )

        narrative = composed
        try:
            llm_text = await self._llm.chat(system="你是交通信号优化专家。", user=prompt)
            llm_text = (llm_text or "").strip()
            if llm_text and not narrative_echoes_diagnosis(llm_text, data):
                narrative = llm_text
            else:
                log_event(
                    logger,
                    logging.INFO,
                    "suggestion.llm_skipped",
                    reason="echoes_diagnosis_or_empty",
                    llm_preview=llm_text,
                )
        except RuntimeError as exc:
            log_event(
                logger,
                logging.WARNING,
                "suggestion.llm_failed",
                error=str(exc),
                fallback=composed,
            )
            narrative = self._fallback_narrative(
                rule,
                data,
                direction_text=direction_text,
                delta=delta,
                user_suggestion=user_suggestion,
            )
            if narrative_echoes_diagnosis(narrative, data):
                narrative = composed

        log_event(
            logger,
            logging.INFO,
            "suggestion.result",
            rule_id=rule.get("id"),
            narrative=narrative,
            delta_seconds=delta,
            direction=direction,
        )

        return SuggestionResult(
            delta_seconds=delta,
            direction=direction,
            narrative=narrative.strip(),
            confidence=float(action_plan.get("confidence") or rule.get("confidence", 0.7)),
            rule_id=str(rule.get("id", "")),
            action_type=str(action_plan.get("action_type") or action.get("type", "green_light_adjustment")),
            action_plan=action_plan or None,
        )

    @staticmethod
    def _fallback_narrative(
        rule: dict[str, Any],
        data: dict[str, Any],
        *,
        direction_text: str,
        delta: int,
        user_suggestion: str | None,
    ) -> str:
        governance = data.get("flow_timing_governance") or {}
        action_plan = governance.get("action_plan") or {}
        if action_plan.get("narrative_template"):
            base = str(action_plan["narrative_template"])
            suffix = f"同时结合用户约束：{user_suggestion}。" if user_suggestion else ""
            return f"{base}{suffix}"

        composed = compose_suggestion_narrative(
            data,
            user_suggestion=user_suggestion,
            quantitative_constraints=data.get("quantitative_constraints"),
        )
        if composed:
            return composed

        primary = governance.get("primary_diagnosis") or {}
        lever = str(primary.get("lever") or "").strip()
        if lever:
            base = lever
        else:
            detected = [
                p.get("governance", "")
                for p in governance.get("problems", [])
                if p.get("detected") and p.get("governance")
            ]
            base = detected[0] if detected else str(rule.get("conclusion", ""))
        suffix = f"同时结合用户约束：{user_suggestion}。" if user_suggestion else ""
        primary_type = str(primary.get("type") or "")
        if primary_type == "capacity_bottleneck":
            return f"{base}{suffix}"
        if primary_type == "timing_optimizable":
            return f"{base}可参考{direction_text}绿灯约{delta}秒。{suffix}"
        return f"{base}，建议{direction_text}主要方向绿灯 {delta} 秒。{suffix}"

    @staticmethod
    def build_measure_line(
        suggestion: SuggestionResult,
        flow_timing_governance: dict[str, Any] | None = None,
    ) -> str:
        """量化治理措施核心句（不含「📋 参考措施：」前缀）。

        以 action_plan（数据/规则推导）为准生成具体动作，取代仅暴露
        ``min(...)`` 公式的旧表述。供诊断消息与 skill 固化共用。
        """
        primary = (flow_timing_governance or {}).get("primary_diagnosis") or {}
        action_plan = (flow_timing_governance or {}).get("action_plan") or {}
        primary_type = str(primary.get("type") or "")
        sign = "+" if suggestion.direction == "increase" else "-"
        plan_type = str(action_plan.get("action_type") or "")
        if plan_type == "reallocate_green" and suggestion.delta_seconds:
            donor = (action_plan.get("donor_turn") or {}).get("label", "低利用转向")
            recipient = (action_plan.get("recipient_turn") or {}).get("label", "主饱和转向")
            return (
                f"从**{donor}**向**{recipient}**挪绿约 "
                f"**{suggestion.delta_seconds} 秒**（周期不变）"
            )
        if plan_type == "increase_green" and suggestion.delta_seconds:
            label = (action_plan.get("recipient_turn") or {}).get("label", "主饱和转向")
            return f"为**{label}**增加有效绿灯约 **{suggestion.delta_seconds} 秒**"
        if plan_type == "upstream_coordination":
            up_name = action_plan.get("upstream_inter_name") or "上游来源路口"
            return (
                f"本路口已过饱和、单点加绿空间有限；"
                f"建议在上游**{up_name}**协同优化放行节奏，从源头削减进入车流"
            )
        if plan_type in ("spillback_control", "capacity_non_timing"):
            return str(action_plan.get("headline") or "优先非加绿手段")
        if primary_type == "capacity_bottleneck":
            return "优先从周期、协调、渠化或需求调控入手，单点加绿空间有限"
        if primary_type not in ("basically_matched",):
            return (
                f"主要方向绿灯时长**{sign}{suggestion.delta_seconds} 秒**"
                "（须结合绿信比与空放情况综合研判）"
            )
        return ""

    @staticmethod
    def format_diagnosis_message(
        suggestion: SuggestionResult,
        nlu_intersection: str,
        time_label: str,
        resolution_note: str = "",
        *,
        flow_timing_governance: dict[str, Any] | None = None,
    ) -> str:
        """Format user-facing diagnosis markdown."""
        note = f"\n{resolution_note}" if resolution_note else ""

        core_measure = SuggestionService.build_measure_line(
            suggestion, flow_timing_governance
        )
        measure_line = f"\n\n📋 参考措施：{core_measure}" if core_measure else ""

        supplement = str((flow_timing_governance or {}).get("flow_trace_supplement") or "").strip()
        supplement_line = f"\n\n🔗 {supplement}" if supplement else ""

        return f"""**诊断结果** · {nlu_intersection} · {time_label}{note}

{suggestion.narrative}{measure_line}{supplement_line}
📊 置信度：{suggestion.confidence:.0%}"""
