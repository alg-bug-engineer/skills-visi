"""LLM-generated conversational follow-up messages."""

from __future__ import annotations

import json
import logging

from intersection_agent.llm.qwen_client import QwenClient
from intersection_agent.logging.helpers import log_event, safe_preview
from intersection_agent.models.domain import CorridorScanNlu, NluResult

logger = logging.getLogger(__name__)

FOLLOW_UP_SYSTEM = """
你是「交通智能体」，专门帮助用户做路口拥堵诊断。

要求：
- 一次只引导用户补充一个信息点
- 结合用户已说内容自然回应，避免机械套话
- 若用户只是寒暄，先简短问候，再说明你能做拥堵诊断，引导提供路口、时段和进口方向
- 当用户已描述路口或时段但未说明进口方向时，必须引导补充，
  如「东西向」「南北向」或具体进口（东进口、西进口）
- 不要展开渠化设计、信号配时方案细节
- 只输出 1～3 句中文，不要 JSON、不要 markdown
- 语气专业友好
""".strip()

FIELD_GUIDE = {
    "intersection": "发生拥堵的具体路口名称",
    "time_period": "拥堵明显的时段（如晚高峰、下午四点）",
    "directions": "拥堵明显的进口方向（如东西向、南北向，或东进口、西进口）",
}

FALLBACK_TEMPLATES = {
    "intersection": "请告诉我具体是哪个路口拥堵？",
    "time_period": "这个路口一般在什么时段拥堵比较明显？如方便也可说明方向（东西向、南北向）。",
    "directions": "拥堵主要集中在哪个方向？例如东西向或南北向，也可以说具体进口。",
    "corridor": "请告诉我您要扫描哪条干线？例如奥体西路、经十路。",
}

CORRIDOR_FIELD_GUIDE = {
    "corridor": "要扫描的干线/道路名称（如奥体西路）",
    "time_period": "关心的时段（早高峰、晚高峰、平峰等）",
}

CORRIDOR_FALLBACK = {
    "corridor": "请告诉我您要查看哪条干线？例如奥体西路、经十路。",
    "time_period": "请问您关心哪个时段？早高峰、晚高峰还是平峰？",
}

CORRIDOR_FOLLOW_UP_SYSTEM = """
你是「交通智能体」，专门帮助交警扫描一条干线/道路上各路口的拥堵情况。

要求：
- 用户已说明道路名时，不要追问具体路口名称，只追问缺失的时段
- 一次只引导补充一个信息点
- 只输出 1～2 句中文，不要 JSON
- 语气专业友好
""".strip()


