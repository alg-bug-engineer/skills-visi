"""High-confidence diagnosis data prefetch that runs alongside LLM NLU."""

from __future__ import annotations

from copy import deepcopy
import logging
import re
from typing import Any

from app.data.pg_adapters import parse_time_step_range
from app.data.ticket_nlu_schema import resolve_period_label
from app.trace.topology import normalize_travel_direction

logger = logging.getLogger(__name__)

_ROAD = r"[\u4e00-\u9fff]{2,12}?(?:大道|大街|路|街|道)"
_INTERSECTION_RE = re.compile(
    rf"(?:^|[，,。；;：:\s])(?P<a>{_ROAD})[与和×xX/](?P<b>{_ROAD})(?:交叉口|路口)?"
)
_ENTRY_DIRECTIONS = {
    "北": "北向南",
    "东北": "东北向西南",
    "东": "东向西",
    "东南": "东南向西北",
    "南": "南向北",
    "西南": "西南向东北",
    "西": "西向东",
    "西北": "西北向东南",
}
_PERIOD_WINDOWS = {
    "早高峰": "07:00-09:00",
    "晚高峰": "17:00-19:00",
    "平峰": "10:00-16:00",
    "白平峰": "10:00-16:00",
}
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_number(text: str) -> int | None:
    if not text:
        return None
    if text == "十":
        return 10
    if "十" in text:
        left, right = text.split("十", 1)
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    if all(char in _CN_DIGITS for char in text):
        value = 0
        for char in text:
            value = value * 10 + _CN_DIGITS[char]
        return value
    return None


def _extract_time_range(text: str, period: str | None) -> str | None:
    clock_matches = re.findall(r"(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})(?!\d)", text)
    if len(clock_matches) >= 2:
        values = [f"{int(hour):02d}:{minute}" for hour, minute in clock_matches[:2]]
        return f"{values[0]}-{values[1]}"

    hour_matches = re.findall(r"([零一二三四五六七八九十两]{1,3})\s*[点时]", text)
    if len(hour_matches) >= 2:
        hours = [_cn_number(value) for value in hour_matches[:2]]
        if all(hour is not None and 0 <= hour <= 23 for hour in hours):
            return f"{hours[0]:02d}:00-{hours[1]:02d}:00"
    return _PERIOD_WINDOWS.get(str(period or ""))


def build_prefetch_ticket(user_input: str, task: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Build a provisional ticket only when every data-routing field is explicit."""
    base = dict((task or {}).get("diagnosis_ticket") or {})
    match = _INTERSECTION_RE.search(user_input or "")
    if not (base.get("inter_id") or base.get("intersection_name")):
        if not match:
            return None
        base["intersection_name"] = f"{match.group('a')}与{match.group('b')}路口"

    direction = base.get("direction")
    if not direction:
        entry = re.search(r"(东北|东南|西南|西北|北|东|南|西)进口", user_input or "")
        if not entry:
            return None
        direction = _ENTRY_DIRECTIONS[entry.group(1)]
    direction = normalize_travel_direction(str(direction))

    movement = base.get("movement")
    if not movement:
        movement_match = re.search(r"(左转|直行|右转|掉头)", user_input or "")
        if not movement_match:
            return None
        movement = movement_match.group(1)

    period = base.get("period") or resolve_period_label(user_input)
    time_range = base.get("time_range") or _extract_time_range(user_input or "", period)
    if not time_range:
        return None

    from app.data.intersection_registry import enrich_ticket

    ticket = enrich_ticket(
        {
            **base,
            "object_type": base.get("object_type") or "路口",
            "direction": direction,
            "movement": movement,
            "period": period,
            "time_range": time_range,
            "problem_type": base.get("problem_type") or "排队溢出",
        },
        user_input=user_input,
    )
    if not ticket.get("inter_id"):
        return None
    return ticket


def _ticket_signature(ticket: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(ticket.get("inter_id") or ""),
        normalize_travel_direction(str(ticket.get("direction") or "")),
        str(ticket.get("movement") or ""),
        parse_time_step_range(ticket.get("time_range")),
    )


def run_diagnosis_prefetch(
    *, user_input: str, task: dict[str, Any] | None, settings: Any
) -> dict[str, Any] | None:
    """Resolve PG diagnosis inputs in an isolated task while NLU is running."""
    ticket = build_prefetch_ticket(user_input, task)
    if ticket is None:
        return None
    from app.data.diagnosis_input import resolve_diagnosis_inputs

    local_task = deepcopy(task or {})
    local_task["diagnosis_ticket"] = ticket
    resolved = resolve_diagnosis_inputs(local_task, settings, ticket=ticket)
    return {"ticket": ticket, "task": local_task, "resolved": resolved}


def apply_diagnosis_prefetch(
    task: dict[str, Any], actual_ticket: dict[str, Any], prefetched: dict[str, Any] | None
) -> bool:
    """Merge a prefetch only after the authoritative LLM ticket matches exactly."""
    if not prefetched or not (prefetched.get("resolved") or {}).get("ok"):
        return False
    if _ticket_signature(actual_ticket) != _ticket_signature(prefetched.get("ticket") or {}):
        logger.info("诊断预取与 NLU 工单不一致，丢弃预取结果")
        return False
    prefetched_task = prefetched.get("task") or {}
    for key, value in prefetched_task.items():
        if key not in {"diagnosis_ticket", "artifacts"}:
            task[key] = value
    task["_diagnosis_prefetch_resolved"] = prefetched["resolved"]
    return True
