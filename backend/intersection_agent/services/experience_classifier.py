"""LLM 经验归类：把用户原话拆成三类经验（认知画像 / 诊断经验 / 方案诊断经验）。

用户口径：
- 认知画像：问题记录（某路口某方向某时段拥堵）。有数据支撑→已验证，否则→待验证。
- 诊断经验：用户口述、库内通常无记录的原因（如"附近学校放学导致下午四点常堵"）。
- 方案诊断经验：用户给出的治理经验（对向不能溢出、绿灯加减 x 秒、增加左转车道等）。
"""

from __future__ import annotations

import logging
from typing import Any

from intersection_agent.llm.qwen_client import QwenClient

logger = logging.getLogger(__name__)

EXPERIENCE_CLASSIFY_PROMPT = """
你是「交通经验归类器」。把用户关于某路口的一段话拆解为三类经验，只输出 JSON：

{
  "problem": "问题记录：某方向/某时段的拥堵或排队现象，简短一句；没有则 null",
  "cognition_structured": {
    "time_period": "时段标签，如 晚高峰、17:00-19:00；没有则空字符串",
    "directions": ["进口方向，如 东、西进口；没有则空数组"],
    "movement": "转向类型：左转/直行/右转/掉头/混行；没有则空字符串",
    "phenomenon": "现象类型：排队/拥堵/空放/延误/溢出/机非冲突；没有则空字符串",
    "summary": "一句话概括问题记录，便于人读"
  },
  "tags": ["展示标签，如 晚高峰、东进口、左转、排队；2-5 个"],
  "causes": ["用户口述的原因，库内通常无记录，如'附近学校放学'；没有则空数组"],
  "measures": ["用户给出的治理措施，如'对向不能溢出'、'绿灯加30秒'、'增加左转车道'；没有则空数组"]
}

判别要点：
- problem 只描述「现象」（堵/排队/溢出发生在哪个方向、什么时段），不含原因与措施。
- cognition_structured 把 problem 拆成时段/方向/转向/现象，summary 是一句完整人话。
- tags 从 structured 字段提炼，便于列表展示。
- causes 是「为什么堵」的解释（学校放学、商圈、潮汐、施工、事故等用户观察）。
- measures 是「怎么治」的动作（增减绿灯、加车道、禁溢出、协调上游等）。
- 一句话可能同时包含三类，也可能只含其一；拿不准就留空，不要编造。
""".strip()


class ExperienceClassifier:
    """用户原话 → {problem, causes[], measures[]} 三类经验。"""

    def __init__(self, llm: QwenClient | None = None) -> None:
        self._llm = llm or QwenClient()

    async def classify(self, text: str) -> dict[str, Any]:
        empty_struct = {
            "time_period": "",
            "directions": [],
            "movement": "",
            "phenomenon": "",
            "summary": "",
        }
        empty = {
            "problem": None,
            "cognition_structured": empty_struct,
            "tags": [],
            "causes": [],
            "measures": [],
        }
        if not text or not text.strip():
            return empty
        try:
            out = await self._llm.chat_json(
                system=EXPERIENCE_CLASSIFY_PROMPT, user=text
            )
        except Exception as exc:  # noqa: BLE001 - 归类失败不应阻断主诊断
            logger.warning("experience classify failed: %s", exc)
            return empty
        if not isinstance(out, dict):
            return empty
        problem = out.get("problem")
        if not isinstance(problem, str) or not problem.strip():
            problem = None
        structured = out.get("cognition_structured")
        if not isinstance(structured, dict):
            structured = {}
        return {
            "problem": problem,
            "cognition_structured": {
                "time_period": _clean_str(structured.get("time_period")),
                "directions": _clean_list(structured.get("directions")),
                "movement": _clean_str(structured.get("movement")),
                "phenomenon": _clean_str(structured.get("phenomenon")),
                "summary": _clean_str(structured.get("summary")) or (problem or ""),
            },
            "tags": _clean_list(out.get("tags")),
            "causes": _clean_list(out.get("causes")),
            "measures": _clean_list(out.get("measures")),
        }


def _clean_str(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _clean_list(value: Any) -> list[str]:
    """保留非空字符串，去重保序。"""
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out
