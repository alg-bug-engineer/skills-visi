"""LLM-first intent classification with regex fallback."""

from __future__ import annotations

import logging
from typing import Any, Literal

from intersection_agent.llm.qwen_client import QwenClient
from intersection_agent.logging.helpers import log_event
from intersection_agent.models.domain import Session
from intersection_agent.services.intent_router import (
    route_intent_by_rules,
    route_intent_by_state,
)

logger = logging.getLogger(__name__)

FirstTurnIntent = Literal["corridor_scan", "intersection_diagnosis"]

INTENT_CLASSIFIER_SYSTEM_PROMPT = """
你是交通意图二分类器。只输出 JSON，不要解释、不要推理过程：
{"intent":"corridor_scan"|"intersection_diagnosis","confidence":"high"|"medium"|"low","reason":"10字内"}

corridor_scan：问一条路上多个/哪个最堵/哪些堵/哪里堵，未锁定具体「X路与Y路路口」。
intersection_diagnosis：已指明具体路口（含X路与Y路），或问某路口某方向为何堵、如何治理。

示例：
- 「奥体西晚高峰哪些路口堵」→ corridor_scan
- 「奥体西与经十路」在干线选型后 → intersection_diagnosis
- 「奥体西路与经十路路口东进口堵」→ intersection_diagnosis
""".strip()

_VALID_INTENTS = frozenset({"corridor_scan", "intersection_diagnosis"})
_TRUSTED_CONFIDENCE = frozenset({"high", "medium"})


class IntentClassifierService:
    """Classify first-turn intent via LLM; fall back to regex rules."""

    def __init__(self, llm: QwenClient | None = None) -> None:
        self._llm = llm or QwenClient()

    async def route_intent(self, text: str, session: Session) -> FirstTurnIntent:
        state_intent = route_intent_by_state(session)
        if state_intent:
            return state_intent

        llm_intent = await self._classify_with_llm(text)
        if llm_intent:
            log_event(
                logger,
                logging.INFO,
                "intent_classifier.llm",
                intent=llm_intent,
                preview=text[:80],
            )
            return llm_intent

        fallback = route_intent_by_rules(text)
        log_event(
            logger,
            logging.INFO,
            "intent_classifier.fallback",
            intent=fallback,
            preview=text[:80],
        )
        return fallback

    async def _classify_with_llm(self, text: str) -> FirstTurnIntent | None:
        normalized = text.strip()
        if not normalized:
            return None
        try:
            raw = await self._llm.chat_json(
                system=INTENT_CLASSIFIER_SYSTEM_PROMPT,
                user=normalized,
                max_retries=0,
                temperature=0,
                enable_thinking=False,
                max_tokens=80,
            )
        except (ValueError, RuntimeError) as exc:
            logger.warning("Intent LLM classification failed: %s", exc)
            return None
        return self._parse_llm_intent(raw)

    @staticmethod
    def _parse_llm_intent(raw: dict[str, Any]) -> FirstTurnIntent | None:
        intent = str(raw.get("intent") or "").strip()
        confidence = str(raw.get("confidence") or "low").strip().lower()
        if intent not in _VALID_INTENTS:
            return None
        if confidence not in _TRUSTED_CONFIDENCE:
            return None
        return intent  # type: ignore[return-value]
