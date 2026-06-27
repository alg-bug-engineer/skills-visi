"""NLU for corridor-wide congestion scan (corridor + time_period)."""

from __future__ import annotations

import logging
import re
from typing import Any

from intersection_agent.llm.qwen_client import QwenClient
from intersection_agent.logging.helpers import log_event
from intersection_agent.models.domain import CorridorScanNlu, TimePeriod
from intersection_agent.services.follow_up_service import FollowUpService
from intersection_agent.services.nlu_service import TIME_LABEL_MAP

logger = logging.getLogger(__name__)

CORRIDOR_SCAN_SYSTEM_PROMPT = """
你是「交通智能体」，专门做干线拥堵扫描。从用户描述中提取结构化信息，只输出 JSON，不要解释。

必须严格使用以下字段名：
{
  "corridor": "干线/道路名称或 null，如奥体西路、经十路",
  "time_period": {"start":"HH:MM","end":"HH:MM","label":"早高峰|午高峰|晚高峰|平峰|夜间"} 或 null,
  "problem_type": "congestion"
}

说明：
- 用户问「哪些路口堵」「最拥堵的路口」「经常拥堵的路口有哪些」时，corridor 为道路名（口语「奥体西」规范为「奥体西路」）
- 用户在一句话里已给出道路名和时段（如「奥体西晚高峰」）时，两项都要提取，不要遗漏
- 不要提取具体路口名（含「X路与Y路」的是单点诊断，不属于本任务）
- problem_type 固定 congestion
- 时段归一化：早高峰 07:00-09:00，午高峰 11:30-13:30，晚高峰 16:00-18:00
""".strip()

FIELD_PRIORITY = ("time_period", "corridor")


class CorridorScanNluService:
    def __init__(
        self,
        llm: QwenClient | None = None,
        follow_ups: FollowUpService | None = None,
    ) -> None:
        self._llm = llm or QwenClient()
        self._follow_ups = follow_ups or FollowUpService(self._llm)

    async def extract(self, user_context: str) -> dict[str, Any]:
        try:
            raw = await self._llm.chat_json(system=CORRIDOR_SCAN_SYSTEM_PROMPT, user=user_context)
        except (ValueError, RuntimeError) as exc:
            logger.warning("Corridor scan NLU failed: %s", exc)
            return {
                "status": "error",
                "error": "无法理解您的描述，请说明干线名称和拥堵时段（如奥体西路、晚高峰）。",
            }

        scan_nlu = self._parse_raw(self._normalize_raw(raw))
        log_event(
            logger,
            logging.INFO,
            "corridor_scan_nlu.parsed",
            corridor=scan_nlu.corridor,
            time_label=scan_nlu.time_period.label if scan_nlu.time_period else None,
        )
        missing = self._missing_required(scan_nlu)
        if not missing:
            return {"status": "complete", "data": scan_nlu}

        field = self._pick_field(missing)
        follow_up = await self._follow_ups.for_corridor_scan(
            user_context,
            missing=missing,
            focus_field=field,
            partial=scan_nlu,
        )
        return {
            "status": "incomplete",
            "data": scan_nlu,
            "missing": missing,
            "follow_up_field": field,
            "follow_up": follow_up,
        }

    def _normalize_raw(self, raw: dict[str, Any]) -> dict[str, Any]:
        data = dict(raw)
        if not data.get("corridor"):
            for key in ("line", "road", "干线", "道路", "line_name"):
                if data.get(key):
                    data["corridor"] = data[key]
                    break
        corridor = str(data.get("corridor") or "").strip()
        if corridor:
            if re.search(r"奥体西(?!路)", corridor):
                data["corridor"] = "奥体西路"
            elif not corridor.endswith("路") and len(corridor) <= 8:
                data["corridor"] = f"{corridor}路"
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
        data.setdefault("problem_type", "congestion")
        return data

    def _parse_raw(self, raw: dict[str, Any]) -> CorridorScanNlu:
        tp_raw = raw.get("time_period")
        time_period = None
        if isinstance(tp_raw, dict) and tp_raw.get("start") and tp_raw.get("end"):
            time_period = TimePeriod(
                start=str(tp_raw["start"]),
                end=str(tp_raw["end"]),
                label=str(tp_raw.get("label") or "平峰"),
            )
        return CorridorScanNlu(
            corridor=raw.get("corridor"),
            time_period=time_period,
            problem_type=str(raw.get("problem_type") or "congestion"),
        )

    @staticmethod
    def _missing_required(scan_nlu: CorridorScanNlu) -> list[str]:
        missing: list[str] = []
        if not scan_nlu.corridor:
            missing.append("corridor")
        if not scan_nlu.time_period:
            missing.append("time_period")
        return missing

    @staticmethod
    def _pick_field(missing: list[str]) -> str:
        for field in FIELD_PRIORITY:
            if field in missing:
                return field
        return missing[0]
