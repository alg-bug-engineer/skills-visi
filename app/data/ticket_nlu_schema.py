"""诊断工单 NLU 字段约束与 flow_correlate.period_type 映射（LLM + 护栏共用）。"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_SCHEMA_PATH = (
    Path(__file__).resolve().parent / "intersection_config" / "ticket_nlu_schema.yaml"
)

_PERIOD_DB_CODES = frozenset({"MORNING_PEAK", "EVENING_PEAK", "OFF_PEAK"})

# TODO(流量溯源): 当前 flow_correlate 仅覆盖单日样本，暂不卡 period_type 时间片；
# 多日复用后将 FLOW_TRACE_PERIOD_FILTER_ENABLED 置 True 恢复单时段过滤。
FLOW_TRACE_PERIOD_FILTER_ENABLED = False
FLOW_TRACE_PERIOD_FILTER_CAVEAT = (
    "流量溯源暂未按诊断时段过滤 flow_correlate（单日样本期）；"
    "待多日复用后恢复 period_type 时间片约束。"
)


@lru_cache(maxsize=1)
def load_ticket_nlu_schema() -> dict[str, Any]:
    if not _SCHEMA_PATH.exists():
        return {}
    return yaml.safe_load(_SCHEMA_PATH.read_text(encoding="utf-8")) or {}


def allowed_directions(*, include_diagonal: bool = False) -> list[str]:
    schema = load_ticket_nlu_schema()
    direction = schema.get("direction") or {}
    items = list(direction.get("allowed") or [])
    if include_diagonal:
        items.extend(direction.get("allowed_diagonal") or [])
    return items


def allowed_movements() -> list[str]:
    return list((load_ticket_nlu_schema().get("movement") or {}).get("allowed") or [])


def allowed_periods() -> list[str]:
    return list((load_ticket_nlu_schema().get("period") or {}).get("allowed") or [])


def period_db_codes() -> dict[str, str]:
    return dict((load_ticket_nlu_schema().get("period") or {}).get("db_code") or {})


def period_synonyms() -> dict[str, list[str]]:
    return dict((load_ticket_nlu_schema().get("period") or {}).get("synonyms") or {})


def normalize_travel_direction(direction: str) -> str:
    """口语方向 → 标准方向标签（LLM 输出护栏，不替代 NLU 语义理解）。"""
    raw = str(direction or "").strip()
    if not raw:
        return raw
    if raw.startswith("由") and "向" in raw:
        raw = raw[1:].strip()
    for suffix in allowed_movements():
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)].strip()
            break
    allowed = allowed_directions(include_diagonal=True)
    if raw in allowed:
        return raw
    for label in allowed:
        if label in raw or raw in label:
            return label
    return str(direction or "").strip()


def resolve_period_label(*candidates: Any) -> str | None:
    """从 LLM period / 口语片段推断标准中文时段（早高峰|晚高峰|平峰）。"""
    synonyms = period_synonyms()
    for candidate in candidates:
        if not candidate:
            continue
        text = str(candidate).strip()
        upper = text.upper()
        if upper in _PERIOD_DB_CODES:
            for cn, code in period_db_codes().items():
                if code == upper and cn in allowed_periods():
                    return cn
        for canonical, keys in synonyms.items():
            if canonical in text:
                return canonical
            for key in keys:
                if key in text:
                    return canonical
    return None


def resolve_correlate_period(*candidates: Any) -> str | None:
    """标准中文时段或 DB 代码 → flow_correlate.period_type。"""
    codes = period_db_codes()
    for candidate in candidates:
        if not candidate:
            continue
        text = str(candidate).strip()
        upper = text.upper()
        if upper in _PERIOD_DB_CODES:
            return upper
        for cn, code in codes.items():
            if cn in text:
                return code
    label = resolve_period_label(*candidates)
    if label:
        return codes.get(label)
    return None


def infer_diagnosis_period_type(ticket: dict[str, Any]) -> str | None:
    """从 ticket.period / time_range 推断 flow_correlate.period_type；无法推断返回 None。"""
    code = resolve_correlate_period(ticket.get("period"), ticket.get("time_range"))
    if code:
        return code
    time_range = str(ticket.get("time_range") or "")
    match = re.search(r"(\d{1,2})[:：](\d{2})", time_range)
    if not match:
        return None
    hour = int(match.group(1))
    hour_ranges = (load_ticket_nlu_schema().get("period") or {}).get("hour_ranges") or {}
    for label, bounds in hour_ranges.items():
        if not isinstance(bounds, list) or len(bounds) != 2:
            continue
        lo, hi = int(bounds[0]), int(bounds[1])
        if lo <= hour < hi:
            return period_db_codes().get(label)
    return period_db_codes().get("平峰")


def normalize_ticket_period(period: str | None) -> str | None:
    """LLM 输出的 period 归一化为三档标准中文。"""
    if not period:
        return None
    return resolve_period_label(period) or str(period).strip()
