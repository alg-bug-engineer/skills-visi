"""Generate governance suggestions."""

from __future__ import annotations

import logging
from typing import Any

from intersection_agent.llm.qwen_client import QwenClient
from intersection_agent.models.domain import SuggestionResult
from intersection_agent.services.rule_engine import evaluate_formula

logger = logging.getLogger(__name__)

NARRATIVE_PROMPT = """
根据以下诊断结果，生成一段简洁的治理建议（不超过120字，中文）：
- 路口：{intersection}
- 时段：{time_label}
- 问题：{conclusion}
- 建议：{direction_text}绿灯时长 {delta} 秒
- 数据支撑：饱和度 {saturation:.0%}，延迟指数 {delay_index}，当前绿灯占比 {green_ratio:.0%}
- 流量-配时匹配：{flow_timing_match}
- 四类问题摘要：{focus_problems}
- 用户约束或建议：{user_suggestion}
- 量化约束：{quantitative_constraints}
要求：优先从「流量与信号配时是否匹配」角度给出治理建议；如用户约束或建议不为“无”，治理建议正文必须优先体现并回应该约束。
如量化约束不为“无”，需说明在约束边界内给出的调整方案。
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
    ) -> SuggestionResult:
        """Build suggestion from matched rule."""
        action = rule["action"]
        formula = action["formula"]
        delta = evaluate_formula(formula, data)
        direction = action.get("direction", "increase")

        meta = data.get("meta", {})
        tf = data.get("traffic_flow", {})
        sp = data.get("signal_plan", {})
        ev = data.get("evaluation", {})

        direction_text = "增加" if direction == "increase" else "减少"
        tp = meta.get("time_period", {})
        delay_index = ev.get("delay_index") or data.get("congestion_index", {}).get(
            "delay_index", 0
        )
        governance = data.get("flow_timing_governance") or {}
        focus_problems = "、".join(
            p.get("label", "")
            for p in governance.get("problems", [])
            if p.get("detected")
        ) or "无显著异常"
        prompt = NARRATIVE_PROMPT.format(
            intersection=meta.get("intersection", ""),
            time_label=tp.get("label", ""),
            conclusion=rule.get("conclusion", ""),
            direction_text=direction_text,
            delta=delta,
            saturation=float(tf.get("saturation_rate") or 0),
            delay_index=delay_index,
            green_ratio=float(sp.get("green_ratio") or 0),
            flow_timing_match=governance.get("match_narrative") or "待评估",
            focus_problems=focus_problems,
            user_suggestion=user_suggestion or "无",
            quantitative_constraints=(
                quantitative_constraints.get("narrative")
                if quantitative_constraints
                else "无"
            ),
        )

        try:
            narrative = await self._llm.chat(system="你是交通信号优化专家。", user=prompt)
        except RuntimeError:
            suffix = f"同时结合用户约束：{user_suggestion}。" if user_suggestion else ""
            narrative = (
                f"{rule.get('conclusion', '')}，建议{direction_text}主要方向绿灯 "
                f"{delta} 秒。{suffix}"
            )

        return SuggestionResult(
            delta_seconds=delta,
            direction=direction,
            narrative=narrative.strip(),
            confidence=float(rule.get("confidence", 0.7)),
            rule_id=str(rule.get("id", "")),
            action_type=action.get("type", "green_light_adjustment"),
        )

    @staticmethod
    def format_diagnosis_message(
        suggestion: SuggestionResult,
        nlu_intersection: str,
        time_label: str,
        resolution_note: str = "",
    ) -> str:
        """Format user-facing diagnosis markdown."""
        sign = "+" if suggestion.direction == "increase" else "-"
        note = f"\n{resolution_note}" if resolution_note else ""
        return f"""**诊断结果** · {nlu_intersection} · {time_label}{note}

{suggestion.narrative}

📋 建议措施：将主要方向绿灯时长**{sign}{suggestion.delta_seconds} 秒**
📊 置信度：{suggestion.confidence:.0%}"""
