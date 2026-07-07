"""Normalize and tag user experiences from NLU output."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "data"
    / "intersection_config"
    / "experience_tag_schema.yaml"
)

EXPERIENCE_TYPES = ("cognitive", "diagnostic", "solution")

_STRATEGY_PATTERNS: list[tuple[str, str]] = [
    (r"加.{0,2}绿", "加绿"),
    (r"增.{0,2}绿", "加绿"),
    (r"减.{0,2}绿", "减绿"),
    (r"控流", "控流"),
    (r"协调|绿波|联控", "协调"),
    (r"相位", "相位调整"),
    (r"渠化|可变车道", "渠化"),
    (r"单口放行|单点放行", "单点放行"),
    (r"上游控流", "上游控流"),
]

_CAUSE_DIMENSION_HINTS: list[tuple[str, str]] = [
    (r"学校|接送|放学|医院|施工|事故", "event"),
    (r"下游|接不住|外溢|溢出", "event"),
    (r"上游|来车|冲击", "coordination"),
    (r"绿灯|相位|配时|信号", "control"),
    (r"车道|渠化|通行能力", "supply"),
    (r"流量|需求|饱和", "demand"),
]


def _load_schema() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _infer_time_period(text: str, schema: dict[str, Any]) -> str | None:
    synonyms = schema.get("time_period_synonyms") or {}
    for period, keys in synonyms.items():
        for key in keys:
            if key in text:
                return period
    hour_match = re.search(r"(\d{1,2})[点时]", text)
    if hour_match:
        hour = int(hour_match.group(1))
        if 7 <= hour <= 9:
            return "早高峰"
        if 17 <= hour <= 19:
            return "晚高峰"
        if 13 <= hour <= 16:
            return "下午时段"
    return None


def _infer_related_poi(text: str, schema: dict[str, Any]) -> list[str]:
    poi_map = schema.get("related_poi_keywords") or {}
    found: list[str] = []
    for poi, keys in poi_map.items():
        if any(key in text for key in keys):
            found.append(poi)
    return found


def _infer_strategy_action(text: str) -> str | None:
    for pattern, action in _STRATEGY_PATTERNS:
        if re.search(pattern, text):
            return action
    return None


def _infer_cause_dimension(text: str) -> str | None:
    for pattern, dimension in _CAUSE_DIMENSION_HINTS:
        if re.search(pattern, text):
            return dimension
    return None


def _infer_cause_keywords(text: str) -> list[str]:
    keywords: list[str] = []
    for token in ("接送", "放学", "学校", "下游", "上游", "加绿", "溢流", "拥堵"):
        if token in text and token not in keywords:
            keywords.append(token)
    return keywords


def _base_tags(ticket: dict[str, Any]) -> dict[str, Any]:
    return {
        "inter_id": ticket.get("inter_id"),
        "intersection_name": ticket.get("intersection_name"),
        "problem_type": ticket.get("problem_type"),
        "time_period": None,
        "direction": ticket.get("direction"),
        "movement": ticket.get("movement"),
        "spatial_structure": None,
        "severity": None,
        "cause_dimension": None,
        "cause_keywords": [],
        "strategy_action": None,
        "related_poi": [],
        "target_phase": None,
        "adjustment_direction": None,
        "constraints": ticket.get("constraints") or [],
        "confidence": None,
    }


def _enrich_tags(
    experience_type: str,
    content: str,
    tags: dict[str, Any],
    ticket: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    merged = _base_tags(ticket)
    merged.update({k: v for k, v in tags.items() if v is not None})

    time_period = _infer_time_period(content, schema) or _infer_time_period(
        ticket.get("time_range", "") or "", schema
    )
    if time_period:
        merged["time_period"] = time_period

    if experience_type == "cognitive":
        if not merged.get("problem_type"):
            if any(k in content for k in ("拥堵", "排队", "溢出", "溢流")):
                merged["problem_type"] = "拥堵" if "拥堵" in content else ticket.get("problem_type")
    elif experience_type == "diagnostic":
        if not merged.get("cause_dimension"):
            merged["cause_dimension"] = _infer_cause_dimension(content)
        if not merged.get("cause_keywords"):
            merged["cause_keywords"] = _infer_cause_keywords(content)
        if not merged.get("related_poi"):
            merged["related_poi"] = _infer_related_poi(content, schema)
    elif experience_type == "solution":
        if not merged.get("strategy_action"):
            merged["strategy_action"] = _infer_strategy_action(content)

    return merged


def _heuristic_split(user_input: str, ticket: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Fallback when LLM does not return user_experiences."""
    experiences: list[dict[str, Any]] = []
    text = user_input.strip()
    if not text:
        return experiences

    cognitive_parts: list[str] = []
    diagnostic_parts: list[str] = []
    solution_parts: list[str] = []

    if re.search(r"(经常|时常|下午|高峰).{0,20}(拥堵|排队|溢出)", text):
        cognitive_parts.append(text)
    elif ticket.get("problem_type"):
        cognitive_parts.append(
            f"{ticket.get('intersection_name', '该路口')} {ticket.get('time_range', '')} {ticket.get('problem_type', '')}".strip()
        )

    if re.search(r"(学校|接送|放学|导致|因为|由于)", text):
        diagnostic_parts.append(text)
    if re.search(r"(应该|建议|需要|可以).{0,10}(加绿|增绿|控流|协调|相位)", text):
        solution_parts.append(text)

    for content in cognitive_parts:
        experiences.append(
            {
                "experience_type": "cognitive",
                "content": content[:300],
                "source_span": content[:300],
                "tags": _enrich_tags("cognitive", content, {}, ticket, schema),
            }
        )
    for content in diagnostic_parts:
        experiences.append(
            {
                "experience_type": "diagnostic",
                "content": content[:300],
                "source_span": content[:300],
                "tags": _enrich_tags("diagnostic", content, {}, ticket, schema),
            }
        )
    for content in solution_parts:
        experiences.append(
            {
                "experience_type": "solution",
                "content": content[:300],
                "source_span": content[:300],
                "tags": _enrich_tags("solution", content, {}, ticket, schema),
            }
        )
    return experiences


def extract_user_experiences(
    *,
    parsed: dict[str, Any],
    user_input: str,
    diagnosis_ticket: dict[str, Any],
) -> list[dict[str, Any]]:
    schema = _load_schema()
    raw_items = parsed.pop("user_experiences", None)
    if not isinstance(raw_items, list) or not raw_items:
        return _heuristic_split(user_input, diagnosis_ticket, schema)

    normalized: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        exp_type = item.get("experience_type")
        content = (item.get("content") or "").strip()
        if exp_type not in EXPERIENCE_TYPES or not content:
            continue
        tags = item.get("tags") if isinstance(item.get("tags"), dict) else {}
        normalized.append(
            {
                "experience_type": exp_type,
                "content": content,
                "source_span": (item.get("source_span") or content)[:300],
                "tags": _enrich_tags(exp_type, content, tags, diagnosis_ticket, schema),
            }
        )
    return normalized
