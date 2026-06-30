"""LLM 经验抽取归一化：把定性反馈抽成结构化条目。"""

from __future__ import annotations

from typing import Any

from intersection_agent.llm.qwen_client import QwenClient

EXPERIENCE_EXTRACT_PROMPT = """
你是「交通经验抽取器」，把用户的定性治理反馈归一化为结构化 JSON，只输出 JSON。

字段：
{
  "dimension": "control|signal_timing|channelization|demand|event|coordination",
  "polarity": "increase_green|decrease_green|rebalance|none",
  "target_turn": "受影响的转向/进口或 null",
  "raw": "用户原话"
}

说明：
- dimension：判断反馈属于哪个治理维度，绿灯增减类归 signal_timing 或 control。
- polarity：绿灯多给/延长 -> increase_green；绿灯太长/缩短 -> decrease_green；
  调整分配/均衡 -> rebalance；无明确方向 -> none。
- raw 原样保留用户输入。
""".strip()


class ExperienceExtractor:
    """定性反馈 → 结构化经验条目（判定权威仍在规则脚本）。"""

    def __init__(self, llm: QwenClient | None = None) -> None:
        self._llm = llm or QwenClient()

    async def to_structured(self, text: str) -> dict[str, Any]:
        out = await self._llm.chat_json(system=EXPERIENCE_EXTRACT_PROMPT, user=text)
        out.setdefault("dimension", "control")
        out.setdefault("polarity", "none")
        out.setdefault("target_turn", None)
        out["raw"] = text
        return out
