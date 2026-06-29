"""NLU service with field completion."""

from __future__ import annotations

import logging
import re
from typing import Any

from intersection_agent.llm.qwen_client import QwenClient
from intersection_agent.logging.helpers import log_event
from intersection_agent.models.domain import NluResult, TimePeriod
from intersection_agent.models.skill import DEFAULT_PROBLEM_TYPE
from intersection_agent.services.follow_up_service import FollowUpService
from intersection_agent.utils.place_name_normalize import (
    extract_intersection_phrases,
    normalize_place_names,
)

logger = logging.getLogger(__name__)

NLU_SYSTEM_PROMPT = """
你是「交通智能体」，专门做路口问题诊断。从用户描述中提取结构化信息，只输出 JSON，不要解释。

必须严格使用以下字段名：
{
  "intersection": "路口全称或 null",
  "time_period": {"start":"HH:MM","end":"HH:MM","label":"早高峰|午高峰|晚高峰|平峰|夜间"} 或 null,
  "problem_types": [],
  "directions": [],
  "user_suggestion": "用户对治理的初步想法或 null"
}

说明：
- problem_types: 判定用户描述的问题类型，可多选，取值只能来自集合
  {congestion, spillback, empty_green, conflict}：
  congestion=拥堵(排队长、通行慢)，spillback=溢出(排队外溢到上游/下游路口)，
  empty_green=空放(绿灯放空、无车却放行)，conflict=相位/渠化冲突(相序、机非冲突、左转混行)。
  无法判断时输出 ["congestion"]。
- intersection: 标准化为"X路与Y路交叉口"或"X路与Y路路口"
- directions: 必填。用户须说明拥堵进口方向，如「东西向」「南北向」，
  或具体进口（东进口、西进口）；无法判断时输出 [] 由系统追问
- user_suggestion: 用户对治理的初步想法或 null

方向归一化：
- 「东西」「东西方向」-> ["东西向"]
- 「南北」「南北方向」-> ["南北向"]
- 具体进口如「东进口」「西进口」可保留原样或归入对应方向组

时段归一化：
- 早高峰 07:00-09:00，午高峰 11:30-13:30，晚高峰 16:00-18:00
- "下午四点" -> 16:00-18:00 晚高峰
""".strip()

TIME_LABEL_MAP = {
    "早高峰": ("07:00", "09:00", "早高峰"),
    "午高峰": ("11:30", "13:30", "午高峰"),
    "晚高峰": ("16:00", "18:00", "晚高峰"),
    "平峰": ("10:00", "11:00", "平峰"),
    "夜间": ("22:00", "06:00", "夜间"),
}

REQUIRED_FIELDS = ("intersection", "time_period", "directions")
FIELD_PRIORITY = ("intersection", "time_period", "directions")