class FollowUpService:
    """Generate context-aware follow-up prompts via LLM."""

    def __init__(self, llm: QwenClient | None = None) -> None:
        self._llm = llm or QwenClient()

    async def for_nlu(
        self,
        user_context: str,
        *,
        missing: list[str],
        focus_field: str,
        partial: NluResult | None = None,
        direction_hints: list[str] | None = None,
    ) -> str:
        """Generate NLU field completion prompt."""
        partial_dict = partial.model_dump() if partial else {}
        other = [f for f in missing if f != focus_field]
        user_prompt = (
            f"【对话历史】\n{user_context}\n\n"
            f"【已识别信息】\n{json.dumps(partial_dict, ensure_ascii=False)}\n\n"
            f"【本轮需引导补充】{focus_field}：{FIELD_GUIDE.get(focus_field, focus_field)}\n"
        )
        if direction_hints and focus_field == "directions":
            user_prompt += f"【可参考方向分组】{', '.join(direction_hints)}\n"
        if other:
            user_prompt += f"【稍后还需】{', '.join(other)}\n"
        user_prompt += "\n请生成下一句追问（仅围绕拥堵诊断）。"

        fallback = FALLBACK_TEMPLATES.get(focus_field, "请补充路口或时段信息。")
        return await self._generate("nlu", user_prompt, fallback=fallback)

    async def for_corridor_scan(
        self,
        user_context: str,
        *,
        missing: list[str],
        focus_field: str,
        partial: CorridorScanNlu | None = None,
    ) -> str:
        partial_dict = partial.model_dump() if partial else {}
        user_prompt = (
            f"【对话历史】\n{user_context}\n\n"
            f"【已识别】\n{json.dumps(partial_dict, ensure_ascii=False)}\n\n"
            f"【本轮需补充】{focus_field}：{CORRIDOR_FIELD_GUIDE.get(focus_field, focus_field)}\n"
            "请生成追问（干线扫描场景，不要问具体路口名）。"
        )
        fallback = CORRIDOR_FALLBACK.get(focus_field, "请补充干线名称或时段。")
        try:
            text = await self._llm.chat(
                system=CORRIDOR_FOLLOW_UP_SYSTEM,
                user=user_prompt,
                temperature=0.3,
            )
            text = text.strip()
            if text:
                return text
        except RuntimeError as exc:
            logger.warning("corridor follow_up failed: %s", exc)
        return fallback

    async def for_corridor_pick(self, user_context: str) -> str:
        return (
            "请告诉我您想深入分析哪个路口？可以说「最拥堵的」「第二个」，"
            "或直接说路口名称，也可以点击地图上的标注。"
        )

    async def for_intersection_candidates(
        self,
        user_context: str,
        *,
        input_name: str,
        candidates: list[str],
    ) -> str:
        """Ask user to pick from intersection candidates."""
        lines = "\n".join(f"- {c}" for c in candidates)
        user_prompt = (
            f"【对话历史】\n{user_context}\n\n"
            f"【用户提到的路口】{input_name}\n"
            f"【系统候选路口】\n{lines}\n\n"
            "未能精确匹配，请自然引导用户从候选中选择。"
        )
        fallback = (
            f"没能精确匹配「{input_name}」，您指的是下面哪个路口吗？\n"
            + "\n".join(f"· {c}" for c in candidates)
        )
        return await self._generate("intersection_candidates", user_prompt, fallback=fallback)

    async def for_intersection_not_found(
        self,
        user_context: str,
        *,
        input_name: str,
    ) -> str:
        """Inform user intersection data is unavailable."""
        user_prompt = (
            f"【对话历史】\n{user_context}\n\n"
            f"【用户提到的路口】{input_name}\n"
            "【情况】数据库中未找到该路口运行数据。\n"
            "请礼貌说明并引导用户核对路口名称。"
        )
        fallback = f"暂未找到「{input_name}」的运行数据，请核对路口名称。"
        return await self._generate("intersection_not_found", user_prompt, fallback=fallback)

    async def for_skill_confirm(
        self,
        user_context: str,
        *,
        action: str,
        intent_unclear: bool = True,
    ) -> str:
        """Clarify skill create/update confirmation."""
        if not intent_unclear:
            return ""
        verb = "更新已有诊断技能" if action == "update" else "固化本次拥堵诊断技能"
        user_prompt = (
            f"【对话历史】\n{user_context}\n\n"
            f"【情况】已给出拥堵诊断，等待确认是否{verb}。\n"
            "用户回复不明确，请引导其回复「是」或「否」。"
        )
        fallback = (
            "请回复「是」确认固化，或「否」结束。"
            if action != "update"
            else "请回复「是」更新技能，或「否」仅作参考。"
        )
        return await self._generate("skill_confirm", user_prompt, fallback=fallback)

    async def _generate(self, kind: str, user_prompt: str, *, fallback: str) -> str:
        """Call LLM with logging and fallback."""
        try:
            text = await self._llm.chat(
                system=FOLLOW_UP_SYSTEM,
                user=user_prompt,
                temperature=0.4,
            )
            text = text.strip()
            if text:
                log_event(
                    logger,
                    logging.INFO,
                    "follow_up.generated",
                    kind=kind,
                    preview=safe_preview(text),
                )
                return text
        except RuntimeError as exc:
            logger.warning("follow_up.llm_failed kind=%s: %s", kind, exc)
        return fallback
