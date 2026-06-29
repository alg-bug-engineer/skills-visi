"""Generate governance suggestions."""

from __future__ import annotations

import logging
from typing import Any

from intersection_agent.llm.qwen_client import QwenClient
from intersection_agent.models.domain import SuggestionResult
from intersection_agent.services.governance_guidance import format_category_guidance_block
from intersection_agent.services.governance_action_plan_service import format_action_plan_for_prompt
from intersection_agent.services.rule_engine import evaluate_formula

logger = logging.getLogger(__name__)

NARRATIVE_PROMPT = """
你是交通信号优化专家。根据诊断结果与四维信控分析，生成一段简洁治理建议（不超过150字，中文）。

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

## 专业原则（必须遵守）
1. 若绿灯利用率已偏高或存在空放/失衡，禁止简单建议「一律加绿灯」；应优先绿信比再分配、压缩空放相位。
2. 若各转向普遍过饱和（能力瓶颈），应指出单点加绿空间有限，给出周期/协调/渠化/控流等出路。
3. 溢出风险时优先防锁死与上游控流，不单靠加绿。
4. 用户约束不为「无」时，正文必须优先回应；量化约束不为「无」时说明边界内方案。
5. 结构化动作方案中的秒数、供绿/受绿转向、动作类型为硬约束，只可润色表述，禁止另起炉灶。

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
        )

        try:
            narrative = await self._llm.chat(system="你是交通信号优化专家。", user=prompt)
        except RuntimeError:
            narrative = self._fallback_narrative(
                rule,
                data,
                direction_text=direction_text,
                delta=delta,
                user_suggestion=user_suggestion,
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
    def format_diagnosis_message(
        suggestion: SuggestionResult,
        nlu_intersection: str,
        time_label: str,
        resolution_note: str = "",
        *,
        flow_timing_governance: dict[str, Any] | None = None,
    ) -> str:
        """Format user-facing diagnosis markdown."""
        primary = (flow_timing_governance or {}).get("primary_diagnosis") or {}
        action_plan = (flow_timing_governance or {}).get("action_plan") or {}
        primary_type = str(primary.get("type") or "")
        sign = "+" if suggestion.direction == "increase" else "-"
        note = f"\n{resolution_note}" if resolution_note else ""

        measure_line = ""
        plan_type = str(action_plan.get("action_type") or "")
        if plan_type == "reallocate_green" and suggestion.delta_seconds:
            donor = (action_plan.get("donor_turn") or {}).get("label", "低利用转向")
            recipient = (action_plan.get("recipient_turn") or {}).get("label", "主饱和转向")
            measure_line = (
                f"\n\n📋 参考措施：从**{donor}**向**{recipient}**挪绿约 "
                f"**{suggestion.delta_seconds} 秒**（周期不变）"
            )
        elif plan_type == "increase_green" and suggestion.delta_seconds:
            label = (action_plan.get("recipient_turn") or {}).get("label", "主饱和转向")
            measure_line = (
                f"\n\n📋 参考措施：为**{label}**增加有效绿灯约 **{suggestion.delta_seconds} 秒**"
            )
        elif plan_type == "upstream_coordination":
            up_name = action_plan.get("upstream_inter_name") or "上游来源路口"
            measure_line = (
                f"\n\n📋 参考措施：本路口已过饱和、单点加绿空间有限；"
                f"建议在上游**{up_name}**协同优化放行节奏，从源头削减进入车流"
            )
        elif plan_type in ("spillback_control", "capacity_non_timing"):
            measure_line = f"\n\n📋 参考措施：{action_plan.get('headline') or '优先非加绿手段'}"
        elif primary_type not in ("capacity_bottleneck", "basically_matched"):
            measure_line = (
                f"\n\n📋 参考措施：主要方向绿灯时长**{sign}{suggestion.delta_seconds} 秒**"
                "（须结合绿信比与空放情况综合研判）"
            )
        elif primary_type == "capacity_bottleneck":
            measure_line = "\n\n📋 参考措施：优先从周期、协调、渠化或需求调控入手，单点加绿空间有限"

        supplement = str((flow_timing_governance or {}).get("flow_trace_supplement") or "").strip()
        supplement_line = f"\n\n🔗 {supplement}" if supplement else ""

        return f"""**诊断结果** · {nlu_intersection} · {time_label}{note}

{suggestion.narrative}{measure_line}{supplement_line}
📊 置信度：{suggestion.confidence:.0%}"""