class NluService:
    """Natural language understanding with multi-turn completion."""

    def __init__(
        self,
        llm: QwenClient | None = None,
        follow_ups: FollowUpService | None = None,
    ) -> None:
        self._llm = llm or QwenClient()
        self._follow_ups = follow_ups or FollowUpService(self._llm)

    async def extract(self, user_context: str) -> dict[str, Any]:
        """Extract NLU JSON from accumulated user context."""
        try:
            raw = await self._llm.chat_json(system=NLU_SYSTEM_PROMPT, user=user_context)
        except (ValueError, RuntimeError) as exc:
            logger.warning("NLU extraction failed: %s", exc)
            return {
                "status": "error",
                "error": (
                    "无法理解您的描述，请说明路口名称、拥堵时段和进口方向"
                    "（如东西向、南北向）。"
                ),
            }

        raw = self._normalize_raw(raw)
        nlu = self._parse_raw(raw)
        nlu = self._fill_directions_from_context(nlu, user_context)
        nlu = self._fill_user_suggestion_from_context(nlu, user_context)
        log_event(
            logger,
            logging.INFO,
            "nlu.parsed",
            intersection=nlu.intersection,
            problem_type=nlu.problem_type,
            time_label=nlu.time_period.label if nlu.time_period else None,
        )
        missing = self._missing_required(nlu)
        if not missing:
            return {"status": "complete", "data": nlu}

        field = self._pick_field(missing)
        follow_up = await self._follow_ups.for_nlu(
            user_context,
            missing=missing,
            focus_field=field,
            partial=nlu,
        )
        return {
            "status": "incomplete",
            "data": nlu,
            "missing": missing,
            "follow_up_field": field,
            "follow_up": follow_up,
        }

    def _normalize_raw(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Map common LLM field aliases to canonical schema."""
        data = dict(raw)

        if not data.get("intersection"):
            for key in ("location", "路口", "inter_name", "路口名称", "crossing"):
                if data.get(key):
                    data["intersection"] = data[key]
                    break

        tp = data.get("time_period")
        if isinstance(tp, str):
            for label, triple in TIME_LABEL_MAP.items():
                if label in tp:
                    data["time_period"] = {
                        "start": triple[0],
                        "end": triple[1],
                        "label": triple[2],
                    }
                    break

        return data

    def _parse_raw(self, raw: dict[str, Any]) -> NluResult:
        """Convert raw dict to NluResult."""
        tp_raw = raw.get("time_period")
        time_period = None
        if isinstance(tp_raw, dict) and tp_raw.get("start") and tp_raw.get("end"):
            time_period = TimePeriod(
                start=str(tp_raw["start"]),
                end=str(tp_raw["end"]),
                label=str(tp_raw.get("label") or "平峰"),
            )

        intersection = raw.get("intersection")
        if intersection is not None:
            intersection = normalize_place_names(str(intersection).strip()) or None

        directions = raw.get("directions") or []
        if not isinstance(directions, list):
            directions = []
        directions = [str(d).strip() for d in directions if str(d).strip()]

        suggestion = raw.get("user_suggestion")
        if suggestion is not None:
            suggestion = str(suggestion).strip() or None

        return NluResult(
            intersection=intersection,
            time_period=time_period,
            problem_type=DEFAULT_PROBLEM_TYPE,
            problem_types=self._parse_problem_types(raw.get("problem_types")),
            directions=[str(d) for d in directions],
            user_suggestion=suggestion,
        )

    @staticmethod
    def _parse_problem_types(raw: Any) -> list[str]:
        """Normalize problem_types to the allowed four-class set, default congestion."""
        allowed = {"congestion", "spillback", "empty_green", "conflict"}
        if not isinstance(raw, list):
            return ["congestion"]
        types: list[str] = []
        for item in raw:
            value = str(item).strip()
            if value in allowed and value not in types:
                types.append(value)
        return types or ["congestion"]

    @staticmethod
    def _fill_directions_from_context(nlu: NluResult, text: str) -> NluResult:
        """Infer directions from user text when LLM left the field empty."""
        if nlu.directions:
            return nlu
        inferred: list[str] = []
        if any(token in text for token in ("东西向", "东西方向")) or (
            "东西" in text and "东西路" not in text
        ):
            inferred.append("东西向")
        elif any(token in text for token in ("南北向", "南北方向")) or (
            "南北" in text and "南北路" not in text
        ):
            inferred.append("南北向")
        else:
            for label in ("东进口", "西进口"):
                if label in text:
                    inferred.append(label)
            for label in ("南进口", "北进口"):
                if label in text:
                    inferred.append(label)
        if not inferred:
            return nlu
        return NluResult(
            intersection=nlu.intersection,
            time_period=nlu.time_period,
            problem_type=nlu.problem_type,
            problem_types=nlu.problem_types,
            directions=inferred,
            user_suggestion=nlu.user_suggestion,
        )

    @staticmethod
    def _fill_user_suggestion_from_context(nlu: NluResult, text: str) -> NluResult:
        """Infer a governance constraint/suggestion when the model only returned a generic slot."""
        suggestion = extract_user_suggestion_text(text)
        if not suggestion:
            return nlu
        if nlu.user_suggestion and len(nlu.user_suggestion) >= len(suggestion):
            return nlu
        return NluResult(
            intersection=nlu.intersection,
            time_period=nlu.time_period,
            problem_type=nlu.problem_type,
            problem_types=nlu.problem_types,
            directions=nlu.directions,
            user_suggestion=suggestion,
        )

    @staticmethod
    def _missing_required(nlu: NluResult) -> list[str]:
        """Return list of missing required field names."""
        missing: list[str] = []
        if not nlu.intersection:
            missing.append("intersection")
        if not nlu.time_period:
            missing.append("time_period")
        if not nlu.directions:
            missing.append("directions")
        return missing

    @staticmethod
    def _pick_field(missing: list[str]) -> str:
        """Pick highest priority missing field."""
        for field in FIELD_PRIORITY:
            if field in missing:
                return field
        return missing[0]


def extract_user_suggestion_text(text: str) -> str | None:
    """Best-effort extraction for user-provided governance constraints."""
    cleaned = text.strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace("\n", " ")
    for prefix in ("是，", "是,", "确认，", "确认,", "可以，", "可以,", "好的，", "好的,"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break

    keywords = (
        "建议",
        "约束",
        "优先",
        "保障",
        "考虑",
        "不能",
        "不要",
        "避免",
        "溢出",
        "延长",
        "增加",
        "减少",
        "缩短",
        "协调",
        "放行",
        "渠化",
        "不影响",
        "尽量",
        "可以",
        "应",
    )
    if not any(keyword in cleaned for keyword in keywords):
        return None
    clauses = [part.strip() for part in re.split(r"[，,。；;]", cleaned) if part.strip()]
    suggestion_clauses = [
        part for part in clauses if any(keyword in part for keyword in keywords)
    ]
    if suggestion_clauses:
        return "，".join(suggestion_clauses)
    return cleaned or None
